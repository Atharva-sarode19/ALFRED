-- Phase 5: agentic workflows. Additive only: no Phase 4 table is touched.
-- conversation_id is a plain reference (no foreign key) so a workflow never depends on conversation rows.

CREATE TABLE workflows (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT,
    title            TEXT NOT NULL DEFAULT '',
    request          TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN
                     ('created', 'planning', 'ready', 'running', 'waiting_for_approval',
                      'completed', 'failed', 'cancelled')),
    failure          TEXT,
    summary          TEXT,
    result           TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at     TIMESTAMPTZ
);
CREATE INDEX idx_workflows_updated ON workflows (updated_at DESC);
CREATE INDEX idx_workflows_conversation ON workflows (conversation_id, updated_at DESC);

CREATE TABLE workflow_tasks (
    workflow_id       TEXT NOT NULL REFERENCES workflows (id) ON DELETE CASCADE,
    task_id           TEXT NOT NULL,
    position          INTEGER NOT NULL,
    description       TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN
                      ('pending', 'ready', 'running', 'waiting_for_approval', 'completed',
                       'failed', 'retrying', 'cancelled', 'blocked')),
    dependencies      JSONB NOT NULL DEFAULT '[]',
    expected_outcome  TEXT NOT NULL DEFAULT '',
    tools             JSONB NOT NULL DEFAULT '[]',
    attempts          INTEGER NOT NULL DEFAULT 0,
    result_summary    TEXT,
    error             TEXT,
    pending_approval  JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (workflow_id, task_id)
);

CREATE TABLE workflow_events (
    workflow_id  TEXT NOT NULL REFERENCES workflows (id) ON DELETE CASCADE,
    seq          INTEGER NOT NULL,
    at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    kind         TEXT NOT NULL,
    task_id      TEXT,
    message      TEXT NOT NULL,
    PRIMARY KEY (workflow_id, seq)
);
