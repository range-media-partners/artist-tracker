#!/usr/bin/env python3
"""Fetch TikTok sound UGC metrics. Resolves video URLs to music IDs. Writes to SQLite."""

import sys
import os
import re
import logging
from datetime import date
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
        logging.FileHandler(LOG_DIR / "fetch_sounds.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

HEADERS = {"x-api-key": API_KEY}
TODAY = str(date.today())

SOUND_ENDPOINTS = [
    "https://api.scrapecreators.com/v2/tiktok/sound/posts",
    "https://api.scrapecreators.com/v1/tiktok/sound/posts",
]


def extract_music_id(url: str) -> str | None:
    """Extract a TikTok music ID from a music URL."""
    if not url:
        return None
    # tiktok.com/music/name-1234567890
    match = re.search(r"/music/[^/]+-(\d{10,})", url)
    if match:
        return match.group(1)
    # musicId= query param
    match = re.search(r"[?&]musicId=(\d+)", url)
    if match:
        return match.group(1)
    # bare numeric ID
    if re.match(r"^\d{10,}$", url.strip()):
        return url.strip()
    return None


def is_video_url(url: str) -> bool:
    return bool(re.search(r"tiktok\.com/@[^/]+/video/\d+", url))


def resolve_music_id_from_video(video_url: str) -> str | None:
    """Call the TikTok video endpoint to get the music ID used in a video."""
    vid_match = re.search(r"/video/(\d+)", video_url)
    if not vid_match:
        return None
    video_id = vid_match.group(1)
    resp = requests.get(
        "https://api.scrapecreators.com/v1/tiktok/post",
        headers=HEADERS, params={"url": video_url}, timeout=30
    )
    if resp.status_code != 200:
        log.debug("Video endpoint returned %s for %s", resp.status_code, video_url)
        return None
    data = resp.json()
    # music info is usually at data.music.id or item.music.id
    item = data.get("data") or data.get("item") or data
    music = item.get("music") or {}
    music_id = str(music.get("id") or "")
    if music_id and music_id != "0":
        log.info("Resolved music ID %s from video %s", music_id, video_id)
        return music_id
    return None


def fetch_sound_posts(music_id: str) -> dict | None:
    for endpoint in SOUND_ENDPOINTS:
        resp = requests.get(
            endpoint, headers=HEADERS, params={"musicId": music_id}, timeout=30
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success") or "itemList" in data or "posts" in data:
                return data
    return None


def run(conn, artist_name: str, sound_url: str) -> dict | None:
    # Spotify or other non-TikTok link — can't track
    if sound_url and "spotify.com" in sound_url:
        log.debug("Skipping Spotify link for %s (need TikTok music URL)", artist_name)
        return None

    # Try to get music ID directly
    music_id = extract_music_id(sound_url)

    # If it's a video URL, resolve the music ID from that video
    if not music_id and is_video_url(sound_url):
        log.info("Sound URL is a video link for %s — resolving music ID...", artist_name)
        music_id = resolve_music_id_from_video(sound_url)

    if not music_id:
        log.warning("Cannot resolve music ID for %s from: %s", artist_name, sound_url)
        return None

    log.info("Fetching sound UGC for %s (musicId=%s)", artist_name, music_id)
    data = fetch_sound_posts(music_id)
    if not data:
        log.warning("Sound UGC fetch returned no data for musicId=%s", music_id)
        return None

    items = data.get("itemList") or data.get("posts") or []
    total_plays = sum(
        int((item.get("stats") or item.get("statistics") or {}).get("playCount", 0))
        for item in items if isinstance(item, dict)
    )
    total_likes = sum(
        int((item.get("stats") or item.get("statistics") or {}).get("diggCount", 0))
        for item in items if isinstance(item, dict)
    )

    row = {
        "artist_name": artist_name,
        "music_id": music_id,
        "date": TODAY,
        "ugc_count": len(items),
        "total_plays": total_plays,
        "total_likes": total_likes,
    }


    db.upsert_sound(conn, row)

    log.info("Saved sound UGC: %s — %d posts, %d plays", artist_name, len(items), total_plays)
    return row


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: fetch_tiktok_sounds.py <artist_name> <sound_url_or_music_id>")
        sys.exit(1)
    with db.get_conn() as conn:
        result = run(conn, sys.argv[1], sys.argv[2])
    print(result)
