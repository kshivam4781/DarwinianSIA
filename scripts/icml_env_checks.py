#!/usr/bin/env python3
"""Shared ICML environment capability checks.

Tick 32: Gate G2/G3/G4 previously treated ``import venv`` as sufficient.
On the default Cursor image, ``venv.create(..., with_pip=True)`` fails
(missing ensurepip / python3.12-venv), so SIA per-run venvs only work when
``uv`` is on PATH (``SIA/sia/run_setup._create_venv`` prefers uv).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path


def probe_per_run_venv_capable() -> tuple[bool, str]:
    """Return whether SIA can create a per-run virtualenv on this host.

    Order matches ``SIA/sia/run_setup._create_venv``:
    1. ``uv venv`` if ``uv`` is on PATH
    2. else stdlib ``venv.create(..., with_pip=True)`` (needs ensurepip)
    """
    if shutil.which("uv"):
        return True, f"uv available at {shutil.which('uv')} (SIA per-run venv path)"

    try:
        import venv
    except Exception as exc:  # pragma: no cover
        return False, f"venv import failed: {exc}"

    tmp = Path(tempfile.mkdtemp(prefix="icml_venv_probe_"))
    target = tmp / "probe"
    try:
        venv.create(str(target), with_pip=True)
        py = target / ("Scripts" if os.name == "nt" else "bin") / (
            "python.exe" if os.name == "nt" else "python"
        )
        if py.is_file():
            return True, f"{sys_executable_label()} venv.create(with_pip=True) ok"
        return False, "venv.create returned but python executable missing"
    except Exception as exc:
        return (
            False,
            "stdlib venv.create(with_pip=True) failed "
            f"({type(exc).__name__}: {exc}). "
            "Install uv (preferred on Cursor images) or python3-venv/ensurepip.",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def sys_executable_label() -> str:
    import sys

    return sys.executable
