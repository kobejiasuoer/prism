from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from .paths import LABELS_ROOT, PANELS_ROOT, REPORTS_ROOT


PANEL_PATH = PANELS_ROOT / "daily_signal_panel.jsonl"
LABEL_PATH = LABELS_ROOT / "forward_return_labels.jsonl"
HARDENED_LABEL_PATH = LABELS_ROOT / "forward_return_labels_hardened.jsonl"
FACTOR_REPORT_PATH = REPORTS_ROOT / "factor_evaluation_latest.md"
BACKTEST_REPORT_PATH = REPORTS_ROOT / "portfolio_backtest_latest.md"
QUANT_HEALTH_MD_PATH = REPORTS_ROOT / "quant_health_latest.md"
QUANT_HEALTH_JSON_PATH = REPORTS_ROOT / "quant_health_latest.json"

MIN_BUCKET_SAMPLE = 30
REPORT_ONLY_FLAGS = [
    "report_only",
    "research_only",
    "benchmark_unavailable",
    "execution_data_missing",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"


def fmt(value: float | None, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def status_for_sample(sample_size: int, *, research_only: bool = True) -> str:
    if sample_size < MIN_BUCKET_SAMPLE:
        return "insufficient_sample"
    return "research_only" if research_only else "candidate"


def summary_stats(values: Iterable[float]) -> dict[str, Any]:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return {
            "sample_size": 0,
            "mean": None,
            "median": None,
            "win_rate": None,
            "min": None,
            "max": None,
        }
    return {
        "sample_size": len(clean),
        "mean": sum(clean) / len(clean),
        "median": median(clean),
        "win_rate": sum(1 for value in clean if value > 0) / len(clean),
        "min": min(clean),
        "max": max(clean),
    }


def max_drawdown(returns: Iterable[float]) -> float | None:
    equity = 1.0
    peak = 1.0
    worst = 0.0
    seen = False
    for value in returns:
        seen = True
        equity *= 1.0 + float(value)
        peak = max(peak, equity)
        drawdown = equity / peak - 1.0
        worst = min(worst, drawdown)
    return worst if seen else None


def join_panel_labels(
    *,
    available_only: bool = True,
    panel_path: Path = PANEL_PATH,
    label_path: Path = LABEL_PATH,
) -> list[dict[str, Any]]:
    panel_by_id = {row["panel_row_id"]: row for row in load_jsonl(panel_path)}
    hardened_by_id = {row.get("label_id"): row for row in load_jsonl(HARDENED_LABEL_PATH)}
    joined: list[dict[str, Any]] = []
    for label in load_jsonl(label_path):
        if available_only and label.get("label_status") != "available_research_only":
            continue
        panel = panel_by_id.get(label.get("panel_row_id"))
        if not panel:
            continue
        joined.append({"panel": panel, "label": label, "hardened_label": hardened_by_id.get(label.get("label_id"))})
    return joined


def group_key_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return "missing"
    return str(value)


def hardened_label_summary(path: Path = HARDENED_LABEL_PATH) -> dict[str, Any]:
    rows = load_jsonl(path)
    reason_counts: dict[str, int] = {}
    for row in rows:
        for reason in row.get("research_only_reason") or []:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    return {
        "path": str(path),
        "exists": path.exists(),
        "rows": len(rows),
        "formal_label_ready_count": sum(1 for row in rows if row.get("formal_label_ready") is True),
        "formal_execution_eligible_count": sum(1 for row in rows if row.get("formal_execution_eligible") is True),
        "benchmark_status_counts": count_values(row.get("benchmark_status") for row in rows),
        "benchmark_return_status_counts": count_values(row.get("benchmark_return_status") for row in rows),
        "excess_return_status_counts": count_values(row.get("excess_return_status") for row in rows),
        "internal_benchmark_status_counts": count_values((row.get("benchmark_reference") or {}).get("internal_benchmark_return_status") for row in rows),
        "price_adjustment_status_counts": count_values(row.get("price_adjustment_status") for row in rows),
        "formal_adjusted_return_status_counts": count_values(row.get("formal_adjusted_return_status") for row in rows),
        "execution_realism_status_counts": count_values(row.get("execution_realism_status") for row in rows),
        "label_quality_status_counts": count_values(row.get("label_quality_status") for row in rows),
        "research_only_reason_counts": dict(sorted(reason_counts.items())),
    }


def count_values(values: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))
