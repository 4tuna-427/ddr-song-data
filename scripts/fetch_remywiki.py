#!/usr/bin/env python3
"""Phase 2: fetch RemyWiki song pages for every song in the DDR WORLD
Full Song List and parse enrichment data.

- Index: the Full Song List wikitext gives, per song, the exact RemyWiki
  page name, the display title, and the debut-version section it sits in.
- Per song page (via MediaWiki API, batched, descriptive UA):
  BPM, length, and the chart section that covers WORLD: the WORLD-era
  chart levels (incl. Challenge, which the official site under-reports)
  and the matching {{DDR Chart Notecounts}} (notes / freeze / shock).
- Chart rows use range notation ("A3→Present", "X→A3",
  "A20 PLUS→WORLD"); a row covers WORLD when its range includes WORLD.

Cache: phase2/remy_pages.json (page title -> wikitext). Re-runs reuse it.
Output: phase2/remy_songs.json
"""
import json
import re
import sys
import time
import unicodedata

import requests

API = "https://remywiki.com/api.php"
UA = {"User-Agent": "ddr-data-pipeline/0.1 (personal project; https://github.com/4tuna-427)"}
FULL_LIST = "phase1/remy_world_full_list.txt"
CACHE = "phase2/remy_pages.json"
OUT = "phase2/remy_songs.json"

VERSION_ORDER = [
    "1st", "2nd", "3rd", "4th", "5th", "DDRMAX", "DDRMAX2", "EXTREME",
    "SuperNOVA", "SuperNOVA2", "X", "X2", "X3", "2013", "2014",
    "A", "A20", "A20 PLUS", "A3", "WORLD",
]


def norm_title(t: str) -> str:
    t = unicodedata.normalize("NFKC", t)
    t = t.replace("​", "").replace("　", " ")
    return re.sub(r"\s+", " ", t).strip().lower()


def parse_full_list(path: str) -> list[dict]:
    text = open(path, encoding="utf-8").read()
    songs = []
    section = ""
    for line in text.splitlines():
        m = re.match(r"^=+\s*(.+?)\s*=+$", line)
        if m:
            section = m.group(1)
            continue
        # Display titles may themselves contain [ ] (e.g. "[ ]DENTITY",
        # "access super [hyper] focus"), so the alias group must run to
        # the "]]" that is followed by " / " or end-of-line.
        m = re.match(r"^\* '{0,3}\[\[([^\]|]+)(?:\|(.+?))?\]\](?=\s*/|\s*$)", line)
        if m:
            page = m.group(1).strip()
            display = (m.group(2) or m.group(1)).strip()
            songs.append(
                {"page": page, "display_title": display, "list_section": section}
            )
    return songs


def fetch_pages(pages: list[str], cache_path: str) -> dict:
    try:
        cache = json.load(open(cache_path))
    except FileNotFoundError:
        cache = {}
    todo = [p for p in pages if p not in cache]
    print(f"pages: {len(pages)}, cached: {len(pages) - len(todo)}, to fetch: {len(todo)}",
          file=sys.stderr)
    s = requests.Session()
    s.headers.update(UA)
    for k in range(0, len(todo), 40):
        batch = todo[k : k + 40]
        r = None
        for attempt in range(3):
            try:
                r = s.get(
                    API,
                    params={
                        "action": "query", "format": "json", "prop": "revisions",
                        "titles": "|".join(batch), "rvprop": "content",
                        "rvslots": "main", "redirects": 1, "maxlag": 5,
                    },
                    timeout=120,
                )
                r.raise_for_status()
                break
            except Exception as e:  # noqa: BLE001
                print(f"  batch {k}: attempt {attempt + 1} failed: {e}",
                      file=sys.stderr)
                r = None
                time.sleep(5 * (attempt + 1))
        if r is None:
            # Leave these pages uncached for this run; songs still come
            # from the official list / previous delivery, and the next
            # run retries. Do not abort the whole pipeline.
            print(f"  batch {k}: skipped after retries", file=sys.stderr)
            continue
        d = r.json()
        q = d.get("query", {})
        chain = {}
        for n in q.get("normalized", []):
            chain[n["from"]] = n["to"]
        for x in q.get("redirects", []):
            chain[x["from"]] = x["to"]
        texts = {}
        for p in q.get("pages", {}).values():
            if "revisions" in p:
                texts[p["title"]] = p["revisions"][0]["slots"]["main"]["*"]
        for t in batch:
            cur, seen = t, 0
            while cur in chain and seen < 5:
                cur = chain[cur]
                seen += 1
            cache[t] = texts.get(cur, "")
        print(f"  fetched {min(k + 40, len(todo))}/{len(todo)}", file=sys.stderr)
        json.dump(cache, open(cache_path, "w"), ensure_ascii=False)
        time.sleep(1)
    return cache


def norm_game_name(g: str) -> str:
    return g.replace("X3 VS 2ndMIX", "X3").replace("(", "").replace(")", "").strip()


def game_range_covers_world(game: str) -> bool:
    g = game.replace("DanceDanceRevolution ", "").replace("DDR ", "")
    g = norm_game_name(g.replace("&rarr;", "→"))
    if "CS" in g or "GRAND PRIX" in g or "Classic" in g:
        return False
    if g in ("WORLD", "WORLD→Present"):
        return True
    m = re.match(r"^(.+?)→(.+)$", g)
    if m:
        start, end = m.group(1).strip(), m.group(2).strip()
        if end == "Present":
            return start in VERSION_ORDER and VERSION_ORDER.index(start) <= VERSION_ORDER.index("WORLD")
        if end == "WORLD":
            return True
        return False
    return False


def clean_level(v: str):
    v = v.replace("'''", "").strip()
    if v in ("-", ""):
        return None
    v = re.sub(r"&[ud]arr;", "", v).strip()
    if "N/A" in v:  # ⁑N/A / ⁂N/A: chart exists on paper but is unused
        return None
    return int(v) if v.isdigit() else v


def parse_song_page(text: str, display_title: str = "") -> dict:
    out = {"bpm": None, "length": None, "world_levels": None, "notecounts": None,
           "first_ddr_version": None}
    if not text:
        return out
    # Variant entries (X-Special, "…" Special, True Style, ...) share
    # the base song's page, which holds several chart sections
    # ("Original Charts", "X-Special Charts", "True Style", ...).
    # For a variant entry only its own section is correct; for the
    # base entry the variant sections must be skipped.
    want_special = "Special)" in display_title
    variant_keys = []
    if want_special:
        variant_keys = ["Special"]
    else:
        m = re.search(r"\(([^)]+)\)\s*$", display_title)
        if m:
            variant_keys = [m.group(1)]
    m = re.search(r"^BPM: (.+)$", text, re.M)
    if m:
        out["bpm"] = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    m = re.search(r"^Length: (.+)$", text, re.M)
    if m:
        out["length"] = re.sub(r"<[^>]+>", "", m.group(1)).strip()

    # Split into chart sections by header, remembering the nearest
    # preceding ==== heading ==== for each section.
    headings = [(m.start(), m.group(1)) for m in
                re.finditer(r"^={2,5}\s*(.+?)\s*={2,5}$", text, re.M)]
    sections = []
    for m in re.finditer(r"\{\{DDR Chart Header\|", text):
        heading = ""
        for pos, h in headings:
            if pos < m.start():
                heading = h
            else:
                break
        sections.append((heading, text[m.start():]))
    if variant_keys:
        # Sections whose heading names the variant come first.
        sections = sorted(
            sections,
            key=lambda hs: 0 if any(k in hs[0] for k in variant_keys) else 1)
    arcade_versions = []
    for heading, sec in sections:
        is_special_section = "Special" in heading
        nc = re.search(r"\{\{DDR Chart Notecounts\|([^\n}]+)", sec)
        rows = re.findall(r"\{\{DDR Chart\|([^|]+)\|([^\n}]+)", sec)
        for game, vals in rows:
            game_clean = game.replace("&rarr;", "→").strip()
            base = game_clean.replace("DanceDanceRevolution ", "")
            start = norm_game_name(re.split(r"→", base)[0])
            if ("CS" not in game_clean and "GRAND PRIX" not in game_clean
                    and start in VERSION_ORDER):
                arcade_versions.append(start)
            if game_range_covers_world(game_clean) and is_special_section == want_special:
                parts = [clean_level(v) for v in vals.split("|")]
                if len(parts) >= 9 and out["world_levels"] is None:
                    keys = ["sp_beginner", "sp_basic", "sp_difficult", "sp_expert",
                            "sp_challenge", "dp_basic", "dp_difficult", "dp_expert",
                            "dp_challenge"]
                    out["world_levels"] = dict(zip(keys, parts[:9]))
                    out["world_row_game"] = game_clean
                    if nc:
                        ncs = []
                        for item in nc.group(1).split("|"):
                            item = item.strip()
                            if item in ("-", ""):
                                ncs.append(None)
                            else:
                                nums = [x.strip() for x in item.split("/")]
                                entry = {"notes": int(nums[0]) if nums[0].isdigit() else nums[0]}
                                if len(nums) > 1:
                                    entry["freeze"] = int(nums[1]) if nums[1].isdigit() else nums[1]
                                if len(nums) > 2:
                                    entry["shock"] = int(nums[2]) if nums[2].isdigit() else nums[2]
                                ncs.append(entry)
                        out["notecounts"] = dict(zip(
                            ["sp_beginner", "sp_basic", "sp_difficult", "sp_expert",
                             "sp_challenge", "dp_basic", "dp_difficult", "dp_expert",
                             "dp_challenge"], ncs[:9]))
    if arcade_versions:
        out["first_ddr_version"] = min(arcade_versions, key=VERSION_ORDER.index)
    return out


def main() -> int:
    index = parse_full_list(FULL_LIST)
    print(f"full list entries: {len(index)}", file=sys.stderr)
    cache = fetch_pages([s["page"] for s in index], CACHE)
    results = []
    for s in index:
        parsed = parse_song_page(cache.get(s["page"], ""), s["display_title"])
        results.append({**s, **parsed, "has_page": bool(cache.get(s["page"]))})
    json.dump(results, open(OUT, "w"), ensure_ascii=False, indent=2)
    n = len(results)
    print(f"total={n} pages_ok={sum(r['has_page'] for r in results)} "
          f"bpm={sum(1 for r in results if r['bpm'])} "
          f"world_levels={sum(1 for r in results if r['world_levels'])} "
          f"notecounts={sum(1 for r in results if r['notecounts'])} "
          f"first_ver={sum(1 for r in results if r['first_ddr_version'])}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
