from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .paths import ANALYTICS_ROOT, REPO_ROOT
from .repositories import artifact_row_to_dict
from .sqlite_store import connection


DATASET_RE = re.compile(r"^[A-Za-z0-9_./-]+$")


def now_partition_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def validate_dataset_name(dataset: str) -> str:
    value = str(dataset or "").strip().strip("/")
    if not value or value.startswith(".") or ".." in Path(value).parts or not DATASET_RE.fullmatch(value):
        raise ValueError(f"invalid analytics dataset name: {dataset!r}")
    return value


def write_jsonl_file(path: str | Path, records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(f"{target.suffix}.tmp")
    count = 0
    with tmp_path.open("w", encoding="utf-8") as handle:
        for record in records:
            if not isinstance(record, dict):
                raise TypeError("analytics JSONL records must be dicts")
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
            count += 1
    tmp_path.replace(target)
    return {"path": str(target), "record_count": count}


def write_jsonl_dataset(
    records: Iterable[dict[str, Any]],
    dataset: str,
    *,
    partition: dict[str, str] | None = None,
    filename: str | None = None,
    root: str | Path | None = None,
) -> dict[str, Any]:
    dataset_name = validate_dataset_name(dataset)
    base = Path(root).expanduser() if root else ANALYTICS_ROOT
    directory = base / dataset_name
    for key, value in sorted((partition or {}).items()):
        clean_key = validate_dataset_name(str(key)).replace("/", "_")
        clean_value = validate_dataset_name(str(value)).replace("/", "_")
        directory /= f"{clean_key}={clean_value}"
    output_name = filename or f"part-{now_partition_stamp()}.jsonl"
    return write_jsonl_file(directory / output_name, records)


def export_artifacts_jsonl(
    *,
    db_path: str | Path | None = None,
    repo_root: str | Path | None = None,
    output_path: str | Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).expanduser().resolve() if repo_root else REPO_ROOT
    query = "SELECT * FROM artifacts ORDER BY COALESCE(generated_at, mtime) DESC, path"
    params: tuple[Any, ...] = ()
    if limit is not None:
        query += " LIMIT ?"
        params = (limit,)

    with connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    records = [artifact_row_to_dict(row) for row in rows]

    if output_path:
        target = Path(output_path).expanduser()
        if not target.is_absolute():
            target = root / target
        result = write_jsonl_file(target, records)
    else:
        result = write_jsonl_dataset(
            records,
            "artifact_index",
            partition={"exported_at": datetime.now().strftime("%Y-%m-%d")},
            filename=f"artifacts-{now_partition_stamp()}.jsonl",
            root=root / "data" / "analytics",
        )

    return {"ok": True, **result}


def duckdb_available() -> bool:
    return importlib.util.find_spec("duckdb") is not None


def duckdb_query(sql: str, *, database: str | Path | None = None) -> list[dict[str, Any]]:
    if not duckdb_available():
        raise RuntimeError("DuckDB 未安装；如需本地分析查询，请先在项目环境中安装 duckdb。")
    import duckdb  # type: ignore[import-not-found]

    conn = duckdb.connect(str(database) if database else ":memory:")
    try:
        result = conn.execute(sql)
        columns = [column[0] for column in result.description or []]
        return [dict(zip(columns, row, strict=False)) for row in result.fetchall()]
    finally:
        conn.close()
