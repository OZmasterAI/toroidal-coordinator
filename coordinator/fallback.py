"""Backend selector: Neon coordinator or SQLite agent_channel fallback.

Usage in memory_server.py:
    from coordinator.fallback import get_backend
    backend = get_backend()
    backend.create_task(...)
    backend.post_message(...)
"""

from __future__ import annotations

import logging
import os
from types import ModuleType

log = logging.getLogger(__name__)

_backend: ModuleType | None = None


def get_backend() -> ModuleType:
    """Return the active backend module (coordinator or agent_channel)."""
    global _backend
    if _backend is not None:
        return _backend

    if os.environ.get("COORDINATOR_DSN") or os.environ.get("NEON_DSN"):
        try:
            import coordinator as neon_backend

            if neon_backend.is_connected():
                _backend = neon_backend
                log.info("coordinator backend: neon")
                return _backend
            log.warning("Neon DSN set but connection failed, falling back to SQLite")
        except ImportError:
            log.warning("coordinator package not installed, falling back to SQLite")

    from shared import agent_channel as sqlite_backend

    _backend = sqlite_backend
    log.info("coordinator backend: sqlite (local)")
    return _backend


def reset() -> None:
    """Force re-detection on next get_backend() call."""
    global _backend
    _backend = None
