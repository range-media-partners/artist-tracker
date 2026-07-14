#!/usr/bin/env python3
"""Generate daily alert + snapshot report from SQLite. Saves HTML + plain text."""

import os
import logging
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "config" / "config.env")

import sys
sys.path.insert(0, str(Path(__file__).parent))
import db
import storage

REPORTS_DIR = BASE_DIR / "reports"
LOG_DIR     = BASE_DIR / "logs"
REPORTS_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "generate_report.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

TODAY     = str(date.today())
YESTERDAY = str(date.today() - timedelta(days=1))
WEEK_AGO  = str(date.today() - timedelta(days=7))

VIDEO_VIEWS_THRESHOLD = 30_000
FOLLOWER_GROWTH_PCT   = 3.0
SOUND_UGC_PER_DAY     = 50


def fmt(n) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return "—"


def pct_str(old, new) -> str:
    try:
        old, new = int(old), int(new)
        if not old:
            return "—"
        p = ((new - old) / old) * 100
        if abs(p) < 0.05:
            return "—"
        sign = "+" if p >= 0 else ""
        return f"{sign}{p:.1f}%"
    except Exception:
        return "—"


# ── Alert sections ────────────────────────────────────────────────────────────

def get_follower_spikes() -> dict:
    """Returns {tiktok: [...], instagram: [...]} each ranked by pct desc."""
    rows = db.query("""
        SELECT t.artist_name, t.platform,
               t.followers AS now_f, y.followers AS prev_f,
               ROUND(100.0 * (t.followers - y.followers) / y.followers, 1) AS pct,
               t.handle AS handle
        FROM social_metrics t
        JOIN social_metrics y ON t.artist_name = y.artist_name AND t.platform = y.platform
                              AND t.handle = y.handle
        WHERE t.date = %s AND y.date = %s AND y.followers > 0
          AND (t.followers - y.followers) * 1.0 / y.followers >= %s
          AND (t.followers - y.followers) >= 40
          AND (t.followers - y.followers) * 1.0 / y.followers <= 3.0
          AND y.followers >= 10
          AND t.artist_name IN (SELECT artist_name FROM roster)
        ORDER BY pct DESC
    """, (TODAY, YESTERDAY, FOLLOWER_GROWTH_PCT / 100))
    return {
        "tiktok":    [r for r in rows if r["platform"] == "tiktok"],
        "instagram": [r for r in rows if r["platform"] == "instagram"],
    }


def get_new_viral_videos() -> list[dict]:
    """Videos posted within 48h that already have >30K views."""
    return db.query("""
        SELECT artist_name, platform, video_id, views, description, url, posted_date
        FROM video_metrics
        WHERE date_collected = %s
          AND posted_date >= DATEADD(day, -2, %s)
          AND views >= 30000
          AND artist_name IN (SELECT artist_name FROM roster)
        ORDER BY views DESC
    """, (TODAY, TODAY))


def get_momentum_videos() -> list[dict]:
    """Videos in past 30 days that gained >50K views day-over-day."""
    return db.query("""
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
          AND t.artist_name IN (SELECT artist_name FROM roster)
        ORDER BY (t.views - y.views) DESC
    """, (TODAY, YESTERDAY, TODAY))


def get_sound_spikes() -> list[dict]:
    # Use ugc_delta_24h from cobrand uploads when available, else compute from DB
    cobrand = db.query("""
        SELECT artist_name, music_id, sound_title, ugc_count AS now_ugc,
               ugc_delta_24h AS new_creates
        FROM sound_metrics
        WHERE date = %s AND source = 'cobrand'
        ORDER BY ugc_delta_24h DESC
    """, (TODAY,))
    if cobrand:
        return cobrand
    return db.query("""
        SELECT t.artist_name, t.music_id, t.sound_title,
               t.ugc_count AS now_ugc, y.ugc_count AS prev_ugc,
               (t.ugc_count - y.ugc_count) AS new_creates
        FROM sound_metrics t
        JOIN sound_metrics y ON t.artist_name = y.artist_name AND t.music_id = y.music_id
        WHERE t.date = %s AND y.date = %s
          AND (t.ugc_count - y.ugc_count) >= %s
          AND t.artist_name IN (SELECT artist_name FROM roster)
        ORDER BY new_creates DESC
    """, (TODAY, YESTERDAY, SOUND_UGC_PER_DAY))


def get_streaming_spikes() -> list[dict]:
    return db.query("""
        SELECT t.artist_name, t.platform,
               t.streams AS now_s, w.streams AS prev_s,
               ROUND(100.0 * (t.streams - w.streams) / w.streams, 1) AS pct
        FROM streaming_metrics t
        JOIN streaming_metrics w ON t.artist_name = w.artist_name AND t.platform = w.platform
        WHERE t.date = %s AND w.date = %s AND w.streams > 0
          AND (t.streams - w.streams) * 1.0 / w.streams >= 0.10
        ORDER BY pct DESC
    """, (TODAY, WEEK_AGO))


def get_urgency_flags() -> list[dict]:
    return db.query("""
        SELECT DISTINCT s.artist_name
        FROM social_metrics s
        WHERE s.date = %s
        ORDER BY s.artist_name
    """, (TODAY,))  # placeholder — urgency comes from Airtable, shown separately


def get_snapshot() -> dict:
    """Two independent tables: top TikTok movers and top Instagram movers by DoD gain."""
    tt = db.query("""
        SELECT t.artist_name, t.handle AS tt_handle,
               t.followers AS tt_followers,
               y.followers AS tt_prev_followers,
               (t.followers - y.followers) AS tt_gained,
               ROUND(100.0 * (t.followers - y.followers) / y.followers, 1) AS tt_pct
        FROM social_metrics t
        JOIN social_metrics y ON t.artist_name = y.artist_name AND t.platform = y.platform
                              AND t.handle = y.handle
        WHERE t.date = %s AND y.date = %s AND t.platform = 'tiktok'
          AND y.followers > 0
          AND (t.followers - y.followers) >= 5000
          AND t.artist_name IN (SELECT artist_name FROM roster)
        ORDER BY (t.followers - y.followers) DESC
    """, (TODAY, YESTERDAY))

    ig = db.query("""
        SELECT t.artist_name, t.handle AS ig_handle,
               t.followers AS ig_followers,
               y.followers AS ig_prev_followers,
               (t.followers - y.followers) AS ig_gained,
               ROUND(100.0 * (t.followers - y.followers) / y.followers, 1) AS ig_pct
        FROM social_metrics t
        JOIN social_metrics y ON t.artist_name = y.artist_name AND t.platform = y.platform
                              AND t.handle = y.handle
        WHERE t.date = %s AND y.date = %s AND t.platform = 'instagram'
          AND y.followers > 0
          AND (t.followers - y.followers) >= 5000
          AND t.artist_name IN (SELECT artist_name FROM roster)
        ORDER BY (t.followers - y.followers) DESC
    """, (TODAY, YESTERDAY))

    return {"tiktok": tt, "instagram": ig}


def get_wow_follower_spikes() -> dict:
    """Saturday deep-dive: artists who gained >10% followers WoW on either platform."""
    rows = db.query("""
        SELECT t.artist_name, t.platform,
               t.followers AS now_f, w.followers AS prev_f,
               ROUND(100.0 * (t.followers - w.followers) / w.followers, 1) AS pct
        FROM social_metrics t
        JOIN social_metrics w ON t.artist_name = w.artist_name AND t.platform = w.platform
        WHERE t.date = %s AND w.date = %s AND w.followers > 0
          AND (t.followers - w.followers) * 1.0 / w.followers >= 0.10
        ORDER BY pct DESC
    """, (TODAY, WEEK_AGO))
    return {
        "tiktok":    [r for r in rows if r["platform"] == "tiktok"],
        "instagram": [r for r in rows if r["platform"] == "instagram"],
    }

def render_txt(follower_spikes, new_viral, momentum, sound_spikes, streaming_spikes, snapshot) -> str:
    lines = [f"Artist Tracking Report — {TODAY}", "=" * 60, ""]

    total_flags = len(follower_spikes) + len(new_viral) + len(momentum) + len(sound_spikes) + len(streaming_spikes)
    lines.append(f"  {total_flags} flag(s) today\n")

    tt_spikes = follower_spikes.get("tiktok", [])
    ig_spikes = follower_spikes.get("instagram", [])
    if tt_spikes or ig_spikes:
        lines += ["FOLLOWER SPIKES  (>3% day-over-day)", "-" * 40]
        if tt_spikes:
            lines.append("  TikTok:")
            for r in tt_spikes:
                lines.append(f"    {r['artist_name']:30s}  +{r['pct']:.1f}%   {fmt(r['prev_f'])} → {fmt(r['now_f'])}")
        if ig_spikes:
            lines.append("  Instagram:")
            for r in ig_spikes:
                lines.append(f"    {r['artist_name']:30s}  +{r['pct']:.1f}%   {fmt(r['prev_f'])} → {fmt(r['now_f'])}")
        lines.append("")

    if new_viral:
        lines += ["NEW VIRAL VIDEOS (30K+ VIEWS IN FIRST 48H)", "-" * 40]
        for r in new_viral:
            snippet = (r["description"] or "")[:50].replace("\n", " ")
            lines.append(f"  {r['artist_name']:30s}  {r['platform'].title():10s}  "
                         f"{fmt(r['views'])} views  (posted {r['posted_date']})")
            lines.append(f"    {r['url']}")
            if snippet:
                lines.append(f"    \"{snippet}\"")
        lines.append("")

    if momentum:
        lines += ["MOMENTUM VIDEOS (50K+ VIEWS DAY-OVER-DAY)", "-" * 40]
        for r in momentum:
            snippet = (r["description"] or "")[:50].replace("\n", " ")
            lines.append(f"  {r['artist_name']:30s}  {r['platform'].title():10s}  "
                         f"+{fmt(r['gained'])} DoD  ({fmt(r['today_views'])} total)")
            lines.append(f"    {r['url']}")
            if snippet:
                lines.append(f"    \"{snippet}\"")
        lines.append("")

    if sound_spikes:
        lines += ["SOUND UGC", "-" * 40]
        for r in sound_spikes:
            title = r.get("sound_title") or r.get("music_id") or ""
            delta = r.get("new_creates") or 0
            sign = "+" if delta >= 0 else ""
            pct_change = ""
            prev = r.get("prev_ugc")
            if prev and prev > 0:
                p = (delta / prev) * 100
                pct_change = f"  ({p:+.1f}%)"
            lines.append(f"  {r['artist_name']:30s}  {title[:30]:30s}  "
                         f"{sign}{fmt(delta)}/day  {fmt(r['now_ugc'])} total{pct_change}")
        lines.append("")

    if streaming_spikes:
        lines += ["STREAMING SPIKES  (>10% week-over-week)", "-" * 40]
        for r in streaming_spikes:
            lines.append(f"  {r['artist_name']:30s}  {r['platform']:12s}  "
                         f"+{r['pct']:.1f}%   {fmt(r['prev_s'])} → {fmt(r['now_s'])}")
        lines.append("")

    tt_snap = snapshot.get("tiktok", [])
    ig_snap = snapshot.get("instagram", [])
    if tt_snap or ig_snap:
        lines += ["FOLLOWER MOVERS >5K DAY-OVER-DAY", "-" * 40]
        if tt_snap:
            lines.append("  TikTok:")
            for r in tt_snap:
                lines.append(f"    {r['artist_name']:<30}  +{int(r.get('tt_gained') or 0):>8,}  "
                             f"+{r.get('tt_pct') or 0:.1f}%  ({fmt(r.get('tt_prev_followers'))} -> {fmt(r.get('tt_followers'))})")
        if ig_snap:
            lines.append("  Instagram:")
            for r in ig_snap:
                lines.append(f"    {r['artist_name']:<30}  +{int(r.get('ig_gained') or 0):>8,}  "
                             f"+{r.get('ig_pct') or 0:.1f}%  ({fmt(r.get('ig_prev_followers'))} -> {fmt(r.get('ig_followers'))})")

    return "\n".join(lines)


def render_html(follower_spikes, new_viral, momentum, sound_spikes, streaming_spikes, snapshot) -> str:
    total_flags = len(follower_spikes) + len(new_viral) + len(momentum) + len(sound_spikes) + len(streaming_spikes)

    def section(title, rows_html, empty_msg="None today.", subtitle=None):
        sub = f'<p style="margin:0 0 10px;font-size:12px;color:#888;font-style:italic">{subtitle}</p>' if subtitle else ''
        if not rows_html:
            return f'<div class="section"><h2>{title}</h2>{sub}<p class="empty">{empty_msg}</p></div>'
        return f'<div class="section"><h2>{title}</h2>{rows_html}</div>'

    # Follower spikes — TikTok and Instagram side by side
    def _fs_table(rows, platform):
        if not rows:
            return "<p class='empty'>None today.</p>"
        def _link(r):
            h = r.get('handle','')
            if not h:
                return r['artist_name']
            if platform == 'tiktok':
                url = f"https://www.tiktok.com/@{h}"
            else:
                url = f"https://www.instagram.com/{h}/"
            return f"<a href='{url}' target='_blank'>{r['artist_name']}</a>"
        trs = "".join(
            f"<tr><td>{_link(r)}</td>"
            f"<td class='up'>+{r['pct']:.1f}%</td>"
            f"<td>{fmt(r['prev_f'])} → {fmt(r['now_f'])}</td></tr>"
            for r in rows
        )
        return f"<table><tr><th>Artist</th><th>Growth</th><th>Followers</th></tr>{trs}</table>"

    tt_spikes = follower_spikes.get("tiktok", [])
    ig_spikes = follower_spikes.get("instagram", [])
    fs_html = (
        f"<div style='display:flex;gap:32px;align-items:flex-start'>"
        f"<div style='flex:1'><h3 style='margin:0 0 6px;font-size:13px;color:#555'>TikTok</h3>{_fs_table(tt_spikes, 'tiktok')}</div>"
        f"<div style='flex:1'><h3 style='margin:0 0 6px;font-size:13px;color:#555'>Instagram</h3>{_fs_table(ig_spikes, 'instagram')}</div>"
        f"</div>"
    ) if (tt_spikes or ig_spikes) else ""

    # New viral videos
    nv_rows = "".join(
        f"<tr>"
        f"<td><a href='https://www.tiktok.com/@{r.get("url","").split("/@")[1].split("/")[0] if "tiktok" in r.get("url","") else "#"}' target='_blank'>{r['artist_name']}</a></td>"
        f"<td>{r['platform'].title()}</td>"
        f"<td class='up'>{fmt(r['views'])}</td>"
        f"<td>{r.get('posted_date','')}</td>"
        f"<td><a href='{r['url']}' target='_blank'>{(r['description'] or '')[:50]}</a></td></tr>"
        for r in new_viral
    )
    nv_html = (f"<table><tr><th>Artist</th><th>Platform</th><th>Views</th><th>Posted</th><th>Video</th></tr>"
               f"{nv_rows}</table>") if nv_rows else ""

    # Momentum videos
    mv_rows = "".join(
        f"<tr>"
        f"<td>{r['artist_name']}</td>"
        f"<td>{r['platform'].title()}</td>"
        f"<td class='up'>+{fmt(r['gained'])}</td>"
        f"<td>{fmt(r['today_views'])}</td>"
        f"<td>{r.get('posted_date','')}</td>"
        f"<td><a href='{r['url']}' target='_blank'>{(r['description'] or '')[:50]}</a></td></tr>"
        for r in momentum
    )
    mv_html = (f"<table><tr><th>Artist</th><th>Platform</th><th>+Views DoD</th><th>Total Views</th><th>Posted</th><th>Video</th></tr>"
               f"{mv_rows}</table>") if mv_rows else ""

    # Sound spikes
    def sound_pct(r):
        delta = r.get("new_creates") or 0
        prev = r.get("prev_ugc") or r.get("now_ugc", 0) - delta
        if prev and prev > 0:
            p = (delta / prev) * 100
            return f"{p:+.1f}%"
        return "—"

    ss_rows = "".join(
        f"<tr><td>{r['artist_name']}</td>"
        f"<td>{r.get('sound_title') or r.get('music_id','')}</td>"
        f"<td class='{'up' if (r.get('new_creates') or 0) >= 0 else 'down'}'>"
        f"{'+' if (r.get('new_creates') or 0) >= 0 else ''}{fmt(r.get('new_creates',0))}/day</td>"
        f"<td>{sound_pct(r)}</td>"
        f"<td>{fmt(r['now_ugc'])} total</td></tr>"
        for r in sound_spikes
    )
    ss_html = (f"<table><tr><th>Artist</th><th>Sound</th><th>Daily Creates</th><th>DoD %</th><th>Total UGC</th></tr>"
               f"{ss_rows}</table>") if ss_rows else ""

    # Streaming spikes
    st_rows = "".join(
        f"<tr><td>{r['artist_name']}</td><td>{r['platform']}</td>"
        f"<td class='up'>+{r['pct']:.1f}%</td>"
        f"<td>{fmt(r['prev_s'])} → {fmt(r['now_s'])}</td></tr>"
        for r in streaming_spikes
    )
    st_html = (f"<table><tr><th>Artist</th><th>Platform</th><th>Growth (WoW)</th><th>Streams</th></tr>"
               f"{st_rows}</table>") if st_rows else ""

    # Snapshot table
    def tt_link(r):
        h = r.get("tt_handle")
        name = r.get("artist_name") or ""
        if h:
            return f"<a href='https://www.tiktok.com/@{h}' target='_blank'>{name}</a>"
        return name

    def ig_link(r):
        h = r.get("ig_handle")
        if h:
            return f"<a href='https://www.instagram.com/{h}' target='_blank'>@{h}</a>"
        return "—"

    # Snapshot — two independent tables side by side
    def _snap_table(rows, platform):
        if not rows:
            return "<p class='empty'>No artists gained 5,000+ followers today.</p>"
        if platform == 'tiktok':
            hdr = "<tr><th>Artist</th><th>TikTok Followers</th><th>+New</th><th>DoD %</th></tr>"
            trs = "".join(
                f"<tr>"
                f"<td><a href='https://www.tiktok.com/@{r.get('tt_handle','')}' target='_blank'>{r['artist_name']}</a></td>"
                f"<td>{fmt(r.get('tt_followers'))}</td>"
                f"<td class='up'>+{int(r.get('tt_gained') or 0):,}</td>"
                f"<td class='up'>+{r.get('tt_pct') or 0:.1f}%</td>"
                f"</tr>"
                for r in rows
            )
        else:
            hdr = "<tr><th>Artist</th><th>IG Followers</th><th>+New</th><th>DoD %</th></tr>"
            trs = "".join(
                f"<tr>"
                f"<td><a href='https://www.instagram.com/{r.get('ig_handle','')}/' target='_blank'>{r['artist_name']}</a></td>"
                f"<td>{fmt(r.get('ig_followers'))}</td>"
                f"<td class='up'>+{int(r.get('ig_gained') or 0):,}</td>"
                f"<td class='up'>+{r.get('ig_pct') or 0:.1f}%</td>"
                f"</tr>"
                for r in rows
            )
        return f"<table>{hdr}{trs}</table>"

    tt_snap = snapshot.get('tiktok', [])
    ig_snap = snapshot.get('instagram', [])
    snap_html = (
        f"<div style='display:flex;gap:32px;align-items:flex-start'>"
        f"<div style='flex:1'><h3 style='margin:0 0 6px;font-size:13px;color:#555'>TikTok</h3>{_snap_table(tt_snap, 'tiktok')}</div>"
        f"<div style='flex:1'><h3 style='margin:0 0 6px;font-size:13px;color:#555'>Instagram</h3>{_snap_table(ig_snap, 'instagram')}</div>"
        f"</div>"
    ) if (tt_snap or ig_snap) else ""

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Artist Report {TODAY}</title>
  <style>
    body  {{ font-family: Arial, sans-serif; max-width: 1000px; margin: 40px auto; color: #222; }}
    h1    {{ border-bottom: 3px solid #111; padding-bottom: 8px; }}
    h2    {{ color: #333; margin: 0 0 10px; }}
    .section {{ margin-bottom: 32px; }}
    .summary {{ background:#f0f0f0; padding:12px 20px; border-radius:6px; margin-bottom:28px; font-size:15px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 4px; font-size:13px; }}
    th    {{ background:#222; color:#fff; padding:7px 10px; text-align:left; }}
    td    {{ padding:6px 10px; border-bottom:1px solid #eee; }}
    tr:nth-child(even) {{ background:#fafafa; }}
    .up   {{ color: #1a7f1a; font-weight: bold; }}
    .empty {{ color:#999; font-style:italic; }}
    a     {{ color:#0066cc; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
  </style>
</head>
<body>
  <h1>Artist Tracking Report — {TODAY}</h1>
  <div class="summary">{total_flags} flag(s) across {len(snapshot)} artists tracked</div>
  {section("Follower Spikes &gt;3% Day-over-Day", fs_html, subtitle="Filters: &gt;3% DoD | +40 new followers min | max 3x (300%) growth | 10 follower baseline | same handle only")}
  {section("New Viral Videos (30K+ Views in First 48H)", nv_html)}
  {section("Momentum Videos (50K+ Views Day-over-Day)", mv_html)}
  {section("Sound UGC Spikes &gt;50 New Creates/Day", ss_html)}
  {section("Streaming Spikes &gt;10% Week-over-Week", st_html)}
  {section("Follower Movers — Full Roster Snapshot", snap_html, "No follower growth data available yet.")}
  <p style="color:#aaa;font-size:11px;margin-top:30px;">Generated {TODAY}</p>
</body>
</html>"""


def run():
    log.info("Generating report for %s", TODAY)

    follower_spikes   = get_follower_spikes()
    new_viral         = get_new_viral_videos()
    momentum          = get_momentum_videos()
    sound_spikes      = get_sound_spikes()
    streaming_spikes  = get_streaming_spikes()
    snapshot          = get_snapshot()

    txt  = render_txt(follower_spikes, new_viral, momentum, sound_spikes, streaming_spikes, snapshot)
    html = render_html(follower_spikes, new_viral, momentum, sound_spikes, streaming_spikes, snapshot)

    txt_path  = REPORTS_DIR / f"report_{TODAY}.txt"
    html_path = REPORTS_DIR / f"report_{TODAY}.html"
    txt_path.write_text(txt)
    html_path.write_text(html)

    log.info("Saved: %s, %s", txt_path.name, html_path.name)

    # Upload to Cloud Storage: dated copies (archive) + "latest" pointers (handoff)
    try:
        storage.upload_report(txt_path,  f"report_{TODAY}.txt")
        storage.upload_report(html_path, f"report_{TODAY}.html")
        storage.upload_report(txt_path,  "report_latest.txt")
        storage.upload_report(html_path, "report_latest.html")
    except Exception as e:
        log.error("Failed to upload report to Cloud Storage: %s", e)

    return txt_path, html_path


if __name__ == "__main__":
    t, h = run()
    print(f"Text : {t}")
    print(f"HTML : {h}")
