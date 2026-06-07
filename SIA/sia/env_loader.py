"""Load project-level ``.env`` into ``os.environ`` before the orchestrator runs."""

from __future__ import annotations

import os
from pathlib import Path


def load_project_dotenv() -> Path | None:
    """Load ``.env`` from the current working directory or project root.

    Existing environment variables are not overwritten (``load_dotenv`` override=False).
    Returns the path loaded, or None if no ``.env`` file was found.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return None

    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_file():
            load_dotenv(resolved, override=False)
            return resolved
    return None


def required_keys_present(*key_names: str) -> dict[str, bool]:
    """Return whether each named env var is set and non-empty."""
    return {name: bool(os.getenv(name)) for name in key_names}
