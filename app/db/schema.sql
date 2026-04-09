PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    title TEXT,
    status TEXT
);

CREATE INDEX IF NOT EXISTS idx_chats_created_at
    ON chats (created_at, id);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL,
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
    id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES chats (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chat_events_chat_created
    ON chat_events (chat_id, created_at, id);

CREATE INDEX IF NOT EXISTS idx_chat_events_created_at
    ON chat_events (created_at, id);
