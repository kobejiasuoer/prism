# Prism System Architecture

Prism is a monorepo that combines a FastAPI control panel, Python screening workflows, report generation, and historical operational artifacts in one public codebase.

## Components

- `apps/control-panel/`: operator-facing control panel, watchlist refresh, and workflow entrypoints
- `packages/screener/`: scan, AI screening, midday verification, lifecycle tracking, and message generation
- `data/history/`: scrubbed historical outputs, logs, command briefs, and daily snapshots
- `scripts/scrub-secrets.py`: pre-publish privacy scrub for paths, proxy values, and recipient identifiers

## Open-Source Boundary

Prism now publishes the real system rather than a demo shell.

The public repo includes:

- real frontend templates and static assets
- real workflow scripts and decision rules
- real prompts, thresholds, and report formats
- real historical artifacts after mechanical scrub

The public repo excludes only:

- secrets and tokens
- login state and browser session traces
- proxy credentials and private endpoints
- personal recipient identifiers and machine-local paths
