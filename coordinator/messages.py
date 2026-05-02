"""Inter-agent messaging with LISTEN/NOTIFY push."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from coordinator.client import conn, get_pool

log = logging.getLogger(__name__)

_MAX_TEXT = 2000


def post_message(
    from_agent: str, msg_type: str, content: str, to_agent: str = "all"
) -> bool:
    """Post a message. Triggers pg_notify('agent_messages', ...) via DB trigger."""
    with conn() as c:
        c.execute(
            "INSERT INTO messages (from_agent, to_agent, msg_type, content) "
            "VALUES (%s, %s, %s, %s)",
            (from_agent, to_agent, msg_type, content[:_MAX_TEXT]),
        )
    return True


def read_messages(
    since_ts: float, agent_id: Optional[str] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    """Read messages since a timestamp. Optionally filter by recipient."""
    with conn() as c:
        if agent_id:
            rows = c.execute(
                "SELECT id, ts, from_agent, to_agent, msg_type, content, consumed, reply_to "
                "FROM messages "
                "WHERE ts > to_timestamp(%s) AND (to_agent = 'all' OR to_agent = %s) "
                "ORDER BY ts DESC LIMIT %s",
                (since_ts, agent_id, limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT id, ts, from_agent, to_agent, msg_type, content, consumed, reply_to "
                "FROM messages WHERE ts > to_timestamp(%s) ORDER BY ts DESC LIMIT %s",
                (since_ts, limit),
            ).fetchall()
        return [dict(r) for r in rows]


def ack_message(msg_id: int, agent_id: str) -> bool:
    """Mark a message as consumed."""
    with conn() as c:
        cur = c.execute(
            "UPDATE messages SET consumed = true "
            "WHERE id = %s AND (to_agent = %s OR to_agent = 'all')",
            (msg_id, agent_id),
        )
        return cur.rowcount > 0


def reply(msg_id: int, from_agent: str, content: str) -> bool:
    """Reply to a message. Inherits to_agent from the original sender."""
    with conn() as c:
        original = c.execute(
            "SELECT from_agent FROM messages WHERE id = %s", (msg_id,)
        ).fetchone()
        if not original:
            return False
        c.execute(
            "INSERT INTO messages (from_agent, to_agent, msg_type, content, reply_to) "
            "VALUES (%s, %s, 'reply', %s, %s)",
            (from_agent, original["from_agent"], content[:_MAX_TEXT], msg_id),
        )
    return True


def listen(
    channel: str = "agent_messages",
    callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    timeout: float = 30.0,
) -> Optional[Dict[str, Any]]:
    """Listen for a NOTIFY event. With callback loops; without returns first event."""
    pool = get_pool()
    with pool.connection() as c:
        c.autocommit = True
        c.execute(f"LISTEN {channel}")
        for notify in c.notifies(timeout=timeout):
            payload = _parse_payload(notify.payload)
            if callback:
                callback(payload)
            else:
                return payload
    return None


def _parse_payload(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"raw": raw}


def cleanup(max_age_hours: int = 2) -> int:
    """Delete messages older than max_age_hours."""
    with conn() as c:
        cur = c.execute(
            "DELETE FROM messages WHERE ts < now() - make_interval(hours => %s)",
            (max_age_hours,),
        )
        return cur.rowcount
