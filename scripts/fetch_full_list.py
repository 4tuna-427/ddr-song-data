#!/usr/bin/env python3
"""Fetch the RemyWiki 'DanceDanceRevolution WORLD Full Song List' page
wikitext — the index fetch_remywiki.py parses (page name, display title,
debut-version section per song).

Output: phase1/remy_world_full_list.txt (kept path for compatibility).
"""
import sys

import requests

API = "https://remywiki.com/api.php"
UA = {"User-Agent": "ddr-data-pipeline/0.1 (personal project; https://github.com/4tuna-427)"}
PAGE = "DanceDanceRevolution WORLD Full Song List"
OUT = "phase1/remy_world_full_list.txt"


def main() -> int:
    import os
    import time
    last_err = None
    for attempt in range(3):
        try:
            r = requests.get(API, params={
                "action": "query", "format": "json", "prop": "revisions",
                "titles": PAGE, "rvprop": "content", "rvslots": "main",
                "redirects": 1, "maxlag": 5,
            }, headers=UA, timeout=60)
            r.raise_for_status()
            page = list(r.json()["query"]["pages"].values())[0]
            text = page["revisions"][0]["slots"]["main"]["*"]
            open(OUT, "w", encoding="utf-8").write(text)
            bullets = sum(1 for line in text.splitlines() if line.startswith("* "))
            print(f"wrote {OUT}: {bullets} bullets")
            return 0
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"attempt {attempt + 1} failed: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    # Fallback: the previous index is committed to the repo, so a
    # transient RemyWiki outage (or a bot-wall on CI IPs) must not stop
    # the whole pipeline. The index changes slowly; tomorrow's run
    # retries the fetch.
    if os.path.exists(OUT):
        print(f"WARNING: fetch failed ({last_err}); using committed {OUT}",
              file=sys.stderr)
        return 0
    print(f"ERROR: fetch failed and no fallback {OUT} exists", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
