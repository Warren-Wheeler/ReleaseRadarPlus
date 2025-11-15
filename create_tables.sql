CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    singles_channel_id INTEGER,
    albums_channel_id INTEGER,
    allow_non_admins INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS follows (
    guild_id INTEGER,
    artist_id TEXT,
    artist_name TEXT,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, artist_id)
);

CREATE TABLE IF NOT EXISTS seen_releases (
    guild_id INTEGER,
    release_id TEXT,
    release_type TEXT,
    seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, release_id)
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
