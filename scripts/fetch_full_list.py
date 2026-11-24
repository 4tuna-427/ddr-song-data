#!/usr/bin/env python3
"""Fetch the RemyWiki 'DanceDanceRevolution WORLD Full Song List' page
wikitext — the index fetch_remywiki.py parses (page name, display title,
debut-version section per song).

Output: phase1/remy_world_full_list.txt (kept path for compatibility).
"""
import requests

API = "https://remywiki.com/api.php"
UA = {"User-Agent": "ddr-data-pipeline/0.1 (personal project; https://github.com/4tuna-427)"}
PAGE = "DanceDanceRevolution WORLD Full Song List"
OUT = "phase1/remy_world_full_list.txt"


def main() -> int:
    r = requests.get(API, params={
        "action": "query", "format": "json", "prop": "revisions",
        "titles": PAGE, "rvprop": "content", "rvslots": "main",
        "redirects": 1, "maxlag": 5,
    }, headers=UA, timeout=30)
    r.raise_for_status()
    page = list(r.json()["query"]["pages"].values())[0]
    text = page["revisions"][0]["slots"]["main"]["*"]
    open(OUT, "w", encoding="utf-8").write(text)
    bullets = sum(1 for line in text.splitlines() if line.startswith("* "))
    print(f"wrote {OUT}: {bullets} bullets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
