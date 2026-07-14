#!/usr/bin/env python3
"""Shared Snowflake helper — connection + upsert helpers.

NOTE (cleanup later): sound_metrics.sound_title / ugc_delta_24h / source are
carried over from the legacy SQLite DB but are not populated by any current
code — candidates for removal once confirmed nothing external reads them.
"""

import os
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "config" / "config.env")


def get_conn() -> snowflake.connector.SnowflakeConnection:
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        private_key=_load_private_key(),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        schema=os.getenv("SNOWFLAKE_SCHEMA"),
        role=os.getenv("SNOWFLAKE_ROLE"),
    )


def _load_private_key() -> bytes:
    """Read the encrypted private key, unlock it with the passphrase, and return
    it in the DER format the Snowflake connector expects.

    Two sources, checked in order:
      1. SNOWFLAKE_PRIVATE_KEY  — the PEM *contents* directly (used in the cloud,
         injected from Secret Manager).
      2. SNOWFLAKE_PRIVATE_KEY_PATH — a path to the .p8 file (used locally).
    """
    passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
    pem_contents = os.getenv("SNOWFLAKE_PRIVATE_KEY")

    if pem_contents:
        key_bytes = pem_contents.encode()
    else:
        key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH")
        with open(key_path, "rb") as f:
            key_bytes = f.read()

    private_key = serialization.load_pem_private_key(
        key_bytes,
        password=passphrase.encode() if passphrase else None,
    )

    return private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def upsert_social(conn, row: dict):
    cur = conn.cursor()
    try:
        cur.execute("""
            MERGE INTO SOCIAL_METRICS AS t
            USING (SELECT
                %(artist_name)s AS artist_name,
                %(platform)s    AS platform,
                %(date)s        AS date,
                %(followers)s   AS followers,
                %(following)s   AS "FOLLOWING",
                %(likes)s       AS likes,
                %(video_count)s AS video_count,
                %(reel_count)s  AS reel_count,
                %(post_count)s  AS post_count,
                %(verified)s    AS verified,
                %(handle)s      AS handle
            ) AS s
            ON  t.artist_name = s.artist_name
            AND t.platform    = s.platform
            AND t.date        = s.date
            WHEN MATCHED THEN UPDATE SET
                followers   = s.followers,
                "FOLLOWING" = s."FOLLOWING",
                likes       = s.likes,
                video_count = s.video_count,
                reel_count  = s.reel_count,
                post_count  = s.post_count,
                verified    = s.verified,
                handle      = s.handle
            WHEN NOT MATCHED THEN INSERT
                (artist_name, platform, date, followers, "FOLLOWING", likes,
                 video_count, reel_count, post_count, verified, handle)
            VALUES
                (s.artist_name, s.platform, s.date, s.followers, s."FOLLOWING", s.likes,
                 s.video_count, s.reel_count, s.post_count, s.verified, s.handle)
        """, row)
    finally:
        cur.close()


def upsert_video(conn, row: dict):
    cur = conn.cursor()
    try:
        cur.execute("""
            MERGE INTO VIDEO_METRICS AS t
            USING (SELECT
                %(artist_name)s    AS artist_name,
                %(platform)s       AS platform,
                %(video_id)s       AS video_id,
                %(date_collected)s AS date_collected,
                %(posted_date)s    AS posted_date,
                %(views)s          AS views,
                %(likes)s          AS likes,
                %(comments)s       AS comments,
                %(shares)s         AS shares,
                %(description)s    AS description,
                %(url)s            AS url
            ) AS s
            ON  t.video_id       = s.video_id
            AND t.date_collected = s.date_collected
            WHEN MATCHED THEN UPDATE SET
                views    = s.views,
                likes    = s.likes,
                comments = s.comments,
                shares   = s.shares
            WHEN NOT MATCHED THEN INSERT
                (artist_name, platform, video_id, date_collected, posted_date,
                 views, likes, comments, shares, description, url)
            VALUES
                (s.artist_name, s.platform, s.video_id, s.date_collected, s.posted_date,
                 s.views, s.likes, s.comments, s.shares, s.description, s.url)
        """, row)
    finally:
        cur.close()


def upsert_sound(conn, row: dict):
    cur = conn.cursor()
    try:
        cur.execute("""
            MERGE INTO SOUND_METRICS AS t
            USING (SELECT
                %(artist_name)s AS artist_name,
                %(music_id)s    AS music_id,
                %(date)s        AS date,
                %(ugc_count)s   AS ugc_count,
                %(total_plays)s AS total_plays,
                %(total_likes)s AS total_likes
            ) AS s
            ON  t.artist_name = s.artist_name
            AND t.music_id    = s.music_id
            AND t.date        = s.date
            WHEN MATCHED THEN UPDATE SET
                ugc_count   = s.ugc_count,
                total_plays = s.total_plays,
                total_likes = s.total_likes
            WHEN NOT MATCHED THEN INSERT
                (artist_name, music_id, date, ugc_count, total_plays, total_likes)
            VALUES
                (s.artist_name, s.music_id, s.date, s.ugc_count, s.total_plays, s.total_likes)
        """, row)
    finally:
        cur.close()


def upsert_streaming(conn, row: dict):
    cur = conn.cursor()
    try:
        cur.execute("""
            MERGE INTO STREAMING_METRICS AS t
            USING (SELECT
                %(artist_name)s AS artist_name,
                %(platform)s    AS platform,
                %(date)s        AS date,
                %(streams)s     AS streams,
                %(source_file)s AS source_file
            ) AS s
            ON  t.artist_name = s.artist_name
            AND t.platform    = s.platform
            AND t.date        = s.date
            WHEN MATCHED THEN UPDATE SET
                streams     = s.streams,
                source_file = s.source_file
            WHEN NOT MATCHED THEN INSERT
                (artist_name, platform, date, streams, source_file)
            VALUES
                (s.artist_name, s.platform, s.date, s.streams, s.source_file)
        """, row)
    finally:
        cur.close()


def upsert_sound_cobrand(conn, row: dict):
    """Upsert cobrand-sourced sound data (from screenshot extraction).
    Distinct from upsert_sound: populates sound_title, ugc_delta_24h, and
    source='cobrand', which the regular collection path leaves null."""
    cur = conn.cursor()
    try:
        cur.execute("""
            MERGE INTO SOUND_METRICS AS t
            USING (SELECT
                %(artist_name)s   AS artist_name,
                %(music_id)s      AS music_id,
                %(date)s          AS date,
                %(ugc_count)s     AS ugc_count,
                %(sound_title)s   AS sound_title,
                %(ugc_delta_24h)s AS ugc_delta_24h
            ) AS s
            ON  t.artist_name = s.artist_name
            AND t.music_id    = s.music_id
            AND t.date        = s.date
            WHEN MATCHED THEN UPDATE SET
                ugc_count     = s.ugc_count,
                ugc_delta_24h = s.ugc_delta_24h,
                sound_title   = s.sound_title
            WHEN NOT MATCHED THEN INSERT
                (artist_name, music_id, date, ugc_count, sound_title, ugc_delta_24h, source)
                VALUES (s.artist_name, s.music_id, s.date, s.ugc_count, s.sound_title, s.ugc_delta_24h, 'cobrand')
        """, row)
    finally:
        cur.close()


def query(sql: str, params=None) -> list[dict]:
    """Run a SELECT and return rows as dicts with LOWERCASE keys.

    Snowflake stores unquoted column names in uppercase, so DictCursor returns
    keys like 'ARTIST_NAME'. The rest of the codebase (ported from SQLite, which
    preserved lowercase) expects lowercase keys, so we lowercase them here at the
    boundary — one place — rather than touching every caller.
    """
    from snowflake.connector import DictCursor
    with get_conn() as conn:
        cur = conn.cursor(DictCursor)
        try:
            cur.execute(sql, params)
            return [
                {k.lower(): v for k, v in row.items()}
                for row in cur.fetchall()
            ]
        finally:
            cur.close()


if __name__ == "__main__":
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT CURRENT_VERSION()")
        print("Connected to Snowflake:", cur.fetchone()[0])
        cur.close()
