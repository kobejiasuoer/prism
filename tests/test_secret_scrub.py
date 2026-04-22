from pathlib import Path


BAD_MARKERS = [
    "cookie=",
    "gho_",
    "xoxb-",
    "Authorization: Bearer",
    "http://127.0.0.1:7897",
    "/Users/yangbishang",
    "user:ou_",
]

BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".woff", ".woff2", ".docx", ".pyc"}
SELF_SKIPS = {Path("tests/test_secret_scrub.py"), Path("scripts/scrub-secrets.py")}


def iter_text_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", ".venv", "__pycache__", ".superpowers"} for part in path.parts):
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        if path in SELF_SKIPS:
            continue
        yield path


def test_repo_has_no_committed_secret_or_privacy_markers():
    root = Path(".")

    for path in iter_text_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert all(marker not in text for marker in BAD_MARKERS), path
