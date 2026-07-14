#!/usr/bin/env python3
"""Weekend Deep Dive report — full week-over-week breakdown per artist.

Covers:
  - TikTok: followers, likes, video count (DoD and WoW)
  - Instagram: followers, reels, post count (DoD and WoW)
  - Top videos/reels over 30K views this week
  - Sound UGC: total creates and weekly change
  - Streaming: weekly streams and WoW change (where data exists)

Saves to reports/deepdive_YYYY-MM-DD.html + .txt
"""

import os
import sys
import logging
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "config" / "config.env")
sys.path.insert(0, str(Path(__file__).parent))
import db

REPORTS_DIR = BASE_DIR / "reports"
LOG_DIR     = BASE_DIR / "logs"
REPORTS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "generate_deepdive.log"), logging.StreamHandler()],
)
log = logging.getLogger(__name__)

TODAY    = str(date.today())
WEEK_AGO = str(date.today() - timedelta(days=7))
TWO_WEEKS_AGO = str(date.today() - timedelta(days=14))


def fmt(n) -> str:
    try:
        v = int(n)
        return f"{v:,}"
    except Exception:
        return "—"


def delta(old, new, show_pct=True) -> str:
    try:
        old, new = int(old or 0), int(new or 0)
        diff = new - old
        sign = "+" if diff >= 0 else ""
        if not old:
            return f"{sign}{fmt(diff)}"
        pct = (diff / old) * 100
        if show_pct:
            return f"{sign}{fmt(diff)} ({sign}{pct:.1f}%)"
        return f"{sign}{fmt(diff)}"
    except Exception:
        return "—"


def get_all_artists():
    rows = db.query("""
        SELECT DISTINCT artist_name FROM social_metrics
        ORDER BY artist_name
    """)
    return [r["artist_name"] for r in rows]


def get_social(artist, platform, day):
    rows = db.query("""
        SELECT * FROM social_metrics
        WHERE artist_name=%s AND platform=%s AND date=%s
    """, (artist, platform, day))
    return rows[0] if rows else {}


def get_top_videos(artist, days=7):
    since = str(date.today() - timedelta(days=days))
    return db.query("""
        SELECT platform, views, likes, description, url, posted_date
        FROM video_metrics
        WHERE artist_name=%s AND date_collected >= %s AND views >= 30000
        ORDER BY views DESC
        LIMIT 10
    """, (artist, since))


def get_sound(artist, day):
    rows = db.query("""
        SELECT ugc_count, total_plays FROM sound_metrics
        WHERE artist_name=%s AND date=%s
        ORDER BY ugc_count DESC LIMIT 1
    """, (artist, day))
    return rows[0] if rows else {}


def get_streaming(artist, day):
    rows = db.query("""
        SELECT SUM(streams) as total FROM streaming_metrics
        WHERE artist_name=%s AND date=%s
    """, (artist, day))
    return rows[0] if rows else {}


def build_artist_block(artist: str) -> dict:
    tt_now  = get_social(artist, "tiktok",    TODAY)
    tt_week = get_social(artist, "tiktok",    WEEK_AGO)
    ig_now  = get_social(artist, "instagram", TODAY)
    ig_week = get_social(artist, "instagram", WEEK_AGO)
    snd_now  = get_sound(artist, TODAY)
    snd_week = get_sound(artist, WEEK_AGO)
    str_now  = get_streaming(artist, TODAY)
    str_week = get_streaming(artist, WEEK_AGO)
    videos   = get_top_videos(artist)

    return {
        "name":     artist,
        "tt_now":   tt_now,
        "tt_week":  tt_week,
        "ig_now":   ig_now,
        "ig_week":  ig_week,
        "snd_now":  snd_now,
        "snd_week": snd_week,
        "str_now":  str_now,
        "str_week": str_week,
        "videos":   videos,
    }


def has_data(b) -> bool:
    return bool(b["tt_now"] or b["ig_now"])


def render_html(blocks: list[dict]) -> str:
    artist_sections = ""
    for b in blocks:
        if not has_data(b):
            continue

        tt  = b["tt_now"]
        tt0 = b["tt_week"]
        ig  = b["ig_now"]
        ig0 = b["ig_week"]
        snd  = b["snd_now"]
        snd0 = b["snd_week"]
        st   = b["str_now"]
        st0  = b["str_week"]

        # Social rows
        def row(label, now_val, old_val, show_pct=True):
            d = delta(old_val, now_val, show_pct)
            cls = "up" if now_val and old_val and int(now_val or 0) > int(old_val or 0) else ""
            return (f"<tr><td>{label}</td><td>{fmt(now_val)}</td>"
                    f"<td class='{cls}'>{d}</td></tr>")

        tt_rows = ""
        if tt:
            tt_rows = (row("Followers", tt.get("followers"), tt0.get("followers")) +
                       row("Total Likes", tt.get("likes"), tt0.get("likes")) +
                       row("Videos Posted", tt.get("video_count"), tt0.get("video_count"), False))

        ig_rows = ""
        if ig:
            ig_rows = (row("Followers", ig.get("followers"), ig0.get("followers")) +
                       row("Reels", ig.get("reel_count"), ig0.get("reel_count"), False) +
                       row("Posts", ig.get("post_count"), ig0.get("post_count"), False))

        snd_rows = ""
        if snd:
            snd_rows = (row("UGC Creates", snd.get("ugc_count"), snd0.get("ugc_count")) +
                        row("Total Plays", snd.get("total_plays"), snd0.get("total_plays")))

        str_rows = ""
        if st.get("total"):
            str_rows = row("Streams", st.get("total"), st0.get("total"))

        # Top videos
        vid_rows = ""
        for v in b["videos"]:
            snippet = (v.get("description") or "")[:55].replace("\n", " ")
            vid_rows += (f"<tr><td>{v['platform'].title()}</td>"
                         f"<td>{fmt(v['views'])}</td>"
                         f"<td>{fmt(v['likes'])}</td>"
                         f"<td><a href='{v.get('url','')}' target='_blank'>{snippet or '—'}</a></td></tr>")

        video_section = ""
        if vid_rows:
            video_section = f"""
            <h4>Videos Over 30K Views This Week</h4>
            <table>
              <tr><th>Platform</th><th>Views</th><th>Likes</th><th>Video</th></tr>
              {vid_rows}
            </table>"""

        handle_tt = f"@{tt.get('handle','')}" if tt.get('handle') else ""
        handle_ig = f"@{ig.get('handle','')}" if ig.get('handle') else ""

        artist_sections += f"""
        <div class="artist">
          <div class="artist-header">
            <span class="artist-name">{b['name']}</span>
            <span class="handles">{handle_tt}{'  ·  ' + handle_ig if handle_ig else ''}</span>
          </div>
          <div class="platforms">
            {'<div class="platform"><h4>TikTok</h4><table><tr><th>Metric</th><th>Current</th><th>WoW</th></tr>' + tt_rows + '</table></div>' if tt_rows else ''}
            {'<div class="platform"><h4>Instagram</h4><table><tr><th>Metric</th><th>Current</th><th>WoW</th></tr>' + ig_rows + '</table></div>' if ig_rows else ''}
            {'<div class="platform"><h4>Sound UGC</h4><table><tr><th>Metric</th><th>Current</th><th>WoW</th></tr>' + snd_rows + '</table></div>' if snd_rows else ''}
            {'<div class="platform"><h4>Streaming</h4><table><tr><th>Metric</th><th>Current</th><th>WoW</th></tr>' + str_rows + '</table></div>' if str_rows else ''}
          </div>
          {video_section}
        </div>"""

    artist_count = sum(1 for b in blocks if has_data(b))

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Deep Dive — {TODAY}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: Arial, sans-serif; max-width: 1100px; margin: 40px auto;
            color: #222; background: #f5f5f5; padding: 0 20px; }}
    h1 {{ border-bottom: 3px solid #111; padding-bottom: 10px; }}
    .summary {{ background:#fff; padding: 14px 20px; border-radius:6px;
                margin-bottom: 28px; font-size:14px; color:#555;
                box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
    .artist {{ background: #fff; border-radius: 8px; margin-bottom: 24px;
               padding: 20px 24px; box-shadow: 0 1px 6px rgba(0,0,0,.08); }}
    .artist-header {{ display:flex; align-items:baseline; gap:14px; margin-bottom:14px;
                      border-bottom:1px solid #eee; padding-bottom:10px; }}
    .artist-name {{ font-size:18px; font-weight:bold; }}
    .handles {{ font-size:13px; color:#999; }}
    .platforms {{ display:flex; flex-wrap:wrap; gap:16px; }}
    .platform {{ flex:1; min-width:200px; }}
    h4 {{ margin: 0 0 8px; font-size:13px; text-transform:uppercase;
          letter-spacing:.05em; color:#555; }}
    table {{ border-collapse:collapse; width:100%; font-size:13px; }}
    th {{ background:#f0f0f0; padding:5px 8px; text-align:left;
          font-weight:600; color:#444; }}
    td {{ padding:5px 8px; border-bottom:1px solid #f5f5f5; }}
    .up {{ color:#1a7f1a; font-weight:600; }}
    a {{ color:#0066cc; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    @media(max-width:600px) {{ .platforms {{ flex-direction:column; }} }}
  </style>
</head>
<body>
  <h1>Weekly Deep Dive — {TODAY}</h1>
  <div class="summary">
    {artist_count} artists tracked &nbsp;·&nbsp;
    Week of {WEEK_AGO} → {TODAY}
  </div>
  {artist_sections}
</body>
</html>"""


def render_txt(blocks: list[dict]) -> str:
    lines = [f"Weekly Deep Dive — {TODAY}", "=" * 60,
             f"Week of {WEEK_AGO} → {TODAY}", ""]

    for b in blocks:
        if not has_data(b):
            continue
        lines.append(f"  {b['name']}")
        lines.append("  " + "-" * 36)

        tt, tt0 = b["tt_now"], b["tt_week"]
        ig, ig0 = b["ig_now"], b["ig_week"]

        if tt:
            lines.append(f"  TikTok")
            lines.append(f"    Followers : {fmt(tt.get('followers'))}   WoW: {delta(tt0.get('followers'), tt.get('followers'))}")
            lines.append(f"    Likes     : {fmt(tt.get('likes'))}   WoW: {delta(tt0.get('likes'), tt.get('likes'))}")
        if ig:
            lines.append(f"  Instagram")
            lines.append(f"    Followers : {fmt(ig.get('followers'))}   WoW: {delta(ig0.get('followers'), ig.get('followers'))}")
        if b["snd_now"].get("ugc_count"):
            snd, snd0 = b["snd_now"], b["snd_week"]
            lines.append(f"  Sound UGC : {fmt(snd.get('ugc_count'))}   WoW: {delta(snd0.get('ugc_count'), snd.get('ugc_count'))}")
        if b["str_now"].get("total"):
            lines.append(f"  Streaming : {fmt(b['str_now'].get('total'))}   WoW: {delta(b['str_week'].get('total'), b['str_now'].get('total'))}")
        if b["videos"]:
            lines.append(f"  Hot Videos (30K+):")
            for v in b["videos"]:
                lines.append(f"    {v['platform'].title()} {fmt(v['views'])} views — {v.get('url','')}")
        lines.append("")

    return "\n".join(lines)


def run():
    log.info("Generating Deep Dive for %s", TODAY)
    artists = get_all_artists()
    blocks  = [build_artist_block(a) for a in artists]

    txt  = render_txt(blocks)
    html = render_html(blocks)

    txt_path  = REPORTS_DIR / f"deepdive_{TODAY}.txt"
    html_path = REPORTS_DIR / f"deepdive_{TODAY}.html"
    txt_path.write_text(txt)
    html_path.write_text(html)
    log.info("Saved: %s, %s", txt_path.name, html_path.name)
    return txt_path, html_path


if __name__ == "__main__":
    t, h = run()
    print(f"Text : {t}")
    print(f"HTML : {h}")
