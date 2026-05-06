from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import CONFIG_PATH


@dataclass(frozen=True)
class QuantResearchConfig:
    path: Path
    data: dict[str, Any]
    checksum: str


def config_checksum(path: str | Path = CONFIG_PATH) -> str:
    target = Path(path)
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_quant_research_config(path: str | Path = CONFIG_PATH) -> QuantResearchConfig:
    target = Path(path)
    with target.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return QuantResearchConfig(path=target, data=data, checksum=config_checksum(target))
