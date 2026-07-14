#!/usr/bin/env python3
"""Fetch TikTok profile + recent video metrics for an artist. Writes to SQLite."""

import sys
import os
import re
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "config" / "config.env")
sys.path.insert(0, str(Path(__file__).parent))
import db

API_KEY = os.getenv("SCRAPECREATORS_API_KEY")
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "fetch_tiktok.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

HEADERS = {"x-api-key": API_KEY}
TODAY = str(date.today())


def extract_handle(url: str) -> str | None:
    if not url:
        return None
    if not url.startswith("http"):
        return url.lstrip("@").split("?")[0].strip()
    match = re.search(r"tiktok\.com/@([^/?&#\s]+)", url)
    return match.group(1) if match else None


def fetch_profile(handle: str) -> dict | None:
    resp = requests.get(
        "https://api.scrapecreators.com/v1/tiktok/profile",
        headers=HEADERS, params={"handle": handle}, timeout=30
    )
    if resp.status_code != 200 or not resp.json().get("success"):
        log.error("TikTok profile failed for @%s: HTTP %s", handle, resp.status_code)
        return None
    return resp.json()


def fetch_videos(handle: str) -> list[dict]:
    """Fetch recent videos via v3 endpoint."""
    resp = requests.get(
        "https://api.scrapecreators.com/v3/tiktok/profile/videos",
        headers=HEADERS, params={"handle": handle}, timeout=30
    )
    if resp.status_code != 200:
        log.debug("TikTok videos endpoint returned %s for @%s", resp.status_code, handle)
        return []
    data = resp.json()
    items = data.get("aweme_list") or []
    if not isinstance(items, list):
        items = []
    return items


def ts_to_date(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None


def run(conn, artist_name: str, tiktok_url: str) -> dict | None:
    handle = extract_handle(tiktok_url)
    if not handle:
        log.error("Could not extract TikTok handle from: %s", tiktok_url)
        return None

    log.info("Fetching TikTok for @%s (%s)", handle, artist_name)
    profile = fetch_profile(handle)
    if not profile:
        return None

    stats = profile.get("statsV2") or profile.get("stats", {})
    user = profile.get("user", {})

    social_row = {
        "artist_name": artist_name,
        "platform": "tiktok",
        "date": TODAY,
        "followers": int(stats.get("followerCount", 0)),
        "following": int(stats.get("followingCount", 0)),
        "likes": int(stats.get("heartCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
        "reel_count": None,
        "post_count": None,
        "verified": 1 if user.get("verified") else 0,
        "handle": handle,
    }


    db.upsert_social(conn, social_row)

    videos = fetch_videos(handle)

    video_rows_saved = 0
    for item in videos:
        if not isinstance(item, dict):
            continue
        vstats = item.get("statistics") or item.get("stats") or {}
        vid_id = item.get("aweme_id") or item.get("id") or ""
        if not vid_id:
            continue
        desc = item.get("desc") or item.get("description") or ""
        create_time = item.get("create_time") or item.get("createTime") or ""
        db.upsert_video(conn, {
            "artist_name": artist_name,
            "platform": "tiktok",
            "video_id": str(vid_id),
            "date_collected": TODAY,
            "posted_date": ts_to_date(create_time),
            "views": int(vstats.get("play_count", 0)),
            "likes": int(vstats.get("digg_count", 0)),
            "comments": int(vstats.get("comment_count", 0)),
            "shares": int(vstats.get("share_count", 0)),
            "description": desc[:500],
            "url": "https://www.tiktok.com/@" + handle + "/video/" + str(vid_id),
        })
        video_rows_saved += 1

    log.info(
        "Saved TikTok: %s — followers=%s, %d videos",
        artist_name, social_row["followers"], video_rows_saved
    )
    return social_row


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: fetch_tiktok_artist.py <artist_name> <tiktok_url>")
        sys.exit(1)
    with db.get_conn() as conn:
        result = run(conn, sys.argv[1], sys.argv[2])
    print(result)
