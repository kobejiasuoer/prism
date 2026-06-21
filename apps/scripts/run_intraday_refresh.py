#!/usr/bin/env python3
"""Intraday incremental refresh: re-run ai_screening with fresh quotes/capital-flow.

Runs every 30 minutes during trading hours (cron */30 10-14). Does NOT re-scan
the full market — it reuses the 09:40 scan_result.json candidate list, fetches
live quotes + capital flow for those ~30 candidates only, patches the scan data,
and re-runs ai_screening in baseline-only mode (no LLM call).

Output overwrites ai_screening_result.json so the discovery page reads fresh
analysis on its next request.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for p in (str(REPO_ROOT / "packages"), str(REPO_ROOT / "apps" / "control-panel")):
    if p not in sys.path:
        sys.path.insert(0, p)

from screener.ai_screening import run_screening  # noqa: E402
from screener.stage_contract import validate_stage_output  # noqa: E402
from trading_calendar import most_recent_trading_day  # noqa: E402
from prism_data.service import get_data_gateway  # noqa: E402

SCAN_PATH = REPO_ROOT / "packages" / "data" / "scan_result.json"
OUTPUT_PATH = REPO_ROOT / "packages" / "data" / "ai_screening_result.json"


def _collect_candidate_codes(scan_data: dict) -> list[str]:
    """Extract all 6-digit stock codes from the scan's strategy candidates."""
    codes: list[str] = []
    seen: set[str] = set()
    strats = scan_data.get("strategies") or {}
    for sv in strats.values():
        stocks = sv if isinstance(sv, list) else (sv.get("candidates") or sv.get("selected_stocks") or [])
        for s in stocks:
            if not isinstance(s, dict):
                continue
            code = str(s.get("code") or "").strip()
            if len(code) == 6 and code.isdigit() and code not in seen:
                codes.append(code)
                seen.add(code)
    # Also include verification_universe codes
    for s in scan_data.get("verification_universe") or []:
        if isinstance(s, dict):
            code = str(s.get("code") or "").strip()
            if len(code) == 6 and code.isdigit() and code not in seen:
                codes.append(code)
                seen.add(code)
    return codes


def _fetch_fresh_quotes(codes: list[str], trade_date: str) -> dict[str, dict]:
    """Fetch live quotes for the candidate pool. Returns {code: {change_pct, amount_yi, ...}}."""
    if not codes:
        return {}
    gateway = get_data_gateway()
    fresh: dict[str, dict] = {}
    batch_size = 50
    for i in range(0, len(codes), batch_size):
        chunk = codes[i:i + batch_size]
        try:
            result = gateway.fetch_quotes_batch(
                chunk,
                trade_date=trade_date,
                key=f"intraday-quotes-{i // batch_size}",
                allow_fallback=True,
            )
            for row in (result.data or []):
                code = str(row.get("code") or "").strip()
                if len(code) == 6:
                    fresh[code] = {
                        "change_pct": _safe_float(row.get("change_pct")),
                        "price": _safe_float(row.get("price")),
                        "amount": _safe_float(row.get("amount")),
                        "amount_yi": _safe_float(row.get("amount_yi")),
                        "turnover": _safe_float(row.get("turnover")),
                        "high": _safe_float(row.get("high")),
                        "low": _safe_float(row.get("low")),
                        "open": _safe_float(row.get("open")),
                    }
        except Exception:
            continue
    return fresh


def _safe_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _patch_scan_with_fresh_data(scan_data: dict, fresh: dict[str, dict]) -> dict:
    """Patch change_pct/amount/turnover in the scan's strategy candidates + universe."""
    patched = json.loads(json.dumps(scan_data))  # deep copy

    def _patch_stock(s: dict) -> None:
        if not isinstance(s, dict):
            return
        code = str(s.get("code") or "").strip()
        if code not in fresh:
            return
        f = fresh[code]
        if f.get("change_pct") is not None:
            s["change_pct"] = f["change_pct"]
        if f.get("amount_yi") is not None:
            s["amount_yi"] = f["amount_yi"]
        if f.get("amount") is not None:
            s["amount"] = f["amount"]
        if f.get("turnover") is not None:
            s["turnover"] = f["turnover"]
        if f.get("price") is not None:
            s["price"] = f["price"]

    strats = patched.get("strategies") or {}
    for sv in strats.values():
        stocks = sv if isinstance(sv, list) else (sv.get("candidates") or sv.get("selected_stocks") or [])
        for s in stocks:
            _patch_stock(s)
    for s in patched.get("verification_universe") or []:
        _patch_stock(s)

    # Patch market_regime metrics from the fresh universe
    uni = patched.get("verification_universe") or []
    if uni:
        changes = [s.get("change_pct", 0) for s in uni if isinstance(s, dict) and s.get("change_pct") is not None]
        amounts = [s.get("amount_yi", 0) for s in uni if isinstance(s, dict) and s.get("amount_yi")]
        if changes:
            positive = sum(1 for c in changes if c > 0)
            mr = patched.get("market_regime") or {}
            metrics = mr.get("metrics") or {}
            metrics["positive_ratio"] = round(positive / len(changes), 3)
            metrics["avg_change_pct"] = round(sum(changes) / len(changes), 2)
            if amounts:
                metrics["avg_turnover"] = round(sum(amounts) / len(amounts), 1)
            mr["metrics"] = metrics
            patched["market_regime"] = mr

    return patched


def main() -> int:
    if not SCAN_PATH.exists():
        print(f"[intraday-refresh] scan_result.json not found at {SCAN_PATH}, skipping")
        return 0

    trade_date = str(most_recent_trading_day())
    with SCAN_PATH.open("r", encoding="utf-8") as fh:
        scan_data = json.load(fh)

    codes = _collect_candidate_codes(scan_data)
    print(f"[intraday-refresh] {len(codes)} candidates, trade_date={trade_date}")

    fresh = _fetch_fresh_quotes(codes, trade_date)
    print(f"[intraday-refresh] fetched fresh quotes for {len(fresh)}/{len(codes)} codes")

    if not fresh:
        print("[intraday-refresh] no fresh quotes obtained, skipping re-run")
        return 0

    patched_scan = _patch_scan_with_fresh_data(scan_data, fresh)

    # Re-run ai_screening in baseline-only mode (no LLM).
    # run_screening reads scan_data and recomputes valve/confidence/action.
    result = run_screening(patched_scan)
    result["intraday_refresh"] = {
        "refreshed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fresh_codes": len(fresh),
        "baseline_only": True,
    }

    # Validate + write
    try:
        validate_stage_output(result, "ai_screening")
    except Exception as e:
        print(f"[intraday-refresh] stage contract validation failed: {e}")
        return 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    tmp.replace(OUTPUT_PATH)

    sl = result.get("shortlist") or []
    from collections import Counter
    actions = Counter(s.get("suggested_action") for s in sl)
    gate = (result.get("market_regime") or {}).get("execution_gate", {}).get("status", "?")
    print(f"[intraday-refresh] done: gate={gate} shortlist={len(sl)} actions={dict(actions)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
