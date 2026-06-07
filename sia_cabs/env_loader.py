"""Load project .env before SIA reads API key environment variables."""

from __future__ import annotations

from pathlib import Path


def load_project_dotenv() -> bool:
    """Load `.env` from the SIA2 project root. Returns True if a file was loaded."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False

    project_root = Path(__file__).resolve().parents[1]
    candidates = [Path.cwd() / ".env", project_root / ".env"]
    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=False)
            return True
    return False
