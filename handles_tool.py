#!/usr/bin/env python3
import os, requests
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / "config" / "config.env")

AIRTABLE_KEY  = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE = os.getenv("AIRTABLE_BASE_ID")
TABLE_ID      = "tblQVgffrMKG3VWAD"
UPLOAD_TOKEN = ''

app = Flask(__name__)

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>A&R Research — Handle Lookup</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
:root{--bg:#0e0e0f;--surface:#18181b;--border:#2a2a2e;--accent:#c8f135;--accent2:#7c6af7;--text:#f0f0ef;--muted:#666670;--ok:#3ecf8e;--err:#f97066;--warn:#fbbf24}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'DM Mono',monospace;min-height:100vh}
header{border-bottom:1px solid var(--border);padding:20px 40px;display:flex;align-items:center;justify-content:space-between}
header h1{font-family:'Syne',sans-serif;font-weight:800;font-size:20px}
header h1 span{color:var(--accent)}
.stats{display:flex;gap:24px;font-size:12px;color:var(--muted)}
.stats b{color:var(--text)}
.filters{padding:16px 40px;display:flex;gap:10px;align-items:center;border-bottom:1px solid var(--border)}
.filter-btn{background:var(--surface);border:1px solid var(--border);color:var(--muted);padding:5px 14px;border-radius:4px;cursor:pointer;font-family:'DM Mono',monospace;font-size:12px;transition:all .15s}
.filter-btn:hover,.filter-btn.active{border-color:var(--accent);color:var(--accent)}
.search{background:var(--surface);border:1px solid var(--border);color:var(--text);padding:5px 14px;border-radius:4px;font-family:'DM Mono',monospace;font-size:12px;width:200px;outline:none;margin-left:auto}
.search:focus{border-color:var(--accent2)}
.progress-bar{height:3px;background:var(--border)}
.progress-fill{height:100%;background:var(--accent);transition:width .4s}
table{width:100%;border-collapse:collapse}
thead th{padding:10px 16px;text-align:left;font-size:11px;color:var(--muted);font-weight:500;letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--bg)}
tbody tr{border-bottom:1px solid var(--border);transition:background .1s}
tbody tr:hover{background:var(--surface)}
tbody tr.done{opacity:.35}
td{padding:9px 16px;font-size:13px;vertical-align:middle}
td.name{font-weight:500;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.badge{display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:500;letter-spacing:.05em}
.badge-tt{background:#1a1a2e;color:#69c9d0;border:1px solid #69c9d020}
.badge-ig{background:#1a1220;color:#e1306c;border:1px solid #e1306c20}
.badge-both{background:#1a1500;color:var(--warn);border:1px solid #fbbf2420}
.url-input{background:transparent;border:none;border-bottom:1px solid var(--border);color:var(--text);font-family:'DM Mono',monospace;font-size:12px;padding:4px 0;width:100%;outline:none;transition:border-color .15s}
.url-input:focus{border-color:var(--accent2)}
.url-input.filled{border-color:var(--ok);color:var(--ok)}
.url-input::placeholder{color:var(--muted)}
.save-btn{background:var(--accent);color:#0e0e0f;border:none;padding:5px 14px;border-radius:3px;font-family:'DM Mono',monospace;font-size:11px;font-weight:500;cursor:pointer;transition:opacity .15s;white-space:nowrap}
.save-btn:hover{opacity:.85}
.save-btn:disabled{background:var(--border);color:var(--muted);cursor:not-allowed}
.empty{padding:60px;text-align:center;color:var(--muted);font-size:14px}
.gate{max-width:360px;margin:120px auto;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:40px}
.gate h2{font-family:'Syne',sans-serif;font-size:18px;margin-bottom:20px}
.gate input{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);padding:10px 14px;border-radius:4px;font-family:'DM Mono',monospace;font-size:13px;outline:none;margin-bottom:12px}
.gate button{width:100%;background:var(--accent);color:#0e0e0f;border:none;padding:10px;border-radius:4px;font-family:'DM Mono',monospace;font-size:13px;font-weight:500;cursor:pointer}
.toast{position:fixed;bottom:24px;right:24px;background:var(--surface);border:1px solid var(--border);padding:12px 20px;border-radius:6px;font-size:13px;transform:translateY(80px);opacity:0;transition:all .25s;z-index:100}
.toast.show{transform:translateY(0);opacity:1}
.toast.ok{border-color:var(--ok);color:var(--ok)}
.toast.err{border-color:var(--err);color:var(--err)}
</style>
</head>
<body>
<div id="main">
  <header>
    <h1>A&R Research <span>/ Handle Lookup</span></h1>
    <div class="stats">
      <span>Total: <b id="s-total">—</b></span>
      <span>Done: <b id="s-done">0</b></span>
      <span>Left: <b id="s-left">—</b></span>
    </div>
  </header>
  <div class="progress-bar"><div class="progress-fill" id="prog" style="width:0%"></div></div>
  <div class="filters">
    <button class="filter-btn active" onclick="setF('all',this)">All</button>
    <button class="filter-btn" onclick="setF('both',this)">Missing Both</button>
    <button class="filter-btn" onclick="setF('tiktok',this)">Missing TikTok</button>
    <button class="filter-btn" onclick="setF('instagram',this)">Missing Instagram</button>
    <input class="search" id="srch" placeholder="Search artist..." oninput="render()">
  </div>
  <table>
    <thead><tr>
      <th style="width:190px">Artist</th>
      <th style="width:90px">Missing</th>
      <th>TikTok URL</th>
      <th>Instagram URL</th>
      <th style="width:80px"></th>
    </tr></thead>
    <tbody id="tbody"></tbody>
  </table>
  <div id="empty" class="empty" style="display:none">No artists match.</div>
</div>
<div class="toast" id="toast"></div>
<script>
let artists=[],filter='all',token='';
window.addEventListener('load',auth);
function auth(){
  fetch('/api/artists',{headers:{'X-Token':''}})
    .then(r=>{if(r.status===401)throw new Error();return r.json();})
    .then(d=>{artists=d;stats();render();})
    .catch(e=>console.error(e));
}

function setF(f,btn){filter=f;document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');render();}
function stats(){
  const total=artists.length,done=artists.filter(a=>a.saved).length;
  document.getElementById('s-total').textContent=total;
  document.getElementById('s-done').textContent=done;
  document.getElementById('s-left').textContent=total-done;
  document.getElementById('prog').style.width=total?(done/total*100)+'%':'0%';
}
function render(){
  const q=document.getElementById('srch').value.toLowerCase();
  const filtered=artists.filter(a=>{
    if(q&&!a.name.toLowerCase().includes(q))return false;
    if(filter==='both')return !a.tiktok&&!a.instagram;
    if(filter==='tiktok')return !a.tiktok&&a.instagram;
    if(filter==='instagram')return a.tiktok&&!a.instagram;
    return true;
  });
  document.getElementById('empty').style.display=filtered.length?'none':'block';
  document.getElementById('tbody').innerHTML=filtered.map(a=>{
    const m=!a.tiktok&&!a.instagram?'both':!a.tiktok?'tiktok':'instagram';
    const bc=m==='both'?'badge-both':m==='tiktok'?'badge-tt':'badge-ig';
    const bt=m==='both'?'BOTH':m==='tiktok'?'TIKTOK':'INSTAGRAM';
    const tv=a.pending_tt||a.tiktok||'',iv=a.pending_ig||a.instagram||'';
    return `<tr class="${a.saved?'done':''}" id="row-${a.id}">
      <td class="name" title="${a.name}">${a.name}</td>
      <td><span class="badge ${bc}">${bt}</span></td>
      <td><input class="url-input ${tv?'filled':''}" id="tt-${a.id}" value="${tv}" placeholder="https://tiktok.com/@handle" oninput="pend('${a.id}','tt',this.value)"></td>
      <td><input class="url-input ${iv?'filled':''}" id="ig-${a.id}" value="${iv}" placeholder="https://instagram.com/handle" oninput="pend('${a.id}','ig',this.value)"></td>
      <td><button class="save-btn" id="btn-${a.id}" onclick="save('${a.id}')">${a.saved?'✓ Saved':'Save'}</button></td>
    </tr>`;
  }).join('');
}
function pend(id,f,v){const a=artists.find(x=>x.id===id);if(!a)return;if(f==='tt')a.pending_tt=v;else a.pending_ig=v;const el=document.getElementById((f==='tt'?'tt-':'ig-')+id);if(el)el.classList.toggle('filled',!!v);}
function save(id){
  const a=artists.find(x=>x.id===id);if(!a)return;
  const tt=document.getElementById('tt-'+id)?.value.trim();
  const ig=document.getElementById('ig-'+id)?.value.trim();
  const btn=document.getElementById('btn-'+id);
  btn.disabled=true;btn.textContent='...';
  fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json','X-Token':token},body:JSON.stringify({id,tiktok:tt,instagram:ig})})
    .then(r=>r.json())
    .then(d=>{
      if(d.ok){a.tiktok=tt||a.tiktok;a.instagram=ig||a.instagram;a.saved=true;btn.textContent='✓ Saved';document.getElementById('row-'+id)?.classList.add('done');stats();toast(a.name+' saved','ok');}
      else{btn.disabled=false;btn.textContent='Save';toast('Error: '+d.error,'err');}
    })
    .catch(()=>{btn.disabled=false;btn.textContent='Save';toast('Network error','err');});
}
function toast(msg,cls){const t=document.getElementById('toast');t.textContent=msg;t.className='toast show '+cls;setTimeout(()=>t.className='toast',2500);}
</script>
</body>
</html>"""

def check(req):
    return True

def fetch_missing():
    records, offset = [], None
    while True:
        params = {"fields[]": ["Name","Artist TikTok","Instagram"], "pageSize": 100}
        if offset: params["offset"] = offset
        r = requests.get(f"https://api.airtable.com/v0/{AIRTABLE_BASE}/{TABLE_ID}",
                         headers={"Authorization": f"Bearer {AIRTABLE_KEY}"}, params=params, timeout=30)
        d = r.json()
        records.extend(d.get("records", []))
        offset = d.get("offset")
        if not offset: break
    out = []
    for r in records:
        f = r.get("fields", {})
        tt, ig = f.get("Artist TikTok",""), f.get("Instagram","")
        if not tt or not ig:
            out.append({"id":r["id"],"name":f.get("Name","Unknown"),"tiktok":tt,"instagram":ig,"saved":False})
    return out

@app.route("/")
def index(): return render_template_string(HTML)

@app.route("/api/artists")
def api_artists():
    if not check(request): return jsonify({"error":"unauthorized"}), 401
    try: return jsonify(fetch_missing())
    except Exception as e: return jsonify({"error":str(e)}), 500

@app.route("/api/save", methods=["POST"])
def api_save():
    if not check(request): return jsonify({"error":"unauthorized"}), 401
    data = request.json
    fields = {}
    if data.get("tiktok"): fields["Artist TikTok"] = data["tiktok"]
    if data.get("instagram"): fields["Instagram"] = data["instagram"]
    if not fields: return jsonify({"ok":False,"error":"Nothing to save"})
    r = requests.patch(f"https://api.airtable.com/v0/{AIRTABLE_BASE}/{TABLE_ID}/{data['id']}",
                       headers={"Authorization":f"Bearer {AIRTABLE_KEY}","Content-Type":"application/json"},
                       json={"fields":fields}, timeout=10)
    return jsonify({"ok": r.status_code == 200, "error": f"Airtable {r.status_code}" if r.status_code != 200 else None})

if __name__ == "__main__":
    print("Handle tool running at http://89.167.11.114:8766/")
    app.run(host="0.0.0.0", port=8766, debug=False)
