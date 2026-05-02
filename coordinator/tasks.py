"""DAG-aware task queue — compatible with agent_channel.py interface."""

from __future__ import annotations

import uuid
import logging
from typing import Any, Dict, List, Optional

from coordinator.client import conn, tx

log = logging.getLogger(__name__)

_MAX_TEXT = 2000

VALID_STATUSES = frozenset(
    ("pending", "assigned", "running", "done", "failed", "cancelled")
)


def create_task(
    title: str,
    description: str = "",
    created_by: str = "",
    priority: int = 5,
    tags: Optional[list] = None,
    assigned_to: Optional[str] = None,
    depends_on: Optional[list] = None,
    required_role: Optional[str] = None,
    goal: Optional[str] = None,
    parent_task_id: Optional[str] = None,
    notify: bool = True,
) -> Optional[str]:
    """Create a task. Auto-propagates goal from parent if not provided."""
    task_id = str(uuid.uuid4())
    tags_arr = tags or []
    depends_arr = depends_on or []

    with tx() as c:
        if parent_task_id and not goal:
            row = c.execute(
                "SELECT goal, title FROM tasks WHERE id = %s",
                (parent_task_id,),
            ).fetchone()
            if row:
                parent_goal = row["goal"] or ""
                goal = (
                    f"{parent_goal} → {row['title']}" if parent_goal else row["title"]
                )

        c.execute(
            """INSERT INTO tasks
               (id, title, description, created_by, assigned_to, priority,
                tags, depends_on, required_role, goal, parent_task_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s::uuid[], %s, %s, %s)""",
            (
                task_id,
                title[:_MAX_TEXT],
                (description or "")[:_MAX_TEXT],
                created_by,
                assigned_to,
                priority,
                tags_arr,
                depends_arr or None,
                required_role,
                (goal or "")[:_MAX_TEXT],
                parent_task_id,
            ),
        )

    if notify and assigned_to:
        from coordinator.messages import post_message

        post_message("system", "task_assigned", title[:_MAX_TEXT], to_agent=assigned_to)

    return task_id


def claim_next_task(
    agent_id: str, role: Optional[str] = None, tag: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Atomically claim via SELECT FOR UPDATE SKIP LOCKED (server-side function)."""
    with tx() as c:
        row = c.execute(
            "SELECT * FROM claim_next_task(%s, %s, %s)",
            (agent_id, role, tag),
        ).fetchone()
        return dict(row) if row else None


def complete_task(task_id: str, result: str, broadcast: bool = True) -> bool:
    """Mark a task done and optionally broadcast completion."""
    ok = update_task(task_id, "done", result)
    if ok and broadcast:
        task = get_task(task_id)
        if task:
            from coordinator.messages import post_message

            from_agent = task.get("assigned_to") or "system"
            post_message(
                from_agent,
                "task_complete",
                f"{task['title']}: {result}"[:_MAX_TEXT],
            )
    return ok


def update_task(task_id: str, status: str, result: str = "") -> bool:
    """Update a task's status and optional result."""
    if status not in VALID_STATUSES:
        return False
    with conn() as c:
        cur = c.execute(
            "UPDATE tasks SET status = %s, result = %s, updated_at = now() WHERE id = %s",
            (status, (result or "")[:_MAX_TEXT], task_id),
        )
        return cur.rowcount > 0


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """Get a single task by ID."""
    with conn() as c:
        row = c.execute("SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone()
        return dict(row) if row else None


def list_tasks(
    status: Optional[str] = None,
    agent_id: Optional[str] = None,
    tag: Optional[str] = None,
    parent_task_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List tasks with optional filters."""
    conditions: list[str] = []
    params: list = []

    if status:
        conditions.append("status = %s")
        params.append(status)
    if agent_id:
        conditions.append("(assigned_to = %s OR created_by = %s)")
        params.extend([agent_id, agent_id])
    if tag:
        conditions.append("%s = ANY(tags)")
        params.append(tag)
    if parent_task_id:
        conditions.append("parent_task_id = %s")
        params.append(parent_task_id)

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    with conn() as c:
        rows = c.execute(
            f"SELECT * FROM tasks{where} ORDER BY priority ASC, created_at ASC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def cancel_stale(timeout_s: int = 300) -> int:
    """Cancel assigned/running tasks not updated within timeout_s."""
    with conn() as c:
        cur = c.execute(
            "UPDATE tasks SET status = 'cancelled', updated_at = now() "
            "WHERE status IN ('assigned', 'running') "
            "AND updated_at < now() - make_interval(secs => %s)",
            (timeout_s,),
        )
        return cur.rowcount
