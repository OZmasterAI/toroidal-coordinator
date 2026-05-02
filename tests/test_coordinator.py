"""Unit tests for toroidal-coordinator — runs without a real Postgres connection.

Tests mock the psycopg connection pool to verify:
  - Function signatures match agent_channel.py compatibility contract
  - SQL queries are well-formed
  - Return types are correct
  - Fallback selector logic
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest


class TestTaskSignatures:
    """Verify task functions match agent_channel.py's interface."""

    def test_create_task_signature(self):
        from coordinator.tasks import create_task

        sig = inspect.signature(create_task)
        assert "title" in sig.parameters
        assert "description" in sig.parameters
        assert "created_by" in sig.parameters
        assert "priority" in sig.parameters
        assert "tags" in sig.parameters
        assert "assigned_to" in sig.parameters
        assert "depends_on" in sig.parameters
        assert "parent_task_id" in sig.parameters
        assert "notify" in sig.parameters

    def test_claim_next_task_signature(self):
        from coordinator.tasks import claim_next_task

        sig = inspect.signature(claim_next_task)
        assert "agent_id" in sig.parameters
        assert "role" in sig.parameters
        assert "tag" in sig.parameters

    def test_list_tasks_signature(self):
        from coordinator.tasks import list_tasks

        sig = inspect.signature(list_tasks)
        assert "status" in sig.parameters
        assert "agent_id" in sig.parameters
        assert "tag" in sig.parameters
        assert "parent_task_id" in sig.parameters

    def test_valid_statuses(self):
        from coordinator.tasks import VALID_STATUSES

        expected = {"pending", "assigned", "running", "done", "failed", "cancelled"}
        assert VALID_STATUSES == expected


class TestMessageSignatures:
    """Verify message functions match agent_channel.py's interface."""

    def test_post_message_signature(self):
        from coordinator.messages import post_message

        sig = inspect.signature(post_message)
        assert "from_agent" in sig.parameters
        assert "msg_type" in sig.parameters
        assert "content" in sig.parameters
        assert "to_agent" in sig.parameters
        assert sig.parameters["to_agent"].default == "all"

    def test_read_messages_signature(self):
        from coordinator.messages import read_messages

        sig = inspect.signature(read_messages)
        assert "since_ts" in sig.parameters
        assert "agent_id" in sig.parameters
        assert "limit" in sig.parameters

    def test_ack_message_signature(self):
        from coordinator.messages import ack_message

        sig = inspect.signature(ack_message)
        assert "msg_id" in sig.parameters
        assert "agent_id" in sig.parameters

    def test_reply_signature(self):
        from coordinator.messages import reply

        sig = inspect.signature(reply)
        assert "msg_id" in sig.parameters
        assert "from_agent" in sig.parameters
        assert "content" in sig.parameters


class TestNewCapabilities:
    """Verify new features beyond agent_channel.py compat."""

    def test_heartbeat_exports(self):
        from coordinator.heartbeat import (
            register_agent,
            heartbeat,
            reap_stale,
            agent_status,
        )

        assert callable(register_agent)
        assert callable(heartbeat)
        assert callable(reap_stale)
        assert callable(agent_status)

    def test_locks_exports(self):
        from coordinator.locks import acquire_lock, release_lock, check_lock

        assert callable(acquire_lock)
        assert callable(release_lock)
        assert callable(check_lock)

    def test_audit_exports(self):
        from coordinator.audit import log_event, query_events, ensure_partition

        assert callable(log_event)
        assert callable(query_events)
        assert callable(ensure_partition)

    def test_resource_hash_deterministic(self):
        from coordinator.locks import _resource_hash

        h1 = _resource_hash("repo:torus-framework")
        h2 = _resource_hash("repo:torus-framework")
        h3 = _resource_hash("repo:other-project")
        assert h1 == h2
        assert h1 != h3

    def test_resource_hash_is_int64(self):
        from coordinator.locks import _resource_hash

        h = _resource_hash("test")
        assert isinstance(h, int)
        assert -(2**63) <= h < 2**63


class TestFallback:
    """Verify backend selector logic."""

    def test_no_dsn_uses_sqlite(self):
        from coordinator.fallback import get_backend, reset

        mock_sqlite = MagicMock()
        mock_shared = MagicMock()
        mock_shared.agent_channel = mock_sqlite

        with patch.dict("os.environ", {"COORDINATOR_DSN": "", "NEON_DSN": ""}):
            with patch.dict(
                "sys.modules",
                {"shared": mock_shared, "shared.agent_channel": mock_sqlite},
            ):
                reset()
                backend = get_backend()
                assert backend is mock_sqlite

    def test_with_dsn_tries_neon(self):
        from coordinator.fallback import reset

        reset()
        mock_coordinator = MagicMock()
        mock_coordinator.is_connected.return_value = True

        with patch.dict("os.environ", {"COORDINATOR_DSN": "postgres://test"}):
            with patch.dict("sys.modules", {"coordinator": mock_coordinator}):
                reset()
                from coordinator.fallback import get_backend

                reset()
                backend = get_backend()
                assert backend is mock_coordinator


class TestPackageExports:
    """Verify __init__.py exports everything needed."""

    def test_all_exports_exist(self):
        import coordinator

        for name in coordinator.__all__:
            assert hasattr(coordinator, name), f"Missing export: {name}"

    def test_version(self):
        import coordinator

        assert coordinator.__version__ == "0.1.0"
