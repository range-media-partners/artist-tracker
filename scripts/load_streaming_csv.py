#!/usr/bin/env python3
"""Load streaming data from a Luminate/DSP CSV export into SQLite.

Expected columns (flexible matching):
  artist_name / artist / name
  streams / stream_count / plays / listeners
  date / report_date / period / week
  platform / service / dsp
"""

import sys
import csv
import re
import logging
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "config" / "config.env")
sys.path.insert(0, str(Path(__file__).parent))
import db

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "load_streaming.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

COLUMN_MAP = {
    "artist_name": "artist_name", "artist": "artist_name", "name": "artist_name",
    "streams": "streams", "stream_count": "streams", "plays": "streams",
    "listeners": "streams", "on_demand_streams": "streams",
    "date": "date", "report_date": "date", "period": "date",
    "week": "date", "week_of": "date",
    "platform": "platform", "service": "platform", "dsp": "platform",
    "distributor": "platform",
}


def normalize_headers(headers):
    return {h: COLUMN_MAP[h.strip().lower().replace(" ", "_")]
            for h in headers
            if h.strip().lower().replace(" ", "_") in COLUMN_MAP}


def parse_date(raw: str) -> str:
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d",
                "%B %d, %Y", "%b %d, %Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return raw


def load_csv(path: str) -> int:
    path = Path(path)
    if not path.exists():
        log.error("File not found: %s", path)
        return 0

    saved = 0

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            log.error("CSV has no headers")
            return 0

        col_map = normalize_headers(reader.fieldnames)
        log.info("Detected columns: %s", list(col_map.values()))

        with db.get_conn() as conn:
            for i, row in enumerate(reader):
                normalized = {col_map[k]: v.strip() for k, v in row.items() if k in col_map}
                artist_name = normalized.get("artist_name", "").strip()
                if not artist_name:
                    continue
                streams_raw = re.sub(r"[,\s]", "", normalized.get("streams", "0") or "0")
                row_data = {
                    "artist_name": artist_name,
                    "platform": normalized.get("platform", "luminate"),
                    "date": parse_date(normalized.get("date", "")),
                    "streams": int(streams_raw) if streams_raw.isdigit() else 0,
                    "source_file": path.name,
                }
                db.upsert_streaming(conn, row_data)
                saved += 1

    log.info("Loaded %d records from %s", saved, path.name)
    return saved


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: load_streaming_csv.py <path_to_csv>")
        sys.exit(1)
    count = load_csv(sys.argv[1])
    print(f"Loaded {count} records.")
