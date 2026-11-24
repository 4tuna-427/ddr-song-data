#!/usr/bin/env python3
"""Phase 2: merge official list + current dataset + RemyWiki enrichment.

Matching: RemyWiki entries are matched to songs by normalized title
(NFKC, zero-width-space removed, whitespace collapsed, case-folded).
Duplicate normalized titles are reported, not silently merged.

Field policy (from Phase 1):
- title / artist: official list first; for songs the official list does
  not carry, fall back to the current title and RemyWiki's Artist line.
- levels: official list; Challenge always from RemyWiki (the official
  site does not display WORLD-added Challenge charts).
- bpm / length / notecounts / first DDR version: RemyWiki.
- existence flags are kept, never used to drop songs here.

Outputs: phase2/enriched_songs.json, phase2/merge_report.json
"""
import json
import re
import unicodedata
import urllib.request

OFFICIAL = "phase0/official_songs.json"
REMY = "phase2/remy_songs.json"
REMY_CACHE = "phase2/remy_pages.json"
CURRENT_URL = "https://4tuna-427.github.io/ddr-song-data/songs.json"
OUT = "phase2/enriched_songs.json"
REPORT = "phase2/merge_report.json"

LEVEL_KEYS = ["sp_beginner", "sp_basic", "sp_difficult", "sp_expert",
              "sp_challenge", "dp_basic", "dp_difficult", "dp_expert",
              "dp_challenge"]


def norm_title(t: str) -> str:
    t = unicodedata.normalize("NFKC", t or "")
    t = t.replace("​", "").replace("　", " ")
    return re.sub(r"\s+", " ", t).strip().lower()


def loose_title(t: str) -> str:
    """Fallback key: drop every symbol/punctuation so stylistic variants
    (♡ vs ♥, ～ vs ~, ’ vs ', ･∀･ decorations) still match."""
    t = norm_title(t)
    return "".join(c for c in t if c.isalnum())


def official_levels(s: dict) -> dict:
    lv = s["levels"]
    return {
        "sp_beginner": lv["sp"]["beginner"], "sp_basic": lv["sp"]["basic"],
        "sp_difficult": lv["sp"]["difficult"], "sp_expert": lv["sp"]["expert"],
        "sp_challenge": lv["sp"]["challenge"], "dp_basic": lv["dp"]["basic"],
        "dp_difficult": lv["dp"]["difficult"], "dp_expert": lv["dp"]["expert"],
        "dp_challenge": lv["dp"]["challenge"],
    }


def current_levels(s: dict) -> dict:
    def v(k):
        x = s.get(k, "")
        return None if x == "" else int(x)
    return {
        "sp_beginner": v("single_beginner_level"), "sp_basic": v("single_basic_level"),
        "sp_difficult": v("single_difficult_level"), "sp_expert": v("single_expert_level"),
        "sp_challenge": v("single_challenge_level"), "dp_basic": v("double_basic_level"),
        "dp_difficult": v("double_difficult_level"), "dp_expert": v("double_expert_level"),
        "dp_challenge": v("double_challenge_level"),
    }


def remy_artist(cache_text: str):
    m = re.search(r"^Artist: (.+)$", cache_text or "", re.M)
    if not m:
        return None
    a = m.group(1)
    a = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]+)\]\]", r"\1", a)
    return re.sub(r"<[^>]+>", "", a).strip()


def main() -> int:
    official = json.load(open(OFFICIAL))
    remy = json.load(open(REMY))
    cache = json.load(open(REMY_CACHE))
    current = json.load(urllib.request.urlopen(CURRENT_URL))

    # Remy index by normalized display title; record duplicates.
    remy = [r for r in remy if r["page"] != "Footnotes on BPM"]
    remy_by_norm = {}
    dup_norm = {}
    for r in remy:
        k = norm_title(r["display_title"])
        if k in remy_by_norm:
            dup_norm.setdefault(k, [remy_by_norm[k]["page"]]).append(r["page"])
        else:
            remy_by_norm[k] = r
    remy_by_loose = {}
    for r in remy:
        remy_by_loose.setdefault(loose_title(r["display_title"]), []).append(r)

    off_by_id = {s["id"]: s for s in official}
    cur_by_id = {s["id"]: s for s in current}
    all_ids = list(off_by_id) + [i for i in cur_by_id if i not in off_by_id]

    enriched = []
    report = {
        "total_ids": len(all_ids), "remy_matched": 0, "remy_unmatched": [],
        "duplicate_remy_titles": dup_norm,
        "level_mismatches_vs_official": [], "level_mismatches_vs_current": [],
        "version_mismatches_vs_current": [], "challenge_from_remy": 0,
    }
    used_remy_pages = set()
    for sid in all_ids:
        off = off_by_id.get(sid)
        cur = cur_by_id.get(sid)
        title = (off or cur)["title"]
        r = remy_by_norm.get(norm_title(title))
        match_method = "exact_norm" if r else None
        if not r:
            cands = remy_by_loose.get(loose_title(title), [])
            if len(cands) == 1:
                r = cands[0]
                match_method = "loose"
        if r:
            report["remy_matched"] += 1
            used_remy_pages.add(r["page"])
        else:
            report["remy_unmatched"].append({"id": sid, "title": title})

        levels = {}
        off_lv = official_levels(off) if off else None
        cur_lv = current_levels(cur) if cur else None
        remy_lv = r["world_levels"] if r else None
        for k in LEVEL_KEYS:
            if k == "sp_challenge" or k == "dp_challenge":
                levels[k] = remy_lv[k] if remy_lv else (off_lv[k] if off_lv else cur_lv[k])
            elif off_lv:
                levels[k] = off_lv[k]
            elif remy_lv:
                levels[k] = remy_lv[k]
            else:
                levels[k] = cur_lv[k]
        if remy_lv and (remy_lv["sp_challenge"] or remy_lv["dp_challenge"]):
            report["challenge_from_remy"] += 1

        # Cross-checks (record only; nothing is overwritten silently).
        if off_lv and remy_lv:
            for k in LEVEL_KEYS:
                if k.endswith("challenge"):
                    continue
                if off_lv[k] != remy_lv[k]:
                    report["level_mismatches_vs_official"].append(
                        {"id": sid, "title": title, "field": k,
                         "official": off_lv[k], "remy": remy_lv[k]})
        if cur_lv and remy_lv:
            for k in LEVEL_KEYS:
                if cur_lv[k] != remy_lv[k]:
                    report["level_mismatches_vs_current"].append(
                        {"id": sid, "title": title, "field": k,
                         "current": cur_lv[k], "remy": remy_lv[k]})
        if cur and r and r["first_ddr_version"]:
            # current version strings: 'A20 PLUS', '2013', '1st'... compare loosely
            cv = cur["version"].replace("X3 vs 2nd", "X3").replace("SuperNOVA2", "SuperNOVA2")
            if norm_title(cv) != norm_title(r["first_ddr_version"]):
                report["version_mismatches_vs_current"].append(
                    {"id": sid, "title": title, "current": cur["version"],
                     "remy_first_ddr": r["first_ddr_version"]})

        enriched.append({
            "id": sid,
            "title": title,
            "artist": (off["artist"] if off else None) or (remy_artist(cache.get(r["page"], "")) if r else None) or "",
            "version_current": cur["version"] if cur else None,
            "version_remy_first_ddr": r["first_ddr_version"] if r else None,
            "bpm": r["bpm"] if r else None,
            "length": r["length"] if r else None,
            "levels": levels,
            "notecounts": r["notecounts"] if r else None,
            "in_official_list": off is not None,
            "in_current_dataset": cur is not None,
            "remy_page": r["page"] if r else None,
            "remy_match": match_method,
            "phash_8": cur["phash_8"] if cur else None,
            "phash_16": cur["phash_16"] if cur else None,
        })

    report["remy_pages_unused"] = sorted(
        {r["page"] for r in remy} - used_remy_pages)
    json.dump(enriched, open(OUT, "w"), ensure_ascii=False, indent=2)
    json.dump(report, open(REPORT, "w"), ensure_ascii=False, indent=2)
    print(f"enriched={len(enriched)} matched={report['remy_matched']} "
          f"unmatched={len(report['remy_unmatched'])} "
          f"lv_vs_official={len(report['level_mismatches_vs_official'])} "
          f"lv_vs_current={len(report['level_mismatches_vs_current'])} "
          f"ver_vs_current={len(report['version_mismatches_vs_current'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
