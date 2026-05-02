-- Stored functions for toroidal-coordinator

-- Atomic task claiming: SELECT FOR UPDATE SKIP LOCKED
-- Respects DAG dependencies, role requirements, and tag filtering
CREATE OR REPLACE FUNCTION claim_next_task(
    p_agent_id TEXT,
    p_role TEXT DEFAULT NULL,
    p_tag TEXT DEFAULT NULL
) RETURNS SETOF tasks
LANGUAGE sql
AS $$
    WITH claimable AS (
        SELECT t.id
        FROM tasks t
        WHERE t.status = 'pending'
          -- DAG: all dependencies must be done
          AND NOT EXISTS (
              SELECT 1 FROM unnest(t.depends_on) AS dep_id
              WHERE NOT EXISTS (
                  SELECT 1 FROM tasks d WHERE d.id = dep_id AND d.status = 'done'
              )
          )
          -- Role filter
          AND (t.required_role IS NULL OR t.required_role = p_role)
          -- Tag filter
          AND (p_tag IS NULL OR p_tag = ANY(t.tags))
        ORDER BY t.priority ASC, t.created_at ASC
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    UPDATE tasks SET
        status = 'assigned',
        assigned_to = p_agent_id,
        updated_at = now()
    FROM claimable
    WHERE tasks.id = claimable.id
    RETURNING tasks.*;
$$;

-- Unblock check: called after task completion to notify waiting agents
CREATE OR REPLACE FUNCTION notify_dependents()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status = 'done' AND OLD.status != 'done' THEN
        -- Notify any listeners that a task completed
        PERFORM pg_notify('task_events', json_build_object(
            'event', 'task_complete',
            'task_id', NEW.id::text,
            'title', NEW.title,
            'result', NEW.result
        )::text);
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_notify_dependents
    AFTER UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION notify_dependents();

-- Message notification trigger
CREATE OR REPLACE FUNCTION notify_message()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM pg_notify('agent_messages', json_build_object(
        'id', NEW.id,
        'from', NEW.from_agent,
        'to', NEW.to_agent,
        'type', NEW.msg_type,
        'content', left(NEW.content, 200)
    )::text);
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_notify_message
    AFTER INSERT ON messages
    FOR EACH ROW
    EXECUTE FUNCTION notify_message();

-- Reap stale agents: mark dead, reclaim their tasks
CREATE OR REPLACE FUNCTION reap_stale_agents(
    p_timeout INTERVAL DEFAULT '60 seconds'
) RETURNS TABLE(agent_id TEXT, reclaimed_tasks INTEGER)
LANGUAGE plpgsql
AS $$
DECLARE
    stale RECORD;
    count INTEGER;
BEGIN
    FOR stale IN
        SELECT id FROM agents
        WHERE status = 'active'
          AND last_heartbeat < now() - p_timeout
    LOOP
        -- Mark agent dead
        UPDATE agents SET status = 'dead' WHERE id = stale.id;

        -- Reclaim their tasks
        UPDATE tasks SET
            status = 'pending',
            assigned_to = NULL,
            updated_at = now()
        WHERE assigned_to = stale.id
          AND status IN ('assigned', 'running');

        GET DIAGNOSTICS count = ROW_COUNT;

        agent_id := stale.id;
        reclaimed_tasks := count;
        RETURN NEXT;
    END LOOP;
END;
$$;

-- Audit partition creator: call monthly or on-demand
CREATE OR REPLACE FUNCTION create_audit_partition(p_date DATE DEFAULT CURRENT_DATE)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
BEGIN
    start_date := date_trunc('month', p_date)::date;
    end_date := (start_date + INTERVAL '1 month')::date;
    partition_name := 'audit_' || to_char(start_date, 'YYYY_MM');

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS %I PARTITION OF audit FOR VALUES FROM (%L) TO (%L)',
        partition_name, start_date, end_date
    );

    RETURN partition_name;
END;
$$;

-- Expire distributed locks
CREATE OR REPLACE FUNCTION expire_locks()
RETURNS INTEGER
LANGUAGE sql
AS $$
    WITH expired AS (
        DELETE FROM distributed_locks
        WHERE expires_at < now()
        RETURNING resource
    )
    SELECT count(*)::integer FROM expired;
$$;
