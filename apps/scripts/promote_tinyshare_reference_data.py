#!/usr/bin/env python3
"""Promote Tinyshare reference supplement raw archives into Prism datasets."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_ROOT = REPO_ROOT / "packages"
CONTROL_PANEL_ROOT = REPO_ROOT / "apps" / "control-panel"
for path in (PACKAGES_ROOT, CONTROL_PANEL_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from prism_data.contracts import DatasetStatus, ProviderRole, ProviderResult  # noqa: E402
from prism_data.manifest import manifest_from_provider_result  # noqa: E402
from prism_data.repositories import DatasetRepository  # noqa: E402
from prism_data.utils import default_dataset_repository_root, hash_payload  # noqa: E402
try:
    from readiness import expected_trade_date  # noqa: E402
except Exception:  # pragma: no cover - CLI fallback.
    expected_trade_date = None  # type: ignore[assignment]


DEFAULT_REFERENCE_LATEST = REPO_ROOT / "data" / "prism_data" / "tinyshare_reference_supplement" / "latest_run.json"
TINYSHARE_ENDPOINT = "tinyshare://pro_api/reference_supplement"
LICENSE_SCOPE = "authorized_tinyshare_proxy"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote Tinyshare reference supplement raw data into Prism datasets.")
    parser.add_argument("--reference-run", default="", help="Reference supplement run directory. Defaults to latest_run.json.")
    parser.add_argument("--trade-date", default="")
    parser.add_argument("--repository-root", default="")
    parser.add_argument("--refresh-existing", action="store_true")
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def resolve_reference_run(raw: str) -> Path:
    if raw.strip():
        return resolve_path(raw).resolve()
    latest = read_json(DEFAULT_REFERENCE_LATEST)
    return resolve_path(str(latest["run_dir"])).resolve()


def compact_date(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())[:8]


def dash_date(value: Any) -> str:
    digits = compact_date(value)
    if len(digits) != 8:
        return str(value or "").strip()
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"


def digits_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    return "".join(ch for ch in text if ch.isdigit()).zfill(6)


def prism_code(ts_code: Any) -> str:
    text = str(ts_code or "").strip().upper()
    code = digits_code(text)
    if not code or len(code) != 6:
        return str(ts_code or "").strip().lower()
    suffix = text.split(".")[-1] if "." in text else ("SH" if code.startswith(("5", "6", "9")) else "BJ" if code.startswith(("4", "8")) else "SZ")
    return f"{'sh' if suffix == 'SH' else 'bj' if suffix == 'BJ' else 'sz'}{code}"


def safe_float(value: Any) -> float | None:
    if value in (None, "", "-", "None"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) or math.isinf(number) else number


def json_clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_clean(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if hasattr(value, "item"):
        try:
            return json_clean(value.item())
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def rows_from_path(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = read_json(path)
    return [dict(row) for row in rows] if isinstance(rows, list) else []


def rows_from_dir(raw_dir: Path, api: str) -> tuple[list[dict[str, Any]], list[Path]]:
    api_dir = raw_dir / api
    paths = sorted(api_dir.glob("*.json")) if api_dir.exists() else []
    return rows_from_paths(paths), paths


def rows_from_paths(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        for row in rows_from_path(path):
            rows.append(dict(row))
    return rows


def unique_rows(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for row in rows:
        fingerprint = "|".join(str(row.get(key) or "") for key in keys)
        if not fingerprint.strip("|"):
            fingerprint = json.dumps(json_clean(row), ensure_ascii=False, sort_keys=True)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        output.append(row)
    return output


def enrich_stock_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    ts_code = str(item.get("ts_code") or item.get("con_code") or item.get("symbol") or "").strip().upper()
    if ts_code:
        code = digits_code(ts_code)
        if len(code) == 6:
            item.setdefault("code", code)
            item.setdefault("symbol", prism_code(ts_code))
    for key in ("trade_date", "ann_date", "end_date", "list_date", "delist_date", "in_date", "out_date", "float_date", "unlock_date"):
        if item.get(key):
            item[key] = dash_date(item.get(key))
    return item


def enrich_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [enrich_stock_row(row) for row in rows]


def filter_800(rows: list[dict[str, Any]], universe_codes: set[str]) -> list[dict[str, Any]]:
    if not universe_codes:
        return rows
    output = []
    for row in rows:
        code = digits_code(row.get("ts_code") or row.get("con_code") or row.get("symbol") or row.get("code"))
        if code in universe_codes:
            output.append(row)
    return output


def universe_codes_from_report(reference_run: Path) -> set[str]:
    report_path = reference_run / "report.json"
    if not report_path.exists():
        return set()
    report = read_json(report_path)
    source_path = ((report.get("universe_meta") or {}) if isinstance(report, dict) else {}).get("source_path")
    if not source_path:
        return set()
    path = resolve_path(str(source_path))
    if not path.exists():
        return set()
    rows = read_json(path)
    codes: set[str] = set()
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            code = digits_code(row.get("code") or row.get("symbol"))
            if len(code) == 6:
                codes.add(code)
    return codes


def save_dataset(
    repository: DatasetRepository,
    *,
    dataset: str,
    trade_date: str,
    key: str,
    rows: Any,
    source_api: str,
    params: dict[str, Any],
    source_raw_paths: list[Path],
    refresh_existing: bool,
) -> dict[str, Any] | None:
    if repository.load_manifest(dataset, trade_date, key) and not refresh_existing:
        return None
    payload = json_clean(rows)
    result = ProviderResult(
        status=DatasetStatus.OK,
        data=payload,
        provider="tushare",
        provider_role=ProviderRole.PRIMARY,
        dataset=dataset,
        trade_date=trade_date,
        fetched_at=datetime.now(),
        asof=datetime.strptime(trade_date, "%Y-%m-%d"),
        ttl_seconds=86400,
        source_endpoint=TINYSHARE_ENDPOINT,
        params_hash=hash_payload({
            "source_api": source_api,
            "params": params,
            "source_raw_paths": [str(path) for path in source_raw_paths],
            "source_proxy": "tinyshare",
        }),
        payload_hash=hash_payload(payload),
        row_count=len(payload) if isinstance(payload, (list, dict, tuple, set)) else int(payload is not None),
        quality_flags=[],
        license_scope=LICENSE_SCOPE,
        live_small_allowed=False,
        request_key=key,
        extra={
            "source_api": source_api,
            "source_proxy": "tinyshare",
            "authority_provider_override": "tushare",
            "promoted_from_raw": True,
        },
    )
    manifest = manifest_from_provider_result(result, expected_trade_date=trade_date, live_small_allowed=False)
    data_path, manifest_path = repository.save_dataset(dataset, trade_date, key, payload, manifest)
    manifest["data_path"] = str(data_path.resolve())
    manifest["manifest_path"] = str(manifest_path.resolve())
    return manifest


def promote(reference_run: Path, trade_date: str, repository: DatasetRepository, *, refresh_existing: bool = False) -> dict[str, Any]:
    raw_dir = reference_run / "raw"
    universe_codes = universe_codes_from_report(reference_run)
    manifests: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    counts: dict[str, int] = {}

    def promote_one(dataset: str, key: str, rows: Any, source_api: str, source_paths: list[Path], params: dict[str, Any] | None = None) -> None:
        manifest = save_dataset(
            repository,
            dataset=dataset,
            trade_date=trade_date,
            key=key,
            rows=rows,
            source_api=source_api,
            params=params or {},
            source_raw_paths=source_paths,
            refresh_existing=refresh_existing,
        )
        row_count = len(rows) if isinstance(rows, (list, dict, tuple, set)) else int(rows is not None)
        counts[dataset] = row_count
        if manifest:
            manifests.append(manifest)
        else:
            skipped.append({"dataset": dataset, "key": key, "reason": "manifest_exists"})

    # Company profile and name-change references.
    stock_company_rows, stock_company_paths = rows_from_dir(raw_dir, "stock_company")
    if stock_company_paths:
        stock_company_rows = enrich_rows(unique_rows(stock_company_rows, ("ts_code", "exchange")))
        promote_one("reference.stock_company", "all", stock_company_rows, "stock_company", stock_company_paths)
    namechange_path = raw_dir / "namechange" / "all.json"
    if namechange_path.exists():
        rows = enrich_rows(rows_from_path(namechange_path))
        promote_one("reference.namechange", "all", rows, "namechange", [namechange_path])

    # Concept and board memberships.
    concept_path = raw_dir / "concept" / "all.json"
    if concept_path.exists():
        promote_one("reference.concept", "all", rows_from_path(concept_path), "concept", [concept_path])
    concept_rows, concept_paths = rows_from_dir(raw_dir, "concept_detail")
    if concept_paths:
        rows = enrich_rows(unique_rows(concept_rows, ("ts_code", "concept_code", "id", "name")))
        promote_one("reference.concept_detail", "hs300-zz500", rows, "concept_detail", concept_paths, {"universe": "hs300+zz500"})

    classify_rows, classify_paths = rows_from_dir(raw_dir, "index_classify")
    if classify_paths:
        promote_one("reference.industry_classify", "SW2021", unique_rows(classify_rows, ("index_code", "level")), "index_classify", classify_paths, {"src": "SW2021"})
    member_rows, member_paths = rows_from_dir(raw_dir, "index_member")
    if member_paths:
        rows = enrich_rows(filter_800(unique_rows(member_rows, ("index_code", "con_code", "in_date", "out_date")), universe_codes))
        promote_one("reference.industry_member", "SW2021-hs300-zz500", rows, "index_member", member_paths, {"src": "SW2021", "universe": "hs300+zz500"})

    ths_index_path = raw_dir / "ths_index" / "all.json"
    if ths_index_path.exists():
        promote_one("reference.ths_index", "all", rows_from_path(ths_index_path), "ths_index", [ths_index_path])
    ths_rows, ths_paths = rows_from_dir(raw_dir, "ths_member")
    if ths_paths:
        rows = enrich_rows(unique_rows(ths_rows, ("ts_code", "con_code", "in_date", "out_date", "is_new")))
        promote_one("reference.ths_member", "hs300-zz500", rows, "ths_member", ths_paths, {"universe": "hs300+zz500"})

    dc_index_path = raw_dir / "dc_index" / "all.json"
    if dc_index_path.exists():
        promote_one("reference.dc_index", "all", rows_from_path(dc_index_path), "dc_index", [dc_index_path])
    dc_member_dir = raw_dir / "dc_member"
    dc_paths = sorted(dc_member_dir.glob("*.json")) if dc_member_dir.exists() else []
    if dc_paths:
        if universe_codes and len(dc_paths) < len(universe_codes):
            skipped.append({
                "dataset": "reference.dc_member",
                "key": "hs300-zz500",
                "reason": "partial_optional_harvest_skipped",
                "raw_files": len(dc_paths),
                "expected_files": len(universe_codes),
            })
        else:
            possible_unfiltered = None
            for path in dc_paths:
                row_count = len(rows_from_path(path))
                if row_count >= 5000:
                    possible_unfiltered = {"path": str(path), "rows": row_count}
                    break
            if possible_unfiltered:
                skipped.append({
                    "dataset": "reference.dc_member",
                    "key": "hs300-zz500",
                    "reason": "possible_unfiltered_or_limit_hit",
                    **possible_unfiltered,
                })
            else:
                dc_rows, _dc_paths = rows_from_dir(raw_dir, "dc_member")
                rows = enrich_rows(unique_rows(dc_rows, ("ts_code", "con_code", "in_date", "out_date")))
                promote_one("reference.dc_member", "hs300-zz500", rows, "dc_member", dc_paths, {"universe": "hs300+zz500"})

    # Financial and market event supplements.
    mainbz_rows, mainbz_paths = rows_from_dir(raw_dir, "fina_mainbz")
    if mainbz_paths:
        rows = enrich_rows(filter_800(unique_rows(mainbz_rows, ("ts_code", "end_date", "bz_item", "type")), universe_codes))
        promote_one("financial.main_business", "hs300-zz500-recent", rows, "fina_mainbz", mainbz_paths, {"universe": "hs300+zz500"})

    for api, dataset, key in (
        ("margin_detail", "market.margin_detail", "recent"),
        ("margin_secs", "market.margin_secs", "recent"),
        ("block_trade", "market.block_trade", "recent"),
        ("hsgt_top10", "market.hsgt_top10", "recent"),
        ("ggt_top10", "market.ggt_top10", "recent"),
    ):
        rows, paths = rows_from_dir(raw_dir, api)
        if not paths:
            continue
        rows = enrich_rows(rows)
        promote_one(dataset, key, rows, api, paths)

    for api, dataset in (
        ("pledge_stat", "corporate_action.pledge_stat"),
        ("pledge_detail", "corporate_action.pledge_detail"),
        ("share_float", "corporate_action.share_float"),
        ("repurchase", "corporate_action.repurchase"),
    ):
        rows, paths = rows_from_dir(raw_dir, api)
        if not paths:
            continue
        rows = enrich_rows(filter_800(unique_rows(rows, ("ts_code", "ann_date", "end_date", "holder_name", "float_date")), universe_codes))
        promote_one(dataset, "all", rows, api, paths)

    audit_rows, audit_paths = rows_from_dir(raw_dir, "fina_audit")
    if audit_paths:
        rows = enrich_rows(unique_rows(audit_rows, ("ts_code", "end_date", "ann_date")))
        promote_one("financial.audit", "hs300-zz500", rows, "fina_audit", audit_paths, {"universe": "hs300+zz500"})

    report_rows, report_paths = rows_from_dir(raw_dir, "report_rc")
    if report_paths:
        rows = enrich_rows(filter_800(unique_rows(report_rows, ("ts_code", "report_date", "title", "org_name")), universe_codes))
        promote_one("research.report_rc", "recent", rows, "report_rc", report_paths)

    for api, dataset in (
        ("stk_factor", "technical.stk_factor"),
        ("cyq_perf", "technical.cyq_perf"),
        ("cyq_chips", "technical.cyq_chips"),
    ):
        if api == "cyq_chips":
            api_dir = raw_dir / api
            all_paths = sorted(api_dir.glob("*.json")) if api_dir.exists() else []
            chunk_paths = [path for path in all_paths if len(path.stem.split("_")) >= 3]
            paths = chunk_paths or all_paths
            rows = rows_from_paths(paths)
        else:
            rows, paths = rows_from_dir(raw_dir, api)
        if not paths:
            continue
        rows = enrich_rows(filter_800(rows, universe_codes))
        if api == "cyq_chips":
            rows = unique_rows(rows, ("ts_code", "trade_date", "price"))
        else:
            rows = unique_rows(rows, ("ts_code", "trade_date"))
        promote_one(dataset, "hs300-zz500-recent", rows, api, paths, {"universe": "hs300+zz500"})

    summary = {
        "ok": True,
        "trade_date": trade_date,
        "reference_run": str(reference_run),
        "dataset_root": str(repository.base_path.resolve()),
        "universe_count": len(universe_codes),
        "counts": counts,
        "written_manifests": len(manifests),
        "skipped": skipped,
        "source_endpoint": TINYSHARE_ENDPOINT,
        "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    out_path = reference_run / "promotion_report.json"
    out_path.write_text(json.dumps(json_clean(summary), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    summary["promotion_report_path"] = str(out_path.resolve())
    return summary


def main() -> int:
    args = parse_args()
    reference_run = resolve_reference_run(args.reference_run)
    trade_date = args.trade_date.strip() or (expected_trade_date() if expected_trade_date else "2026-05-29")
    repository = DatasetRepository(Path(args.repository_root).expanduser() if args.repository_root.strip() else default_dataset_repository_root())
    summary = promote(reference_run, trade_date, repository, refresh_existing=args.refresh_existing)
    print(json.dumps(json_clean(summary), ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
