#!/usr/bin/env python3
"""Phase 3: diff-apply engine.

Takes the Phase 2 enriched snapshot plus the previous delivery and
produces the new master dataset, applying:

- additions (official-list imports, RemyWiki-only songs with
  provisional IDs),
- ID migrations (phase3/id_migrations.json),
- manual title mappings (phase3/manual_title_map.json),
- field updates (levels / title / version) with updated_at bumps,
- tombstones: songs on BEMANIWiki's removed-songs list get deleted_at
  (records are never dropped),
- timestamps: created_at is set on first detection; enrichment-only
  fills (artist / BPM / notecounts) do NOT bump updated_at.

Previous delivery: phase3/master.json when it exists (steady state);
on the first run, the live songs.json is the baseline (bootstrap).

Outputs:
  phase3/master.json            v2 master (full enriched schema)
  phase3/out/songs.json         v1-compatible delivery (current schema)
  phase3/out/songs_v2.json      same content as master.json
  phase3/changelog-<date>.json  what changed in this run
"""
import datetime
import json
import re
import sys
import unicodedata
import urllib.request

ENRICHED = "phase2/enriched_songs.json"
REMY = "phase2/remy_songs.json"
MANUAL_MAP = "phase3/manual_title_map.json"
MIGRATIONS = "phase3/id_migrations.json"
REMOVED_HTML = "phase3/bemani_removed.html"
MASTER = "phase3/master.json"
OUT_V1 = "phase3/out/songs.json"
OUT_V2 = "phase3/out/songs_v2.json"
CURRENT_URL = "https://4tuna-427.github.io/ddr-song-data/songs.json"

LEVEL_KEYS = ["sp_beginner", "sp_basic", "sp_difficult", "sp_expert",
              "sp_challenge", "dp_basic", "dp_difficult", "dp_expert",
              "dp_challenge"]
V1_LEVEL_MAP = {
    "sp_beginner": "single_beginner_level", "sp_basic": "single_basic_level",
    "sp_difficult": "single_difficult_level", "sp_expert": "single_expert_level",
    "sp_challenge": "single_challenge_level", "dp_basic": "double_basic_level",
    "dp_difficult": "double_difficult_level", "dp_expert": "double_expert_level",
    "dp_challenge": "double_challenge_level",
}
GAMEPLAY_FIELDS = ["title", "version"] + LEVEL_KEYS


def norm_title(t: str) -> str:
    t = unicodedata.normalize("NFKC", t or "")
    t = t.replace("​", "").replace("　", " ")
    return re.sub(r"\s+", " ", t).strip().lower()


def slug(page: str) -> str:
    s = unicodedata.normalize("NFKC", page).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "song"


def parse_removed(html_path: str) -> dict:
    """BEMANIWiki removed-songs list -> {normalized title: 'YYYY-MM-DD'}.

    Stdlib-only row parsing: split the HTML into <tr> rows, strip tags
    per <td> cell. Row layout: [date+削除, version, title, artist, ...].
    """
    html = open(html_path, encoding="utf-8", errors="ignore").read()
    out = {}
    current_date = None
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = []
        for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S):
            txt = re.sub(r"<[^>]+>", "", td)
            cells.append(re.sub(r"\s+", " ", txt).strip())
        if not cells:
            continue
        m = re.search(r"(\d{4})/(\d{2})/(\d{2})\s+\d{2}:\d{2}削除", cells[0])
        if m and len(cells) == 1:
            current_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            continue
        # Song rows under a date header: [version, title, artist, ...].
        # Songs revived later are filtered by the caller (a song that is
        # back on the official list must not be tombstoned).
        if current_date and len(cells) >= 2:
            out[norm_title(cells[1])] = current_date
    return out


def levels_of_v1(song: dict) -> dict:
    def v(k):
        x = song.get(k, "")
        return None if x == "" else int(x)
    return {lk: v(v1k) for lk, v1k in V1_LEVEL_MAP.items()}


def main() -> int:
    run_date = datetime.date.today().isoformat()
    enriched = json.load(open(ENRICHED))
    remy = json.load(open(REMY))
    remy_by_page = {r["page"]: r for r in remy}
    manual = {k: v for k, v in json.load(open(MANUAL_MAP)).items()
              if not k.startswith("_")}
    migrations = json.load(open(MIGRATIONS))["migrations"]
    removed = parse_removed(REMOVED_HTML)

    changelog = {"run_date": run_date, "added": [], "id_migrations": [],
                 "updated": [], "tombstoned": [], "manual_maps_applied": [],
                 "enrichment_fills": {"artist": 0, "bpm": 0, "notecounts": 0}}

    records = {e["id"]: dict(e) for e in enriched}

    # 0) Availability overrides (user-confirmed classifications).
    overrides = {k: v for k, v in json.load(open("phase3/availability_overrides.json")).items()
                 if not k.startswith("_")}
    for e in records.values():
        if e["title"] in overrides:
            e["availability"] = overrides[e["title"]]

    # 1) Manual title mappings: attach RemyWiki data to unmatched songs.
    for title, page in manual.items():
        hit = next((e for e in records.values() if e["title"] == title), None)
        if hit is None:
            print(f"WARN manual map title not found: {title}", file=sys.stderr)
            continue
        r = remy_by_page.get(page)
        if r is None:
            print(f"WARN manual map page not found: {page}", file=sys.stderr)
            continue
        hit["bpm"] = r["bpm"]
        hit["length"] = r["length"]
        hit["notecounts"] = r["notecounts"]
        hit["version_remy_first_ddr"] = r["first_ddr_version"]
        if r["world_levels"]:
            for k in ("sp_challenge", "dp_challenge"):
                if hit["levels"].get(k) is None:
                    hit["levels"][k] = r["world_levels"][k]
        hit["remy_page"] = page
        hit["remy_match"] = "manual"
        changelog["manual_maps_applied"].append({"title": title, "page": page})

    # 2) ID migrations: merge the old-ID record into the new-ID record.
    for mig in migrations:
        old = records.pop(mig["old_id"], None)
        new = records.get(mig["new_id"])
        if old is None or new is None:
            print(f"WARN migration pair incomplete: {mig['title']}", file=sys.stderr)
            continue
        new["phash_8"] = new.get("phash_8") or old.get("phash_8")
        new["phash_16"] = new.get("phash_16") or old.get("phash_16")
        new["in_current_dataset"] = True
        new["previous_id"] = mig["old_id"]
        changelog["id_migrations"].append(mig)

    # 3) RemyWiki-only songs: not used by any record and title unmatched.
    used_pages = {e["remy_page"] for e in records.values() if e.get("remy_page")}
    known_titles = {norm_title(e["title"]) for e in records.values()}
    for r in remy:
        if r["page"] == "Footnotes on BPM":
            continue  # not a song; a list footnote that parses as a bullet
        if r["page"] in used_pages:
            continue
        if norm_title(r["display_title"]) in known_titles:
            continue  # duplicate display title (e.g. cover versions) — skip
        pid = "remy-" + slug(r["page"])
        records[pid] = {
            "id": pid, "id_status": "provisional",
            "title": r["display_title"],
            "artist": "", "version_current": None,
            "version_remy_first_ddr": r["first_ddr_version"],
            "bpm": r["bpm"], "length": r["length"],
            "levels": r["world_levels"], "notecounts": r["notecounts"],
            "in_official_list": False, "in_current_dataset": False,
            "remy_page": r["page"], "remy_match": "remy_only",
            "phash_8": None, "phash_16": None, "availability": "standard",
        }

    # 4) Previous delivery baseline.
    try:
        prev_master = json.load(open(MASTER))
        prev = {e["id"]: e for e in prev_master}
        prev_levels = {i: e["levels"] for i, e in prev.items()}
        prev_created = {i: e.get("created_at", "") for i, e in prev.items()}
        prev_updated = {i: e.get("updated_at", "") for i, e in prev.items()}
        bootstrap = False
    except FileNotFoundError:
        live = json.load(urllib.request.urlopen(CURRENT_URL))
        prev = {s["id"]: s for s in live}
        prev_levels = {i: levels_of_v1(s) for i, s in prev.items()}
        prev_created = {i: "" for i in prev}
        prev_updated = {i: "" for i in prev}
        bootstrap = True
    # Migrated songs keep their history under the new ID.
    for mig in migrations:
        if mig["old_id"] in prev_levels and mig["new_id"] not in prev_levels:
            prev_levels[mig["new_id"]] = prev_levels[mig["old_id"]]

    # 5) Timestamps, diffs, tombstones.
    for rid, e in records.items():
        e.setdefault("id_status", "official")
        e.setdefault("availability", "standard")
        if rid in prev:
            e["created_at"] = prev_created.get(rid, "")
            old_lv = prev_levels.get(rid, {})
            changes = [k for k in LEVEL_KEYS if old_lv.get(k) != e["levels"].get(k)]
            if changes:
                e["updated_at"] = run_date
                changelog["updated"].append(
                    {"id": rid, "title": e["title"],
                     "fields": {k: [old_lv.get(k), e["levels"].get(k)] for k in changes}})
            else:
                # No new change: keep the previous updated_at as-is.
                e["updated_at"] = prev_updated.get(rid, "")
        else:
            e["created_at"] = run_date
            e["updated_at"] = ""
            changelog["added"].append(
                {"id": rid, "title": e["title"],
                 "source": "official" if e["in_official_list"] else "remywiki"})
        # Enrichment fill counters (informational; no updated_at bump).
        if e.get("artist"):
            changelog["enrichment_fills"]["artist"] += 1
        if e.get("bpm"):
            changelog["enrichment_fills"]["bpm"] += 1
        if e.get("notecounts"):
            changelog["enrichment_fills"]["notecounts"] += 1
        # Tombstone via BEMANIWiki removed list. Guard: a song that is
        # back on the official list (revived, e.g. シル・ヴ・プレジデント)
        # must not be tombstoned by its old removal entry.
        rdate = removed.get(norm_title(e["title"]))
        if rdate and not e.get("in_official_list"):
            e["deleted_at"] = rdate
            e["availability"] = "removed"
            changelog["tombstoned"].append(
                {"id": rid, "title": e["title"], "deleted_at": rdate})
        else:
            e.setdefault("deleted_at", "")

    master = sorted(records.values(), key=lambda e: e["title"])
    json.dump(master, open(MASTER, "w"), ensure_ascii=False, indent=2)
    json.dump(master, open(OUT_V2, "w"), ensure_ascii=False, indent=2)

    # 6) v1-compatible delivery.
    v1 = []
    for e in master:
        row = {
            "id": e["id"], "title": e["title"], "title_sort": "",
            "artist": e.get("artist") or "",
            "version": e.get("version_current") or e.get("version_remy_first_ddr") or "",
            "aliases": "",
        }
        for lk, v1k in V1_LEVEL_MAP.items():
            val = e["levels"].get(lk) if e["levels"] else None
            row[v1k] = "" if val is None else str(val)
        row["double_beginner_level"] = ""
        row["phash_8"] = e.get("phash_8") or ""
        row["phash_16"] = e.get("phash_16") or ""
        row["created_at"] = e.get("created_at", "")
        row["updated_at"] = e.get("updated_at", "")
        row["deleted_at"] = e.get("deleted_at", "")
        v1.append(row)
    json.dump(v1, open(OUT_V1, "w"), ensure_ascii=False, indent=2)

    clog_path = f"phase3/changelog-{run_date.replace('-', '')}.json"
    json.dump(changelog, open(clog_path, "w"), ensure_ascii=False, indent=2)
    print(f"bootstrap={bootstrap} master={len(master)} added={len(changelog['added'])} "
          f"updated={len(changelog['updated'])} tombstoned={len(changelog['tombstoned'])} "
          f"migrations={len(changelog['id_migrations'])} manual={len(changelog['manual_maps_applied'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
