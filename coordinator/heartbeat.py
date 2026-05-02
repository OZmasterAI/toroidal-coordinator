"""Agent registration, heartbeat, and dead-agent recovery."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from coordinator.client import conn

log = logging.getLogger(__name__)


def register_agent(
    agent_id: str,
    name: str = "",
    role: str = "",
    project: str = "",
    metadata: Optional[dict] = None,
) -> bool:
    """Register an agent (upsert). Reactivates dead agents on re-register."""
    with conn() as c:
        c.execute(
            """INSERT INTO agents (id, name, role, project, metadata)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET
                   last_heartbeat = now(),
                   status = 'active',
                   name = EXCLUDED.name,
                   role = EXCLUDED.role,
                   metadata = EXCLUDED.metadata""",
            (agent_id, name, role, project, json.dumps(metadata or {})),
        )
    return True


def heartbeat(agent_id: str) -> bool:
    """Update an agent's heartbeat timestamp."""
    with conn() as c:
        cur = c.execute(
            "UPDATE agents SET last_heartbeat = now() WHERE id = %s AND status = 'active'",
            (agent_id,),
        )
        return cur.rowcount > 0


def reap_stale(timeout_s: int = 60) -> List[Dict[str, Any]]:
    """Mark stale agents dead and reclaim their tasks."""
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM reap_stale_agents(make_interval(secs => %s))",
            (timeout_s,),
        ).fetchall()
        return [dict(r) for r in rows]


def agent_status(agent_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get status of one or all agents."""
    with conn() as c:
        if agent_id:
            rows = c.execute(
                "SELECT * FROM agents WHERE id = %s", (agent_id,)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM agents ORDER BY last_heartbeat DESC"
            ).fetchall()
        return [dict(r) for r in rows]
