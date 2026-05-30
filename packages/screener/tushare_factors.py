# packages/screener/tushare_factors.py
"""Tushare factor layer: read datasets → normalized factor values → score / tags / explanation.

Self-contained and read-only. Imports only stdlib + prism_data (never apps/control-panel).
Never raises on missing/NaN data; every factor value is Optional.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any


def _dataset_root() -> Path:
    override = os.environ.get("PRISM_DATASET_REPOSITORY_ROOT")
    if override:
        return Path(override)
    from prism_data.utils import default_dataset_repository_root
    return Path(default_dataset_repository_root())


def _sanitize(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "default"
    return "".join(ch if ch.isalnum() or ch in {"-", "_", ".", "+"} else "_" for ch in text)


def _read_json_or_none(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _resolve_trade_date(dataset: str, requested: str | None) -> str | None:
    base = _dataset_root() / _sanitize(dataset)
    if not base.exists():
        return None
    dates = sorted(p.name for p in base.iterdir() if p.is_dir())
    if not dates:
        return None
    if requested:
        req = _sanitize(requested)
        if req in dates:
            return req
        earlier = [d for d in dates if d <= req]
        if earlier:
            return earlier[-1]
    return dates[-1]


def _load_dataset(dataset: str, trade_date: str | None, key: str) -> tuple[Any, dict[str, Any] | None]:
    resolved = _resolve_trade_date(dataset, trade_date)
    if not resolved:
        return None, None
    base = _dataset_root() / _sanitize(dataset) / resolved
    data_path = base / f"{_sanitize(key)}.json"
    if not data_path.exists():
        return None, None
    manifest = _read_json_or_none(base / f"{_sanitize(key)}.manifest.json")
    return _read_json_or_none(data_path), manifest


def _safe_float(value: Any) -> float | None:
    if value in (None, "", "-", "None"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def _normalize_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return "".join(ch for ch in text if ch.isdigit()).zfill(6)


def _compact_date(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:8]


def _latest_row(rows: Any, *fields: str) -> dict[str, Any] | None:
    if not isinstance(rows, list):
        return None
    dict_rows = [row for row in rows if isinstance(row, dict)]
    if not dict_rows:
        return None
    keys = fields or ("trade_date", "end_date", "ann_date")
    return sorted(dict_rows, key=lambda row: max((_compact_date(row.get(f)) for f in keys), default=""))[-1]
