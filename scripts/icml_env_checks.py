#!/usr/bin/env python3
"""Shared ICML environment capability checks.

Tick 32: Gate G2/G3/G4 previously treated ``import venv`` as sufficient.
On the default Cursor image, ``venv.create(..., with_pip=True)`` fails
(missing ensurepip / python3.12-venv), so SIA per-run venvs only work when
``uv`` is on PATH (``SIA/sia/run_setup._create_venv`` prefers uv).

Tick 34: ``venv.create`` on some images calls ``sys.exit(1)`` instead of
raising, which killed G2/G3/G4 preflight before writing reports. Probe the
stdlib path in a subprocess so SystemExit cannot abort the parent.

Tick 265: Cron often boots a linked env whose SYSTEM snapshot still lacks uv
(Portal Save of draft AGENT builds does not stick). ``ensure_uv_on_path`` can
install Astral uv into ``~/.local/bin`` and prepend it to ``PATH`` so G2/G3/G4
preflight + subsequent ``sia run`` no longer depend on Portal Save for
``per_run_venv``.

Tick 266: Same cron boots also lack ``huggingface_hub`` (needed for
``--fetch-diamond``) and a host-level ``sia`` install. ``ensure_icml_runtime_deps``
bootstraps those via ``pip install --user`` and prepends ``SIA/`` onto
``PYTHONPATH`` so live G2→G3→G4 only needs secrets + HF gpqa accept — not a
Portal-Saved package snapshot.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

UV_INSTALL_URL = "https://astral.sh/uv/install.sh"
_LOCAL_BIN = Path.home() / ".local" / "bin"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SIA_PKG_ROOT = _REPO_ROOT / "SIA"
_RUNTIME_PIP_PACKAGES = ("huggingface_hub",)

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


def _prepend_local_bin_to_path() -> None:
    """Ensure ``~/.local/bin`` is first on PATH (Astral uv default install dir)."""
    local = str(_LOCAL_BIN)
    path = os.environ.get("PATH", "")
    parts = [p for p in path.split(os.pathsep) if p]
    if local in parts:
        parts = [local, *[p for p in parts if p != local]]
    else:
        parts = [local, *parts]
    os.environ["PATH"] = os.pathsep.join(parts)


def ensure_uv_on_path(*, allow_install: bool = True) -> tuple[bool, str]:
    """Return whether ``uv`` is on PATH, optionally installing it.

    When ``allow_install`` is True and ``uv`` is missing, downloads the official
    Astral install script and runs it (no sudo; installs to ``~/.local/bin``).
    Always prepends ``~/.local/bin`` to ``PATH`` when present so child ``sia``
    processes inherit uv.
    """
    _prepend_local_bin_to_path()
    existing = shutil.which("uv")
    if existing:
        return True, f"uv available at {existing}"

    if not allow_install:
        return False, "uv not on PATH (install disabled)"

    try:
        proc = subprocess.run(
            ["sh", "-c", f'curl -LsSf "{UV_INSTALL_URL}" | sh'],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "uv install timed out (curl|sh)"
    except Exception as exc:
        return False, f"uv install failed ({type(exc).__name__}: {exc})"

    _prepend_local_bin_to_path()
    installed = shutil.which("uv")
    if installed:
        return True, f"uv installed at {installed} (Astral bootstrap)"

    err = (proc.stderr or proc.stdout or "").strip()
    return (
        False,
        "uv install finished but uv still not on PATH "
        f"(exit {proc.returncode}: {err[:300] or 'no output'})",
    )


def probe_per_run_venv_capable(*, bootstrap_uv: bool = False) -> tuple[bool, str]:
    """Return whether SIA can create a per-run virtualenv on this host.

    Order matches ``SIA/sia/run_setup._create_venv``:
    1. ``uv venv`` if ``uv`` is on PATH (optionally bootstrap via ``ensure_uv_on_path``)
    2. else stdlib ``venv.create(..., with_pip=True)`` (needs ensurepip)

    Gate runners should pass ``bootstrap_uv=True`` so cron images without a
    Portal-Saved uv snapshot still clear ``per_run_venv`` before paid runs.
    """
    if bootstrap_uv:
        ok_uv, uv_detail = ensure_uv_on_path(allow_install=True)
        if ok_uv:
            return True, f"{uv_detail} (SIA per-run venv path)"
        # Fall through to stdlib probe; keep bootstrap failure text if that fails.
        bootstrap_note = uv_detail
    else:
        bootstrap_note = ""
        _prepend_local_bin_to_path()
        if shutil.which("uv"):
            return True, f"uv available at {shutil.which('uv')} (SIA per-run venv path)"

    try:
        import venv  # noqa: F401
    except Exception as exc:  # pragma: no cover
        suffix = f" (uv bootstrap: {bootstrap_note})" if bootstrap_note else ""
        return False, f"venv import failed: {exc}{suffix}"

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
        hint = (
            "Install uv (preferred on Cursor images) or python3-venv/ensurepip."
        )
        if bootstrap_note:
            hint = f"uv bootstrap failed ({bootstrap_note}); {hint}"
        if "ensurepip" in err_l or proc.returncode in (1, 2):
            return (
                False,
                "stdlib venv.create(with_pip=True) failed "
                f"(exit {proc.returncode}: {err or 'no output'}). {hint}",
            )
        return (
            False,
            "stdlib venv.create(with_pip=True) failed "
            f"(exit {proc.returncode}: {err or 'python executable missing'}). {hint}",
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


def _module_importable(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


def _pip_install_user(*packages: str) -> tuple[bool, str]:
    """Install packages with ``python -m pip install --user`` (no sudo)."""
    if not packages:
        return True, "no packages requested"
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--user",
        "-q",
        *packages,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"pip install timed out for {', '.join(packages)}"
    except Exception as exc:
        return False, f"pip install failed ({type(exc).__name__}: {exc})"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return (
            False,
            f"pip install exit {proc.returncode} for {', '.join(packages)}: "
            f"{err[:400] or 'no output'}",
        )
    return True, f"pip installed {', '.join(packages)}"


def ensure_sia_on_pythonpath() -> tuple[bool, str]:
    """Prepend monorepo ``SIA/`` to ``PYTHONPATH`` so ``python -m sia`` works.

    Gate runners default ``cwd=SIA/``, which already makes ``-m sia`` work, but
    child tools / preflight imports often run from the repo root. Mutating
    ``os.environ['PYTHONPATH']`` (and ``sys.path``) keeps both consistent.
    """
    sia_root = _SIA_PKG_ROOT
    if not (sia_root / "sia" / "__init__.py").is_file():
        return False, f"SIA package missing at {sia_root}"

    sia_s = str(sia_root)
    if sia_s not in sys.path:
        sys.path.insert(0, sia_s)

    existing = os.environ.get("PYTHONPATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    if sia_s in parts:
        parts = [sia_s, *[p for p in parts if p != sia_s]]
    else:
        parts = [sia_s, *parts]
    os.environ["PYTHONPATH"] = os.pathsep.join(parts)

    if _module_importable("sia"):
        return True, f"sia importable via PYTHONPATH={sia_s}"
    return False, f"sia still not importable after PYTHONPATH prepend ({sia_s})"


def ensure_icml_runtime_deps(*, allow_install: bool = True) -> tuple[bool, str]:
    """Ensure host deps for live G2→G3→G4 without a Portal-Saved install snapshot.

    1. ``ensure_uv_on_path`` (per-run venvs)
    2. ``ensure_sia_on_pythonpath`` (``python -m sia`` from repo root)
    3. ``huggingface_hub`` for ``--fetch-diamond`` / HF gpqa materialization

    Returns ``(ok, detail)``. When ``allow_install`` is False, missing pip
    packages are reported as failures without attempting install.
    """
    notes: list[str] = []

    ok_uv, uv_detail = ensure_uv_on_path(allow_install=allow_install)
    if not ok_uv:
        return False, f"uv required for SIA per-run venvs: {uv_detail}"
    notes.append(uv_detail)

    ok_sia, sia_detail = ensure_sia_on_pythonpath()
    if not ok_sia:
        return False, sia_detail
    notes.append(sia_detail)

    missing = [p for p in _RUNTIME_PIP_PACKAGES if not _module_importable(p)]
    if missing:
        if not allow_install:
            return (
                False,
                f"missing runtime packages {missing} (install disabled); "
                + "; ".join(notes),
            )
        ok_pip, pip_detail = _pip_install_user(*missing)
        notes.append(pip_detail)
        if not ok_pip:
            return False, "; ".join(notes)
        still = [p for p in missing if not _module_importable(p)]
        if still:
            # User-site may need a path refresh in this process.
            user_site = None
            try:
                import site

                user_site = site.getusersitepackages()
            except Exception:
                user_site = None
            if user_site and user_site not in sys.path:
                sys.path.append(user_site)
            still = [p for p in missing if not _module_importable(p)]
            if still:
                return (
                    False,
                    f"packages still missing after pip: {still}; " + "; ".join(notes),
                )
        notes.append(f"bootstrapped {', '.join(missing)}")
    else:
        notes.append("huggingface_hub already importable")

    return True, "; ".join(notes)
