#!/usr/bin/env python3
"""Fetch BEMANIWiki's DDR WORLD removed-songs list (tombstone source).

Output: phase3/bemani_removed.html (parsed by run_pipeline.py).
Politeness: single page, descriptive UA. BEMANIWiki's robots.txt has no
disallow for this path (checked 2026-11-24).
"""
import urllib.request

URL = "https://bemaniwiki.com/index.php?DanceDanceRevolution%20WORLD%2F%BA%EF%BD%FC%B6%CA%A5%EA%A5%B9%A5%C8"
OUT = "phase3/bemani_removed.html"


def main() -> int:
    req = urllib.request.Request(
        URL, headers={"User-Agent": "ddr-data-pipeline/0.1 (personal project)"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="ignore")
    open(OUT, "w", encoding="utf-8").write(html)
    print(f"wrote {OUT}: {len(html)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
