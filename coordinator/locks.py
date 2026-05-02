"""Distributed locking via Postgres advisory locks + metadata table."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, Optional

from coordinator.client import conn

log = logging.getLogger(__name__)


def _resource_hash(resource: str) -> int:
    """Stable int64 hash of a resource name for pg_advisory_lock."""
    h = hashlib.sha256(resource.encode()).digest()
    return int.from_bytes(h[:8], "big", signed=True)


def acquire_lock(
    resource: str,
    holder: str,
    ttl_s: int = 300,
    metadata: Optional[dict] = None,
) -> bool:
    """Acquire a distributed lock on a resource. Non-blocking (try-lock)."""
    with conn() as c:
        locked = c.execute(
            "SELECT pg_try_advisory_lock(%s)", (_resource_hash(resource),)
        ).fetchone()[0]
        if not locked:
            return False

        c.execute(
            """INSERT INTO distributed_locks (resource, holder, expires_at, metadata)
               VALUES (%s, %s, now() + make_interval(secs => %s), %s)
               ON CONFLICT (resource) DO UPDATE SET
                   holder = EXCLUDED.holder,
                   acquired_at = now(),
                   expires_at = EXCLUDED.expires_at,
                   metadata = EXCLUDED.metadata""",
            (resource, holder, ttl_s, json.dumps(metadata or {})),
        )
    return True


def release_lock(resource: str) -> bool:
    """Release a distributed lock."""
    with conn() as c:
        c.execute("SELECT pg_advisory_unlock(%s)", (_resource_hash(resource),))
        c.execute("DELETE FROM distributed_locks WHERE resource = %s", (resource,))
    return True


def check_lock(resource: str) -> Optional[Dict[str, Any]]:
    """Check who holds a lock. Returns None if unlocked or expired."""
    with conn() as c:
        row = c.execute(
            "SELECT * FROM distributed_locks WHERE resource = %s AND expires_at > now()",
            (resource,),
        ).fetchone()
        return dict(row) if row else None
