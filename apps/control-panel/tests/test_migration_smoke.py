from pathlib import Path


def test_control_panel_files_exist():
    root = Path("apps/control-panel")

    assert (root / "app.py").exists()
    assert (root / "dashboard_data.py").exists()
    assert (root / "watchlist_registry.py").exists()


def test_next_frontend_files_exist():
    root = Path("apps/web")

    assert (root / "package.json").exists()
    assert (root / "next.config.ts").exists()
    assert (root / "src" / "app" / "page.tsx").exists()
    assert (root / "src" / "app" / "portfolio" / "page.tsx").exists()
    assert (root / "src" / "app" / "discovery" / "page.tsx").exists()
    assert (root / "src" / "app" / "review" / "page.tsx").exists()
    assert (root / "src" / "app" / "settings" / "page.tsx").exists()
