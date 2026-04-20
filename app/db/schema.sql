PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS chats (
    id PRIMARY KEY,
    created_at TEXT NOT NULL,
    title TEXT,
    status TEXT
);

CREATE INDEX IF NOT EXISTS idx_chats_created_at
    ON chats (created_at, id);

CREATE TABLE IF NOT EXISTS messages (
    id PRIMARY KEY,
    chat_id NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT,
    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_chat_created
    ON messages (chat_id, created_at, id);

CREATE INDEX IF NOT EXISTS idx_messages_created_at
    ON messages (created_at, id);

CREATE TABLE IF NOT EXISTS chat_events (
    id PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_events_chat_created
    ON chat_events (chat_id, created_at, id);

CREATE INDEX IF NOT EXISTS idx_chat_events_created_at
    ON chat_events (created_at, id);

CREATE TABLE IF NOT EXISTS kb_documents (
    file_id                 PRIMARY KEY,
    path            TEXT    NOT NULL,
    filename        TEXT    NOT NULL,
    checksum        TEXT    NOT NULL,
    embedding       BLOB    NOT NULL,
    embedding_model TEXT    NOT NULL,
    embedding_dim   INTEGER NOT NULL,
    updated_at      TEXT    NOT NULL
);

-- Full-text search index over document content, used for BM25 retrieval at
-- query time.  The `file_id` column is unindexed and acts as a join key
-- back to `kb_documents`.
CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts
    USING fts5(file_id UNINDEXED, content);
