from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .analytics import export_artifacts_jsonl
from .artifacts import index_artifacts
from .history import export_history
from .mirror import mirror_analyzer_artifacts
from .repositories import AppStateRepository, ArtifactRepository, TaskRunRepository
from .paths import DEFAULT_DB_PATH, REPO_ROOT
from .sqlite_store import connection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prism storage maintenance commands")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite database path")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Prism workspace root")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index-artifacts", help="scan known artifact directories into SQLite")
    index_parser.add_argument("--limit", type=int, default=None)
    index_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")

    doctor_parser = subparsers.add_parser("doctor", help="print storage health summary")
    doctor_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")

    sync_parser = subparsers.add_parser(
        "sync-runtime",
        help="backfill runtime SQLite tables from compatibility JSON files",
    )
    sync_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")

    mirror_analyzer_parser = subparsers.add_parser(
        "mirror-analyzer-artifacts",
        help="mirror stock-analyzer outputs into data/artifacts/analyzer and register them",
    )
    mirror_analyzer_parser.add_argument("--limit", type=int, default=None)
    mirror_analyzer_parser.add_argument("--dry-run", action="store_true")
    mirror_analyzer_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")

    analytics_parser = subparsers.add_parser(
        "export-artifacts-jsonl",
        help="export artifact ledger rows into data/analytics as JSONL",
    )
    analytics_parser.add_argument("--limit", type=int, default=None)
    analytics_parser.add_argument("--output", default=None)
    analytics_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")

    history_parser = subparsers.add_parser(
        "export-history",
        help="export indexed artifacts and runtime metadata into public data/history",
    )
    history_parser.add_argument("--limit", type=int, default=None)
    history_parser.add_argument("--dry-run", action="store_true")
    history_parser.add_argument("--include-legacy-artifacts", action="store_true")
    history_parser.add_argument("--no-task-runs", action="store_true")
    history_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")

    register_parser = subparsers.add_parser("register-file", help="register one artifact file")
    register_parser.add_argument("path")
    register_parser.add_argument("--artifact-type", required=True)
    register_parser.add_argument("--source", default="")
    register_parser.add_argument("--run-id", default=None)
    register_parser.add_argument("--trade-date", default=None)
    register_parser.add_argument("--generated-at", default=None)
    register_parser.add_argument("--metadata-json", default="{}")
    register_parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db).expanduser()
    repo_root = Path(args.repo_root).expanduser().resolve()

    if args.command == "index-artifacts":
        summary = index_artifacts(db_path=db_path, repo_root=repo_root, limit=args.limit)
        print_summary(summary, as_json=args.json)
        return 0 if summary["ok"] else 1

    if args.command == "doctor":
        summary = doctor(db_path)
        print_summary(summary, as_json=args.json)
        return 0 if summary["ok"] else 1

    if args.command == "sync-runtime":
        summary = sync_runtime(db_path, repo_root)
        print_summary(summary, as_json=args.json)
        return 0 if summary["ok"] else 1

    if args.command == "mirror-analyzer-artifacts":
        summary = mirror_analyzer_artifacts(
            db_path=db_path,
            repo_root=repo_root,
            limit=args.limit,
            dry_run=args.dry_run,
        )
        print_summary(summary, as_json=args.json)
        return 0 if summary["ok"] else 1

    if args.command == "export-artifacts-jsonl":
        summary = export_artifacts_jsonl(
            db_path=db_path,
            repo_root=repo_root,
            output_path=args.output,
            limit=args.limit,
        )
        print_summary(summary, as_json=args.json)
        return 0 if summary["ok"] else 1

    if args.command == "export-history":
        summary = export_history(
            db_path=db_path,
            repo_root=repo_root,
            limit=args.limit,
            dry_run=args.dry_run,
            include_task_runs=not args.no_task_runs,
            include_legacy_artifacts=args.include_legacy_artifacts,
        )
        print_summary(summary, as_json=args.json)
        return 0 if summary["ok"] else 1

    if args.command == "register-file":
        try:
            metadata = json.loads(args.metadata_json)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"invalid --metadata-json: {exc}") from exc
        if not isinstance(metadata, dict):
            raise SystemExit("--metadata-json must decode to an object")
        artifact = ArtifactRepository(db_path, repo_root=repo_root).register_file(
            args.path,
            artifact_type=args.artifact_type,
            source=args.source,
            run_id=args.run_id,
            trade_date=args.trade_date,
            generated_at=args.generated_at,
            metadata=metadata,
        )
        print_summary({"ok": True, "artifact": artifact}, as_json=args.json)
        return 0

    raise SystemExit(f"unknown command: {args.command}")


def doctor(db_path: Path) -> dict[str, Any]:
    with connection(db_path) as conn:
        app_state_count = conn.execute("SELECT COUNT(*) FROM app_state").fetchone()[0]
        task_run_count = conn.execute("SELECT COUNT(*) FROM task_runs").fetchone()[0]
        artifact_count = conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
        artifact_types = [
            {"artifact_type": row[0], "count": row[1]}
            for row in conn.execute(
                """
                SELECT artifact_type, COUNT(*)
                FROM artifacts
                GROUP BY artifact_type
                ORDER BY COUNT(*) DESC, artifact_type
                """
            ).fetchall()
        ]
    return {
        "ok": True,
        "db_path": str(db_path),
        "app_state_count": app_state_count,
        "task_run_count": task_run_count,
        "artifact_count": artifact_count,
        "artifact_types": artifact_types,
    }


def sync_runtime(db_path: Path, repo_root: Path) -> dict[str, Any]:
    state_dir = repo_root / "apps" / "data" / "control_panel_state"
    state_keys = {
        "refresh_state": state_dir / "refresh_state.json",
        "ask_recent_queries": state_dir / "ask_recent_queries.json",
        "today_action_decisions": state_dir / "today_action_decisions.json",
    }
    app_state_repo = AppStateRepository(db_path)
    synced_state_keys: list[str] = []
    for key, path in state_keys.items():
        if not path.exists():
            continue
        app_state_repo.get(key, legacy_path=path, default={})
        synced_state_keys.append(key)

    run_dirs = (
        repo_root / "data" / "runtime" / "runs" / "control_panel",
        repo_root / "apps" / "data" / "control_panel_runs",
    )
    task_repo = TaskRunRepository(db_path)
    task_repo.sync_legacy_dirs(run_dirs)

    health = doctor(db_path)
    return {
        "ok": True,
        "synced_state_keys": synced_state_keys,
        "synced_state_count": len(synced_state_keys),
        "run_dirs": [str(path) for path in run_dirs if path.exists()],
        "app_state_count": health["app_state_count"],
        "task_run_count": health["task_run_count"],
        "artifact_count": health["artifact_count"],
    }


def print_summary(summary: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    for key, value in summary.items():
        if key == "counts":
            print("counts:")
            for item_key, item_value in sorted(value.items()):
                print(f"  {item_key}: {item_value}")
        elif key == "artifact_types":
            print("artifact_types:")
            for item in value:
                print(f"  {item['artifact_type']}: {item['count']}")
        elif key == "failed":
            print(f"failed: {len(value)}")
        else:
            print(f"{key}: {value}")


if __name__ == "__main__":
    raise SystemExit(main())
