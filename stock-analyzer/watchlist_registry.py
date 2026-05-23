"""Compatibility shim — canonical lives at apps/control-panel/watchlist_registry.py.

Do not edit. All symbols are re-exported from the canonical module so that
stock-analyzer scripts continue to work without two copies drifting apart.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_CANONICAL = (
    Path(__file__).resolve().parent.parent
    / "apps" / "control-panel" / "watchlist_registry.py"
)

_CANONICAL_MODULE_NAME = "_prism_canonical_watchlist_registry"

def _load_canonical_module():
    cached = sys.modules.get(_CANONICAL_MODULE_NAME)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(_CANONICAL_MODULE_NAME, _CANONICAL)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load canonical watchlist_registry from {_CANONICAL}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_CANONICAL_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


_module = _load_canonical_module()

for _key, _value in _module.__dict__.items():
    if _key.startswith("__") and _key.endswith("__"):
        continue
    globals()[_key] = _value

del _key, _value
