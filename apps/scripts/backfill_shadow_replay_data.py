"""Backfill local inputs for historical shadow-replay samples.

The script fetches a *research-only* replay dataset:

* current HS300 / CSI500 constituents as an explicitly approximate universe;
* historical daily bars for the requested replay window plus lookback and
  forward-label headroom;
* a manifest and markdown report under ``data/quant/shadow_replay``.

It does not write Decision Ledger records and does not run the production
screener.  Use it as the data-prep step before building shadow decisions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

from trading_calendar import calendar_status  # type: ignore  # noqa: E402


DEFAULT_START_DATE = "2025-05-01"
DEFAULT_END_DATE = "2025-12-31"
DEFAULT_SYMBOLS = "000300:hs300,000905:zz500"
DEFAULT_LOOKBACK_CALENDAR_DAYS = 120
DEFAULT_FORWARD_TRADING_DAYS = 5
DEFAULT_THROTTLE_SECONDS = 0.2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch local research-only data for historical shadow replay.",
    )
    parser.add_argument("--start-date", default=DEFAULT_START_DATE, help="Inclusive replay start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", default=DEFAULT_END_DATE, help="Inclusive replay end date, YYYY-MM-DD.")
    parser.add_argument(
        "--symbols",
        default=DEFAULT_SYMBOLS,
        help="Comma-separated index specs: symbol:pool_label. Default: HS300 + CSI500.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually fetch and write data. Without this flag the script only writes a plan.",
    )
    parser.add_argument(
        "--limit-codes",
        type=int,
        default=0,
        help="Limit fetched stocks after universe dedupe. Use for smoke tests; 0 means no limit.",
    )
    parser.add_argument(
        "--lookback-calendar-days",
        type=int,
        default=DEFAULT_LOOKBACK_CALENDAR_DAYS,
        help="Calendar-day lookback before start date for feature construction.",
    )
    parser.add_argument(
        "--forward-trading-days",
        type=int,
        default=DEFAULT_FORWARD_TRADING_DAYS,
        help="Trading-day headroom after end date for T+n outcome labels.",
    )
    parser.add_argument(
        "--adjust",
        default="qfq",
        choices=("qfq", "hfq", ""),
        help="AkShare adjustment mode for stock_zh_a_hist. Empty string means raw.",
    )
    parser.add_argument(
        "--price-provider",
        default="auto",
        choices=("auto", "akshare", "sina"),
        help="Daily bar provider. auto tries AkShare first, then Sina raw K-line fallback.",
    )
    parser.add_argument(
        "--sina-count",
        type=int,
        default=520,
        help="Daily bars requested from Sina fallback; must be large enough to cover the replay window.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refetch price files even when the target cache file already exists.",
    )
    parser.add_argument(
        "--skip-prices",
        action="store_true",
        help="Fetch/write only the universe artifact.",
    )
    parser.add_argument(
        "--write-research-cache",
        action="store_true",
        help="Also mirror fetched price files into stock-screener research_backfill/cache/price_kline.",
    )
    parser.add_argument(
        "--throttle-seconds",
        type=float,
        default=DEFAULT_THROTTLE_SECONDS,
        help="Sleep between per-code price fetches.",
    )
    parser.add_argument(
        "--output-root",
        default=None,
        help="Override output root. Defaults to data/quant/shadow_replay/<start>_<end>.",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=50,
        help="Write manifest/report after every N processed codes during price fetch. 0 disables checkpoints.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=50,
        help="Print progress after every N processed codes during price fetch. 0 disables progress output.",
    )
    parser.add_argument(
        "--retry-count",
        type=int,
        default=1,
        help="Retries per price code after the first failed attempt.",
    )
    parser.add_argument(
        "--retry-sleep-seconds",
        type=float,
        default=3.0,
        help="Base sleep before retrying a failed price fetch.",
    )
    parser.add_argument(
        "--max-consecutive-failures",
        type=int,
        default=25,
        help="Stop early after this many consecutive price failures. 0 disables the guard.",
    )
    return parser.parse_args()


def parse_date(value: str) -> date:
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def compact_date(value: str | date) -> str:
    if isinstance(value, date):
        value = value.strftime("%Y-%m-%d")
    return str(value)[:10].replace("-", "")


def day_range(start: date, end: date) -> Iterable[date]:
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += timedelta(days=1)


def trading_days(start: date, end: date) -> list[str]:
    return [
        day.strftime("%Y-%m-%d")
        for day in day_range(start, end)
        if calendar_status(day).get("status") == "trading"
    ]


def nth_trading_day_after(value: date, steps: int) -> date:
    cursor = value
    remaining = max(0, int(steps))
    safety = 60
    while remaining > 0 and safety > 0:
        cursor += timedelta(days=1)
        if calendar_status(cursor).get("status") == "trading":
            remaining -= 1
        safety -= 1
    return cursor


def safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def workspace_relative(path: str | Path) -> str:
    target = Path(path)
    try:
        return str(target.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(target)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def parse_symbols(value: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for chunk in str(value or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            symbol, label = chunk.split(":", 1)
        else:
            symbol, label = chunk, chunk
        symbol = symbol.strip()
        label = label.strip().lower()
        if symbol:
            out.append((symbol, label or symbol))
    return out


def load_akshare():
    import akshare as ak  # type: ignore

    return ak


def fetch_index_constituents(symbol: str, pool: str) -> list[dict[str, Any]]:
    ak = load_akshare()
    frame = ak.index_stock_cons_csindex(symbol=symbol)
    if frame is None or frame.empty:
        raise RuntimeError(f"empty index constituents for {symbol}")
    rows: list[dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        code = str(record.get("成分券代码") or record.get("code") or "").strip()
        if code.isdigit():
            code = code.zfill(6)
        if len(code) != 6 or not code.isdigit():
            continue
        rows.append(
            {
                "code": code,
                "symbol": ("sh" if code.startswith("6") else "sz") + code,
                "name": str(record.get("成分券名称") or record.get("name") or "").strip(),
                "source_pool": pool,
                "index_symbol": symbol,
            }
        )
    return rows


def merge_constituents(groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for rows in groups:
        for row in rows:
            code = str(row.get("code") or "").zfill(6)
            if not code:
                continue
            if code not in merged:
                merged[code] = dict(row)
                merged[code]["source_pools"] = [row.get("source_pool")]
                continue
            pools = list(merged[code].get("source_pools") or [])
            pool = row.get("source_pool")
            if pool and pool not in pools:
                pools.append(pool)
            merged[code]["source_pools"] = pools
            merged[code]["source_pool"] = "+".join(str(item) for item in pools if item)
    return sorted(merged.values(), key=lambda item: str(item.get("code") or ""))


def normalize_akshare_price_rows(frame: Any, *, code: str, adjust: str, start: str, end: str) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    rows: list[dict[str, Any]] = []
    for record in frame.to_dict(orient="records"):
        trade_date = str(record.get("日期") or record.get("date") or "")[:10]
        if not trade_date or trade_date < start or trade_date > end:
            continue
        rows.append(
            {
                "date": trade_date,
                "trade_date": trade_date,
                "code": code,
                "open": safe_float(record.get("开盘")),
                "close": safe_float(record.get("收盘")),
                "high": safe_float(record.get("最高")),
                "low": safe_float(record.get("最低")),
                "volume": safe_float(record.get("成交量")),
                "amount": safe_float(record.get("成交额")),
                "amplitude": safe_float(record.get("振幅")),
                "change_pct": safe_float(record.get("涨跌幅")),
                "change": safe_float(record.get("涨跌额")),
                "turnover": safe_float(record.get("换手率")),
                "source": "akshare.stock_zh_a_hist",
                "adjust": adjust or "raw",
            }
        )
    rows.sort(key=lambda row: row["date"])
    return rows


def normalize_sina_price_rows(raw_rows: list[dict[str, Any]], *, code: str, start: str, end: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in raw_rows:
        trade_date = str(record.get("trade_date") or record.get("day") or record.get("date") or "")[:10]
        if not trade_date or trade_date < start or trade_date > end:
            continue
        rows.append(
            {
                "date": trade_date,
                "trade_date": trade_date,
                "code": code,
                "open": safe_float(record.get("open")),
                "close": safe_float(record.get("close")),
                "high": safe_float(record.get("high")),
                "low": safe_float(record.get("low")),
                "volume": safe_float(record.get("volume")),
                "amount": safe_float(record.get("amount")),
                "amplitude": safe_float(record.get("amplitude")),
                "change_pct": safe_float(record.get("change_pct")),
                "change": safe_float(record.get("change")),
                "turnover": safe_float(record.get("turnover")),
                "source": "sina.kline",
                "adjust": "raw",
            }
        )
    rows.sort(key=lambda row: row["date"])
    return rows


def fetch_price_rows_akshare(code: str, *, fetch_start: str, fetch_end: str, adjust: str) -> list[dict[str, Any]]:
    ak = load_akshare()
    frame = ak.stock_zh_a_hist(
        symbol=code,
        period="daily",
        start_date=compact_date(fetch_start),
        end_date=compact_date(fetch_end),
        adjust=adjust,
    )
    return normalize_akshare_price_rows(frame, code=code, adjust=adjust, start=fetch_start, end=fetch_end)


def fetch_price_rows_sina(code: str, *, fetch_start: str, fetch_end: str, count: int) -> list[dict[str, Any]]:
    packages_root = REPO_ROOT / "packages"
    if str(packages_root) not in sys.path:
        sys.path.insert(0, str(packages_root))
    from prism_data.contracts import DatasetStatus  # type: ignore
    from prism_data.providers.sina import SinaProvider  # type: ignore

    result = SinaProvider().fetch_kline(code, count=count)
    if result.status != DatasetStatus.OK:
        raise RuntimeError(result.error or f"sina kline failed for {code}")
    rows = normalize_sina_price_rows(list(result.data or []), code=code, start=fetch_start, end=fetch_end)
    if not rows:
        raise RuntimeError(f"sina returned no rows inside [{fetch_start}, {fetch_end}] for {code}")
    return rows


def fetch_price_rows(
    code: str,
    *,
    fetch_start: str,
    fetch_end: str,
    adjust: str,
    provider: str,
    sina_count: int,
) -> tuple[list[dict[str, Any]], str, str | None]:
    if provider == "sina":
        return fetch_price_rows_sina(code, fetch_start=fetch_start, fetch_end=fetch_end, count=sina_count), "sina", None
    if provider == "akshare":
        return fetch_price_rows_akshare(code, fetch_start=fetch_start, fetch_end=fetch_end, adjust=adjust), "akshare", None

    akshare_error: str | None = None
    try:
        rows = fetch_price_rows_akshare(code, fetch_start=fetch_start, fetch_end=fetch_end, adjust=adjust)
        if rows:
            return rows, "akshare", None
        akshare_error = "akshare returned empty rows"
    except Exception as exc:
        akshare_error = str(exc)
    rows = fetch_price_rows_sina(code, fetch_start=fetch_start, fetch_end=fetch_end, count=sina_count)
    return rows, "sina", akshare_error


def build_paths(args: argparse.Namespace) -> dict[str, Path]:
    if args.output_root:
        root = Path(args.output_root).expanduser()
    else:
        root = (
            REPO_ROOT
            / "data"
            / "quant"
            / "shadow_replay"
            / f"{compact_date(args.start_date)}_{compact_date(args.end_date)}"
        )
    return {
        "root": root,
        "universe_dir": root / "universe",
        "price_dir": root / "price_kline",
        "manifest": root / "manifest.json",
        "report": root / "report.md",
        "research_price_dir": REPO_ROOT / "stock-screener" / "data" / "research_backfill" / "cache" / "price_kline",
    }


def price_file_name(code: str, fetch_start: str, fetch_end: str) -> str:
    return f"{code}_{compact_date(fetch_start)}_{compact_date(fetch_end)}.json"


def write_report(manifest: dict[str, Any], path: Path) -> None:
    summary = manifest["summary"]
    args = manifest["args"]
    lines = [
        "# Shadow Replay Data Backfill",
        "",
        f"Generated at: `{manifest['generated_at']}`",
        "",
        "## Scope",
        "",
        f"- Replay window: `{args['start_date']}` to `{args['end_date']}`",
        f"- Fetch window: `{summary['fetch_start']}` to `{summary['fetch_end']}`",
        f"- Universe policy: `{summary['universe_policy']}`",
        f"- Execute: `{args['execute']}`",
        f"- Limit codes: `{args['limit_codes']}`",
        "",
        "## Result",
        "",
        f"- Index rows fetched: `{summary['index_rows']}`",
        f"- Unique universe codes: `{summary['unique_universe_codes']}`",
        f"- Price files written: `{summary['price_files_written']}`",
        f"- Price files skipped existing: `{summary['price_files_skipped_existing']}`",
        f"- Price files available: `{summary.get('price_files_available', 0)}`",
        f"- Price fetch failures: `{summary['price_fetch_failures']}`",
        f"- Price rows written: `{summary['price_rows_written']}`",
        f"- Price rows available: `{summary.get('price_rows_available', 0)}`",
        f"- Price provider counts: `{summary.get('price_provider_counts', {})}`",
        f"- Price fallback count: `{summary.get('price_fallback_count', 0)}`",
        f"- Stop reason: `{summary.get('stop_reason') or ''}`",
        "",
        "## Notes",
        "",
        "- This is research-only shadow replay input data.",
        "- The initial universe uses current index constituents as an approximation unless a point-in-time constituent source is added later.",
        "- No Decision Ledger records are written by this job.",
        "",
    ]
    if manifest.get("errors"):
        lines.extend(["## Errors", ""])
        for error in manifest["errors"][:50]:
            lines.append(f"- `{error.get('code') or error.get('symbol')}`: {error.get('error')}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    start = parse_date(args.start_date)
    end = parse_date(args.end_date)
    if end < start:
        raise SystemExit("--end-date must be on or after --start-date")

    replay_days = trading_days(start, end)
    fetch_start = (start - timedelta(days=max(0, args.lookback_calendar_days))).strftime("%Y-%m-%d")
    fetch_end = nth_trading_day_after(end, args.forward_trading_days).strftime("%Y-%m-%d")
    symbols = parse_symbols(args.symbols)
    paths = build_paths(args)

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "args": {
            "start_date": args.start_date,
            "end_date": args.end_date,
            "symbols": args.symbols,
            "execute": bool(args.execute),
            "limit_codes": int(args.limit_codes),
            "lookback_calendar_days": int(args.lookback_calendar_days),
            "forward_trading_days": int(args.forward_trading_days),
            "adjust": args.adjust or "raw",
            "price_provider": args.price_provider,
            "sina_count": int(args.sina_count),
            "force": bool(args.force),
            "skip_prices": bool(args.skip_prices),
            "write_research_cache": bool(args.write_research_cache),
            "throttle_seconds": float(args.throttle_seconds),
            "checkpoint_every": int(args.checkpoint_every),
            "progress_every": int(args.progress_every),
            "retry_count": int(args.retry_count),
            "retry_sleep_seconds": float(args.retry_sleep_seconds),
            "max_consecutive_failures": int(args.max_consecutive_failures),
        },
        "summary": {
            "status": "planned" if not args.execute else "running",
            "replay_trading_days": len(replay_days),
            "first_replay_trading_day": replay_days[0] if replay_days else None,
            "last_replay_trading_day": replay_days[-1] if replay_days else None,
            "fetch_start": fetch_start,
            "fetch_end": fetch_end,
            "universe_policy": "current_constituents_approx",
            "index_rows": 0,
            "unique_universe_codes": 0,
            "price_files_written": 0,
            "price_files_skipped_existing": 0,
            "price_fetch_failures": 0,
            "price_rows_written": 0,
            "price_files_available": 0,
            "price_rows_available": 0,
            "research_cache_files_written": 0,
            "price_provider_counts": {},
            "price_fallback_count": 0,
        },
        "paths": {key: workspace_relative(value) for key, value in paths.items()},
        "universe": {
            "symbols": [{"symbol": symbol, "pool": pool} for symbol, pool in symbols],
            "files": [],
            "pool_counts": {},
        },
        "price_files": [],
        "errors": [],
    }

    if not args.execute:
        paths["root"].mkdir(parents=True, exist_ok=True)
        manifest["summary"]["status"] = "planned"
        write_json(paths["manifest"], manifest)
        write_report(manifest, paths["report"])
        print(json.dumps({
            "status": "planned",
            "trading_days": len(replay_days),
            "fetch_start": fetch_start,
            "fetch_end": fetch_end,
            "manifest": workspace_relative(paths["manifest"]),
            "report": workspace_relative(paths["report"]),
            "note": "rerun with --execute to fetch universe and prices",
        }, ensure_ascii=False, indent=2))
        return 0

    universe_groups: list[list[dict[str, Any]]] = []
    index_rows = 0
    for symbol, pool in symbols:
        try:
            rows = fetch_index_constituents(symbol, pool)
            index_rows += len(rows)
            universe_groups.append(rows)
            universe_file = paths["universe_dir"] / f"{pool}_{symbol}_current_constituents.json"
            write_json(universe_file, rows)
            manifest["universe"]["files"].append(
                {
                    "symbol": symbol,
                    "pool": pool,
                    "path": workspace_relative(universe_file),
                    "rows": len(rows),
                    "sha256": sha256_file(universe_file),
                }
            )
        except Exception as exc:
            manifest["errors"].append({"symbol": symbol, "pool": pool, "error": str(exc)})

    universe = merge_constituents(universe_groups)
    if args.limit_codes and args.limit_codes > 0:
        universe = universe[: args.limit_codes]
    merged_universe_file = paths["universe_dir"] / "merged_current_constituents_approx.json"
    write_json(merged_universe_file, universe)
    pool_counts = Counter(str(row.get("source_pool") or "") for row in universe)

    manifest["summary"]["index_rows"] = index_rows
    manifest["summary"]["unique_universe_codes"] = len(universe)
    manifest["universe"]["merged_file"] = workspace_relative(merged_universe_file)
    manifest["universe"]["merged_sha256"] = sha256_file(merged_universe_file)
    manifest["universe"]["pool_counts"] = dict(pool_counts)

    if not args.skip_prices:
        consecutive_failures = 0
        stopped_early = False
        stop_reason = ""
        for index, row in enumerate(universe, start=1):
            code = str(row.get("code") or "").zfill(6)
            if not code:
                continue
            target = paths["price_dir"] / price_file_name(code, fetch_start, fetch_end)
            if target.exists() and not args.force:
                existing_rows = read_json(target)
                row_count = len(existing_rows) if isinstance(existing_rows, list) else 0
                first_date = existing_rows[0].get("date") if row_count and isinstance(existing_rows[0], dict) else None
                last_date = existing_rows[-1].get("date") if row_count and isinstance(existing_rows[-1], dict) else None
                manifest["price_files"].append(
                    {
                        "code": code,
                        "name": row.get("name"),
                        "path": workspace_relative(target),
                        "rows": row_count,
                        "first_date": first_date,
                        "last_date": last_date,
                        "provider": "existing",
                        "fallback_reason": None,
                        "sha256": sha256_file(target),
                    }
                )
                manifest["summary"]["price_files_skipped_existing"] += 1
                manifest["summary"]["price_files_available"] += 1
                manifest["summary"]["price_rows_available"] += row_count
                consecutive_failures = 0
                continue
            try:
                last_error: Exception | None = None
                price_rows: list[dict[str, Any]] = []
                provider_used = ""
                fallback_reason: str | None = None
                attempts = max(1, int(args.retry_count) + 1)
                for attempt in range(attempts):
                    try:
                        price_rows, provider_used, fallback_reason = fetch_price_rows(
                            code,
                            fetch_start=fetch_start,
                            fetch_end=fetch_end,
                            adjust=args.adjust or "",
                            provider=args.price_provider,
                            sina_count=args.sina_count,
                        )
                        last_error = None
                        break
                    except Exception as exc:
                        last_error = exc
                        if attempt + 1 < attempts:
                            time.sleep(max(0.0, float(args.retry_sleep_seconds)) * (attempt + 1))
                if last_error is not None:
                    raise last_error
                if not price_rows:
                    raise RuntimeError("empty price rows")
                write_json(target, price_rows)
                file_record = {
                    "code": code,
                    "name": row.get("name"),
                    "path": workspace_relative(target),
                    "rows": len(price_rows),
                    "first_date": price_rows[0].get("date"),
                    "last_date": price_rows[-1].get("date"),
                    "provider": provider_used,
                    "fallback_reason": fallback_reason,
                    "sha256": sha256_file(target),
                }
                manifest["price_files"].append(file_record)
                manifest["summary"]["price_files_written"] += 1
                manifest["summary"]["price_rows_written"] += len(price_rows)
                manifest["summary"]["price_files_available"] += 1
                manifest["summary"]["price_rows_available"] += len(price_rows)
                provider_counts = manifest["summary"].setdefault("price_provider_counts", {})
                provider_counts[provider_used] = int(provider_counts.get(provider_used) or 0) + 1
                if fallback_reason:
                    manifest["summary"]["price_fallback_count"] += 1
                if args.write_research_cache:
                    mirror = paths["research_price_dir"] / target.name
                    write_json(mirror, price_rows)
                    manifest["summary"]["research_cache_files_written"] += 1
                if args.checkpoint_every > 0 and index % args.checkpoint_every == 0:
                    manifest["summary"]["status"] = "running"
                    write_json(paths["manifest"], manifest)
                    write_report(manifest, paths["report"])
                if args.progress_every > 0 and index % args.progress_every == 0:
                    print(
                        json.dumps(
                            {
                                "progress": f"{index}/{len(universe)}",
                                "price_files_written": manifest["summary"]["price_files_written"],
                                "price_fetch_failures": manifest["summary"]["price_fetch_failures"],
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                if args.throttle_seconds > 0 and index < len(universe):
                    time.sleep(args.throttle_seconds)
                consecutive_failures = 0
            except Exception as exc:
                manifest["summary"]["price_fetch_failures"] += 1
                manifest["errors"].append({"code": code, "name": row.get("name"), "error": str(exc)})
                consecutive_failures += 1
                if args.checkpoint_every > 0 and index % args.checkpoint_every == 0:
                    manifest["summary"]["status"] = "running"
                    write_json(paths["manifest"], manifest)
                    write_report(manifest, paths["report"])
                if args.progress_every > 0 and index % args.progress_every == 0:
                    print(
                        json.dumps(
                            {
                                "progress": f"{index}/{len(universe)}",
                                "price_files_written": manifest["summary"]["price_files_written"],
                                "price_fetch_failures": manifest["summary"]["price_fetch_failures"],
                            },
                            ensure_ascii=False,
                        ),
                        flush=True,
                    )
                if args.max_consecutive_failures > 0 and consecutive_failures >= args.max_consecutive_failures:
                    stopped_early = True
                    stop_reason = f"stopped after {consecutive_failures} consecutive price failures"
                    manifest["summary"]["status"] = "stopped_early"
                    manifest["summary"]["stop_reason"] = stop_reason
                    write_json(paths["manifest"], manifest)
                    write_report(manifest, paths["report"])
                    break

        if stopped_early:
            manifest["summary"]["status"] = "stopped_early"
            manifest["summary"]["stop_reason"] = stop_reason
        else:
            manifest["summary"]["status"] = "completed_with_errors" if manifest["errors"] else "completed"
    else:
        manifest["summary"]["status"] = "completed_with_errors" if manifest["errors"] else "completed"
    write_json(paths["manifest"], manifest)
    write_report(manifest, paths["report"])
    print(json.dumps({
        "status": manifest["summary"]["status"],
        "unique_universe_codes": manifest["summary"]["unique_universe_codes"],
        "price_files_written": manifest["summary"]["price_files_written"],
        "price_fetch_failures": manifest["summary"]["price_fetch_failures"],
        "manifest": workspace_relative(paths["manifest"]),
        "report": workspace_relative(paths["report"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
