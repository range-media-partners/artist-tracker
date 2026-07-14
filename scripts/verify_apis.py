#!/usr/bin/env python3
import argparse, json, time, sys, urllib.request, urllib.error, urllib.parse
from datetime import datetime

TEST_TIKTOK_HANDLE = "charlidamelio"
TEST_INSTAGRAM_HANDLE = "kyliejenner"
TEST_TIKTOK_SOUND_ID = "7106053710842880770"
SC_BASE = "https://api.scrapecreators.com"

def make_request(url, headers):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode("utf-8"))
        except: return e.code, {"raw": e.read().decode("utf-8")[:300]}
    except Exception as ex:
        return 0, {"error": str(ex)}

def check(label, status, data, required_keys=None):
    ok = status == 200
    if ok and required_keys:
        for k in required_keys:
            if k not in str(data): ok = False
    if ok: print(f"  [PASS] {label}")
    else:  print(f"  [FAIL] {label} — HTTP {status} — {str(data)[:150]}")
    return {"test": label, "status": status, "pass": ok}

def run_sc(key):
    h = {"x-api-key": key}
    results = []
    print("\n── ScrapeCreators ───────────────────────────")
    s,d = make_request(f"{SC_BASE}/v1/tiktok/profile?handle={TEST_TIKTOK_HANDLE}", h)
    results.append(check("TikTok profile — follower count", s, d, ["follower"]))
    time.sleep(0.5)
    s,d = make_request(f"{SC_BASE}/v3/tiktok/profile/videos?handle={TEST_TIKTOK_HANDLE}", h)
    results.append(check("TikTok videos — view counts", s, d))
    time.sleep(0.5)
    s,d = make_request(f"{SC_BASE}/v1/tiktok/song/videos?musicId={TEST_TIKTOK_SOUND_ID}", h)
    results.append(check("TikTok sound UGC videos", s, d))
    time.sleep(0.5)
    s,d = make_request(f"{SC_BASE}/v1/instagram/profile?handle={TEST_INSTAGRAM_HANDLE}", h)
    results.append(check("Instagram profile — follower count", s, d, ["follower"]))
    time.sleep(0.5)
    s,d = make_request(f"{SC_BASE}/v1/instagram/user/reels?handle={TEST_INSTAGRAM_HANDLE}", h)
    results.append(check("Instagram reels — view counts", s, d))
    return results

def run_airtable(key, base_id):
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    results = []
    print("\n── Airtable ─────────────────────────────────")
    s,d = make_request(f"https://api.airtable.com/v0/meta/bases/{base_id}/tables", h)
    r = check("Airtable — list tables", s, d, ["tables"])
    if s == 200:
        tables = [t["name"] for t in d.get("tables", [])]
        print(f"         tables found: {tables}")
        r["tables"] = tables
    results.append(r)
    time.sleep(0.3)
    table = urllib.parse.quote("Artists")
    s,d = make_request(f"https://api.airtable.com/v0/{base_id}/{table}?maxRecords=3", h)
    r = check("Airtable — read Artists table", s, d)
    if s == 200:
        recs = d.get("records", [])
        if recs: print(f"         fields: {list(recs[0]['fields'].keys())}")
    results.append(r)
    return results

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sc-key", required=True)
    p.add_argument("--airtable-key", required=True)
    p.add_argument("--base-id", required=True)
    args = p.parse_args()
    print("=" * 50)
    print("  Artist Tracker — API Verification")
    print("=" * 50)
    results = run_sc(args.sc_key) + run_airtable(args.airtable_key, args.base_id)
    passed = sum(1 for r in results if r["pass"])
    total = len(results)
    print(f"\n{'='*50}")
    print(f"  RESULTS: {passed}/{total} passed")
    print(f"{'='*50}")
    if passed == total: print("\n  All tests passed. Safe to proceed to Phase 2.")
    else:
        print("\n  Failed tests:")
        for r in results:
            if not r["pass"]: print(f"    - {r['test']}")
    sys.exit(0 if passed == total else 1)

if __name__ == "__main__":
    main()
