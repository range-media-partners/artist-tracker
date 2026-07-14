#!/usr/bin/env python3
"""Daily orchestration: pull artist list from Airtable (read-only), collect metrics.

Artists are processed in urgency order (5 → 1) so high-priority artists
are captured first in case the run is interrupted.
"""

import os
import json
import logging
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "config" / "config.env")

import sys
sys.path.insert(0, str(Path(__file__).parent))
import db
import fetch_tiktok_artist
import fetch_instagram_artist
import fetch_tiktok_sounds

AIRTABLE_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE = os.getenv("AIRTABLE_BASE_ID")
ARTISTS_TABLE = "tblQVgffrMKG3VWAD"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"daily_collect_{date.today()}.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def get_all_artists() -> list[dict]:
    headers = {"Authorization": f"Bearer {AIRTABLE_KEY}"}
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE}/{ARTISTS_TABLE}"
    records, offset = [], None
    while True:
        params = {"pageSize": 100}
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code != 200:
            log.error("Airtable fetch failed: HTTP %s", resp.status_code)
            break
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    log.info("Fetched %d artist records from Airtable", len(records))
    return records


def sync_roster(conn, current_names: set[str]):
    """Mirror the Airtable roster into the Snowflake ROSTER table.

    Uses a temporary staging table + single MERGE so the whole sync is two
    round-trips instead of one-per-artist. Adds new artists, removes artists
    no longer in Airtable, leaves existing rows untouched.
    """
    cur = conn.cursor()
    try:
        # 1. Temp staging table, same shape as ROSTER's key column.
        #    Dropped automatically when the connection closes.
        cur.execute("""
            CREATE TEMPORARY TABLE ROSTER_STAGING (
                artist_name STRING
            )
        """)

        # 2. Bulk-insert all current names in one batched call.
        cur.executemany(
            "INSERT INTO ROSTER_STAGING (artist_name) VALUES (%(name)s)",
            [{"name": n} for n in current_names],
        )

        # 3a. Insert any new artists (present in staging, absent from ROSTER).
        cur.execute("""
            MERGE INTO ROSTER AS t
            USING ROSTER_STAGING AS s
            ON t.artist_name = s.artist_name
            WHEN NOT MATCHED THEN
                INSERT (artist_name, synced_at)
                VALUES (s.artist_name, CURRENT_TIMESTAMP())
        """)

        # 3b. Find artists no longer in Airtable, log them, then remove.
        cur.execute("""
            SELECT artist_name FROM ROSTER
            WHERE artist_name NOT IN (SELECT artist_name FROM ROSTER_STAGING)
        """)
        to_remove = [row[0] for row in cur.fetchall()]

        if to_remove:
            for name in to_remove:
                log.info("Roster: removing %s (no longer in Airtable)", name)
            cur.execute("""
                DELETE FROM ROSTER
                WHERE artist_name NOT IN (SELECT artist_name FROM ROSTER_STAGING)
            """)

        log.info("Roster sync complete: %d active artists, %d removed",
                 len(current_names), len(to_remove))
    finally:
        cur.close()


def run():

    # ── Roster sync — mirror Airtable into SQLite roster table ──────────────
    # Ensures removed artists disappear from reports immediately.
    # Historical metric data is preserved; only the roster table changes.
    # ── Roster sync — mirror Airtable into Snowflake ROSTER table ──────────
    try:
        artists_for_sync = get_all_artists()
        current_names = {
            r.get("fields", {}).get("Name", "").strip()
            for r in artists_for_sync
            if r.get("fields", {}).get("Name", "").strip()
        }
        with db.get_conn() as conn:
            sync_roster(conn, current_names)
    except Exception as e:
        log.warning("Roster sync failed (non-fatal): %s", e)

    artists = get_all_artists()
    if not artists:
        log.warning("No artists found — nothing to collect")
        return

    # Sort by Urgency descending (5 first), then by Name
    artists.sort(
        key=lambda r: (-(r.get("fields", {}).get("Urgency") or 0),
                       r.get("fields", {}).get("Name", "").lower())
    )
    
    # Optional cap for testing — set ARTIST_LIMIT in the environment to process
    # only the first N artists. Unset/absent = process all. Remove or ignore in production.
    limit = os.getenv("ARTIST_LIMIT")
    if limit:
        artists = artists[: int(limit)]
        log.info("ARTIST_LIMIT set — processing only first %s artists", limit)

    results = {
        "date": str(date.today()),
        "total": len(artists),
        "success": 0,
        "errors": [],
        "skipped": [],
    }

    with db.get_conn() as conn:
        for rec in artists:
            fields = rec.get("fields", {})
            name = fields.get("Name", "").strip()
            if not name:
                continue

            tiktok_url   = fields.get("Artist TikTok", "") or ""
            instagram_url = fields.get("Instagram", "") or ""
            sound_url    = fields.get("TikTok Sound / MIQ Link", "") or ""
            artist_ok    = True

            if tiktok_url:
                try:
                    result = fetch_tiktok_artist.run(conn, name, tiktok_url)
                    if not result:
                        results["errors"].append({"artist": name, "platform": "tiktok", "error": "fetch returned None"})
                        artist_ok = False
                except Exception as e:
                    log.exception("TikTok error for %s", name)
                    results["errors"].append({"artist": name, "platform": "tiktok", "error": str(e)})
                    artist_ok = False
            else:
                results["skipped"].append({"artist": name, "reason": "no TikTok URL"})

            if instagram_url:
                try:
                    result = fetch_instagram_artist.run(conn, name, instagram_url)
                    if not result:
                        results["errors"].append({"artist": name, "platform": "instagram", "error": "fetch returned None"})
                        artist_ok = False
                except Exception as e:
                    log.exception("Instagram error for %s", name)
                    results["errors"].append({"artist": name, "platform": "instagram", "error": str(e)})
                    artist_ok = False
            else:
                results["skipped"].append({"artist": name, "reason": "no Instagram URL"})

            # Sound — only if TikTok URL (not Spotify)
            if sound_url and "spotify.com" not in sound_url:
                try:
                    fetch_tiktok_sounds.run(conn, name, sound_url)
                except Exception as e:
                    log.warning("Sound error for %s: %s", name, e)

            if artist_ok:
                results["success"] += 1

    summary_path = LOG_DIR / f"daily_summary_{date.today()}.json"
    with open(summary_path, "w") as f:
        json.dump(results, f, indent=2)

    log.info(
        "Done. %d/%d OK, %d errors, %d skipped",
        results["success"], results["total"],
        len(results["errors"]), len(results["skipped"])
    )


if __name__ == "__main__":
    run()
