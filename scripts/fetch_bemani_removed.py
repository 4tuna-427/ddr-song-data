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
    import os
    import sys
    import time
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                URL, headers={"User-Agent": "ddr-data-pipeline/0.1 (personal project)"})
            html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", errors="ignore")
            open(OUT, "w", encoding="utf-8").write(html)
            print(f"wrote {OUT}: {len(html)} bytes")
            return 0
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"attempt {attempt + 1} failed: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    # Fallback: the previous snapshot is committed to the repo; the
    # removed list changes slowly, so a transient failure must not
    # stop the pipeline.
    if os.path.exists(OUT):
        print(f"WARNING: fetch failed ({last_err}); using committed {OUT}",
              file=sys.stderr)
        return 0
    print(f"ERROR: fetch failed and no fallback {OUT} exists", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
