from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_REAL_ROOT = Path(__file__).resolve().parents[1] / "apps" / "control-panel"
_REAL_PATH = _REAL_ROOT / "app.py"

if str(_REAL_ROOT) not in sys.path:
    sys.path.insert(0, str(_REAL_ROOT))

_spec = importlib.util.spec_from_file_location(__name__, _REAL_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Unable to load Prism control panel app from {_REAL_PATH}")

_module = importlib.util.module_from_spec(_spec)
sys.modules[__name__] = _module
_spec.loader.exec_module(_module)
globals().update(_module.__dict__)
