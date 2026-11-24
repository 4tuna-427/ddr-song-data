# DDR song data — automatic update pipeline

Replaces the manual input stage of ddr-song-data. Daily, on GitHub
Actions, it fetches three public sources, merges them, applies the
diff to the master dataset, and commits the result.

## Sources and what each is trusted for

| Source | Role |
|---|---|
| Official e-amusement ALL MUSIC list | Resident songs: ID, title, artist, non-Challenge levels |
| RemyWiki (MediaWiki API) | BPM, length, note counts, first DDR version, Challenge levels, newest songs |
| BEMANIWiki removed-songs list | Deletion detection (tombstones) |

Rules learned the hard way (Phases 0–2):

- The official list does **not** carry event/unlock songs and does not
  display WORLD-added Challenge charts. Absence from the official list
  is never treated as deletion.
- A song is tombstoned (`deleted_at` set, record kept) only when it
  appears on BEMANIWiki's removed list **and** is not back on the
  official list (revived songs exist, e.g. シル・ヴ・プレジデント).
- Songs only RemyWiki knows get a provisional ID (`remy-<slug>`,
  `id_status: "provisional"` in the v2 master). When the official list
  picks the song up, add an entry to `phase3/id_migrations.json` to
  merge the provisional record into the official ID.

## Layout

- `scripts/` — fetchers, merger, diff-apply engine (run in the order
  given in `.github/workflows/update-songs.yml`)
- `phase3/master.json` — the v2 master dataset (state; committed)
- `phase3/out/songs.json` — v1-compatible delivery (same schema as the
  current songs.json: string levels, `created_at` / `updated_at` /
  `deleted_at`)
- `phase3/out/songs_v2.json` — v2 delivery (BPM, note counts, flags)
- `phase3/changelog-<date>.json` — per-run record of what changed
- `phase3/manual_title_map.json` — title → RemyWiki page for songs
  automated matching cannot resolve (notation variants)
- `phase3/id_migrations.json` — old ID → new ID merges
- `phase3/availability_overrides.json` — user-confirmed availability
  classes (limited-time event songs, EXTRA SAVIOR unlocks, scheduled
  removals) that no source publishes in structured form

## Timestamps policy

- `created_at`: first date the pipeline detected the song. Songs that
  predate the pipeline keep `""` (unknown).
- `updated_at`: bumped only when a gameplay field (levels, title,
  version) changes. Enrichment fills (artist, BPM, note counts) are
  counted in the changelog but do not bump `updated_at`.

## First run

With no `phase3/master.json`, the engine bootstraps against the live
songs.json (see `CURRENT_URL` in `scripts/run_pipeline.py` — change it
if the delivery URL changes). The run is idempotent: running it twice
in a row produces no further changes.

## Politeness

- Official site: once a day, ≥1s between pages, descriptive UA. On
  fetch failure the job stops and the previous data keeps being served.
- RemyWiki: API only, descriptive UA, page wikitext cached in
  `phase2/remy_pages.json` (committed, so daily runs fetch only new
  pages).
- Never scrape Zenius (robots.txt disallows it), Sanbai, or Skill
  Attack; never use login-gated pages.
