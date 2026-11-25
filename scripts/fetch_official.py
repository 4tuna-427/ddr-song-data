#!/usr/bin/env python3
"""Phase 0 prototype: fetch the official DDR WORLD ALL MUSIC list.

Source: https://p.eagate.573.jp/game/ddr/ddrworld/music/index.html?filter=7
- Public, no login. filter=7 (ALL MUSIC) is the only view that shows all
  SP/DP levels per song; folder views (filter=1..6) show a single level.
- The song ID is the `img=` parameter of the jacket image URL
  (binary_jk.html?img=<id>&kind=1), the same e-amusement-style ID scheme
  as the existing ddr-song-data dataset.
- Politeness: descriptive UA, 1s interval between pages, fail loudly.

Output: JSON list of {id, title, artist, levels{sp{...}, dp{...}}}
Usage: python3 fetch_official.py [output.json] [--max-pages N]
"""
import json
import re
import sys
import time

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE = "https://p.eagate.573.jp/game/ddr/ddrworld/music/index.html"
UA = "ddr-data-pipeline/0.1 (personal project; https://github.com/4tuna-427)"
SP_DIFFS = ["BEGINNER", "BASIC", "DIFFICULT", "EXPERT", "CHALLENGE"]
DP_DIFFS = ["BASIC", "DIFFICULT", "EXPERT", "CHALLENGE"]


def parse_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    songs = []
    for tr in soup.select("tr.data"):
        img = tr.select_one("img.left-image")
        title_el = tr.select_one(".music-title")
        artist_el = tr.select_one(".artist")
        if not img or not title_el:
            continue
        src = img.get("src", "")
        m = re.search(r"[?&]img=([^&]+)", src)
        if not m:
            continue
        levels = {"sp": {}, "dp": {}}
        containers = tr.select(".diff-style-container")
        for container, diffs, key in (
            (containers[0] if len(containers) > 0 else None, SP_DIFFS, "sp"),
            (containers[1] if len(containers) > 1 else None, DP_DIFFS, "dp"),
        ):
            if container is None:
                continue
            for diff in diffs:
                el = container.select_one(f".diff.{diff} .level")
                text = el.get_text(strip=True) if el else "-"
                levels[key][diff.lower()] = None if text == "-" else int(text)
        songs.append(
            {
                "id": m.group(1),
                "jacket_url": urljoin("https://p.eagate.573.jp", src) if src else None,
                "title": title_el.get_text(strip=True),
                "artist": artist_el.get_text(strip=True) if artist_el else "",
                "levels": levels,
            }
        )
    return songs


def main() -> int:
    out = "official_songs.json"
    max_pages = None
    args = sys.argv[1:]
    if "--max-pages" in args:
        i = args.index("--max-pages")
        max_pages = int(args[i + 1])
        del args[i : i + 2]
    if args:
        out = args[0]

    session = requests.Session()
    session.headers["User-Agent"] = UA
    all_songs: list[dict] = []
    offset = 0
    page = 0
    while True:
        resp = None
        for attempt in range(4):
            try:
                resp = session.get(
                    BASE,
                    params={
                        "offset": offset,
                        "filter": 7,
                        "filtertype": 0,
                        "playmode": 2,
                    },
                    timeout=60,
                )
                resp.raise_for_status()
                break
            except requests.RequestException as e:
                wait = 5 * (2**attempt)
                print(
                    f"offset={offset} attempt {attempt + 1} failed: {e}; "
                    f"retry in {wait}s",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(wait)
        if resp is None:
            print(f"FAILED at offset={offset}; aborting", file=sys.stderr)
            return 1
        songs = parse_page(resp.text)
        page += 1
        print(
            f"page {page}: offset={offset} songs={len(songs)}",
            file=sys.stderr,
            flush=True,
        )
        if not songs:
            break
        all_songs.extend(songs)
        if max_pages and page >= max_pages:
            break
        offset += 1  # NOTE: offset is a page number (0-based), not a song count.
        time.sleep(1)

    ids = [s["id"] for s in all_songs]
    print(f"total={len(all_songs)} unique_ids={len(set(ids))}", file=sys.stderr)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_songs, f, ensure_ascii=False, indent=2)
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
