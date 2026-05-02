-- Indexes for toroidal-coordinator

-- Agents
CREATE INDEX IF NOT EXISTS idx_agents_heartbeat ON agents (last_heartbeat);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents (status);

-- Tasks
CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks (status, priority);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned ON tasks (assigned_to) WHERE assigned_to IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks (parent_task_id) WHERE parent_task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_updated ON tasks (updated_at);
CREATE INDEX IF NOT EXISTS idx_tasks_depends ON tasks USING GIN (depends_on);

-- Messages
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages (ts);
CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages (to_agent, consumed) WHERE consumed = false;
CREATE INDEX IF NOT EXISTS idx_messages_reply ON messages (reply_to) WHERE reply_to IS NOT NULL;

-- Distributed locks
CREATE INDEX IF NOT EXISTS idx_locks_expires ON distributed_locks (expires_at);
CREATE INDEX IF NOT EXISTS idx_locks_holder ON distributed_locks (holder);

-- Audit (per-partition indexes created automatically by partition creation)
CREATE INDEX IF NOT EXISTS idx_audit_session ON audit (session_id, ts);
CREATE INDEX IF NOT EXISTS idx_audit_event ON audit (event_type, ts);
CREATE INDEX IF NOT EXISTS idx_audit_gate ON audit (gate_name, ts) WHERE gate_name IS NOT NULL;
