"""Utility helpers shared across Prism data ingress modules."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_dataset_repository_root() -> Path:
    return workspace_root() / "data" / "prism_data" / "datasets"


def hash_payload(value: Any) -> str:
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        serialized = str(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def normalize_code(code: Any) -> str:
    text = str(code or "").strip().lower()
    if len(text) == 8 and text[:2] in {"sh", "sz"} and text[2:].isdigit():
        return text
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) != 6:
        raise ValueError(f"invalid stock code: {code!r}")
    market = "sh" if digits.startswith(("5", "6", "9")) else "sz"
    return f"{market}{digits}"


def digits_code(code: Any) -> str:
    return normalize_code(code)[2:]


def market_of(code: Any) -> str:
    return normalize_code(code)[:2]


def sina_symbol(code: Any) -> str:
    return normalize_code(code)


def eastmoney_secid(code: Any) -> str:
    normalized = normalize_code(code)
    market = "1" if normalized.startswith("sh") else "0"
    return f"{market}.{normalized[2:]}"


__all__ = [
    "default_dataset_repository_root",
    "digits_code",
    "eastmoney_secid",
    "hash_payload",
    "market_of",
    "normalize_code",
    "sina_symbol",
    "workspace_root",
]
