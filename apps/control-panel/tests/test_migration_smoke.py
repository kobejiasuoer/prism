from pathlib import Path


def test_control_panel_files_exist():
    root = Path("apps/control-panel")

    assert (root / "app.py").exists()
    assert (root / "dashboard_data.py").exists()
    assert (root / "watchlist_registry.py").exists()
    assert (root / "templates" / "ask.html").exists()
    assert (root / "templates" / "dashboard.html").exists()
    assert (root / "static" / "control-panel.css").exists()
