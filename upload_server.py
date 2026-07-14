#!/usr/bin/env python3
import os, sys, json, base64, subprocess
from datetime import date, datetime
from pathlib import Path
import requests
from flask import Flask, request, render_template_string
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / "config" / "config.env")
sys.path.insert(0, str(BASE_DIR / "scripts"))
import db
import logging

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "upload_server.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

UPLOAD_DIR = BASE_DIR / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_TOKEN = os.getenv("UPLOAD_TOKEN", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Artist Tracker — Data Upload</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 40px 20px; }
    .card { background: #fff; max-width: 660px; margin: 0 auto; border-radius: 8px;
            box-shadow: 0 2px 12px rgba(0,0,0,.1); padding: 40px; }
    h1 { margin: 0 0 20px; font-size: 22px; }
    .tabs { display: flex; gap: 0; margin-bottom: 30px; border-bottom: 2px solid #eee; }
    .tab { padding: 10px 22px; cursor: pointer; font-size: 14px; font-weight: 600;
           color: #888; border-bottom: 2px solid transparent; margin-bottom: -2px; }
    .tab.active { color: #111; border-bottom-color: #111; }
    .tab-content { display: none; }
    .tab-content.active { display: block; }
    .sub { color: #666; margin: 0 0 24px; font-size: 14px; }
    .drop { border: 2px dashed #ccc; border-radius: 6px; padding: 36px 20px;
            text-align: center; cursor: pointer; transition: border-color .2s; background: #fafafa; }
    .drop:hover, .drop.over { border-color: #333; background: #f0f0f0; }
    .drop input { display: none; }
    .drop label { cursor: pointer; display: block; }
    .drop .icon { font-size: 36px; margin-bottom: 8px; }
    .drop .hint { color: #999; font-size: 13px; margin-top: 6px; }
    .filelist { margin-top: 12px; font-size: 13px; color: #333; min-height: 18px; }
    input[type=password] { width: 100%; padding: 10px; border: 1px solid #ddd;
                            border-radius: 4px; font-size: 14px; margin: 12px 0; }
    button { background: #111; color: #fff; border: none; padding: 12px 28px;
             border-radius: 4px; font-size: 15px; cursor: pointer; width: 100%; margin-top: 10px; }
    button:hover { background: #333; }
    button:disabled { background: #999; cursor: not-allowed; }
    .msg { padding: 14px 18px; border-radius: 5px; margin-bottom: 20px; font-size: 14px; }
    .ok  { background: #e8f5e9; color: #1b5e20; border-left: 4px solid #4caf50; }
    .err { background: #ffebee; color: #b71c1c; border-left: 4px solid #f44336; }
    .warn { background: #fff8e1; color: #5d4037; border-left: 4px solid #ffc107; }
    .log { background: #f5f5f5; border-radius: 4px; padding: 12px; font-family: monospace;
           font-size: 12px; white-space: pre-wrap; max-height: 240px; overflow-y: auto;
           margin-top: 12px; color: #333; }
    .preview-table { width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 13px; }
    .preview-table th { background: #f0f0f0; padding: 8px 10px; text-align: left;
                         border-bottom: 2px solid #ddd; font-weight: 600; }
    .preview-table td { padding: 7px 10px; border-bottom: 1px solid #eee; }
    .preview-table tr:last-child td { border-bottom: none; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px;
             font-weight: 600; background: #e3f2fd; color: #1565c0; }
    .badge.neg { background: #fce4ec; color: #880e4f; }
    .spinner { display: none; text-align: center; padding: 20px; color: #666; font-size: 14px; }
    .spinner.show { display: block; }
  </style>
</head>
<body>
<div class="card">
  <h1>&#127925; Artist Tracker &#8212; Data Upload</h1>
  <div class="tabs">
    <div class="tab {% if active_tab == 'luminate' %}active{% endif %}" onclick="switchTab('luminate', event)">&#128202; Luminate CSV</div>
    <div class="tab {% if active_tab == 'cobrand' %}active{% endif %}" onclick="switchTab('cobrand', event)">&#127925; Cobrand Sounds</div>
  </div>

  <div class="tab-content {% if active_tab == 'luminate' %}active{% endif %}" id="tab-luminate">
    <p class="sub">Upload a Luminate CSV export &#8212; streaming data loads automatically.</p>
    {% if luminate_msg %}
    <div class="msg {{ luminate_msg_class }}">{{ luminate_msg }}</div>
    {% if luminate_log %}<div class="log">{{ luminate_log }}</div>{% endif %}
    {% endif %}
    <form method="POST" action="/upload" enctype="multipart/form-data">
      <div class="drop" id="drop-luminate">
        <label for="lum-file">
          <div class="icon">&#128196;</div>
          <strong>Click to choose a CSV file</strong><br>
          <span class="hint">or drag and drop here</span>
        </label>
        <input type="file" name="file" id="lum-file" accept=".csv,.tsv,.txt">
      </div>
      <div class="filelist" id="fname-luminate"></div>
      {% if token_required %}<input type="password" name="token" placeholder="Upload token" required>{% endif %}
      <button type="submit">Upload &amp; Import</button>
    </form>
  </div>

  <div class="tab-content {% if active_tab == 'cobrand' %}active{% endif %}" id="tab-cobrand">
    <p class="sub">Upload screenshots from your Cobrand Discovery segment. Claude reads the sound data and saves it to the tracker. Select multiple screenshots at once to cover the full list.</p>
    {% if cobrand_msg %}
    <div class="msg {{ cobrand_msg_class }}">{{ cobrand_msg }}</div>
    {% endif %}
    {% if cobrand_rows %}
    <table class="preview-table">
      <thead><tr><th>Sound</th><th>Artist</th><th>Total Creates</th><th>Creates (24h)</th></tr></thead>
      <tbody>
      {% for r in cobrand_rows %}
      <tr>
        <td>{{ r.sound_title }}</td>
        <td>{{ r.artist_name }}</td>
        <td>{{ "{:,}".format(r.ugc_count) }}</td>
        <td><span class="badge {% if r.ugc_delta_24h < 0 %}neg{% endif %}">{{ "+" if r.ugc_delta_24h >= 0 else "" }}{{ "{:,}".format(r.ugc_delta_24h) }}</span></td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
    {% endif %}
    {% if not anthropic_key_set %}
    <div class="msg warn">&#9888; ANTHROPIC_API_KEY not set in config.env &#8212; screenshot parsing unavailable.</div>
    {% else %}
    <form method="POST" action="/cobrand" enctype="multipart/form-data" id="cobrand-form">
      <div class="drop" id="drop-cobrand">
        <label for="screenshots">
          <div class="icon">&#128247;</div>
          <strong>Click to choose screenshots</strong><br>
          <span class="hint">PNG or JPG &#8212; select multiple to cover full list</span>
        </label>
        <input type="file" name="screenshots" id="screenshots" accept=".png,.jpg,.jpeg" multiple>
      </div>
      <div class="filelist" id="fname-cobrand"></div>
      {% if token_required %}<input type="password" name="token" placeholder="Upload token" required>{% endif %}
      <button type="submit" id="cobrand-btn">Parse &amp; Import</button>
    </form>
    <div class="spinner" id="cobrand-spinner">&#9203; Sending to Claude for extraction&#8230; this may take 15&#8211;30 seconds per screenshot.</div>
    {% endif %}
  </div>
</div>
<script>
function switchTab(name, event) {
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(t => t.classList.remove("active"));
  document.getElementById("tab-" + name).classList.add("active");
  event.target.classList.add("active");
}
var lf = document.getElementById("lum-file");
if (lf) lf.addEventListener("change", function() {
  document.getElementById("fname-luminate").textContent = this.files[0] ? "\u1F4CE " + this.files[0].name : "";
});
var ss = document.getElementById("screenshots");
if (ss) ss.addEventListener("change", function() {
  var names = Array.from(this.files).map(function(f){return f.name;}).join(", ");
  document.getElementById("fname-cobrand").textContent = names ? "\u1F4CE " + names : "";
});
var cf = document.getElementById("cobrand-form");
if (cf) cf.addEventListener("submit", function() {
  document.getElementById("cobrand-btn").disabled = true;
  document.getElementById("cobrand-btn").textContent = "Processing\u2026";
  document.getElementById("cobrand-spinner").classList.add("show");
});
["luminate","cobrand"].forEach(function(zone) {
  var drop = document.getElementById("drop-" + zone);
  if (!drop) return;
  ["dragenter","dragover"].forEach(function(e) {
    drop.addEventListener(e, function(ev) { ev.preventDefault(); drop.classList.add("over"); });
  });
  ["dragleave","drop"].forEach(function(e) {
    drop.addEventListener(e, function(ev) { drop.classList.remove("over"); });
  });
  drop.addEventListener("drop", function(ev) {
    ev.preventDefault();
    var input = drop.querySelector("input[type=file]");
    var fnameEl = document.getElementById("fname-" + zone);
    if (input && ev.dataTransfer.files.length) {
      input.files = ev.dataTransfer.files;
      var names = Array.from(ev.dataTransfer.files).map(function(f){return f.name;}).join(", ");
      if (fnameEl) fnameEl.textContent = "\u1F4CE " + names;
    }
  });
});
</script>
</body>
</html>"""


def parse_cobrand_screenshots(image_paths):
    all_rows = []
    errors = []
    for img_path in image_paths:
        try:
            with open(img_path, "rb") as f:
                img_data = base64.standard_b64encode(f.read()).decode("utf-8")
            suffix = Path(img_path).suffix.lower()
            media_type = "image/png" if suffix == ".png" else "image/jpeg"
            prompt = (
                "This is a screenshot from Cobrand's Discovery segment showing TikTok sounds. "
                "Extract every visible row from the sounds table. For each row return a JSON array of objects with keys: "
                "sound_title (string), artist_name (string), ugc_count (integer, no commas), ugc_delta_24h (integer, negative if shown as negative). "
                "Return ONLY a valid JSON array, no markdown, no explanation. "
                "Example: [{\"sound_title\": \"Save My Soul\", \"artist_name\": \"Noah Rinker\", \"ugc_count\": 897973, \"ugc_delta_24h\": 1214}] "
                "If you cannot read the table clearly, return []."
            )
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={"model": "claude-sonnet-4-6", "max_tokens": 2000, "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_data}},
                    {"type": "text", "text": prompt}
                ]}]},
                timeout=60
            )
            if resp.status_code != 200:
                errors.append(f"{Path(img_path).name}: API error {resp.status_code}")
                continue
            raw = resp.json()["content"][0]["text"].strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            rows = json.loads(raw)
            all_rows.extend(rows)
        except json.JSONDecodeError:
            errors.append(f"{Path(img_path).name}: Could not parse Claude response as JSON")
        except Exception as e:
            errors.append(f"{Path(img_path).name}: {e}")
    seen = set()
    deduped = []
    for r in all_rows:
        key = (r.get("sound_title","").lower(), r.get("artist_name","").lower())
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    return deduped, "; ".join(errors)


def save_cobrand_rows(rows):
    today = str(date.today())
    saved = 0
    with db.get_conn() as conn:
        for r in rows:
            try:
                music_id = r.get("sound_title", "").lower().replace(" ", "_")[:80]
                db.upsert_sound_cobrand(conn, {
                    "artist_name": r.get("artist_name", "Unknown"),
                    "music_id": music_id,
                    "date": today,
                    "ugc_count": int(r.get("ugc_count", 0)),
                    "sound_title": r.get("sound_title", ""),
                    "ugc_delta_24h": int(r.get("ugc_delta_24h", 0)),
                })
                saved += 1
            except Exception as e:
                log.warning(
                    "Failed to save cobrand row for %s (%s): %s",
                    r.get("artist_name", "Unknown"),
                    r.get("sound_title", ""),
                    e,
                )
    return saved


def _render(active_tab="luminate", luminate_msg=None, luminate_log=None, luminate_msg_class=None,
            cobrand_msg=None, cobrand_msg_class=None, cobrand_rows=None):
    return render_template_string(HTML,
        active_tab=active_tab,
        luminate_msg=luminate_msg, luminate_log=luminate_log, luminate_msg_class=luminate_msg_class,
        cobrand_msg=cobrand_msg, cobrand_msg_class=cobrand_msg_class, cobrand_rows=cobrand_rows,
        token_required=bool(UPLOAD_TOKEN), anthropic_key_set=bool(ANTHROPIC_KEY))


@app.route("/")
def index():
    return _render()


@app.route("/upload", methods=["POST"])
def upload():
    if UPLOAD_TOKEN and request.form.get("token","") != UPLOAD_TOKEN:
        return _render("luminate", luminate_msg="Invalid token.", luminate_msg_class="err")
    f = request.files.get("file")
    if not f or not f.filename:
        return _render("luminate", luminate_msg="No file selected.", luminate_msg_class="err")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = UPLOAD_DIR / f"luminate_{timestamp}.csv"
    f.save(save_path)
    result = subprocess.run(
        ["python3", str(BASE_DIR / "scripts" / "load_streaming_csv.py"), str(save_path)],
        capture_output=True, text=True, timeout=60
    )
    output = (result.stdout + result.stderr).strip()
    ok = result.returncode == 0
    return _render("luminate",
        luminate_msg=f"\u2713 Imported from {f.filename}" if ok else "Import ran with errors.",
        luminate_msg_class="ok" if ok else "err",
        luminate_log=output)


@app.route("/cobrand", methods=["POST"])
def cobrand():
    if UPLOAD_TOKEN and request.form.get("token","") != UPLOAD_TOKEN:
        return _render("cobrand", cobrand_msg="Invalid token.", cobrand_msg_class="err")
    if not ANTHROPIC_KEY:
        return _render("cobrand", cobrand_msg="ANTHROPIC_API_KEY not configured.", cobrand_msg_class="err")
    files = request.files.getlist("screenshots")
    if not files or not files[0].filename:
        return _render("cobrand", cobrand_msg="No screenshots uploaded.", cobrand_msg_class="err")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_paths = []
    for i, f in enumerate(files):
        if f.filename:
            suffix = Path(f.filename).suffix.lower() or ".png"
            path = UPLOAD_DIR / f"cobrand_{timestamp}_{i}{suffix}"
            f.save(path)
            saved_paths.append(str(path))
    rows, errors = parse_cobrand_screenshots(saved_paths)
    if not rows:
        msg = f"No sound data extracted from {len(saved_paths)} screenshot(s)."
        if errors: msg += f" {errors}"
        return _render("cobrand", cobrand_msg=msg, cobrand_msg_class="err")
    n_saved = save_cobrand_rows(rows)
    msg = f"\u2713 Extracted {len(rows)} sounds from {len(saved_paths)} screenshot(s) \u2014 {n_saved} rows saved."
    if errors: msg += f" Warnings: {errors}"

    class Row:
        pass
    row_objs = []
    for r in rows:
        obj = Row()
        obj.sound_title = r.get("sound_title","")
        obj.artist_name = r.get("artist_name","")
        obj.ugc_count = int(r.get("ugc_count",0))
        obj.ugc_delta_24h = int(r.get("ugc_delta_24h",0))
        row_objs.append(obj)
    return _render("cobrand", cobrand_msg=msg, cobrand_msg_class="ok", cobrand_rows=row_objs)


if __name__ == "__main__":
    print("Upload server running at http://89.167.11.114:8765/")
    app.run(host="0.0.0.0", port=8765, debug=False)
