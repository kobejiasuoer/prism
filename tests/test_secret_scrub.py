import subprocess
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
SKIP_DATA_DIRS = {"runtime", "artifacts", "analytics", "cache"}


def _git_repo_files(root: Path):
    """Return files git considers part of the repository.

    Uses ``git ls-files --cached --others --exclude-standard`` so that:
      * tracked files are scanned (catches anything actually committed),
      * untracked-but-not-ignored files are scanned (catches in-flight work
        before commit, e.g. new modules a developer just added),
      * gitignored runtime artifacts (``.prism-control.log``, ``*.log``,
        local caches, ``.venv``, etc.) are excluded automatically.

    The test is named ``..._committed_secret_or_privacy_markers`` and is
    intended to scan the repo's source surface, not local runtime noise.
    Returns ``None`` if git is unavailable so the caller can fall back.
    """
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return [Path(line) for line in result.stdout.splitlines() if line]


def iter_text_files(root: Path):
    candidates = _git_repo_files(root)
    if candidates is None:
        # Fallback: walk the filesystem. Same skip rules as before.
        candidates = [p.relative_to(root) for p in root.rglob("*") if p.is_file()]

    for rel_path in candidates:
        full = root / rel_path
        if not full.is_file():
            continue
        if len(rel_path.parts) >= 2 and rel_path.parts[0] == "data" and rel_path.parts[1] in SKIP_DATA_DIRS:
            continue
        if len(rel_path.parts) >= 2 and rel_path.parts[0] == "packages" and rel_path.parts[1] in {"data", "reports"}:
            continue
        if any(part in {".git", ".venv", "__pycache__", ".superpowers", "node_modules", ".next"} for part in rel_path.parts):
            continue
        if full.suffix.lower() in BINARY_SUFFIXES:
            continue
        if rel_path in SELF_SKIPS:
            continue
        yield full


def test_repo_has_no_committed_secret_or_privacy_markers():
    root = Path(".")

    for path in iter_text_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert all(marker not in text for marker in BAD_MARKERS), path
