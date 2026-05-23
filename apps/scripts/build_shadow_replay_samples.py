"""Build research-only shadow samples from replay price cache.

This generator is intentionally labelled ``price_signal_baseline``.  It is
not the production Prism AI screener.  Its job is to quickly create a large,
auditable historical shadow sample set from local daily bars so we can study
setup / rank / risk buckets while the full historical screener replay is
being built.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
if str(CONTROL_PANEL_ROOT) not in sys.path:
    sys.path.insert(0, str(CONTROL_PANEL_ROOT))

from trading_calendar import calendar_status  # type: ignore  # noqa: E402


DEFAULT_START_DATE = "2025-05-01"
DEFAULT_END_DATE = "2025-12-31"
DEFAULT_REPLAY_ROOT = REPO_ROOT / "data" / "quant" / "shadow_replay" / "20250501_20251231"
WINDOWS = (1, 3, 5)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build price-signal historical shadow samples.")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", default=DEFAULT_END_DATE)
    parser.add_argument("--replay-root", default=str(DEFAULT_REPLAY_ROOT))
    parser.add_argument("--top-n", type=int, default=10, help="Top ranked observations per day.")
    parser.add_argument("--near-n", type=int, default=20, help="Near-miss observations per day.")
    parser.add_argument("--reject-n", type=int, default=10, help="Risk-rejected observations per day.")
    parser.add_argument("--min-lookback", type=int, default=20)
    parser.add_argument("--output-panel", default=None)
    parser.add_argument("--output-labels", default=None)
    parser.add_argument("--output-report", default=None)
    parser.add_argument("--output-manifest", default=None)
    return parser.parse_args()


def parse_date(value: str) -> date:
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


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


def workspace_relative(path: str | Path) -> str:
    target = Path(path)
    try:
        return str(target.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(target)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def output_paths(args: argparse.Namespace, replay_root: Path) -> dict[str, Path]:
    return {
        "panel": Path(args.output_panel).expanduser() if args.output_panel else replay_root / "shadow_signal_panel.jsonl",
        "labels": Path(args.output_labels).expanduser() if args.output_labels else replay_root / "shadow_forward_labels.jsonl",
        "report": Path(args.output_report).expanduser() if args.output_report else replay_root / "shadow_signal_report.md",
        "manifest": Path(args.output_manifest).expanduser() if args.output_manifest else replay_root / "shadow_signal_manifest.json",
    }


def load_universe(replay_root: Path) -> dict[str, dict[str, Any]]:
    path = replay_root / "universe" / "merged_current_constituents_approx.json"
    rows = load_json(path)
    if not isinstance(rows, list):
        raise RuntimeError(f"universe file is not a list: {path}")
    return {str(row.get("code") or "").zfill(6): dict(row) for row in rows if row.get("code")}


def load_price_cache(replay_root: Path) -> dict[str, list[dict[str, Any]]]:
    price_dir = replay_root / "price_kline"
    by_code: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(price_dir.glob("*.json")):
        code = path.name.split("_", 1)[0]
        rows = load_json(path)
        if not isinstance(rows, list):
            continue
        clean: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            day = str(row.get("date") or row.get("trade_date") or "")[:10]
            close = safe_float(row.get("close"))
            if not day or close is None or close <= 0:
                continue
            clean.append({**row, "date": day, "close": close})
        clean.sort(key=lambda item: item["date"])
        if clean:
            by_code[code] = clean
    return by_code


def rolling_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return mean(values)


def setup_type(*, ret_1d: float, ret_5d: float, range_pos_20: float, volume_ratio_5: float | None, close: float, ma10: float | None) -> str:
    if ret_1d >= 0.075 or range_pos_20 >= 0.93:
        return "overheated_reject"
    if volume_ratio_5 is not None and volume_ratio_5 >= 1.35 and ret_1d > 0:
        return "volume_rebound"
    if ma10 and close >= ma10 and 0.25 <= range_pos_20 <= 0.65 and ret_5d >= -0.03:
        return "pullback_support"
    if ret_5d > 0.035 and range_pos_20 >= 0.55:
        return "trend_follow"
    return "mixed_observation"


def risk_flags(*, ret_1d: float, ret_5d: float, range_pos_20: float, volume_ratio_5: float | None, ma20: float | None, close: float) -> list[str]:
    flags: list[str] = []
    if ret_1d >= 0.075:
        flags.append("one_day_overheat")
    if range_pos_20 >= 0.93:
        flags.append("range_overextended")
    if volume_ratio_5 is not None and volume_ratio_5 >= 3.0:
        flags.append("volume_spike")
    if ma20 and close < ma20:
        flags.append("below_ma20")
    if ret_5d <= -0.08:
        flags.append("five_day_weak")
    return flags


def score_candidate(row: dict[str, Any]) -> float:
    score = 50.0
    score += clamp(float(row["ret_1d_pct"]), -5.0, 8.0) * 3.0
    score += clamp(float(row["ret_5d_pct"]), -10.0, 18.0) * 1.2
    score += (float(row["range_pos_20"]) - 0.5) * 18.0
    volume_ratio = row.get("volume_ratio_5")
    if volume_ratio is not None:
        score += clamp((float(volume_ratio) - 1.0) * 6.0, -5.0, 12.0)
    if row.get("ma_stack") == "bullish":
        score += 8.0
    if row.get("setup_type") == "pullback_support":
        score += 5.0
    if row.get("setup_type") == "overheated_reject":
        score -= 18.0
    if "below_ma20" in row.get("risk_flags", []):
        score -= 10.0
    return round(score, 4)


def build_daily_features(
    *,
    code: str,
    rows: list[dict[str, Any]],
    index: int,
    min_lookback: int,
) -> dict[str, Any] | None:
    if index < min_lookback:
        return None
    current = rows[index]
    close = safe_float(current.get("close"))
    prev_close = safe_float(rows[index - 1].get("close"))
    if close is None or prev_close is None or prev_close <= 0:
        return None
    prior_5 = rows[index - 5:index]
    prior_10 = rows[index - 10:index]
    prior_20 = rows[index - 20:index]
    if len(prior_20) < 20:
        return None
    closes_5 = [float(item["close"]) for item in prior_5 if safe_float(item.get("close")) is not None]
    closes_10 = [float(item["close"]) for item in prior_10 if safe_float(item.get("close")) is not None]
    closes_20 = [float(item["close"]) for item in prior_20 if safe_float(item.get("close")) is not None]
    if len(closes_20) < 20:
        return None
    ret_1d = close / prev_close - 1.0
    ret_5d = close / closes_5[0] - 1.0 if closes_5 and closes_5[0] > 0 else 0.0
    high_20 = max(closes_20)
    low_20 = min(closes_20)
    range_pos_20 = (close - low_20) / (high_20 - low_20) if high_20 > low_20 else 0.5
    ma5 = rolling_mean(closes_5)
    ma10 = rolling_mean(closes_10)
    ma20 = rolling_mean(closes_20)
    volumes_5 = [safe_float(item.get("volume")) for item in prior_5]
    volumes_5_clean = [float(value) for value in volumes_5 if value is not None and value > 0]
    current_volume = safe_float(current.get("volume"))
    volume_ratio_5 = None
    if current_volume is not None and volumes_5_clean:
        avg_volume = mean(volumes_5_clean)
        if avg_volume > 0:
            volume_ratio_5 = current_volume / avg_volume
    ma_stack = "bullish" if ma5 and ma10 and ma20 and close > ma5 > ma10 > ma20 else "mixed"
    setup = setup_type(
        ret_1d=ret_1d,
        ret_5d=ret_5d,
        range_pos_20=range_pos_20,
        volume_ratio_5=volume_ratio_5,
        close=close,
        ma10=ma10,
    )
    flags = risk_flags(
        ret_1d=ret_1d,
        ret_5d=ret_5d,
        range_pos_20=range_pos_20,
        volume_ratio_5=volume_ratio_5,
        ma20=ma20,
        close=close,
    )
    item: dict[str, Any] = {
        "code": code,
        "trade_date": current["date"],
        "close": close,
        "ret_1d_pct": round(ret_1d * 100, 4),
        "ret_5d_pct": round(ret_5d * 100, 4),
        "range_pos_20": round(range_pos_20, 4),
        "volume_ratio_5": round(volume_ratio_5, 4) if volume_ratio_5 is not None else None,
        "ma5": round(ma5, 4) if ma5 else None,
        "ma10": round(ma10, 4) if ma10 else None,
        "ma20": round(ma20, 4) if ma20 else None,
        "ma_stack": ma_stack,
        "setup_type": setup,
        "risk_flags": flags,
    }
    item["score"] = score_candidate(item)
    return item


def classify_rows_for_day(features: list[dict[str, Any]], *, top_n: int, near_n: int, reject_n: int) -> list[dict[str, Any]]:
    ranked = sorted(features, key=lambda item: (float(item["score"]), float(item["ret_5d_pct"])), reverse=True)
    hard_risk_flags = {"one_day_overheat", "range_overextended", "below_ma20"}
    candidate_pool = [
        item
        for item in ranked
        if item.get("setup_type") != "overheated_reject"
        and not (hard_risk_flags & set(item.get("risk_flags") or []))
    ]
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    for rank, item in enumerate(candidate_pool[:top_n], start=1):
        selected.append({**item, "bucket": "top_observe", "rank": rank, "action": "observe"})
        used.add(item["code"])
    near_rows = [item for item in candidate_pool if item["code"] not in used]
    for rank, item in enumerate(near_rows[:near_n], start=1):
        selected.append({**item, "bucket": "near_miss", "rank": rank, "action": "observe"})
        used.add(item["code"])
    rejected_candidates = [
        item
        for item in ranked
        if item["code"] not in used
        and (
            item.get("setup_type") == "overheated_reject"
            or bool(hard_risk_flags & set(item.get("risk_flags") or []))
        )
    ]
    for rank, item in enumerate(rejected_candidates[:reject_n], start=1):
        selected.append({**item, "bucket": "risk_reject", "rank": rank, "action": "skip"})
        used.add(item["code"])
    return selected


def build_panel(
    *,
    replay_root: Path,
    start_date: str,
    end_date: str,
    top_n: int,
    near_n: int,
    reject_n: int,
    min_lookback: int,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    universe = load_universe(replay_root)
    prices = load_price_cache(replay_root)
    dates = trading_days(parse_date(start_date), parse_date(end_date))
    features_by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    index_by_code_date: dict[tuple[str, str], int] = {}

    for code, rows in prices.items():
        for idx, row in enumerate(rows):
            index_by_code_date[(code, row["date"])] = idx
        for idx, _row in enumerate(rows):
            item = build_daily_features(code=code, rows=rows, index=idx, min_lookback=min_lookback)
            if item and start_date <= item["trade_date"] <= end_date:
                features_by_date[item["trade_date"]].append(item)

    panel_rows: list[dict[str, Any]] = []
    for trade_date in dates:
        daily_features = features_by_date.get(trade_date, [])
        selected = classify_rows_for_day(daily_features, top_n=top_n, near_n=near_n, reject_n=reject_n)
        for item in selected:
            info = universe.get(item["code"], {})
            panel_row_id = sha256_text(
                "|".join([
                    "price_signal_baseline",
                    item["trade_date"],
                    item["code"],
                    item["bucket"],
                    str(item["rank"]),
                ])
            )[:24]
            panel_rows.append(
                {
                    "schema_version": 1,
                    "panel_row_id": panel_row_id,
                    "sample_origin": "historical_shadow",
                    "source_lane": "shadow_price_signal_baseline",
                    "universe_policy": "current_constituents_approx",
                    "trade_date": item["trade_date"],
                    "code": item["code"],
                    "name": info.get("name") or "",
                    "source_pool": info.get("source_pool") or "",
                    "bucket": item["bucket"],
                    "rank": item["rank"],
                    "action": item["action"],
                    "setup_type": item["setup_type"],
                    "score": item["score"],
                    "risk_flags": item["risk_flags"],
                    "metrics": {
                        "close": item["close"],
                        "ret_1d_pct": item["ret_1d_pct"],
                        "ret_5d_pct": item["ret_5d_pct"],
                        "range_pos_20": item["range_pos_20"],
                        "volume_ratio_5": item["volume_ratio_5"],
                        "ma5": item["ma5"],
                        "ma10": item["ma10"],
                        "ma20": item["ma20"],
                        "ma_stack": item["ma_stack"],
                    },
                    "instruction": instruction_for(item, info),
                    "source_artifact": workspace_relative(replay_root),
                }
            )
    return panel_rows, prices, index_by_code_date


def instruction_for(item: dict[str, Any], info: dict[str, Any]) -> str:
    name = info.get("name") or item["code"]
    if item["bucket"] == "risk_reject":
        return f"{name}：价格影子样本标记为风险剔除；只用于复盘，不视为 Prism 买入信号。"
    if item["bucket"] == "top_observe":
        return f"{name}：价格影子样本进入 Top 观察；后续用 T+1/T+3/T+5 检查强度是否延续。"
    return f"{name}：价格影子样本接近入池；用于比较近候选和 Top 观察的差异。"


def build_labels(panel_rows: list[dict[str, Any]], prices: dict[str, list[dict[str, Any]]], index_by_code_date: dict[tuple[str, str], int]) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    for row in panel_rows:
        code = row["code"]
        trade_date = row["trade_date"]
        price_rows = prices.get(code) or []
        signal_index = index_by_code_date.get((code, trade_date))
        signal_close = safe_float((price_rows[signal_index] if signal_index is not None else {}).get("close"))
        for window in WINDOWS:
            label_id = sha256_text(f"{row['panel_row_id']}|T+{window}")[:24]
            label = {
                "schema_version": 1,
                "label_id": label_id,
                "panel_row_id": row["panel_row_id"],
                "sample_origin": row["sample_origin"],
                "source_lane": row["source_lane"],
                "trade_date": trade_date,
                "code": code,
                "name": row["name"],
                "bucket": row["bucket"],
                "action": row["action"],
                "setup_type": row["setup_type"],
                "window": f"T+{window}",
                "holding_window_days": window,
                "label_status": "unavailable",
                "entry_close": signal_close,
                "exit_trade_date": None,
                "exit_close": None,
                "raw_return": None,
                "classification": None,
                "unavailable_reason": None,
            }
            if signal_index is None or signal_close is None or signal_close <= 0:
                label["unavailable_reason"] = "signal_price_missing"
                labels.append(label)
                continue
            exit_index = signal_index + window
            if exit_index >= len(price_rows):
                label["unavailable_reason"] = "forward_price_missing"
                labels.append(label)
                continue
            exit_row = price_rows[exit_index]
            exit_close = safe_float(exit_row.get("close"))
            if exit_close is None or exit_close <= 0:
                label["unavailable_reason"] = "exit_price_missing"
                labels.append(label)
                continue
            raw_return = exit_close / signal_close - 1.0
            label.update(
                {
                    "label_status": "available_research_only",
                    "exit_trade_date": exit_row.get("date"),
                    "exit_close": round(exit_close, 6),
                    "raw_return": round(raw_return, 8),
                    "classification": classify_outcome(row["action"], raw_return),
                }
            )
            labels.append(label)
    return labels


def classify_outcome(action: str, raw_return: float) -> str:
    if action == "skip":
        if raw_return <= -0.02:
            return "avoided_loss"
        if raw_return >= 0.03:
            return "missed_opportunity"
        return "inconclusive"
    if raw_return >= 0.03:
        return "validated"
    if raw_return <= -0.03:
        return "invalidated"
    return "inconclusive"


def render_report(manifest: dict[str, Any]) -> str:
    summary = manifest["summary"]
    lines = [
        "# Shadow Replay Price-Signal Samples",
        "",
        f"Generated at: `{manifest['generated_at']}`",
        "",
        "## Scope",
        "",
        f"- Replay window: `{summary['start_date']}` to `{summary['end_date']}`",
        "- Sample origin: `historical_shadow`",
        "- Source lane: `shadow_price_signal_baseline`",
        "- Important: this is not the production Prism AI screener.",
        "",
        "## Counts",
        "",
        f"- Panel rows: `{summary['panel_rows']}`",
        f"- Label rows: `{summary['label_rows']}`",
        f"- Available labels: `{summary['available_labels']}`",
        f"- Trade dates with samples: `{summary['trade_dates_with_samples']}`",
        f"- Codes covered in samples: `{summary['sample_codes']}`",
        "",
        "## Buckets",
        "",
    ]
    for bucket, count in summary["bucket_counts"].items():
        lines.append(f"- `{bucket}`: `{count}`")
    lines.extend(["", "## Label Outcomes", ""])
    for key, count in summary["classification_counts"].items():
        lines.append(f"- `{key}`: `{count}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    replay_root = Path(args.replay_root).expanduser()
    paths = output_paths(args, replay_root)
    panel_rows, prices, index_by_code_date = build_panel(
        replay_root=replay_root,
        start_date=args.start_date,
        end_date=args.end_date,
        top_n=args.top_n,
        near_n=args.near_n,
        reject_n=args.reject_n,
        min_lookback=args.min_lookback,
    )
    labels = build_labels(panel_rows, prices, index_by_code_date)
    write_jsonl(paths["panel"], panel_rows)
    write_jsonl(paths["labels"], labels)

    available_labels = [row for row in labels if row.get("label_status") == "available_research_only"]
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "args": {
            "start_date": args.start_date,
            "end_date": args.end_date,
            "replay_root": workspace_relative(replay_root),
            "top_n": args.top_n,
            "near_n": args.near_n,
            "reject_n": args.reject_n,
            "min_lookback": args.min_lookback,
        },
        "outputs": {key: workspace_relative(path) for key, path in paths.items()},
        "summary": {
            "status": "completed",
            "start_date": args.start_date,
            "end_date": args.end_date,
            "panel_rows": len(panel_rows),
            "label_rows": len(labels),
            "available_labels": len(available_labels),
            "trade_dates_with_samples": len({row["trade_date"] for row in panel_rows}),
            "sample_codes": len({row["code"] for row in panel_rows}),
            "bucket_counts": dict(Counter(row["bucket"] for row in panel_rows)),
            "action_counts": dict(Counter(row["action"] for row in panel_rows)),
            "setup_counts": dict(Counter(row["setup_type"] for row in panel_rows)),
            "classification_counts": dict(Counter(row.get("classification") for row in available_labels)),
        },
        "input_hashes": {
            "backfill_manifest": sha256_file(replay_root / "manifest.json") if (replay_root / "manifest.json").exists() else None,
        },
    }
    write_json(paths["manifest"], manifest)
    paths["report"].write_text(render_report(manifest), encoding="utf-8")
    print(json.dumps({
        "status": "completed",
        "panel_rows": len(panel_rows),
        "label_rows": len(labels),
        "available_labels": len(available_labels),
        "panel": workspace_relative(paths["panel"]),
        "labels": workspace_relative(paths["labels"]),
        "report": workspace_relative(paths["report"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
