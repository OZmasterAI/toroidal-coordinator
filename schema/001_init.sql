-- toroidal-coordinator schema v1
-- Neon Postgres (compatible with any Postgres 15+)

-- Agents: registration, heartbeat, liveness
CREATE TABLE IF NOT EXISTS agents (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL DEFAULT '',
    role        TEXT NOT NULL DEFAULT '',
    project     TEXT NOT NULL DEFAULT '',
    registered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_heartbeat TIMESTAMPTZ NOT NULL DEFAULT now(),
    status      TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'idle', 'dead')),
    metadata    JSONB NOT NULL DEFAULT '{}'
);

-- Tasks: DAG-aware priority queue
CREATE TABLE IF NOT EXISTS tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    created_by      TEXT NOT NULL,
    assigned_to     TEXT REFERENCES agents(id) ON DELETE SET NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'assigned', 'running', 'done', 'failed', 'cancelled')),
    priority        INTEGER NOT NULL DEFAULT 5,
    tags            TEXT[] NOT NULL DEFAULT '{}',
    result          TEXT NOT NULL DEFAULT '',
    depends_on      UUID[] NOT NULL DEFAULT '{}',
    required_role   TEXT,
    goal            TEXT,
    parent_task_id  UUID REFERENCES tasks(id) ON DELETE SET NULL
);

-- Messages: inter-agent pub/sub
CREATE TABLE IF NOT EXISTS messages (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    from_agent  TEXT NOT NULL,
    to_agent    TEXT NOT NULL DEFAULT 'all',
    msg_type    TEXT NOT NULL,
    content     TEXT NOT NULL,
    consumed    BOOLEAN NOT NULL DEFAULT false,
    reply_to    BIGINT REFERENCES messages(id) ON DELETE SET NULL
);

-- Distributed locks: advisory lock metadata tracking
CREATE TABLE IF NOT EXISTS distributed_locks (
    resource    TEXT PRIMARY KEY,
    holder      TEXT NOT NULL,
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}'
);

-- Audit events: structured replacement for .audit_trail.jsonl
-- Partitioned by month for cheap retention management
CREATE TABLE IF NOT EXISTS audit (
    id          BIGSERIAL,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id  TEXT,
    agent_id    TEXT,
    event_type  TEXT NOT NULL,
    gate_name   TEXT,
    tool_name   TEXT,
    duration_ms INTEGER,
    severity    TEXT CHECK (severity IN ('info', 'warn', 'error', 'critical')),
    details     JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (id, ts)
) PARTITION BY RANGE (ts);
