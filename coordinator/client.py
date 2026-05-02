"""Neon Postgres connection pool with automatic fallback detection."""

from __future__ import annotations

import os
import logging
from contextlib import contextmanager
from typing import Optional, Generator

import psycopg
from psycopg_pool import ConnectionPool

log = logging.getLogger(__name__)

_pool: Optional[ConnectionPool] = None
_dsn: Optional[str] = None


def _get_dsn() -> str:
    dsn = os.environ.get("COORDINATOR_DSN") or os.environ.get("NEON_DSN")
    if not dsn:
        raise RuntimeError(
            "Set COORDINATOR_DSN or NEON_DSN env var "
            "(e.g. postgres://user:pass@ep-xyz.us-east-2.aws.neon.tech/coordinator)"
        )
    return dsn


def get_pool() -> ConnectionPool:
    global _pool, _dsn
    if _pool is None:
        _dsn = _get_dsn()
        _pool = ConnectionPool(
            _dsn,
            min_size=1,
            max_size=5,
            open=True,
            kwargs={"autocommit": True},
        )
        log.info("coordinator pool opened: %s", _dsn.split("@")[-1])
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
        log.info("coordinator pool closed")


def is_connected() -> bool:
    try:
        with conn() as c:
            c.execute("SELECT 1")
        return True
    except Exception:
        return False


@contextmanager
def conn() -> Generator[psycopg.Connection, None, None]:
    """Yield a connection from the pool."""
    pool = get_pool()
    with pool.connection() as c:
        yield c


@contextmanager
def tx() -> Generator[psycopg.Connection, None, None]:
    """Yield a connection inside a transaction (auto-commit on exit, rollback on error)."""
    pool = get_pool()
    with pool.connection() as c:
        with c.transaction():
            yield c
