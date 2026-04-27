from __future__ import annotations

from pathlib import Path


_APP_PACKAGE_DIR = Path(__file__).resolve().parents[1] / "apps" / "control-panel"
if _APP_PACKAGE_DIR.exists():
    __path__.append(str(_APP_PACKAGE_DIR))
