#!/usr/bin/env python3
"""Shared ICML environment capability checks.

Tick 32: Gate G2/G3/G4 previously treated ``import venv`` as sufficient.
On the default Cursor image, ``venv.create(..., with_pip=True)`` fails
(missing ensurepip / python3.12-venv), so SIA per-run venvs only work when
``uv`` is on PATH (``SIA/sia/run_setup._create_venv`` prefers uv).

Tick 34: ``venv.create`` on some images calls ``sys.exit(1)`` instead of
raising, which killed G2/G3/G4 preflight before writing reports. Probe the
stdlib path in a subprocess so SystemExit cannot abort the parent.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


_VENV_PROBE_SCRIPT = r"""
import sys
from pathlib import Path
import venv

target = Path(sys.argv[1])
try:
    venv.create(str(target), with_pip=True)
except SystemExit as exc:
    code = exc.code if isinstance(exc.code, int) else 1
    sys.stderr.write(f"venv.create SystemExit:{code}\n")
    raise SystemExit(code)
except Exception as exc:
    sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
    raise SystemExit(2)
py = target / ("Scripts" if sys.platform == "win32" else "bin") / (
    "python.exe" if sys.platform == "win32" else "python"
)
raise SystemExit(0 if py.is_file() else 3)
"""


def probe_per_run_venv_capable() -> tuple[bool, str]:
    """Return whether SIA can create a per-run virtualenv on this host.

    Order matches ``SIA/sia/run_setup._create_venv``:
    1. ``uv venv`` if ``uv`` is on PATH
    2. else stdlib ``venv.create(..., with_pip=True)`` (needs ensurepip)
    """
    if shutil.which("uv"):
        return True, f"uv available at {shutil.which('uv')} (SIA per-run venv path)"

    try:
        import venv  # noqa: F401
    except Exception as exc:  # pragma: no cover
        return False, f"venv import failed: {exc}"

    tmp = Path(tempfile.mkdtemp(prefix="icml_venv_probe_"))
    target = tmp / "probe"
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _VENV_PROBE_SCRIPT, str(target)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode == 0:
            return True, f"{sys_executable_label()} venv.create(with_pip=True) ok"
        err = (proc.stderr or proc.stdout or "").strip()
        err_l = err.lower()
        if "ensurepip" in err_l or proc.returncode in (1, 2):
            return (
                False,
                "stdlib venv.create(with_pip=True) failed "
                f"(exit {proc.returncode}: {err or 'no output'}). "
                "Install uv (preferred on Cursor images) or python3-venv/ensurepip.",
            )
        return (
            False,
            "stdlib venv.create(with_pip=True) failed "
            f"(exit {proc.returncode}: {err or 'python executable missing'}). "
            "Install uv (preferred on Cursor images) or python3-venv/ensurepip.",
        )
    except subprocess.TimeoutExpired:
        return False, "stdlib venv.create probe timed out; install uv on Cursor images"
    except Exception as exc:
        return (
            False,
            "stdlib venv.create probe failed "
            f"({type(exc).__name__}: {exc}). "
            "Install uv (preferred on Cursor images) or python3-venv/ensurepip.",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def sys_executable_label() -> str:
    return sys.executable
