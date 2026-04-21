from pathlib import Path


def test_core_screener_files_exist():
    root = Path("packages/screener")

    assert (root / "scan.py").exists()
    assert (root / "ai_screening.py").exists()
    assert (root / "midday_verify.py").exists()
    assert (root / "candidate_lifecycle.py").exists()
    assert (root / "generate_feishu_message.py").exists()
