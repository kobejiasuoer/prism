from __future__ import annotations

from ._compat import export_public, install_legacy_proxy, load_legacy_module


_module = load_legacy_module("app", "app.py")
install_legacy_proxy(__name__, _module)
export_public(_module, globals())
