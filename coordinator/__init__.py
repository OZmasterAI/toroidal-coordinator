"""toroidal-coordinator: Distributed agent coordination via Neon Postgres.

Drop-in replacement for shared/agent_channel.py with:
  - DAG-aware task scheduling (SELECT FOR UPDATE SKIP LOCKED)
  - LISTEN/NOTIFY real-time pub/sub
  - Agent heartbeats + dead agent recovery
  - Distributed advisory locks
  - Structured audit logging (replaces .audit_trail.jsonl)
  - Automatic SQLite fallback when Neon is unreachable
"""

from coordinator.client import get_pool, close_pool, is_connected
from coordinator.tasks import (
    create_task,
    claim_next_task,
    complete_task,
    update_task,
    get_task,
    list_tasks,
    cancel_stale,
)
from coordinator.messages import (
    post_message,
    read_messages,
    ack_message,
    reply,
    listen,
)
from coordinator.heartbeat import (
    register_agent,
    heartbeat,
    reap_stale,
    agent_status,
)
from coordinator.locks import acquire_lock, release_lock, check_lock
from coordinator.audit import log_event, query_events

__version__ = "0.1.0"

__all__ = [
    # Connection
    "get_pool",
    "close_pool",
    "is_connected",
    # Tasks (agent_channel.py compatible)
    "create_task",
    "claim_next_task",
    "complete_task",
    "update_task",
    "get_task",
    "list_tasks",
    "cancel_stale",
    # Messages (agent_channel.py compatible)
    "post_message",
    "read_messages",
    "ack_message",
    "reply",
    "listen",
    # Heartbeat (new)
    "register_agent",
    "heartbeat",
    "reap_stale",
    "agent_status",
    # Locks (new)
    "acquire_lock",
    "release_lock",
    "check_lock",
    # Audit (new)
    "log_event",
    "query_events",
]
