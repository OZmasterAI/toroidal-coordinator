"""Structured audit logging — replaces .audit_trail.jsonl."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from coordinator.client import conn

log = logging.getLogger(__name__)


def log_event(
    event_type: str,
    session_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    gate_name: Optional[str] = None,
    tool_name: Optional[str] = None,
    duration_ms: Optional[int] = None,
    severity: str = "info",
    details: Optional[dict] = None,
) -> bool:
    """Insert a structured audit event."""
    with conn() as c:
        c.execute(
            """INSERT INTO audit
               (event_type, session_id, agent_id, gate_name, tool_name,
                duration_ms, severity, details)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                event_type,
                session_id,
                agent_id,
                gate_name,
                tool_name,
                duration_ms,
                severity,
                json.dumps(details or {}),
            ),
        )
    return True


def query_events(
    event_type: Optional[str] = None,
    session_id: Optional[str] = None,
    gate_name: Optional[str] = None,
    severity: Optional[str] = None,
    since_hours: int = 24,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Query audit events with filters."""
    conditions = ["ts > now() - make_interval(hours => %s)"]
    params: list = [since_hours]

    if event_type:
        conditions.append("event_type = %s")
        params.append(event_type)
    if session_id:
        conditions.append("session_id = %s")
        params.append(session_id)
    if gate_name:
        conditions.append("gate_name = %s")
        params.append(gate_name)
    if severity:
        conditions.append("severity = %s")
        params.append(severity)

    where = " AND ".join(conditions)
    params.append(limit)

    with conn() as c:
        rows = c.execute(
            f"SELECT * FROM audit WHERE {where} ORDER BY ts DESC LIMIT %s",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def ensure_partition(months_ahead: int = 2) -> List[str]:
    """Create audit partitions for current + future months."""
    created = []
    with conn() as c:
        for i in range(months_ahead + 1):
            row = c.execute(
                "SELECT create_audit_partition(CURRENT_DATE + make_interval(months => %s))",
                (i,),
            ).fetchone()
            if row:
                created.append(row[0])
    return created
