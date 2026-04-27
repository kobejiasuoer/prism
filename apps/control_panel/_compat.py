from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


APPS_ROOT = Path(__file__).resolve().parents[1]
LEGACY_CONTROL_PANEL_ROOT = APPS_ROOT / "control-panel"
REPO_ROOT = APPS_ROOT.parent


def _ensure_import_paths() -> None:
    for path in (LEGACY_CONTROL_PANEL_ROOT, REPO_ROOT, REPO_ROOT / "packages"):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)


def load_legacy_module(module_name: str, filename: str) -> ModuleType:
    _ensure_import_paths()
    import_name = f"_prism_legacy_control_panel_{module_name}"
    if import_name in sys.modules:
        return sys.modules[import_name]

    module_path = LEGACY_CONTROL_PANEL_ROOT / filename
    spec = importlib.util.spec_from_file_location(import_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load legacy control-panel module: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[import_name] = module
    spec.loader.exec_module(module)
    return module


class LegacyModuleProxy(ModuleType):
    def __setattr__(self, key: str, value: object) -> None:
        legacy_module = self.__dict__.get("_legacy_module")
        if isinstance(legacy_module, ModuleType) and not key.startswith("_"):
            setattr(legacy_module, key, value)
        super().__setattr__(key, value)


def install_legacy_proxy(module_name: str, legacy_module: ModuleType) -> None:
    module = sys.modules[module_name]
    module.__dict__["_legacy_module"] = legacy_module
    module.__class__ = LegacyModuleProxy


def export_public(module: ModuleType, target_globals: dict[str, object]) -> None:
    for key, value in module.__dict__.items():
        if key.startswith("__") and key.endswith("__"):
            continue
        target_globals[key] = value
