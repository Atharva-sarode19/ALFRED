-- Phase 4: conversations, messages, memories, tasks.

CREATE TABLE conversations (
    id              TEXT PRIMARY KEY,
    title           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_conversations_updated ON conversations (updated_at DESC);

CREATE TABLE messages (
    id               BIGSERIAL PRIMARY KEY,
    conversation_id  TEXT NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content          TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_vector    TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);
CREATE INDEX idx_messages_conversation ON messages (conversation_id, id);
CREATE INDEX idx_messages_search ON messages USING GIN (search_vector);

CREATE TABLE memories (
    id                      BIGSERIAL PRIMARY KEY,
    category                TEXT NOT NULL DEFAULT 'fact'
                            CHECK (category IN ('preference', 'fact', 'instruction', 'project', 'other')),
    key                     TEXT,
    content                 TEXT NOT NULL,
    content_hash            TEXT NOT NULL,
    importance              SMALLINT NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
    status                  TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    source                  TEXT NOT NULL DEFAULT 'extracted',
    source_conversation_id  TEXT REFERENCES conversations (id) ON DELETE SET NULL,
    superseded_by           BIGINT REFERENCES memories (id) ON DELETE SET NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_accessed_at        TIMESTAMPTZ,
    access_count            INTEGER NOT NULL DEFAULT 0,
    expires_at              TIMESTAMPTZ,
    search_vector           TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);
CREATE INDEX idx_memories_search ON memories USING GIN (search_vector);
CREATE INDEX idx_memories_category_status ON memories (category, status);
CREATE INDEX idx_memories_key_active ON memories (key) WHERE status = 'active' AND key IS NOT NULL;
CREATE UNIQUE INDEX uq_memories_active_hash ON memories (content_hash) WHERE status = 'active';
CREATE INDEX idx_memories_expires ON memories (expires_at) WHERE expires_at IS NOT NULL;

CREATE TABLE tasks (
    id             BIGSERIAL PRIMARY KEY,
    title          TEXT NOT NULL,
    description    TEXT,
    project        TEXT,
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'in_progress', 'blocked', 'completed', 'cancelled')),
    priority       SMALLINT NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at   TIMESTAMPTZ,
    search_vector  TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, '') || ' ' || coalesce(project, ''))
    ) STORED
);
CREATE INDEX idx_tasks_status ON tasks (status, updated_at DESC);
CREATE INDEX idx_tasks_project ON tasks (lower(project));
CREATE INDEX idx_tasks_search ON tasks USING GIN (search_vector);

CREATE TABLE task_updates (
    id             BIGSERIAL PRIMARY KEY,
    task_id        BIGINT NOT NULL REFERENCES tasks (id) ON DELETE CASCADE,
    kind           TEXT NOT NULL DEFAULT 'note' CHECK (kind IN ('note', 'decision', 'milestone', 'step')),
    content        TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_vector  TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);
CREATE INDEX idx_task_updates_task ON task_updates (task_id, id);
CREATE INDEX idx_task_updates_search ON task_updates USING GIN (search_vector);
