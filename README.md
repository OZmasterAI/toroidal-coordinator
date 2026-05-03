# Toroidal Coordinator

Distributed agent coordination via Neon Postgres. Drop-in replacement for SQLite-based `agent_channel.py` with DAG task scheduling, real-time pub/sub, heartbeats, distributed locking, and structured audit logging.

Works standalone or as part of the [Torus Framework](https://github.com/OZmasterAI/Torus-Framework).

## The Problem

Local SQLite coordination works fine for a single machine — one Claude Code session with sub-agents sharing a file. But the moment you have multiple independent sessions, scheduled routines, CI agents, or agents across machines, SQLite can't coordinate them. Tasks get double-claimed, dead agents leave zombie tasks, and there's no way to know what's alive.

## The Solution

Toroidal Coordinator replaces the SQLite backend with Neon Postgres while keeping the same API. Agents that worked with `agent_channel.py` work with this — no code changes. New capabilities unlock automatically:

| Capability | SQLite (before) | Coordinator (after) |
|---|---|---|
| Task claiming | `BEGIN EXCLUSIVE` (blocks all writers) | `SELECT FOR UPDATE SKIP LOCKED` (concurrent) |
| Messaging | Poll with `since_ts` | `LISTEN/NOTIFY` push |
| Dead agent recovery | Manual `cancel_stale()` | Heartbeat + automatic `reap_stale_agents()` |
| Distributed locking | Not possible | `pg_advisory_lock` per resource |
| Audit trail | 326MB append-only JSONL | Partitioned Postgres table, queryable |
| Multi-machine | No | Yes |

## Quick Start

```bash
pip install -e .
```

Set the connection string:
```bash
export COORDINATOR_DSN="postgres://user:pass@ep-xyz.us-east-2.aws.neon.tech/coordinator?sslmode=require"
```

Run the schema:
```bash
psql "$COORDINATOR_DSN" -f schema/001_init.sql
psql "$COORDINATOR_DSN" -f schema/002_indexes.sql
psql "$COORDINATOR_DSN" -f schema/003_functions.sql
```

Use it:
```python
from coordinator import create_task, claim_next_task, post_message, register_agent, heartbeat

# Register this agent
register_agent("agent-1", name="builder", role="code", project="my-project")

# Create a task
task_id = create_task("Fix auth bug", created_by="lead", priority=3, tags=["backend"])

# Another agent claims it atomically
task = claim_next_task("agent-2", role="code", tag="backend")

# Send a message (triggers LISTEN/NOTIFY)
post_message("agent-2", "status", "Starting work on auth fix")

# Keep alive
heartbeat("agent-2")
```

## Automatic Fallback

No `COORDINATOR_DSN` set? Everything falls back to local SQLite automatically:

```python
from coordinator.fallback import get_backend

backend = get_backend()
# Returns coordinator module if Neon is reachable, otherwise shared.agent_channel
backend.create_task(...)
```

## Architecture

```
coordinator/
├── client.py        # psycopg connection pool (1-5 conns), conn()/tx() context managers
├── tasks.py         # DAG-aware task queue — same API as agent_channel.py
├── messages.py      # LISTEN/NOTIFY pub/sub — same API + listen() for push
├── heartbeat.py     # Agent registration, liveness detection, dead recovery
├── locks.py         # pg_advisory_lock distributed locking
├── audit.py         # Structured audit events with monthly partitions
└── fallback.py      # Auto-selects Neon or SQLite based on env
schema/
├── 001_init.sql     # 5 tables: agents, tasks, messages, distributed_locks, audit
├── 002_indexes.sql  # GIN index for DAG deps, partial indexes for perf
└── 003_functions.sql # claim_next_task, reap_stale_agents, triggers, partitions
```

## Key Features

### DAG Task Scheduling

Tasks can declare dependencies. `claim_next_task()` won't hand out a task until all its upstream dependencies are done:

```python
task_a = create_task("Build binary", created_by="lead")
task_b = create_task("Run tests", created_by="lead", depends_on=[task_a])
task_c = create_task("Deploy", created_by="lead", depends_on=[task_b])

# An agent trying to claim will only get task_a — B and C are blocked
claim_next_task("agent-1")  # returns task_a
```

### Heartbeat + Dead Agent Recovery

Agents register and send periodic heartbeats. If an agent dies, `reap_stale_agents()` marks it dead and returns its tasks to the pending queue:

```python
register_agent("agent-1", role="code")
heartbeat("agent-1")  # call periodically

# If agent-1 disappears for >60s:
reaped = reap_stale(timeout_s=60)
# [{"agent_id": "agent-1", "reclaimed_tasks": 2}]
```

### Distributed Locks

Prevent two agents from working on the same resource:

```python
from coordinator import acquire_lock, release_lock

acquired = acquire_lock("repo:torus-framework", holder="agent-1", ttl_s=300)
if acquired:
    # Only this agent can hold this lock
    ...
    release_lock("repo:torus-framework")
```

### Real-time Messaging

Messages trigger Postgres `NOTIFY` events. Agents can subscribe instead of polling:

```python
from coordinator.messages import listen

# Blocking wait for next event (up to 30s timeout)
event = listen(channel="agent_messages", timeout=30.0)

# Or with a callback for continuous listening
def on_message(payload):
    print(f"Got: {payload}")

listen(callback=on_message)
```

### Structured Audit

Replaces append-only JSONL with queryable, partitioned Postgres tables:

```python
from coordinator import log_event, query_events

log_event("gate_fired", gate_name="gate_05", duration_ms=12, severity="info")

# Query last 24h of gate blocks
blocks = query_events(event_type="gate_blocked", severity="error", since_hours=24)
```

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

17 tests verify API compatibility with `agent_channel.py`, new capability exports, fallback logic, and lock hash determinism. Tests run without a Postgres connection.

## License

Apache-2.0
