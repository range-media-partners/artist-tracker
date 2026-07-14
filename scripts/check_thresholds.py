#!/usr/bin/env python3
"""Check artist metrics against thresholds. Writes alerts to logs/alerts.log.

Thresholds:
  Instagram  follower growth  > 3%   day-over-day
  TikTok     follower growth  > 3%   day-over-day
  Instagram  video/reel views > 30K  (any single video collected today)
  TikTok     video views      > 30K  (any single video collected today)
  TikTok     sound UGC count  > 50 new creates/day  (today vs yesterday)
  Streaming  streams growth   > 10%  week-over-week  (requires streaming data)
"""

import os
import logging
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "config" / "config.env")

import sys
sys.path.insert(0, str(Path(__file__).parent))
import db

AIRTABLE_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE = os.getenv("AIRTABLE_BASE_ID")
ARTISTS_TABLE = "tblQVgffrMKG3VWAD"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "check_thresholds.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

ALERT_LOG = LOG_DIR / "alerts.log"

# ── Thresholds ────────────────────────────────────────────────────────────────
FOLLOWER_GROWTH_PCT   = 3.0    # % day-over-day
VIDEO_VIEWS_THRESHOLD = 30_000 # single video
SOUND_UGC_NEW_PER_DAY = 50     # new creates/day
STREAMING_GROWTH_PCT  = 10.0   # % week-over-week
# ─────────────────────────────────────────────────────────────────────────────

TODAY     = str(date.today())
YESTERDAY = str(date.today() - timedelta(days=1))
WEEK_AGO  = str(date.today() - timedelta(days=7))


def write_alert(category: str, msg: str):
    full = f"[{TODAY}] [{category}] {msg}"
    log.warning("ALERT: %s", full)
    with open(ALERT_LOG, "a") as f:
        f.write(full + "\n")


def pct(old, new) -> float:
    if not old:
        return 0.0
    return ((new - old) / old) * 100.0


# ── Follower growth ───────────────────────────────────────────────────────────
def check_follower_growth() -> list[str]:
    alerts = []
    rows = db.query("""
        SELECT t.artist_name, t.platform, t.followers AS today_f, y.followers AS yest_f
        FROM social_metrics t
        JOIN social_metrics y
          ON t.artist_name = y.artist_name AND t.platform = y.platform
        WHERE t.date = %s AND y.date = %s
          AND t.followers IS NOT NULL AND y.followers IS NOT NULL AND y.followers > 0
    """, (TODAY, YESTERDAY))

    for r in rows:
        p = pct(r["yest_f"], r["today_f"])
        if p >= FOLLOWER_GROWTH_PCT:
            msg = (f"{r['artist_name']} {r['platform'].title()} followers "
                   f"+{p:.1f}%  ({r['yest_f']:,} → {r['today_f']:,})")
            write_alert("FOLLOWERS", msg)
            alerts.append(msg)
    return alerts


# ── Video / reel views ────────────────────────────────────────────────────────
def check_video_views() -> dict:
    """Returns dict with two sections: new_viral and momentum."""

    # Section 1: New Viral — posted within 48h, already >30K views
    new_viral = db.query("""
        SELECT t.artist_name, t.platform, t.video_id, t.views, t.description, t.url, t.posted_date
        FROM video_metrics t
        WHERE t.date_collected = %s
          AND t.posted_date >= DATEADD(day, -2, %s)
          AND t.views >= 30000
        ORDER BY t.views DESC
    """, (TODAY, TODAY))

    # Section 2: Momentum — gained >50K views day-over-day in past 30 days
    momentum = db.query("""
        SELECT t.artist_name, t.platform, t.video_id,
               t.views AS today_views, y.views AS yest_views,
               (t.views - y.views) AS gained,
               t.description, t.url, t.posted_date
        FROM video_metrics t
        JOIN video_metrics y
          ON t.video_id = y.video_id AND t.platform = y.platform
        WHERE t.date_collected = %s
          AND y.date_collected = %s
          AND t.posted_date >= DATEADD(day, -30, %s)
          AND (t.views - y.views) >= 50000
        ORDER BY (t.views - y.views) DESC
    """, (TODAY, YESTERDAY, TODAY))

    alerts = []
    for r in new_viral:
        snippet = (r.get("description") or "")[:60].replace("\n", " ")
        msg = (f"[NEW_VIRAL] {r['artist_name']} {r['platform'].title()} "
               f"{int(r['views']):,} views in first 48h — \"{snippet}\" {r['url']}")
        write_alert("NEW_VIRAL", msg)
        alerts.append(msg)

    for r in momentum:
        snippet = (r.get("description") or "")[:60].replace("\n", " ")
        msg = (f"[MOMENTUM] {r['artist_name']} {r['platform'].title()} "
               f"+{int(r['gained']):,} views DoD ({int(r['today_views']):,} total) — \"{snippet}\" {r['url']}")
        write_alert("MOMENTUM", msg)
        alerts.append(msg)

    return {"new_viral": list(new_viral), "momentum": list(momentum), "alerts": alerts}


# ── Sound UGC growth ──────────────────────────────────────────────────────────
def check_sound_ugc() -> list[str]:
    alerts = []
    rows = db.query("""
        SELECT t.artist_name, t.music_id,
               t.ugc_count AS today_ugc, y.ugc_count AS yest_ugc
        FROM sound_metrics t
        JOIN sound_metrics y
          ON t.artist_name = y.artist_name AND t.music_id = y.music_id
        WHERE t.date = %s AND y.date = %s
    """, (TODAY, YESTERDAY))

    for r in rows:
        new_creates = (r["today_ugc"] or 0) - (r["yest_ugc"] or 0)
        if new_creates >= SOUND_UGC_NEW_PER_DAY:
            msg = (f"{r['artist_name']} TikTok sound +{new_creates} new UGC today "
                   f"({r['yest_ugc']:,} → {r['today_ugc']:,} total, musicId={r['music_id']})")
            write_alert("SOUND_UGC", msg)
            alerts.append(msg)
    return alerts


# ── Streaming week-over-week ──────────────────────────────────────────────────
def check_streaming_growth() -> list[str]:
    alerts = []
    rows = db.query("""
        SELECT t.artist_name, t.platform,
               t.streams AS this_week, w.streams AS last_week
        FROM streaming_metrics t
        JOIN streaming_metrics w
          ON t.artist_name = w.artist_name AND t.platform = w.platform
        WHERE t.date = %s AND w.date = %s
          AND w.streams > 0
    """, (TODAY, WEEK_AGO))

    for r in rows:
        p = pct(r["last_week"], r["this_week"])
        if p >= STREAMING_GROWTH_PCT:
            msg = (f"{r['artist_name']} {r['platform']} streaming "
                   f"+{p:.1f}% WoW ({r['last_week']:,} → {r['this_week']:,})")
            write_alert("STREAMING", msg)
            alerts.append(msg)
    return alerts


# ── Urgency flags (from Airtable) ─────────────────────────────────────────────
def check_urgency_flags() -> list[str]:
    alerts = []
    try:
        headers = {"Authorization": f"Bearer {AIRTABLE_KEY}"}
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE}/{ARTISTS_TABLE}"
        resp = requests.get(url, headers=headers,
                            params={"filterByFormula": "{Urgency} >= 4", "pageSize": 100},
                            timeout=30)
        if resp.status_code == 200:
            for rec in resp.json().get("records", []):
                fields = rec.get("fields", {})
                name    = fields.get("Name", "")
                urgency = fields.get("Urgency", 0)
                msg = f"{name} — Urgency {urgency}/5 (flagged in Airtable)"
                write_alert("URGENCY", msg)
                alerts.append(msg)
    except Exception as e:
        log.warning("Could not fetch urgency flags: %s", e)
    return alerts


def run() -> list[str]:
    log.info("Running threshold checks for %s", TODAY)

    all_alerts = []
    all_alerts += check_follower_growth()
    video_results = check_video_views()
    all_alerts += video_results["alerts"]
    all_alerts += check_sound_ugc()
    all_alerts += check_streaming_growth()
    all_alerts += check_urgency_flags()

    log.info("Check complete — %d alert(s)", len(all_alerts))
    return all_alerts


if __name__ == "__main__":
    alerts = run()
    if alerts:
        print(f"\n{len(alerts)} alert(s) today:")
        for a in alerts:
            print(f"  {a}")
    else:
        print("No alerts today.")
