# Shadow Replay Data Backfill

Generated at: `2026-05-20T23:12:31`

## Scope

- Replay window: `2025-05-01` to `2025-12-31`
- Fetch window: `2025-01-01` to `2026-01-09`
- Universe policy: `current_constituents_approx`
- Execute: `True`
- Limit codes: `0`

## Result

- Index rows fetched: `800`
- Unique universe codes: `800`
- Price files written: `0`
- Price files skipped existing: `800`
- Price files available: `800`
- Price fetch failures: `0`
- Price rows written: `0`
- Price rows available: `197802`
- Price provider counts: `{}`
- Price fallback count: `0`
- Stop reason: ``

## Notes

- This is research-only shadow replay input data.
- The initial universe uses current index constituents as an approximation unless a point-in-time constituent source is added later.
- No Decision Ledger records are written by this job.
