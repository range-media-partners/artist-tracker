Artist Tracker - Database Schema
==================================================

CREATE TABLE roster (
                    artist_name TEXT PRIMARY KEY,
                    synced_at   TEXT NOT NULL
                );

CREATE TABLE social_metrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_name   TEXT    NOT NULL,
    platform      TEXT    NOT NULL,   -- 'tiktok' | 'instagram'
    date          TEXT    NOT NULL,   -- YYYY-MM-DD
    followers     INTEGER,
    following     INTEGER,
    likes         INTEGER,            -- TikTok cumulative hearts
    video_count   INTEGER,
    reel_count    INTEGER,
    post_count    INTEGER,
    verified      INTEGER,            -- 0/1
    handle        TEXT,
    UNIQUE(artist_name, platform, date)
);

CREATE TABLE sound_metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_name TEXT    NOT NULL,
    music_id    TEXT    NOT NULL,
    date        TEXT    NOT NULL,  -- YYYY-MM-DD
    ugc_count   INTEGER,           -- number of videos using the sound
    total_plays INTEGER,
    total_likes INTEGER, sound_title TEXT, ugc_delta_24h INTEGER, source TEXT,
    UNIQUE(artist_name, music_id, date)
);

CREATE TABLE sqlite_sequence(name,seq);

CREATE TABLE streaming_metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_name TEXT    NOT NULL,
    platform    TEXT    NOT NULL,  -- 'spotify' | 'apple_music' | etc.
    date        TEXT    NOT NULL,  -- YYYY-MM-DD
    streams     INTEGER,
    source_file TEXT,
    UNIQUE(artist_name, platform, date)
);

CREATE TABLE video_metrics (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    artist_name    TEXT    NOT NULL,
    platform       TEXT    NOT NULL,  -- 'tiktok' | 'instagram'
    video_id       TEXT    NOT NULL,
    date_collected TEXT    NOT NULL,  -- YYYY-MM-DD we ran collection
    posted_date    TEXT,              -- when the video was posted
    views          INTEGER,
    likes          INTEGER,
    comments       INTEGER,
    shares         INTEGER,
    description    TEXT,
    url            TEXT,
    UNIQUE(video_id, date_collected)
);

