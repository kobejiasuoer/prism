"""Manual entry point for the Decision Ledger outcome evaluator.

Run shape::

    ./.venv/bin/python apps/scripts/evaluate_decision_ledger.py \\
        --as-of 2026-05-22 \\
        [--benchmark 000300] \\
        [--provider prism_data|cache|none] \\
        [--data-root <path>]

``--provider`` selects the :class:`PriceProvider` implementation:

* ``prism_data`` (default) -- reuses ``packages/prism_data`` through
  :class:`PrismDataPriceProvider`.  This is the production path; the
  gateway already owns vendor fallback (Sina → AkShare) and writes
  back into ``data/prism_data/datasets/bars.daily/`` so cache reuse is
  automatic.
* ``cache`` -- reads ``bars.daily`` cache files directly via
  :class:`PrismCachePriceProvider`.  Useful when a no-network rerun is
  expected.
* ``none`` -- runs the resolver with ``price_provider=None`` so the
  orchestrator only reports which decisions WOULD be evaluated.  No
  outcomes are appended.  Equivalent to the historical ``--no-provider``
  flag, which is kept as an alias for backwards compatibility.

The summary is written both to stdout (for human callers) and to
``apps/data/decision_ledger/status/outcome_latest.json`` (for the
Settings page).  Status persistence is best-effort: a write failure
appends a ``status_write_error`` field but does not change the exit
code.

Exit codes:

* ``0`` -- evaluation ran (with or without outcomes).
* ``2`` -- ``--provider`` initialization failed.  Status is written
  with ``status="failed"`` so the operator sees the failure on next
  Settings refresh.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
PACKAGES_ROOT = REPO_ROOT / "packages"
SCRIPTS_ROOT = REPO_ROOT / "apps" / "scripts"
for path in (str(CONTROL_PANEL_ROOT), str(PACKAGES_ROOT), str(REPO_ROOT), str(SCRIPTS_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

import decision_ledger  # type: ignore  # noqa: E402


_PROVIDER_CHOICES = ("prism_data", "cache", "none")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate due Decision Ledger outcomes (T+1 / T+3 / T+5).",
    )
    parser.add_argument(
        "--as-of",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Evaluate windows whose as_of trading day is on or before this date "
             "(YYYY-MM-DD; defaults to today).",
    )
    parser.add_argument(
        "--benchmark",
        default="000300",
        help="Benchmark code to fetch alongside each stock (default 000300). "
             "Set to empty to skip the benchmark step.",
    )
    parser.add_argument(
        "--provider",
        default="prism_data",
        choices=_PROVIDER_CHOICES,
        help="Which PriceProvider to use (default prism_data; reuse packages/prism_data).",
    )
    parser.add_argument(
        "--no-provider",
        action="store_true",
        help=(
            "Alias for --provider none -- runs the resolver without a price provider; "
            "prints which decisions WOULD be evaluated, writes nothing to the ledger."
        ),
    )
    parser.add_argument(
        "--data-root",
        default=None,
        help="Override the Prism data root (used by --provider cache; defaults to "
             "<repo_root>/data or PRISM_DATA_ROOT).",
    )
    return parser.parse_args()


def _build_provider(args: argparse.Namespace) -> tuple[object | None, str, str | None]:
    """Return ``(provider, provider_label, init_error)``.

    A ``None`` provider with no error signals deliberate no-provider mode.
    An ``init_error`` string signals a hard failure -- the caller should
    write status with ``status="failed"`` and exit non-zero.
    """

    selection = "none" if args.no_provider else args.provider
    if selection == "none":
        return None, "none", None

    if selection == "cache":
        try:
            provider = decision_ledger.PrismCachePriceProvider(
                data_root=Path(args.data_root) if args.data_root else None,
            )
            return provider, "cache", None
        except Exception as exc:
            return None, "cache", f"PrismCachePriceProvider init failed: {exc}"

    if selection == "prism_data":
        try:
            from decision_ledger_price_provider import (  # type: ignore
                PrismDataPriceProvider,
            )
            provider = PrismDataPriceProvider()
            return provider, "prism_data", None
        except Exception as exc:
            return None, "prism_data", f"PrismDataPriceProvider init failed: {exc}"

    return None, selection, f"unknown provider selection: {selection!r}"


def _write_outcome_status(payload: dict) -> dict:
    """Persist the latest evaluation summary; never raise."""

    try:
        decision_ledger.write_status("outcome", payload)
    except Exception as exc:  # pragma: no cover - defensive
        payload["status_write_error"] = str(exc)
    return payload


def main() -> int:
    args = _parse_args()
    benchmark = (args.benchmark or "").strip() or None
    run_id = os.environ.get("PRISM_SCHEDULED_RUN_ID", "").strip()
    scheduled_via = os.environ.get("PRISM_SCHEDULED_VIA", "").strip()
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    provider, provider_label, init_error = _build_provider(args)

    if init_error is not None:
        status_payload = {
            "status": "failed",
            "task_name": "decision_ledger_outcomes",
            "run_id": run_id,
            "scheduled_via": scheduled_via,
            "provider": provider_label,
            "as_of_date": args.as_of,
            "started_at": started_at,
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": init_error,
        }
        _write_outcome_status(status_payload)
        json.dump(status_payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 2

    summary = decision_ledger.evaluate_due_outcomes(
        as_of_date=args.as_of,
        price_provider=provider,
        benchmark_code=benchmark,
    )

    # Translate orchestrator counts into a status payload the Settings
    # page can render directly.  ``status`` collapses the operational
    # outcome into one of three buckets: "success" (at least one event
    # appended or already_present), "no_provider" (deliberately no
    # provider attached, nothing written), "failed" reserved for the
    # init-error path above.
    if provider is None:
        outcome_status = "no_provider"
    else:
        outcome_status = "success"

    status_payload: dict = {
        "status": outcome_status,
        "task_name": "decision_ledger_outcomes",
        "run_id": run_id,
        "scheduled_via": scheduled_via,
        "provider": provider_label,
        "benchmark": benchmark,
        "as_of_date": summary.get("as_of_date", args.as_of),
        "started_at": started_at,
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "evaluated": int(summary.get("evaluated") or 0),
        "already_present": int(summary.get("already_present") or 0),
        "skipped_no_provider": int(summary.get("skipped_no_provider") or 0),
        "skipped_provider_unavailable": int(summary.get("skipped_provider_unavailable") or 0),
        "data_issue": int(summary.get("data_issue") or 0),
        "errors": int(summary.get("errors") or 0),
        # Keep the most informative per-decision rows; bound the list so
        # the status file does not balloon for very large ledgers.
        "events": list(summary.get("events") or [])[:50],
    }
    _write_outcome_status(status_payload)

    # Stream the orchestrator summary to stdout (back-compat with the
    # previous behaviour).  The status payload is what the UI sees.
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
