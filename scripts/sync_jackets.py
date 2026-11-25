#!/usr/bin/env python3
"""Sync song jackets to Cloudflare Workers KV (authenticated image delivery).

Runs after run_pipeline.py in the daily workflow. The public delivery
(songs.json) keeps carrying data only; jacket IMAGES live in Workers KV
and are served by the score-manager Worker behind its API token, so the
images are not a public mirror.

Per master song (not tombstoned):
- Source: the official jacket URL captured by fetch_official.py (small
  JPEG). Songs absent from the official list fall back to the jacket file
  on their RemyWiki page (MediaWiki API), preferring a "<page> DDR"
  variant when one exists.
- Every image is normalized to JPEG, max 256x256, quality 82 (RemyWiki
  jackets are large PNGs; official ones are already small JPEGs).
- State: phase3/jackets_state.json (committed) maps song_id ->
  {source, sha256, bytes}. A song present in state is assumed present in
  KV and is skipped, so daily runs only send diffs. Upstream jacket
  changes are NOT detected (the official URL carries only the song ID).
- Tombstoned/removed songs are deleted from KV and from state.
- Finally, master.json and phase3/out/songs.json are rewritten with a
  boolean "jacket" flag per song reflecting KV reality.

KV writes go through the bulk API. The Workers KV free plan allows
1,000 writes/day, so a per-run budget (--max-writes, default 900) keeps
the run inside it: the initial load (~1,450 jackets) spans two daily
runs, then only diffs remain. Deletes count against the same budget.

Credentials come from the environment: CF_API_TOKEN, CF_ACCOUNT_ID,
KV_NAMESPACE_ID. Without them the script prints the plan and exits 0,
so the workflow stays green before the secrets are set.

Usage:
  python3 scripts/sync_jackets.py [--max-writes N] [--dry-run]
                                  [--local-dir DIR] [--master PATH]
                                  [--state PATH] [--out PATH]
  --local-dir writes images to a local folder instead of KV (testing).
"""
import argparse
import base64
import hashlib
import io
import json
import os
import sys
import time

import requests
from PIL import Image

UA = {"User-Agent": "ddr-song-data/0.1 (personal project; https://github.com/4tuna-427)"}
REMY_API = "https://remywiki.com/api.php"
MAX_SOURCE_BYTES = 4 * 1024 * 1024
BATCH = 100


def http_get(url: str, **kw) -> requests.Response:
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=30, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"retryable {r.status_code}")
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001 - retried below
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"GET failed: {url}: {last}")


def normalize_jpeg(raw: bytes) -> bytes:
    im = Image.open(io.BytesIO(raw))
    im = im.convert("RGB")
    im.thumbnail((256, 256))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    return buf.getvalue()


def remy_jacket_url(page: str) -> str | None:
    """Resolve the jacket file URL for a RemyWiki song page, or None."""
    data = http_get(REMY_API, params={
        "action": "query", "prop": "images", "titles": page,
        "imlimit": "50", "format": "json"}).json()
    files = [im["title"] for p in data["query"]["pages"].values()
             for im in p.get("images", [])]
    stems = {f[5:].rsplit(".", 1)[0]: f for f in files if f.startswith("File:")}
    pick = stems.get(f"{page} DDR") or stems.get(page)
    if pick is None:
        return None
    info = http_get(REMY_API, params={
        "action": "query", "prop": "imageinfo", "iiprop": "url",
        "titles": pick, "format": "json"}).json()
    for p in info["query"]["pages"].values():
        ii = p.get("imageinfo") or []
        if ii:
            return ii[0]["url"]
    return None


def fetch_jacket(song: dict) -> tuple[bytes, str] | None:
    """Return (normalized jpeg bytes, source) or None when unavailable."""
    url = song.get("jacket_url")
    source = "official"
    if not url and song.get("remy_page"):
        url = remy_jacket_url(song["remy_page"])
        source = "remy"
    if not url:
        return None
    raw = http_get(url).content
    if len(raw) > MAX_SOURCE_BYTES:
        print(f"WARN jacket too large, skipped: {song['id']}", file=sys.stderr)
        return None
    try:
        return normalize_jpeg(raw), source
    except Exception as e:  # noqa: BLE001 - not an image / corrupt
        print(f"WARN jacket not an image, skipped: {song['id']}: {e}", file=sys.stderr)
        return None


class KvClient:
    def __init__(self, account: str, namespace: str, token: str):
        self.base = (f"https://api.cloudflare.com/client/v4/accounts/{account}"
                     f"/storage/kv/namespaces/{namespace}/bulk")
        self.headers = {"Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"}

    def _call(self, method: str, payload) -> None:
        last = None
        for attempt in range(3):
            try:
                r = requests.request(method, self.base, headers=self.headers,
                                     json=payload, timeout=60)
                body = r.json() if r.content else {}
                if r.status_code in (429, 500, 502, 503, 504) or not body.get("success", False):
                    raise RuntimeError(f"KV {method} failed: {r.status_code} {body.get('errors')}")
                return
            except Exception as e:  # noqa: BLE001 - retried below
                last = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"KV {method} failed after retries: {last}")

    def put_many(self, items: list[dict]) -> None:
        for i in range(0, len(items), BATCH):
            self._call("PUT", items[i:i + BATCH])

    def delete_many(self, keys: list[str]) -> None:
        for i in range(0, len(keys), BATCH):
            self._call("DELETE", keys[i:i + BATCH])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-writes", type=int, default=900)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan only; no downloads, no writes")
    ap.add_argument("--local-dir", default=None,
                    help="write images here instead of KV (testing)")
    ap.add_argument("--master", default="phase3/master.json")
    ap.add_argument("--state", default="phase3/jackets_state.json")
    ap.add_argument("--out", default="phase3/out/songs.json")
    args = ap.parse_args()

    master = json.load(open(args.master))
    state = {}
    if os.path.exists(args.state):
        state = json.load(open(args.state))

    desired = {s["id"]: s for s in master if not s.get("deleted_at")}
    to_delete = sorted(set(state) - set(desired))
    # Entries without "v": 2 were stored by the first version of this
    # script, which forgot "base64": true on the bulk PUT — KV holds the
    # base64 TEXT of those images instead of the image bytes. They count
    # as not-in-KV here and are re-uploaded (overwritten) automatically.
    in_kv = {sid for sid, rec in state.items() if rec.get("v") == 2}
    to_fetch = [s for sid, s in sorted(desired.items()) if sid not in in_kv]
    print(f"desired={len(desired)} in_kv={len(in_kv)} "
          f"to_fetch={len(to_fetch)} to_delete={len(to_delete)}")

    token = os.environ.get("CF_API_TOKEN")
    account = os.environ.get("CF_ACCOUNT_ID")
    namespace = os.environ.get("KV_NAMESPACE_ID")
    kv = None
    if not args.dry_run and not args.local_dir:
        if token and account and namespace:
            kv = KvClient(account, namespace, token)
        else:
            print("CF_API_TOKEN / CF_ACCOUNT_ID / KV_NAMESPACE_ID not set: "
                  "plan only, nothing uploaded.")
            # The workflow's commit step git-adds the state file; make
            # sure it exists even when nothing was uploaded yet.
            if not os.path.exists(args.state):
                with open(args.state, "w") as f:
                    json.dump({}, f)
            return 0
    if args.dry_run:
        return 0

    writes = 0
    # Deletes first (they free nothing quota-wise, but keep state truthful).
    if to_delete and writes < args.max_writes:
        batch = to_delete[: args.max_writes - writes]
        if kv:
            kv.delete_many(batch)
        for sid in batch:
            state.pop(sid, None)
        writes += len(batch)
        print(f"deleted={len(batch)}")

    fetched = 0
    failed = 0
    local_written = 0
    pending: list[dict] = []
    for song in to_fetch:
        # Budget = KV writes spent so far: flushed batches + queued puts
        # (+ files written in local mode). Count each song exactly once.
        if writes + len(pending) + local_written >= args.max_writes:
            break
        got = fetch_jacket(song)
        if got is None:
            failed += 1
            continue
        data, source = got
        digest = hashlib.sha256(data).hexdigest()
        if args.local_dir:
            os.makedirs(args.local_dir, exist_ok=True)
            with open(os.path.join(args.local_dir, f"{song['id']}.jpg"), "wb") as f:
                f.write(data)
            local_written += 1
        else:
            pending.append({
                "key": song["id"],
                "value": base64.b64encode(data).decode(),
                # Without this, KV stores the base64 text itself instead
                # of the decoded image bytes.
                "base64": True,
                "metadata": {"content_type": "image/jpeg"},
            })
        state[song["id"]] = {"source": source, "sha256": digest, "bytes": len(data), "v": 2}
        fetched += 1
        if len(pending) >= BATCH:
            kv.put_many(pending)
            writes += len(pending)
            pending = []
    if pending:
        kv.put_many(pending)
        writes += len(pending)
    print(f"fetched={fetched} failed_no_source={failed} writes_used={writes}")

    with open(args.state, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)

    valid = {sid for sid, rec in state.items() if rec.get("v") == 2}
    for s in master:
        s["jacket"] = s["id"] in valid
    with open(args.master, "w") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)
    with open(args.out, "w") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)
    print(f"jacket flags set: {sum(1 for s in master if s['jacket'])}/{len(master)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
