from pathlib import Path


def test_start_script_targets_local_control_panel() -> None:
    script_path = Path("start_prism.sh")

    assert script_path.exists()

    content = script_path.read_text(encoding="utf-8")

    assert "#!/usr/bin/env bash" in content
    assert ".venv/bin/uvicorn" in content
    assert "control_panel.app:app" in content
    assert "127.0.0.1" in content
    assert "8000" in content
    assert "Starting Prism control panel" in content
