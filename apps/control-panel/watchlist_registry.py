from __future__ import annotations

import json
import re
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = SKILL_ROOT.parents[1] if SKILL_ROOT.name == "control-panel" and SKILL_ROOT.parent.name == "apps" else SKILL_ROOT.parent
PACKAGES_ROOT = REPO_ROOT / "packages"
if str(PACKAGES_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGES_ROOT))
WATCHLIST_CONFIG_PATH = REPO_ROOT / "stock-analyzer" / "config" / "stocks.json"
STOCK_SCREENER_ROOT = REPO_ROOT / "stock-screener"
CODE_PATTERN = re.compile(r"^\d{6}$")
HISTORICAL_STOCK_SEARCH_SOURCES = (
    (STOCK_SCREENER_ROOT / "data" / "ai_history", "历史观察"),
    (STOCK_SCREENER_ROOT / "data" / "stale_outputs", "近期记录"),
    (STOCK_SCREENER_ROOT / "data" / "research_backfill" / "ai_history", "历史回测"),
    (STOCK_SCREENER_ROOT / "data" / "research_backfill" / "history", "历史扫描"),
)
_HISTORICAL_STOCK_CATALOG_CACHE: dict[str, Any] = {"signature": None, "items": []}
_SINA_SUGGEST_CACHE: dict[str, dict[str, Any]] = {}
SINA_SUGGEST_CACHE_TTL_SECONDS = 600

try:
    from prism_data.service import get_data_gateway
    from prism_storage import WatchlistConfigRepository
except Exception:  # pragma: no cover - direct JSON remains the compatibility fallback.
    get_data_gateway = None  # type: ignore[assignment]
    WatchlistConfigRepository = None  # type: ignore[assignment]


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_stock_code(code: Any) -> str:
    text = str(code or "").strip()
    if not CODE_PATTERN.fullmatch(text):
        raise ValueError("股票代码需为 6 位数字")
    return text


def infer_market_from_code(code: Any) -> str:
    text = normalize_stock_code(code)
    return "sh" if text.startswith(("5", "6", "9")) else "sz"


def infer_sina_code(code: Any, market: str | None = None) -> str:
    normalized_code = normalize_stock_code(code)
    resolved_market = (market or infer_market_from_code(normalized_code)).strip().lower()
    if resolved_market not in {"sh", "sz"}:
        resolved_market = infer_market_from_code(normalized_code)
    return f"{resolved_market}{normalized_code}"


def _trade_date_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def fetch_stock_name(code: Any, market: str | None = None, timeout: float = 6.0) -> str | None:
    normalized_code = normalize_stock_code(code)
    if get_data_gateway is None:
        return None
    try:
        result = get_data_gateway().fetch_quote(
            infer_sina_code(normalized_code, market),
            trade_date=_trade_date_today(),
            key=normalized_code,
            timeout=timeout,
        )
    except Exception:
        return None
    payload = result.data if isinstance(result.data, dict) else {}
    name = str(payload.get("name") or "").strip()
    if not name or name == normalized_code:
        return None
    return name


def search_sina_stock_suggestions(query: str, limit: int = 8, timeout: float = 2.5) -> list[dict[str, Any]]:
    normalized_query = str(query or "").strip()
    if not normalized_query:
        return []

    cache_key = normalized_query.lower()
    cached = _SINA_SUGGEST_CACHE.get(cache_key)
    now_ts = datetime.now().timestamp()
    if cached and now_ts - float(cached.get("stored_at") or 0) <= SINA_SUGGEST_CACHE_TTL_SECONDS:
        return [deepcopy(item) for item in (cached.get("items") or [])[:limit]]

    if get_data_gateway is None:
        return []
    try:
        result = get_data_gateway().search_stock(
            normalized_query,
            trade_date=_trade_date_today(),
            key=cache_key,
            timeout=timeout,
            retries=0,
        )
    except Exception:
        return []
    items = []
    for row in list(result.data or [])[:limit]:
        code = str(row.get("code") or "").strip()
        market = str(row.get("market") or infer_market_from_code(code)).strip().lower()
        if not CODE_PATTERN.fullmatch(code):
            continue
        items.append(
            {
                "code": code,
                "name": str(row.get("name") or code).strip() or code,
                "market": market,
                "sina": infer_sina_code(code, market),
                "source": "sina_search",
            }
        )

    _SINA_SUGGEST_CACHE[cache_key] = {
        "stored_at": now_ts,
        "items": deepcopy(items),
    }
    return [deepcopy(item) for item in items[:limit]]


def _historical_search_signature() -> tuple[tuple[str, int, int], ...]:
    signature: list[tuple[str, int, int]] = []
    for root, _label in HISTORICAL_STOCK_SEARCH_SOURCES:
        if not root.exists():
            continue
        file_count = 0
        latest_mtime_ns = 0
        for path in root.glob("*.json"):
            try:
                latest_mtime_ns = max(latest_mtime_ns, path.stat().st_mtime_ns)
                file_count += 1
            except OSError:
                continue
        signature.append((str(root), file_count, latest_mtime_ns))
    return tuple(signature)


def _merge_catalog_item(target: dict[str, Any], item: dict[str, Any], source_label: str) -> None:
    code = str(item.get("code") or "").strip()
    name = str(item.get("name") or item.get("stock_name") or code).strip() or code
    record = target.setdefault(
        code,
        {
            "code": code,
            "name": name,
            "market": infer_market_from_code(code),
            "sina": infer_sina_code(code),
            "sources": [],
            "history_label": source_label,
        },
    )

    if record.get("name") in {"", code} and name:
        record["name"] = name

    for field in ("market", "industry", "sector_code", "sina"):
        value = item.get(field)
        if value and not record.get(field):
            record[field] = value

    if not record.get("history_label"):
        record["history_label"] = source_label

    if source_label not in record["sources"]:
        record["sources"].append(source_label)


def _scan_historical_stock_file(path: Path, source_label: str, catalog: dict[str, dict[str, Any]]) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return

    stack: list[Any] = [payload]
    visited = 0
    while stack and visited < 20_000:
        current = stack.pop()
        visited += 1

        if isinstance(current, dict):
            code = str(current.get("code") or "").strip()
            name = str(current.get("name") or current.get("stock_name") or "").strip()
            if CODE_PATTERN.fullmatch(code) and name:
                _merge_catalog_item(catalog, current, source_label)
                continue
            stack.extend(current.values())
            continue

        if isinstance(current, list):
            stack.extend(current)


def list_historical_stock_catalog() -> list[dict[str, Any]]:
    signature = _historical_search_signature()
    cached_signature = _HISTORICAL_STOCK_CATALOG_CACHE.get("signature")
    if signature == cached_signature:
        return [deepcopy(item) for item in (_HISTORICAL_STOCK_CATALOG_CACHE.get("items") or [])]

    catalog: dict[str, dict[str, Any]] = {}
    for root, source_label in HISTORICAL_STOCK_SEARCH_SOURCES:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.json")):
            _scan_historical_stock_file(path, source_label, catalog)

    items = sorted(catalog.values(), key=lambda item: str(item.get("code") or ""))
    _HISTORICAL_STOCK_CATALOG_CACHE["signature"] = signature
    _HISTORICAL_STOCK_CATALOG_CACHE["items"] = items
    return [deepcopy(item) for item in items]


def load_watchlist_config(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).expanduser() if path else WATCHLIST_CONFIG_PATH
    if WatchlistConfigRepository is not None:
        return WatchlistConfigRepository(target).get()
    if not target.exists():
        return {"stocks": []}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {"stocks": []}
    if not isinstance(payload, dict):
        return {"stocks": []}
    stocks = payload.get("stocks")
    payload["stocks"] = stocks if isinstance(stocks, list) else []
    return payload


def save_watchlist_config(payload: dict[str, Any], path: str | Path | None = None) -> Path:
    target = Path(path).expanduser() if path else WATCHLIST_CONFIG_PATH
    if WatchlistConfigRepository is not None:
        return WatchlistConfigRepository(target).set(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def stock_is_active(item: dict[str, Any] | None) -> bool:
    if not isinstance(item, dict):
        return False
    return bool(item.get("active", True))


def _stock_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    stocks = payload.get("stocks")
    if isinstance(stocks, list):
        return stocks
    payload["stocks"] = []
    return payload["stocks"]


def _find_stock(payload: dict[str, Any], code: str) -> dict[str, Any] | None:
    for item in _stock_list(payload):
        if not isinstance(item, dict):
            continue
        if str(item.get("code") or "").strip() == code:
            return item
    return None


def _normalize_entry(entry: dict[str, Any], *, fallback_name: str | None = None, source: str | None = None) -> dict[str, Any]:
    normalized_code = normalize_stock_code(entry.get("code"))
    name = str(entry.get("name") or fallback_name or normalized_code).strip() or normalized_code
    market = str(entry.get("market") or infer_market_from_code(normalized_code)).strip().lower()
    if market not in {"sh", "sz"}:
        market = infer_market_from_code(normalized_code)

    normalized = deepcopy(entry)
    normalized["code"] = normalized_code
    normalized["name"] = name
    normalized["market"] = market
    normalized["sina"] = str(entry.get("sina") or infer_sina_code(normalized_code, market)).strip() or infer_sina_code(normalized_code, market)
    if source and not normalized.get("source"):
        normalized["source"] = source
    return normalized


def list_watchlist_stocks(payload: dict[str, Any] | None = None, *, path: str | Path | None = None) -> list[dict[str, Any]]:
    config = payload if payload is not None else load_watchlist_config(path)
    return [deepcopy(item) for item in _stock_list(config) if isinstance(item, dict) and item.get("code")]


def list_active_watchlist_stocks(payload: dict[str, Any] | None = None, *, path: str | Path | None = None) -> list[dict[str, Any]]:
    return [item for item in list_watchlist_stocks(payload, path=path) if stock_is_active(item)]


def list_archived_watchlist_stocks(payload: dict[str, Any] | None = None, *, path: str | Path | None = None) -> list[dict[str, Any]]:
    return [item for item in list_watchlist_stocks(payload, path=path) if not stock_is_active(item)]


def load_active_watchlist_codes(payload: dict[str, Any] | None = None, *, path: str | Path | None = None) -> list[str]:
    return [str(item.get("code")).strip() for item in list_active_watchlist_stocks(payload, path=path) if item.get("code")]


def upsert_watchlist_stock(
    code: Any,
    name: str | None = None,
    *,
    source: str = "manual",
    path: str | Path | None = None,
) -> dict[str, Any]:
    config = load_watchlist_config(path)
    stocks = _stock_list(config)
    normalized_code = normalize_stock_code(code)
    clean_name = str(name or "").strip()
    current = _find_stock(config, normalized_code)
    stamp = now_str()
    resolved_name = clean_name

    if current:
        if not resolved_name:
            current_name = str(current.get("name") or "").strip()
            if current_name and current_name != normalized_code:
                resolved_name = current_name
            else:
                resolved_name = fetch_stock_name(normalized_code, current.get("market"))
        before = deepcopy(current)
        current.update(
            _normalize_entry(
                {
                    **current,
                    "code": normalized_code,
                    "name": resolved_name or current.get("name") or normalized_code,
                },
                fallback_name=normalized_code,
                source=source,
            )
        )
        current.setdefault("created_at", before.get("created_at") or stamp)
        current["updated_at"] = stamp
        current["active"] = True
        current["archived_at"] = None
        changed = current != before
        status = "restored" if not stock_is_active(before) else ("updated" if changed else "exists")
        if changed:
            save_watchlist_config(config, path)
        return {
            "status": status,
            "changed": changed,
            "stock": deepcopy(current),
            "config_path": str((Path(path).expanduser() if path else WATCHLIST_CONFIG_PATH).resolve()),
        }

    if not resolved_name:
        resolved_name = fetch_stock_name(normalized_code)
    new_item = _normalize_entry(
        {
            "code": normalized_code,
            "name": resolved_name or normalized_code,
            "active": True,
            "created_at": stamp,
            "updated_at": stamp,
            "archived_at": None,
            "source": source,
        },
        fallback_name=normalized_code,
        source=source,
    )
    stocks.append(new_item)
    save_watchlist_config(config, path)
    return {
        "status": "added",
        "changed": True,
        "stock": deepcopy(new_item),
        "config_path": str((Path(path).expanduser() if path else WATCHLIST_CONFIG_PATH).resolve()),
    }


def archive_watchlist_stock(code: Any, *, path: str | Path | None = None) -> dict[str, Any]:
    config = load_watchlist_config(path)
    normalized_code = normalize_stock_code(code)
    current = _find_stock(config, normalized_code)
    if not current:
        raise ValueError(f"自选股中没有这只股票：{normalized_code}")

    if not stock_is_active(current):
        return {
            "status": "already_archived",
            "changed": False,
            "stock": deepcopy(current),
            "config_path": str((Path(path).expanduser() if path else WATCHLIST_CONFIG_PATH).resolve()),
        }

    current["active"] = False
    current["updated_at"] = now_str()
    current["archived_at"] = current["updated_at"]
    save_watchlist_config(config, path)
    return {
        "status": "archived",
        "changed": True,
        "stock": deepcopy(current),
        "config_path": str((Path(path).expanduser() if path else WATCHLIST_CONFIG_PATH).resolve()),
    }


def restore_watchlist_stock(code: Any, *, path: str | Path | None = None) -> dict[str, Any]:
    config = load_watchlist_config(path)
    normalized_code = normalize_stock_code(code)
    current = _find_stock(config, normalized_code)
    if not current:
        raise ValueError(f"归档区里没有这只股票：{normalized_code}")

    if stock_is_active(current):
        return {
            "status": "already_active",
            "changed": False,
            "stock": deepcopy(current),
            "config_path": str((Path(path).expanduser() if path else WATCHLIST_CONFIG_PATH).resolve()),
        }

    current.update(_normalize_entry(current, fallback_name=normalized_code))
    current["active"] = True
    current["updated_at"] = now_str()
    current["archived_at"] = None
    save_watchlist_config(config, path)
    return {
        "status": "restored",
        "changed": True,
        "stock": deepcopy(current),
        "config_path": str((Path(path).expanduser() if path else WATCHLIST_CONFIG_PATH).resolve()),
    }


__all__ = [
    "WATCHLIST_CONFIG_PATH",
    "archive_watchlist_stock",
    "fetch_stock_name",
    "infer_market_from_code",
    "infer_sina_code",
    "list_historical_stock_catalog",
    "list_active_watchlist_stocks",
    "list_archived_watchlist_stocks",
    "list_watchlist_stocks",
    "load_active_watchlist_codes",
    "load_watchlist_config",
    "normalize_stock_code",
    "restore_watchlist_stock",
    "save_watchlist_config",
    "search_sina_stock_suggestions",
    "stock_is_active",
    "upsert_watchlist_stock",
]
