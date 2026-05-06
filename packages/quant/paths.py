from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    override = os.environ.get("PRISM_REPO_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


REPO_ROOT = repo_root()
DATA_ROOT = REPO_ROOT / "data"
CONFIG_ROOT = DATA_ROOT / "config"
CONFIG_PATH = CONFIG_ROOT / "quant-research.json"

DATA_QUANT_ROOT = DATA_ROOT / "quant"
BASELINES_ROOT = DATA_QUANT_ROOT / "baselines"
BENCHMARKS_ROOT = DATA_QUANT_ROOT / "benchmarks"
PRICE_ROOT = DATA_QUANT_ROOT / "price"
EXECUTION_ROOT = DATA_QUANT_ROOT / "execution"
PANELS_ROOT = DATA_QUANT_ROOT / "panels"
LABELS_ROOT = DATA_QUANT_ROOT / "labels"
FACTORS_ROOT = DATA_QUANT_ROOT / "factors"
MODELS_ROOT = DATA_QUANT_ROOT / "models"
BACKTESTS_ROOT = DATA_QUANT_ROOT / "backtests"
REPORTS_ROOT = DATA_QUANT_ROOT / "reports"
LEDGERS_ROOT = DATA_QUANT_ROOT / "ledgers"


QUANT_DIRECTORIES = (
    DATA_QUANT_ROOT,
    BASELINES_ROOT,
    BENCHMARKS_ROOT,
    PRICE_ROOT,
    EXECUTION_ROOT,
    PANELS_ROOT,
    LABELS_ROOT,
    FACTORS_ROOT,
    MODELS_ROOT,
    BACKTESTS_ROOT,
    REPORTS_ROOT,
    LEDGERS_ROOT,
)


def ensure_quant_dirs() -> None:
    for path in QUANT_DIRECTORIES:
        path.mkdir(parents=True, exist_ok=True)


def workspace_relative(path: str | Path, *, root: Path | None = None) -> str:
    target = Path(path).expanduser().resolve()
    base = (root or REPO_ROOT).resolve()
    try:
        return str(target.relative_to(base))
    except ValueError:
        return str(target)


def resolve_workspace_path(path: str | Path, *, root: Path | None = None) -> Path:
    target = Path(path).expanduser()
    if target.is_absolute():
        return target.resolve()
    return ((root or REPO_ROOT) / target).resolve()
