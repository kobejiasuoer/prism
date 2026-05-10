"""Repository for persisted Prism raw datasets and manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DatasetRepository:
    def __init__(self, base_path: Path | str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sanitize_key(value: str | None) -> str:
        text = str(value or "").strip()
        if not text:
            return "default"
        return "".join(ch if ch.isalnum() or ch in {"-", "_", ".", "+"} else "_" for ch in text)

    def dataset_dir(self, dataset_name: str, trade_date: str) -> Path:
        safe_dataset = self.sanitize_key(dataset_name)
        safe_trade_date = self.sanitize_key(trade_date or "unknown")
        path = self.base_path / safe_dataset / safe_trade_date
        path.mkdir(parents=True, exist_ok=True)
        return path

    def dataset_paths(self, dataset_name: str, trade_date: str, key: str) -> tuple[Path, Path]:
        dataset_dir = self.dataset_dir(dataset_name, trade_date)
        safe_key = self.sanitize_key(key)
        return dataset_dir / f"{safe_key}.json", dataset_dir / f"{safe_key}.manifest.json"

    def save_dataset(
        self,
        dataset_name: str,
        trade_date: str,
        key: str,
        data: Any,
        manifest: dict[str, Any],
    ) -> tuple[Path, Path]:
        data_path, manifest_path = self.dataset_paths(dataset_name, trade_date, key)
        data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        payload = dict(manifest)
        payload["data_path"] = str(data_path.resolve())
        payload["manifest_path"] = str(manifest_path.resolve())
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return data_path, manifest_path

    def save_manifest(
        self,
        dataset_name: str,
        trade_date: str,
        key: str,
        manifest: dict[str, Any],
    ) -> Path:
        _, manifest_path = self.dataset_paths(dataset_name, trade_date, key)
        payload = dict(manifest)
        payload["manifest_path"] = str(manifest_path.resolve())
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return manifest_path

    def load_manifest(self, dataset_name: str, trade_date: str, key: str) -> dict[str, Any] | None:
        _, manifest_path = self.dataset_paths(dataset_name, trade_date, key)
        if not manifest_path.exists():
            return None
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def load_dataset(self, dataset_name: str, trade_date: str, key: str) -> tuple[Any, dict[str, Any] | None]:
        data_path, manifest_path = self.dataset_paths(dataset_name, trade_date, key)
        if not data_path.exists():
            return None, None
        try:
            data = json.loads(data_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = None
        manifest = None
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                manifest = None
        return data, manifest

    def list_manifests(self, dataset_name: str, trade_date: str) -> list[dict[str, Any]]:
        dataset_dir = self.dataset_dir(dataset_name, trade_date)
        manifests: list[dict[str, Any]] = []
        for path in sorted(dataset_dir.glob("*.manifest.json")):
            try:
                manifests.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return manifests


__all__ = ["DatasetRepository"]
