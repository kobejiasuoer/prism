from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from .config import load_quant_research_config
from .paths import (
    BASELINES_ROOT,
    LABELS_ROOT,
    LEDGERS_ROOT,
    PANELS_ROOT,
    REPORTS_ROOT,
    REPO_ROOT,
    ensure_quant_dirs,
    workspace_relative,
)


MANIFEST_PATH = BASELINES_ROOT / "quant_baseline_manifest.json"
PANEL_PATH = PANELS_ROOT / "daily_signal_panel.jsonl"
ELIGIBLE_UNIVERSE_PATH = PANELS_ROOT / "eligible_universe_snapshot.jsonl"
STAGE_LEDGER_PATH = LEDGERS_ROOT / "pipeline_stage_ledger.jsonl"
LABEL_PATH = LABELS_ROOT / "forward_return_labels.jsonl"
PANEL_REPORT_PATH = REPORTS_ROOT / "panel_coverage_latest.md"
LABEL_REPORT_PATH = REPORTS_ROOT / "label_coverage_latest.md"

SIGNAL_ARTIFACT_TYPES = {
    "ai_screening_history",
    "scan_history",
    "midday_verification",
    "watchlist_snapshot",
    "command_brief",
}

FORMAL_LABEL_SOURCE_LANES = {"research_backfill_ai_history", "research_backfill_scan_history"}
FORMAL_LABEL_STAGES = {"ai_screened", "shortlisted", "scan_candidate"}


@dataclass(frozen=True)
class BuildResult:
    panel_rows: int
    eligible_universe_rows: int
    stage_ledger_rows: int
    label_rows: int
    available_label_rows: int
    panel_path: Path
    label_path: Path


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now_stamp() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def clean_code(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 6:
        return digits[-6:]
    return text


def parse_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    tmp_path.replace(path)
    return count


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return parse_json(path)


def artifact_generated_at(artifact: dict[str, Any], obj: dict[str, Any] | None = None) -> str | None:
    if obj:
        summary = obj.get("summary") if isinstance(obj.get("summary"), dict) else {}
        return (
            obj.get("generated_at")
            or obj.get("timestamp")
            or obj.get("source_scan_timestamp")
            or summary.get("generated_at")
            or artifact.get("generated_at")
        )
    return artifact.get("generated_at")


def artifact_trade_date(artifact: dict[str, Any], obj: dict[str, Any] | None = None) -> str | None:
    if obj:
        summary = obj.get("summary") if isinstance(obj.get("summary"), dict) else {}
        replay_meta = obj.get("replay_meta") if isinstance(obj.get("replay_meta"), dict) else {}
        value = (
            obj.get("trade_date")
            or obj.get("date")
            or replay_meta.get("trade_date")
            or summary.get("trade_date")
            or artifact.get("trade_date")
        )
    else:
        value = artifact.get("trade_date")
    if value:
        return str(value)[:10]
    generated = artifact_generated_at(artifact, obj)
    return str(generated)[:10] if generated else None


def batch_gate_context(obj: dict[str, Any]) -> dict[str, Any]:
    summary = obj.get("screening_summary") or {}
    gate = obj.get("execution_gate") or {}
    regime = obj.get("market_regime") or {}
    regime_gate = regime.get("execution_gate") or {}
    if isinstance(gate, dict) and gate.get("status"):
        source = gate
    elif isinstance(regime_gate, dict) and regime_gate.get("status"):
        source = regime_gate
    else:
        source = {}
    status = summary.get("execution_gate_status") or source.get("status")
    return {
        "execution_gate_status": status,
        "execution_gate_label": source.get("label"),
        "execution_gate_summary": source.get("summary"),
        "execution_gate_position_cap": source.get("position_cap"),
        "execution_gate_scope": "batch_context" if status else None,
    }


def row_id(parts: Iterable[Any]) -> str:
    return sha256_text("|".join(str(part or "") for part in parts))[:24]


def base_row(
    artifact: dict[str, Any],
    obj: dict[str, Any],
    raw: dict[str, Any],
    *,
    record_type: str,
    pipeline_stage: str,
    rank: int,
    strategy_name: str | None = None,
) -> dict[str, Any]:
    source_artifact = artifact["artifact_path"]
    source_lane = artifact["source_lane"]
    trade_date = artifact_trade_date(artifact, obj)
    generated_at = artifact_generated_at(artifact, obj)
    code = clean_code(raw.get("code"))
    identifier = row_id(
        [
            source_artifact,
            source_lane,
            record_type,
            pipeline_stage,
            trade_date,
            code,
            rank,
            strategy_name,
        ]
    )
    return {
        "panel_row_id": identifier,
        "trade_date": trade_date,
        "code": code,
        "name": raw.get("name") or code,
        "source_lane": source_lane,
        "source_artifact": source_artifact,
        "source_hash": artifact.get("sha256"),
        "source_record_type": record_type,
        "pipeline_stage": pipeline_stage,
        "rank_within_source": rank,
        "strategy_name": strategy_name,
        "signal_timestamp": obj.get("source_scan_timestamp") or obj.get("timestamp") or generated_at,
        "available_timestamp": generated_at,
        "decision_timestamp": generated_at,
        "pit_check_status": "pass" if generated_at and artifact.get("sha256") else "unknown",
        "score": None,
        "score_kind": None,
        "score_source_lane": None,
        "ai_priority_score": None,
        "ai_best_score": None,
        "scan_capital_score": None,
        "scan_technical_score": None,
        "watchlist_technical_score": None,
        "midday_score": None,
        "tier": raw.get("tier"),
        "tier_rank": safe_int(raw.get("tier_rank")),
        "theme": normalize_theme(raw),
        "themes": normalize_themes(raw),
        "setup_type": raw.get("setup_type"),
        "setup_label": raw.get("setup_label"),
        "strategy_hits": raw.get("strategy_hits") or ([strategy_name] if strategy_name else []),
        "strategy_labels": raw.get("strategy_labels") or [],
        "strategy_bucket_status": "not_mapped_sprint1",
        "execution_quality_score": None,
        "execution_quality_label": None,
        "execution_gate_status": None,
        "execution_gate_label": None,
        "execution_gate_scope": None,
        "price": safe_float(raw.get("price")),
        "change_pct": safe_float(raw.get("change_pct")),
        "amount_yi": safe_float(raw.get("amount_yi")),
        "trigger_price": trigger_price(raw),
        "stop_loss": safe_float(raw.get("stop_loss")),
        "position_cap": None,
        "data_quality_flags": ["final_score_not_used_sprint1"],
        "raw_field_keys": sorted(str(key) for key in raw.keys()),
    }


def normalize_themes(raw: dict[str, Any]) -> list[str]:
    values = raw.get("themes")
    if isinstance(values, list):
        return [str(value) for value in values if value]
    value = raw.get("theme")
    return [str(value)] if value else []


def normalize_theme(raw: dict[str, Any]) -> str | None:
    if raw.get("theme"):
        return str(raw.get("theme"))
    themes = normalize_themes(raw)
    return themes[0] if themes else None


def trigger_price(raw: dict[str, Any]) -> float | None:
    entry_plan = raw.get("entry_plan") if isinstance(raw.get("entry_plan"), dict) else {}
    levels = entry_plan.get("levels") if isinstance(entry_plan.get("levels"), dict) else {}
    return safe_float(levels.get("trigger") or raw.get("trigger_price") or raw.get("high20"))


def apply_score(row: dict[str, Any], value: Any, score_kind: str) -> None:
    score = safe_float(value)
    if score is None:
        return
    row["score"] = score
    row["score_kind"] = score_kind
    row["score_source_lane"] = row["source_lane"]


def apply_gate(row: dict[str, Any], artifact: dict[str, Any], context: dict[str, Any]) -> None:
    status = context.get("execution_gate_status")
    if not status:
        row["data_quality_flags"].append("execution_gate_context_missing")
        return
    row["execution_gate_status"] = status
    row["execution_gate_label"] = context.get("execution_gate_label")
    row["execution_gate_scope"] = "batch_context"
    row["execution_gate_source_artifact"] = artifact["artifact_path"]
    row["position_cap"] = context.get("execution_gate_position_cap")


def apply_execution_quality(row: dict[str, Any], raw: dict[str, Any]) -> None:
    quality = raw.get("execution_quality")
    if not isinstance(quality, dict):
        return
    row["execution_quality_score"] = safe_float(quality.get("score"))
    row["execution_quality_label"] = quality.get("label")


def adapt_scan_artifact(artifact: dict[str, Any], obj: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    universe_rows: list[dict[str, Any]] = []
    gate = batch_gate_context(obj)
    for rank, raw in enumerate(obj.get("verification_universe") or [], start=1):
        if not isinstance(raw, dict):
            continue
        universe_rows.append(universe_row(artifact, obj, raw, "verification_universe", rank))
    for strategy_name, candidates in (obj.get("strategies") or {}).items():
        if not isinstance(candidates, list):
            continue
        for rank, raw in enumerate(candidates, start=1):
            if not isinstance(raw, dict):
                continue
            row = base_row(
                artifact,
                obj,
                raw,
                record_type="scan_strategy",
                pipeline_stage="scan_candidate",
                rank=rank,
                strategy_name=strategy_name,
            )
            apply_score(row, raw.get("score"), "raw_scan_composite_score")
            scores = raw.get("scores") if isinstance(raw.get("scores"), dict) else {}
            row["scan_capital_score"] = safe_float(scores.get("capital"))
            row["scan_technical_score"] = safe_float(scores.get("technical"))
            apply_gate(row, artifact, gate)
            if row["scan_capital_score"] is None:
                row["data_quality_flags"].append("scan_capital_score_missing")
            if row["scan_technical_score"] is None:
                row["data_quality_flags"].append("scan_technical_score_missing")
            rows.append(row)
            universe_rows.append(universe_row(artifact, obj, raw, f"scan_strategy:{strategy_name}", rank))
    return rows, universe_rows


def adapt_ai_artifact(artifact: dict[str, Any], obj: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    gate = batch_gate_context(obj)
    for record_type, pipeline_stage, items in (
        ("ai_shortlist", "ai_screened", obj.get("shortlist") or []),
        ("ai_analyzer_candidate", "shortlisted", obj.get("analyzer_candidates") or []),
    ):
        for rank, raw in enumerate(items, start=1):
            if not isinstance(raw, dict):
                continue
            row = base_row(
                artifact,
                obj,
                raw,
                record_type=record_type,
                pipeline_stage=pipeline_stage,
                rank=rank,
            )
            row["ai_priority_score"] = safe_float(raw.get("priority_score"))
            row["ai_best_score"] = safe_float(raw.get("best_score") or raw.get("score"))
            apply_execution_quality(row, raw)
            apply_gate(row, artifact, gate)
            if row["ai_priority_score"] is None and record_type == "ai_shortlist":
                row["data_quality_flags"].append("ai_priority_score_missing")
            if row["ai_best_score"] is None:
                row["data_quality_flags"].append("ai_best_score_missing")
            rows.append(row)
    return rows


def adapt_midday_artifact(artifact: dict[str, Any], obj: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    groups = [
        ("midday_confirmed", "confirmed", obj.get("confirmed") or []),
        ("midday_downgraded", "downgraded", obj.get("downgraded") or []),
        ("midday_fresh_candidate", "fresh_candidate", obj.get("fresh_candidates") or []),
        ("midday_item", "midday_checked", obj.get("items") or []),
    ]
    for record_type, pipeline_stage, items in groups:
        for rank, raw in enumerate(items, start=1):
            if not isinstance(raw, dict):
                continue
            row = base_row(artifact, obj, raw, record_type=record_type, pipeline_stage=pipeline_stage, rank=rank)
            score_value = raw.get("score") if raw.get("score") is not None else raw.get("morning_score")
            apply_score(row, score_value, f"{record_type}_score")
            row["midday_score"] = row["score"]
            row["data_quality_flags"].append("midday_no_formal_forward_label")
            rows.append(row)
    return rows


def adapt_watchlist_artifact(artifact: dict[str, Any], obj: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rank, raw in enumerate((obj.get("stocks") or {}).values(), start=1):
        if not isinstance(raw, dict):
            continue
        row = base_row(artifact, obj, raw, record_type="watchlist_stock", pipeline_stage="watchlist", rank=rank)
        apply_score(row, raw.get("score"), raw.get("score_kind") or "watchlist_technical_score")
        row["watchlist_technical_score"] = row["score"]
        row["data_quality_flags"].append("watchlist_no_formal_forward_label")
        rows.append(row)
    return rows


def adapt_command_brief_artifact(artifact: dict[str, Any], obj: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    watchlist = obj.get("watchlist") or {}
    for rank, raw in enumerate(watchlist.get("records") or [], start=1):
        if not isinstance(raw, dict):
            continue
        row = base_row(artifact, obj, raw, record_type="brief_watchlist", pipeline_stage="command_brief_watchlist", rank=rank)
        snapshot = raw.get("rule_snapshot") if isinstance(raw.get("rule_snapshot"), dict) else {}
        apply_score(row, snapshot.get("score"), snapshot.get("score_kind") or "watchlist_technical_score")
        row["watchlist_technical_score"] = row["score"]
        rows.append(row)

    screener = obj.get("screener") or {}
    gate = batch_gate_context(screener)
    for rank, raw in enumerate(screener.get("shortlist") or [], start=1):
        if not isinstance(raw, dict):
            continue
        row = base_row(artifact, obj, raw, record_type="brief_screener_shortlist", pipeline_stage="command_brief_screener", rank=rank)
        row["ai_priority_score"] = safe_float(raw.get("priority_score"))
        row["ai_best_score"] = safe_float(raw.get("best_score"))
        apply_execution_quality(row, raw)
        apply_gate(row, artifact, gate)
        rows.append(row)

    midday = obj.get("midday") or {}
    for group_key, stage in (("confirmed", "command_brief_midday_confirmed"), ("downgraded", "command_brief_midday_downgraded"), ("fresh_candidates", "command_brief_midday_fresh")):
        for rank, raw in enumerate(midday.get(group_key) or [], start=1):
            if not isinstance(raw, dict):
                continue
            row = base_row(artifact, obj, raw, record_type=f"brief_midday_{group_key}", pipeline_stage=stage, rank=rank)
            apply_score(row, raw.get("score") or raw.get("morning_score"), f"brief_midday_{group_key}_score")
            row["midday_score"] = row["score"]
            rows.append(row)
    return rows


def universe_row(
    artifact: dict[str, Any],
    obj: dict[str, Any],
    raw: dict[str, Any],
    source: str,
    rank: int,
) -> dict[str, Any]:
    source_artifact = artifact["artifact_path"]
    trade_date = artifact_trade_date(artifact, obj)
    code = clean_code(raw.get("code"))
    return {
        "universe_row_id": row_id([source_artifact, trade_date, code, source, rank]),
        "trade_date": trade_date,
        "code": code,
        "name": raw.get("name") or code,
        "source_lane": artifact["source_lane"],
        "source_artifact": source_artifact,
        "source_hash": artifact.get("sha256"),
        "source_pool": raw.get("source_pool") or obj.get("pool") or obj.get("pool_label"),
        "pipeline_stage": "eligible_universe" if source == "verification_universe" else "scan_candidate_pool",
        "inclusion_reason": source,
        "rank_within_source": rank,
        "score": safe_float(raw.get("score")),
        "data_quality_flags": ["universe_is_source_observed_not_full_exchange"],
    }


def adapt_artifact(artifact: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    path = REPO_ROOT / artifact["artifact_path"]
    obj = parse_json(path)
    if not isinstance(obj, dict):
        return [], []
    source_lane = artifact["source_lane"]
    artifact_type = artifact["artifact_type"]
    if artifact_type == "scan_history":
        return adapt_scan_artifact(artifact, obj)
    if artifact_type == "ai_screening_history":
        return adapt_ai_artifact(artifact, obj), []
    if artifact_type == "midday_verification":
        return adapt_midday_artifact(artifact, obj), []
    if artifact_type == "watchlist_snapshot":
        return adapt_watchlist_artifact(artifact, obj), []
    if artifact_type == "command_brief" and source_lane == "command_brief_json":
        return adapt_command_brief_artifact(artifact, obj), []
    return [], []


def stage_ledger_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "ledger_row_id": row_id([row["panel_row_id"], "stage_ledger"]),
        "panel_row_id": row["panel_row_id"],
        "trade_date": row["trade_date"],
        "code": row["code"],
        "name": row["name"],
        "source_lane": row["source_lane"],
        "source_artifact": row["source_artifact"],
        "source_hash": row["source_hash"],
        "pipeline_stage": row["pipeline_stage"],
        "source_record_type": row["source_record_type"],
        "rank_within_source": row["rank_within_source"],
        "inclusion_reason": row["source_record_type"],
        "pit_check_status": row["pit_check_status"],
    }


def load_price_cache(manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows_by_code_date: dict[tuple[str, str], dict[str, Any]] = {}
    price_artifacts = [
        artifact
        for artifact in manifest.get("artifacts", [])
        if artifact.get("artifact_type") == "price_kline_cache"
    ]
    for artifact in price_artifacts:
        path = REPO_ROOT / artifact["artifact_path"]
        code = clean_code(path.name.split("_")[0])
        if not code:
            continue
        try:
            rows = parse_json(path)
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict) or not row.get("date"):
                continue
            key = (code, row["date"])
            rows_by_code_date[key] = {
                **row,
                "code": code,
                "price_source_artifact": artifact["artifact_path"],
                "price_source_hash": artifact["sha256"],
            }
    by_code: dict[str, list[dict[str, Any]]] = {}
    for (code, _date), row in rows_by_code_date.items():
        by_code.setdefault(code, []).append(row)
    for code in by_code:
        by_code[code].sort(key=lambda item: item["date"])
    return by_code


def roundtrip_cost_bps(config: dict[str, Any]) -> float:
    cost = config["transaction_cost"]
    impact = cost.get("impact_cost") or {}
    return float(cost.get("buy_commission_bps") or 0) + float(cost.get("sell_commission_bps") or 0) + float(cost.get("stamp_tax_bps") or 0) + float(cost.get("slippage_bps") or 0) * 2 + float(impact.get("placeholder_bps") or 0)


def label_eligible(row: dict[str, Any]) -> bool:
    return row["source_lane"] in FORMAL_LABEL_SOURCE_LANES and row["pipeline_stage"] in FORMAL_LABEL_STAGES


def build_label_rows(panel_rows: list[dict[str, Any]], manifest: dict[str, Any], config: dict[str, Any]) -> list[dict[str, Any]]:
    price_cache = load_price_cache(manifest)
    windows = [int(value) for value in config["holding_windows"]]
    entry_models = list(config["entry_models"]["supported"])
    cost_bps = roundtrip_cost_bps(config)
    labels: list[dict[str, Any]] = []
    for panel_row in panel_rows:
        if not label_eligible(panel_row):
            continue
        code = panel_row.get("code")
        trade_date = panel_row.get("trade_date")
        prices = price_cache.get(str(code)) or []
        date_to_index = {row["date"]: idx for idx, row in enumerate(prices)}
        signal_index = date_to_index.get(str(trade_date))
        for entry_model in entry_models:
            for window in windows:
                label = base_label_row(panel_row, entry_model, window, cost_bps)
                if signal_index is None:
                    label["label_status"] = "unavailable"
                    label["unavailable_reasons"].append("signal_trade_date_price_missing")
                    labels.append(label)
                    continue
                entry_index = signal_index + 1
                exit_index = signal_index + window
                if entry_index >= len(prices) or exit_index >= len(prices):
                    label["label_status"] = "unavailable"
                    label["unavailable_reasons"].append("forward_price_missing")
                    labels.append(label)
                    continue
                entry_row = prices[entry_index]
                exit_row = prices[exit_index]
                entry_price = safe_float(entry_row.get("open" if entry_model == "next_open" else "close"))
                exit_price = safe_float(exit_row.get("close"))
                if not entry_price or not exit_price:
                    label["label_status"] = "unavailable"
                    label["unavailable_reasons"].append("entry_or_exit_price_missing")
                    labels.append(label)
                    continue
                raw_return = exit_price / entry_price - 1
                label.update(
                    {
                        "label_status": "available_research_only",
                        "entry_trade_date": entry_row.get("date"),
                        "exit_trade_date": exit_row.get("date"),
                        "entry_price": round(entry_price, 6),
                        "exit_price": round(exit_price, 6),
                        "raw_return": round(raw_return, 8),
                        "net_return": round(raw_return - cost_bps / 10000.0, 8),
                        "price_source_artifact": entry_row.get("price_source_artifact"),
                        "price_source_hash": entry_row.get("price_source_hash"),
                        "price_source": entry_row.get("source"),
                    }
                )
                if not entry_row.get("source"):
                    label["label_quality_flags"].append("price_source_unknown")
                labels.append(label)
    return labels


def base_label_row(panel_row: dict[str, Any], entry_model: str, window: int, cost_bps: float) -> dict[str, Any]:
    missing = [
        "adjustment_policy",
        "suspend_status",
        "limit_up_down_status",
        "failed_order",
        "partial_fill",
    ]
    label_id = row_id([panel_row["panel_row_id"], entry_model, window])
    return {
        "label_id": label_id,
        "panel_row_id": panel_row["panel_row_id"],
        "trade_date": panel_row["trade_date"],
        "code": panel_row["code"],
        "name": panel_row["name"],
        "source_lane": panel_row["source_lane"],
        "source_artifact": panel_row["source_artifact"],
        "source_hash": panel_row["source_hash"],
        "label_scope": "2024_research_backfill_only",
        "label_status": "unavailable",
        "entry_model": entry_model,
        "holding_window_days": window,
        "entry_trade_date": None,
        "exit_trade_date": None,
        "entry_price": None,
        "exit_price": None,
        "raw_return": None,
        "net_return": None,
        "cost_bps": round(cost_bps, 4),
        "benchmark_status": "benchmark_unavailable",
        "excess_return_status": "deferred_until_benchmark_frozen",
        "price_adjustment_status": "unknown",
        "calendar_source": "symbol_price_rows",
        "research_label_eligible": True,
        "formal_execution_eligible": False,
        "execution_data_missing": missing,
        "label_quality_flags": [
            "execution_data_missing",
            "benchmark_unavailable",
            "minimum_commission_notional_unavailable",
        ],
        "unavailable_reasons": [],
    }


def build_panel_rows(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    panel_rows: list[dict[str, Any]] = []
    universe_rows: list[dict[str, Any]] = []
    for artifact in manifest.get("artifacts", []):
        if artifact.get("artifact_type") not in SIGNAL_ARTIFACT_TYPES:
            continue
        try:
            rows, universe = adapt_artifact(artifact)
        except Exception as exc:
            # Keep the build reportable; a failed artifact can be traced through the row counts gap.
            print(f"[quant] failed to adapt {artifact.get('artifact_path')}: {exc}")
            continue
        panel_rows.extend(rows)
        universe_rows.extend(universe)
    panel_rows.sort(key=lambda row: (row.get("trade_date") or "", row.get("source_lane") or "", row.get("code") or "", row.get("panel_row_id") or ""))
    universe_rows.sort(key=lambda row: (row.get("trade_date") or "", row.get("source_lane") or "", row.get("code") or "", row.get("universe_row_id") or ""))
    return panel_rows, universe_rows


def pct(num: int, den: int) -> str:
    if den == 0:
        return "0.0%"
    return f"{num / den * 100:.1f}%"


def write_panel_report(path: Path, panel_rows: list[dict[str, Any]], universe_rows: list[dict[str, Any]], stage_rows: list[dict[str, Any]]) -> None:
    generated_at = now_stamp()
    by_lane = Counter(row["source_lane"] for row in panel_rows)
    by_stage = Counter(row["pipeline_stage"] for row in panel_rows)
    pit = Counter(row["pit_check_status"] for row in panel_rows)
    flags = Counter(flag for row in panel_rows for flag in row.get("data_quality_flags") or [])
    critical_fields = [
        "score",
        "score_kind",
        "ai_priority_score",
        "ai_best_score",
        "scan_capital_score",
        "scan_technical_score",
        "execution_gate_status",
        "theme",
        "setup_type",
    ]
    lines = [
        "# Prism Quant Sprint 1 Panel Coverage",
        "",
        f"Generated at: {generated_at}",
        "",
        "Scope: Sprint 1 research panel only. No production sorting, no A/B/C replacement, no factor conclusion, and no backtest conclusion.",
        "",
        "## Outputs",
        "",
        f"- Daily signal panel rows: {len(panel_rows)}.",
        f"- Eligible universe snapshot rows: {len(universe_rows)}.",
        f"- Pipeline stage ledger rows: {len(stage_rows)}.",
        "",
        "## Lane Coverage",
        "",
        "| Source lane | Rows |",
        "| --- | ---: |",
    ]
    for lane, count in by_lane.most_common():
        lines.append(f"| `{lane}` | {count} |")
    lines += [
        "",
        "## Pipeline Stage Coverage",
        "",
        "| Stage | Rows |",
        "| --- | ---: |",
    ]
    for stage, count in by_stage.most_common():
        lines.append(f"| `{stage}` | {count} |")
    lines += [
        "",
        "## Field Coverage",
        "",
        "| Field | Non-null rows | Coverage | Notes |",
        "| --- | ---: | ---: | --- |",
    ]
    for field in critical_fields:
        count = sum(1 for row in panel_rows if row.get(field) not in (None, "", [], {}))
        note = "lane-scoped; do not merge across lanes" if field in {"score", "score_kind"} else ""
        if field == "execution_gate_status":
            note = "batch/context join; not candidate-native"
        if field in {"scan_capital_score", "scan_technical_score"}:
            note = "mapped from raw scan `scores.*`"
        lines.append(f"| `{field}` | {count}/{len(panel_rows)} | {pct(count, len(panel_rows))} | {note} |")
    lines += [
        "",
        "## PIT And Quality",
        "",
        f"- PIT status: {dict(pit)}.",
        f"- Top data quality flags: {dict(flags.most_common(12))}.",
        "- Every row carries `source_artifact`, `source_hash`, `source_lane`, `signal_timestamp`, `available_timestamp`, and `decision_timestamp`.",
        "- `final_score` is intentionally absent from panel rows. AI lane uses `ai_priority_score` / `ai_best_score`; raw scan uses namespaced scan scores.",
        "",
        "## Sprint 1 Guardrails",
        "",
        "- `score` is retained only with `source_lane` and `score_kind`.",
        "- `execution_gate_status` is joined as `execution_gate_scope=batch_context`.",
        "- 2026 artifacts are included for panel coverage only; they are excluded from formal forward label generation.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_label_report(path: Path, panel_rows: list[dict[str, Any]], labels: list[dict[str, Any]]) -> None:
    generated_at = now_stamp()
    eligible_panel_rows = [row for row in panel_rows if label_eligible(row)]
    excluded_2026 = [
        row for row in panel_rows if row["source_lane"] not in FORMAL_LABEL_SOURCE_LANES
    ]
    by_window = Counter((label["holding_window_days"], label["label_status"]) for label in labels)
    by_entry = Counter((label["entry_model"], label["label_status"]) for label in labels)
    available = sum(1 for label in labels if label["label_status"] == "available_research_only")
    unavailable = len(labels) - available
    missing_flags = Counter(flag for label in labels for flag in label.get("execution_data_missing") or [])
    unavailable_reasons = Counter(reason for label in labels for reason in label.get("unavailable_reasons") or [])
    lines = [
        "# Prism Quant Sprint 1 Label Coverage",
        "",
        f"Generated at: {generated_at}",
        "",
        "Scope: raw/net forward labels for 2024 research backfill only. Excess returns are deferred because benchmark series are not frozen.",
        "",
        "## Summary",
        "",
        f"- Panel rows eligible for first label pass: {len(eligible_panel_rows)}.",
        f"- Label rows written: {len(labels)}.",
        f"- Available research-only labels: {available}/{len(labels)} ({pct(available, len(labels))}).",
        f"- Unavailable label rows: {unavailable}/{len(labels)} ({pct(unavailable, len(labels))}).",
        f"- 2026/current/non-backfill panel rows excluded from formal label evaluation: {len(excluded_2026)}.",
        "",
        "## Entry Model Coverage",
        "",
        "| Entry model | Available | Unavailable |",
        "| --- | ---: | ---: |",
    ]
    for entry in sorted({label["entry_model"] for label in labels}):
        lines.append(
            f"| `{entry}` | {by_entry[(entry, 'available_research_only')]} | {by_entry[(entry, 'unavailable')]} |"
        )
    lines += [
        "",
        "## Holding Window Coverage",
        "",
        "| Holding window | Available | Unavailable |",
        "| --- | ---: | ---: |",
    ]
    for window in sorted({int(label["holding_window_days"]) for label in labels}):
        lines.append(
            f"| {window} | {by_window[(window, 'available_research_only')]} | {by_window[(window, 'unavailable')]} |"
        )
    lines += [
        "",
        "## Execution Data Missing Flags",
        "",
        f"- Missing execution data flags on label rows: {dict(missing_flags)}.",
        f"- Unavailable reasons: {dict(unavailable_reasons)}.",
        "- `benchmark_status=benchmark_unavailable` and `excess_return_status=deferred_until_benchmark_frozen` on every label row.",
        "- `formal_execution_eligible=false` on every label row because adjustment, suspend, limit, failed order, and partial fill data are not frozen.",
        "",
        "## Supported In First Version",
        "",
        "- 2024 research backfill raw and net returns for `next_open` and `next_close` entry models.",
        "- Holding windows from config: 1, 3, 5, and 10 observed trading rows.",
        "- Configured bps costs are deducted into `net_return`; minimum commission is flagged unavailable because notional is absent.",
        "",
        "## Not Supported In First Version",
        "",
        "- Excess returns, adjusted-return conclusions, benchmark-relative conclusions, and execution-realistic fills.",
        "- 2026 current operational forward labels; those rows remain panel/coverage only.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_sprint1_outputs(manifest_path: Path = MANIFEST_PATH) -> BuildResult:
    ensure_quant_dirs()
    manifest = load_manifest(manifest_path)
    config = load_quant_research_config().data
    panel_rows, universe_rows = build_panel_rows(manifest)
    stage_rows = [stage_ledger_row(row) for row in panel_rows]
    label_rows = build_label_rows(panel_rows, manifest, config)
    write_jsonl(PANEL_PATH, panel_rows)
    write_jsonl(ELIGIBLE_UNIVERSE_PATH, universe_rows)
    write_jsonl(STAGE_LEDGER_PATH, stage_rows)
    write_jsonl(LABEL_PATH, label_rows)
    write_panel_report(PANEL_REPORT_PATH, panel_rows, universe_rows, stage_rows)
    write_label_report(LABEL_REPORT_PATH, panel_rows, label_rows)
    return BuildResult(
        panel_rows=len(panel_rows),
        eligible_universe_rows=len(universe_rows),
        stage_ledger_rows=len(stage_rows),
        label_rows=len(label_rows),
        available_label_rows=sum(1 for row in label_rows if row["label_status"] == "available_research_only"),
        panel_path=PANEL_PATH,
        label_path=LABEL_PATH,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Prism quant Sprint 1 research panel and labels.")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    args = parser.parse_args()
    result = build_sprint1_outputs(args.manifest)
    print(
        json.dumps(
            {
                "panel_rows": result.panel_rows,
                "eligible_universe_rows": result.eligible_universe_rows,
                "stage_ledger_rows": result.stage_ledger_rows,
                "label_rows": result.label_rows,
                "available_label_rows": result.available_label_rows,
                "panel_path": workspace_relative(result.panel_path),
                "label_path": workspace_relative(result.label_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
