#!/usr/bin/env python3
"""Fetch Instagram profile + recent reel view counts. Writes to SQLite.

Only stores reels posted within the last 30 days to avoid surfacing
old historical content in the alerts/reports.
"""

import sys
import os
import re
import logging
from datetime import date, datetime, timezone, timedelta
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
        logging.FileHandler(LOG_DIR / "fetch_instagram.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

HEADERS = {"x-api-key": API_KEY}
TODAY = str(date.today())
CUTOFF = date.today() - timedelta(days=30)  # only store reels from last 30 days


def extract_handle(url: str) -> str | None:
    if not url:
        return None
    if not url.startswith("http"):
        return url.lstrip("@").split("?")[0].strip()
    match = re.search(r"instagram\.com/([^/?&#\s]+)", url)
    if match:
        h = match.group(1)
        return h if h not in ("p", "reel", "stories", "explore", "accounts") else None
    return None


def fetch_profile(handle: str) -> dict | None:
    resp = requests.get(
        "https://api.scrapecreators.com/v1/instagram/profile",
        headers=HEADERS, params={"handle": handle}, timeout=30
    )
    if resp.status_code != 200 or not resp.json().get("success"):
        log.error("Instagram profile failed for @%s: HTTP %s", handle, resp.status_code)
        return None
    return resp.json()


def fetch_reels(handle: str) -> list[dict]:
    resp = requests.get(
        "https://api.scrapecreators.com/v1/instagram/user/reels",
        headers=HEADERS, params={"handle": handle}, timeout=30
    )
    if resp.status_code != 200:
        log.debug("Instagram reels endpoint returned %s for @%s", resp.status_code, handle)
        return []
    data = resp.json()
    items = data.get("items") or []
    return [item["media"] for item in items if "media" in item]


def ts_to_date(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None


def run(conn, artist_name: str, instagram_url: str) -> dict | None:
    handle = extract_handle(instagram_url)
    if not handle:
        log.error("Could not extract Instagram handle from: %s", instagram_url)
        return None

    log.info("Fetching Instagram for @%s (%s)", handle, artist_name)
    profile = fetch_profile(handle)
    if not profile:
        return None

    user = profile.get("data", {}).get("user", {})
    followers = (user.get("edge_followed_by") or {}).get("count", 0)
    following = (user.get("edge_follow") or {}).get("count", 0)
    post_count = (user.get("edge_owner_to_timeline_media") or {}).get("count", 0)
    reel_data = user.get("edge_felix_video_timeline") or {}
    reel_count = reel_data.get("count", 0)

    social_row = {
        "artist_name": artist_name,
        "platform": "instagram",
        "date": TODAY,
        "followers": followers,
        "following": following,
        "likes": None,
        "video_count": None,
        "reel_count": reel_count,
        "post_count": post_count,
        "verified": 1 if user.get("is_verified") else 0,
        "handle": handle,
    }


    db.upsert_social(conn, social_row)

    reels = fetch_reels(handle)
    reel_rows_saved = 0
    reel_rows_skipped_old = 0

    for m in reels:
        taken_at = m.get("taken_at")
        posted_date_str = ts_to_date(taken_at)
        if posted_date_str:
            try:
                posted = date.fromisoformat(posted_date_str)
                if posted < CUTOFF:
                    reel_rows_skipped_old += 1
                    continue
            except ValueError:
                pass

        vid_id = str(m.get("pk") or m.get("id") or "")
        if not vid_id:
            continue

        view_count = m.get("play_count") or m.get("view_count") or 0
        like_count = m.get("like_count") or 0
        comment_count = m.get("comment_count") or 0
        cap = m.get("caption") or {}
        caption = cap.get("text", "") if isinstance(cap, dict) else str(cap)

        db.upsert_video(conn, {
            "artist_name": artist_name,
            "platform": "instagram",
            "video_id": vid_id,
            "date_collected": TODAY,
            "posted_date": posted_date_str,
            "views": int(view_count),
            "likes": int(like_count),
            "comments": int(comment_count),
            "shares": 0,
            "description": caption[:500],
            "url": f"https://www.instagram.com/p/{vid_id}/",
        })
        reel_rows_saved += 1

    if reel_rows_skipped_old:
        log.debug("Skipped %d reels older than 30 days for %s", reel_rows_skipped_old, artist_name)

    log.info(
        "Saved Instagram: %s — followers=%s, %d recent reels",
        artist_name, followers, reel_rows_saved
    )
    return social_row


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: fetch_instagram_artist.py <artist_name> <instagram_url>")
        sys.exit(1)
    with db.get_conn() as conn:
        result = run(conn, sys.argv[1], sys.argv[2])
    print(result)