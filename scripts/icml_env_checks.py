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

Tick 279: Runtime package bootstrap prefers ``uv pip install --python
<sys.executable>`` before ``python -m pip install --user``. Cursor / Astral
ephemeral envs often have no ``pip`` module; pip-only bootstrap falsely failed
``runtime_deps`` (and blocked ``ready_for_live`` / ``ready_for_dry_run``) even
when uv was already on PATH.

Tick 280: Bare ``uv pip install --python <system>`` tries to write into
``/usr/local/lib/.../dist-packages`` and fails with Permission denied on
read-only system Pythons. On pip-less boots the Tick 279 pip fallback also
fails → ``runtime_deps`` clears. ``_uv_pip_install`` now uses ``--target``
into the user site-packages (pip ``--user`` equivalent) and refreshes
``sys.path``.

Tick 281: Tick 280 only patched the parent ``sys.path``. Under
``PYTHONNOUSERSITE=1`` or venvs that disable user site, child processes
(and a fresh interpreter) cannot import ``huggingface_hub`` from the
``--target`` dir → ``--fetch-diamond`` materialize fails after secrets land.
``_expose_user_site_on_pythonpath`` mirrors ``ensure_sia_on_pythonpath``:
prepend the user site onto ``PYTHONPATH`` (and ``sys.path``) so G2/G3/G4
subprocesses inherit bootstrapped runtime deps.

Tick 282: G2/G3/G4/pipeline historically called ``ensure_icml_runtime_deps``
only inside ``run_preflight`` *after* ``materialize_from_hf``. On a fresh
boot without ``huggingface_hub``, ``--live --fetch-diamond`` (and cron
preflight materialize attempts) fail at import before bootstrap can install
it. ``ensure_deps_before_diamond_fetch`` runs the same bootstrap *before*
HF/CSV materialize.

Tick 283: ``sum_run_dirs_cost_usd`` / ``reconcile_gate_spend_usd`` let the
live pipeline bump ``SIA_BUDGET_SPENT_USD`` from actual ``total_cost_usd``
in run artifacts (× meta overhead) instead of only the gate estimate — so
G4 is not refused when G2/G3 come in under estimate, and overruns are
visible before the next gate.

Tick 284: Mid-stack crash after G2 left the next cron tick stuck —
``run_id_free`` fails on the completed G2 dir and in-process
``SIA_BUDGET_SPENT_USD`` resets to 0. ``darwinian_run_complete`` +
``docs/icml_budget_spent.json`` ledger let the live pipeline resume
(skip completed gates, reload spend, project only remaining estimates).

Tick 285: Tick 284 gitignored the ledger while ``runs/`` stay gitignored,
so a fresh cron VM had neither artifacts nor ledger — resume was same-VM
only. Stop gitignoring the ledger (USD amounts are not secrets) and trust
``stages_complete`` + ``run_ids`` when local run dirs are absent so the
next tip commit can skip completed gates cross-VM.

Tick 268: Machine-readable ``docs/icml_secrets_status.json`` + human unblock
doc so cron ticks stop re-prioritizing Portal Save when packages already
bootstrap in-preflight. Never records secret values.

Tick 269: Tip lineage discovery / guard. Cron often boots a fresh branch from
``main`` without ICML docs. ``collect_icml_tip_status`` +
``scripts/icml_recover_tip.py`` recover the highest Tick tip; live pipeline
refuses ``--live`` on a stale tree so paid GPQA cannot burn budget on pre-CABS
code.

Tick 277: Load gitignored ``.env`` for missing secret names (presence only;
never log values) and auto-detect a local ``gpqa_diamond.csv`` so cron can
pass ``--diamond-csv`` and mark ``fetch_diamond_ok`` without ``HF_TOKEN``.

Tick 278: G2/G3/G4/pipeline ``--fetch-diamond`` auto-wires the same local CSV
via ``autowire_diamond_csv`` (cron no longer the only path that skips HF).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UV_INSTALL_URL = "https://astral.sh/uv/install.sh"
_LOCAL_BIN = Path.home() / ".local" / "bin"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SIA_PKG_ROOT = _REPO_ROOT / "SIA"
_RUNTIME_PIP_PACKAGES = ("huggingface_hub",)
_SECRET_ENV_NAMES = (
    "ANTHROPIC_API_KEY",
    "NEBIUS_API_KEY",
    "HF_TOKEN",
    "HUGGINGFACE_HUB_TOKEN",
)
# Conventional diamond CSV drop paths (Tick 277). Prefer env override.
_DIAMOND_CSV_CANDIDATES = (
    "gpqa_diamond.csv",
    "docs/private/gpqa_diamond.csv",
    ".local/gpqa_diamond.csv",
)

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


def _user_site_packages() -> Path:
    """Return a writable user site-packages dir (pip ``--user`` equivalent)."""
    try:
        import site

        user_site = site.getusersitepackages()
        if isinstance(user_site, str) and user_site:
            return Path(user_site)
    except Exception:
        pass
    major, minor = sys.version_info[:2]
    return Path.home() / ".local" / "lib" / f"python{major}.{minor}" / "site-packages"


def _ensure_path_entry(entry: str) -> None:
    """Prepend ``entry`` onto ``sys.path`` when missing (post user-site install)."""
    if entry and entry not in sys.path:
        sys.path.insert(0, entry)


def _expose_user_site_on_pythonpath(user_site: Path | str | None = None) -> str:
    """Expose user site-packages on ``sys.path`` *and* ``PYTHONPATH`` (Tick 281).

    ``uv pip --target <user_site>`` (Tick 280) writes packages where a normal
    host Python finds them via ``site.ENABLE_USER_SITE``. Child processes that
    set ``PYTHONNOUSERSITE=1`` (or run inside a venv that disables user site)
    do **not** see that directory unless it is also on ``PYTHONPATH``. G2/G3/G4
    launch ``sia`` with ``env=os.environ.copy()``, so mutating ``PYTHONPATH``
    here keeps ``huggingface_hub`` importable for diamond materialize / helpers
    after secrets land.
    """
    target = Path(user_site) if user_site is not None else _user_site_packages()
    entry = str(target)
    if not entry:
        return entry
    _ensure_path_entry(entry)
    existing = os.environ.get("PYTHONPATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    if entry in parts:
        parts = [entry, *[p for p in parts if p != entry]]
    else:
        parts = [entry, *parts]
    os.environ["PYTHONPATH"] = os.pathsep.join(parts)
    return entry


def _uv_pip_install(*packages: str) -> tuple[bool, str]:
    """Install packages via ``uv pip`` into the *user* site (no sudo).

    Tick 280: system Pythons are often read-only (``/usr/local/lib/...``). Bare
    ``uv pip install --python <exe>`` then fails with Permission denied; on
    pip-less interpreters the pip ``--user`` fallback is also unavailable.
    ``--target <user_site>`` mirrors ``pip install --user`` into a writable
    location and keeps huggingface_hub bootstrap working without Portal Save.

    Tick 281: also expose that target on ``PYTHONPATH`` (not only ``sys.path``)
    so PYTHONNOUSERSITE / venv children inherit the install.
    """
    if not packages:
        return True, "no packages requested"
    _prepend_local_bin_to_path()
    uv = shutil.which("uv")
    if not uv:
        return False, "uv not on PATH for package install"

    target = _user_site_packages()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"cannot create user site {target}: {exc}"

    cmd = [
        uv,
        "pip",
        "install",
        "--python",
        sys.executable,
        "--target",
        str(target),
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
        return False, f"uv pip install timed out for {', '.join(packages)}"
    except Exception as exc:
        return False, f"uv pip install failed ({type(exc).__name__}: {exc})"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return (
            False,
            f"uv pip install exit {proc.returncode} for {', '.join(packages)}: "
            f"{err[:400] or 'no output'}",
        )
    _expose_user_site_on_pythonpath(target)
    return True, f"uv pip installed {', '.join(packages)} into {target}"


def _pip_install_user(*packages: str) -> tuple[bool, str]:
    """Install packages into the active interpreter (Tick 266 / 279 / 280).

    Prefer ``uv pip install --python <sys.executable> --target <user_site>``
    when uv is available — works on pip-less Astral ephemeral envs and
    read-only system Pythons (Tick 280). Fall back to ``python -m pip
    install --user``.
    """
    if not packages:
        return True, "no packages requested"

    ok_uv, uv_detail = _uv_pip_install(*packages)
    if ok_uv:
        return True, uv_detail

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
        return (
            False,
            f"{uv_detail}; then pip install timed out for {', '.join(packages)}",
        )
    except Exception as exc:
        return (
            False,
            f"{uv_detail}; then pip install failed ({type(exc).__name__}: {exc})",
        )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return (
            False,
            f"{uv_detail}; then pip install exit {proc.returncode} for "
            f"{', '.join(packages)}: {err[:400] or 'no output'}",
        )
    return True, f"pip installed {', '.join(packages)} (after uv miss: {uv_detail})"


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
    4. Tick 281: expose user site on ``PYTHONPATH`` so PYTHONNOUSERSITE /
       venv children still import ``--target`` bootstrapped packages

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
            _expose_user_site_on_pythonpath()
            still = [p for p in missing if not _module_importable(p)]
            if still:
                return (
                    False,
                    f"packages still missing after pip: {still}; " + "; ".join(notes),
                )
        notes.append(f"bootstrapped {', '.join(missing)}")
    else:
        notes.append("huggingface_hub already importable")

    # Tick 281: always publish user site on PYTHONPATH (even when packages were
    # already importable via ENABLE_USER_SITE) so child env copies inherit them.
    exposed = _expose_user_site_on_pythonpath()
    if exposed:
        notes.append(f"user site on PYTHONPATH ({exposed})")

    return True, "; ".join(notes)


def ensure_deps_before_diamond_fetch(*, allow_install: bool = True) -> tuple[bool, str]:
    """Bootstrap runtime deps *before* ``--fetch-diamond`` materialize (Tick 282).

    ``materialize_from_hf`` imports ``huggingface_hub`` immediately. Gate runners
    used to call ``ensure_icml_runtime_deps`` only later inside ``run_preflight``,
    so a cold boot without that package raised ``ImportError`` / ``RuntimeError``
    and aborted live diamond fetch even though bootstrap would have installed it.

    Returns ``(ok, detail)`` from ``ensure_icml_runtime_deps``. Callers should
    still treat a failed bootstrap as a hard stop for the HF materialize path.
    """
    return ensure_icml_runtime_deps(allow_install=allow_install)


def sum_run_dirs_cost_usd(run_dirs: list[Path]) -> float | None:
    """Sum ``total_cost_usd`` across ``gen_*/agent_*/results.json`` (Tick 283).

    Returns ``None`` when no positive USD fields are found (dry-run / missing
    artifacts). Target-eval costs only — meta/feedback Claude spend is usually
    not in these files; callers should apply a small overhead factor.
    """
    total = 0.0
    found = False
    for run_dir in run_dirs:
        if run_dir is None:
            continue
        root = Path(run_dir)
        if not root.is_dir():
            continue
        for results_path in root.glob("gen_*/agent_*/results.json"):
            try:
                data = json.loads(results_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError):
                continue
            if not isinstance(data, dict):
                continue
            usd = data.get("total_cost_usd")
            if isinstance(usd, (int, float)) and float(usd) > 0.0:
                total += float(usd)
                found = True
            else:
                # Fall back to per-question cost_usd if aggregate missing.
                for detail in data.get("details") or []:
                    if not isinstance(detail, dict):
                        continue
                    c = detail.get("cost_usd")
                    if isinstance(c, (int, float)) and float(c) > 0.0:
                        total += float(c)
                        found = True
    return total if found else None


def reconcile_gate_spend_usd(
    run_dirs: list[Path],
    *,
    fallback_estimate: float,
    meta_overhead: float = 1.25,
) -> tuple[float, str]:
    """Pick gate spend for ``SIA_BUDGET_SPENT_USD`` (Tick 283).

    Prefer actual target-eval USD × ``meta_overhead`` (covers unmetered
    Anthropic meta/feedback). Fall back to the gate estimate when artifacts
    lack USD. Returns ``(amount, detail)``.
    """
    estimate = max(0.0, float(fallback_estimate))
    actual = sum_run_dirs_cost_usd(run_dirs)
    if actual is None:
        return estimate, f"estimate=${estimate:.4f} (no total_cost_usd in run artifacts)"
    overhead = max(1.0, float(meta_overhead))
    amount = actual * overhead
    return (
        amount,
        f"actual_target=${actual:.4f} × overhead={overhead:.2f} → ${amount:.4f} "
        f"(estimate was ${estimate:.4f})",
    )


def darwinian_run_complete(run_dir: Path | None) -> bool:
    """True when a Darwinian run dir has at least one agent ``results.json`` with accuracy.

    Used by Tick 284 resume: completed run IDs must not block the next gate
    via ``run_id_free``, and must not be re-executed (never overwrite).
    """
    if run_dir is None:
        return False
    root = Path(run_dir)
    if not root.is_dir():
        return False
    for results_path in root.glob("gen_*/agent_*/results.json"):
        try:
            data = json.loads(results_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and "accuracy" in data:
            return True
    return False


def budget_spent_ledger_path(repo_root: Path | None = None) -> Path:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    return root / "docs" / "icml_budget_spent.json"


def load_budget_spent_ledger(path: Path | None = None) -> dict[str, Any]:
    """Load persisted spend ledger (presence-only amounts; never secrets)."""
    p = path or budget_spent_ledger_path()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_budget_spent_ledger(
    *,
    spent_usd: float,
    stages_complete: list[str] | None = None,
    detail: str = "",
    run_ids: list[int] | None = None,
    path: Path | None = None,
) -> Path:
    """Persist reconciled spend so the next cron tick can resume (Tick 284)."""
    p = path or budget_spent_ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    prev = load_budget_spent_ledger(p)
    prev_stages = list(prev.get("stages_complete") or [])
    merged_stages: list[str] = []
    for name in list(prev_stages) + list(stages_complete or []):
        if name and name not in merged_stages:
            merged_stages.append(name)
    prev_ids = [int(x) for x in (prev.get("run_ids") or []) if str(x).lstrip("-").isdigit()]
    merged_ids: list[int] = []
    for rid in prev_ids + list(run_ids or []):
        if rid not in merged_ids:
            merged_ids.append(rid)
    payload = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tick_note": (
            "Tick 284/285: persisted SIA_BUDGET_SPENT_USD across cron ticks; "
            "commit this file so cross-VM resume can skip completed G2/G3/G4 "
            "(runs/ are gitignored and do not survive fresh boots)"
        ),
        "spent_usd": round(float(spent_usd), 4),
        "stages_complete": merged_stages,
        "run_ids": merged_ids,
        "detail": detail or prev.get("detail") or "",
    }
    p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return p


def apply_persisted_spent_to_env(
    *,
    path: Path | None = None,
    env_key: str = "SIA_BUDGET_SPENT_USD",
) -> tuple[float, str]:
    """Load ledger into env when ledger spent exceeds current env (Tick 284).

    Returns ``(effective_spent, detail)``. Never lowers an explicitly higher
    env value (manual override / in-process bumps win).
    """
    import os

    raw = (os.environ.get(env_key) or "0").strip()
    try:
        env_spent = float(raw)
    except ValueError:
        env_spent = 0.0
    ledger = load_budget_spent_ledger(path)
    ledger_spent = ledger.get("spent_usd")
    if not isinstance(ledger_spent, (int, float)):
        return env_spent, f"env=${env_spent:.4f} (no ledger)"
    ledger_f = float(ledger_spent)
    if ledger_f > env_spent + 1e-9:
        os.environ[env_key] = f"{ledger_f:.4f}"
        stages = ",".join(ledger.get("stages_complete") or []) or "—"
        return (
            ledger_f,
            f"ledger=${ledger_f:.4f} > env=${env_spent:.4f}; "
            f"loaded stages=[{stages}]",
        )
    return env_spent, f"env=${env_spent:.4f} ≥ ledger=${ledger_f:.4f}"


def ledger_stage_complete(
    stage: str,
    required_run_ids: list[int],
    *,
    path: Path | None = None,
) -> bool:
    """Tick 285: True when committed ledger marks ``stage`` done for these IDs.

    Cross-VM cron boots lose gitignored ``runs/``. After a live tick commits
    ``docs/icml_budget_spent.json``, the next tip can still skip that gate
    without local artifacts — but only when every required run_id is listed
    in the ledger (avoids skipping after CLI run-id changes).
    """
    if not stage or not required_run_ids:
        return False
    ledger = load_budget_spent_ledger(path)
    stages = {str(s) for s in (ledger.get("stages_complete") or []) if s}
    if stage not in stages:
        return False
    ledger_ids = {
        int(x)
        for x in (ledger.get("run_ids") or [])
        if str(x).lstrip("-").isdigit()
    }
    return all(int(rid) in ledger_ids for rid in required_run_ids)

_AUTOMATION_ID = "bf73dff3-8f7a-11f1-a7d1-d6b4613131ce"
_AUTOMATION_URL = f"https://cursor.com/automations/{_AUTOMATION_ID}"
_ENV_DASHBOARD_URL = (
    "https://cursor.com/dashboard/cloud-agents/environments/"
    "e/31d13f14-9d04-11f1-a7d1-d6b4613131ce"
)


def load_icml_dotenv(env_path: Path | None = None) -> list[str]:
    """Load gitignored ``.env`` into ``os.environ`` for *missing* keys only.

    Tick 277: cloud secrets inject as env vars; humans sometimes drop keys into
    ``.env`` (already gitignored). Mirror ``scripts/verify_keys.py`` so cron /
    preflight see the same keys. Returns names that were newly set — **never**
    returns or logs values.
    """
    path = env_path or (_REPO_ROOT / ".env")
    loaded: list[str] = []
    if not path.is_file():
        return loaded
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return loaded
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key not in _SECRET_ENV_NAMES:
            # Only pull ICML-relevant secrets; ignore unrelated .env noise.
            continue
        if key in os.environ and str(os.environ.get(key, "")).strip():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if not value.strip():
            continue
        os.environ[key] = value
        loaded.append(key)
    return loaded


def resolve_diamond_csv_path(repo_root: Path | None = None) -> Path | None:
    """Return a usable local ``gpqa_diamond.csv`` if the operator dropped one.

    Tick 277: ``HF_TOKEN`` is not required when a real CSV is present — cron
    passes ``--diamond-csv`` into the live pipeline. Order:

    1. ``ICML_DIAMOND_CSV`` / ``SIA_DIAMOND_CSV`` env path
    2. ``/tmp/gpqa_diamond.csv``
    3. repo-relative candidates under ``docs/private/``, ``.local/``, root
    """
    root = repo_root or _REPO_ROOT
    env_override = (
        os.environ.get("ICML_DIAMOND_CSV") or os.environ.get("SIA_DIAMOND_CSV") or ""
    ).strip()
    candidates: list[Path] = []
    if env_override:
        candidates.append(Path(env_override).expanduser())
    candidates.append(Path("/tmp/gpqa_diamond.csv"))
    for rel in _DIAMOND_CSV_CANDIDATES:
        candidates.append(root / rel)
    for path in candidates:
        try:
            if path.is_file() and path.stat().st_size >= 64:
                return path.resolve()
        except OSError:
            continue
    return None


def autowire_diamond_csv(
    explicit: Path | None = None,
    *,
    fetch_diamond: bool = False,
    repo_root: Path | None = None,
) -> tuple[Path | None, bool]:
    """Resolve ``--diamond-csv`` for ``--fetch-diamond`` (Tick 278).

    Returns ``(path, auto_wired)``. When ``fetch_diamond`` is true and no
    explicit CSV was passed, falls back to ``resolve_diamond_csv_path`` so
    G2/G3/G4/pipeline skip HF the same way cron does (Tick 277). Does **not**
    invent a CSV when ``fetch_diamond`` is false (avoids surprise materialize).
    """
    if explicit is not None:
        return Path(explicit), False
    if not fetch_diamond:
        return None, False
    auto = resolve_diamond_csv_path(repo_root)
    if auto is None:
        return None, False
    return auto, True


def _secret_present(name: str) -> bool:
    """True when env var looks set (never returns or logs the value)."""
    raw = os.environ.get(name, "")
    if not isinstance(raw, str):
        return False
    value = raw.strip()
    if not value:
        return False
    lowered = value.lower()
    if lowered.startswith("your_") or lowered in {"...", "changeme", "todo"}:
        return False
    return True


def collect_icml_secrets_status() -> dict:
    """Presence-only secrets / diamond gate for live G2→G3→G4 (Tick 268/277).

    Does **not** include secret values. Portal Save is optional once Tick
    265–266 bootstraps succeed; live blockers are API keys + real GPQA
    (HF token **or** a local diamond CSV).
    """
    load_icml_dotenv()
    anthropic = _secret_present("ANTHROPIC_API_KEY")
    nebius = _secret_present("NEBIUS_API_KEY")
    hf = _secret_present("HF_TOKEN") or _secret_present("HUGGINGFACE_HUB_TOKEN")
    diamond_csv = resolve_diamond_csv_path()
    diamond_csv_ok = diamond_csv is not None
    secrets_ok = anthropic and nebius
    # HF needed for --fetch-diamond unless operator supplies CSV offline.
    fetch_diamond_ok = secrets_ok and (hf or diamond_csv_ok)
    # Tick 273/277: cron passes --fetch-diamond (optionally with --diamond-csv).
    cron_live_ok = fetch_diamond_ok
    blockers: list[str] = []
    if not anthropic:
        blockers.append("ANTHROPIC_API_KEY missing")
    if not nebius:
        blockers.append("NEBIUS_API_KEY missing")
    if not hf and not diamond_csv_ok:
        blockers.append(
            "HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing "
            "(required for --fetch-diamond; or provide --diamond-csv / "
            "drop gpqa_diamond.csv at /tmp or docs/private/)"
        )
    return {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tick_note": (
            "Tick 268/273/277: secrets-first live gate; Portal Save optional; "
            "cron auto-live requires fetch_diamond_ok (API keys + HF **or** "
            "local diamond CSV); .env loaded for missing secret names; "
            "human_next prefers bash scripts/icml_cron_entry.sh"
        ),
        "automation_id": _AUTOMATION_ID,
        "automation_url": _AUTOMATION_URL,
        "environment_dashboard_url": _ENV_DASHBOARD_URL,
        "secrets": {
            "ANTHROPIC_API_KEY": "PRESENT" if anthropic else "ABSENT",
            "NEBIUS_API_KEY": "PRESENT" if nebius else "ABSENT",
            "HF_TOKEN_OR_HUGGINGFACE_HUB_TOKEN": "PRESENT" if hf else "ABSENT",
        },
        # Top-level booleans for cron_entry / shell greps (Tick 272–277).
        "anthropic_key_present": anthropic,
        "nebius_key_present": nebius,
        "hf_token_present": hf,
        "diamond_csv_present": diamond_csv_ok,
        "diamond_csv_path": str(diamond_csv) if diamond_csv is not None else None,
        "packages_bootstrapped_in_preflight": True,
        "portal_save_required_for_live": False,
        "secrets_ok_for_paid_sia": secrets_ok,
        "fetch_diamond_ok": fetch_diamond_ok,
        "cron_live_ok": cron_live_ok,
        "ready_for_live_pipeline": False,  # diamond + keys both required; caller may override
        "blockers": blockers,
        "human_next": [
            f"Add ANTHROPIC_API_KEY + NEBIUS_API_KEY + HF_TOKEN to automation "
            f"{_AUTOMATION_URL} (or linked env {_ENV_DASHBOARD_URL})",
            "Accept HuggingFace access for Idavidrein/gpqa with that HF token "
            "(or drop a real gpqa_diamond.csv at /tmp/gpqa_diamond.csv / "
            "docs/private/gpqa_diamond.csv / $ICML_DIAMOND_CSV to skip HF)",
            "Next cron (or now): `bash scripts/icml_cron_entry.sh` "
            "(Tick 271–277 — recovers tip; auto-live only when fetch_diamond_ok)",
            "Portal Save of docs/icml_portal_save_target.json is optional "
            "(warm boots only; packages bootstrap without it)",
        ],
    }


def write_icml_secrets_status(
    path: Path | None = None,
    *,
    gpqa_is_synthetic: bool | None = None,
) -> dict:
    """Write ``docs/icml_secrets_status.json`` (presence-only; no secret values)."""
    status = collect_icml_secrets_status()
    if gpqa_is_synthetic is True:
        status["blockers"] = list(status["blockers"]) + [
            "gpqa still synthetic — need --fetch-diamond or real diamond CSV"
        ]
        status["gpqa_is_synthetic"] = True
    elif gpqa_is_synthetic is False:
        status["gpqa_is_synthetic"] = False
    else:
        status["gpqa_is_synthetic"] = None
    # Tick 274: cron / pipeline --live --fetch-diamond needs HF too.
    # Synthetic fixture is OK as a starting point when fetch_diamond_ok (HF will replace it).
    status["ready_for_live_pipeline"] = bool(status.get("fetch_diamond_ok"))
    out = path or (_REPO_ROOT / "docs" / "icml_secrets_status.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    return status


def live_pipeline_next_steps(
    *,
    secrets_ok: bool,
    tip_ok: bool | None = None,
    tip_ref: str | None = None,
    fetch_diamond_ok: bool | None = None,
) -> list[str]:
    """Human-facing Next bullets — tip + secrets + HF + cron entry (Tick 268–274).

    Tick 274: do **not** claim live-ready on Anthropic+Nebius alone — cron and
    ``--live --fetch-diamond`` also need ``HF_TOKEN`` (``fetch_diamond_ok``).
    """
    steps: list[str] = []
    if tip_ok is False:
        ref = tip_ref or "origin/cursor/icml-epistemic-results-<tip>"
        steps.append(
            "Stale / missing ICML tip — prefer single entry: "
            "`bash scripts/icml_cron_entry.sh` (Tick 271; recovers tip then "
            "live/preflight). Or: `python3 scripts/icml_recover_tip.py --apply` "
            f"(expected tip ≈ `{ref}`). Main boot without tip scripts: "
            f"`git show {ref}:scripts/icml_cron_entry.sh | bash -s --`. "
            "See `docs/icml_tip_status.json`."
        )

    # Explicit False → HF/CSV gap even when API keys present.
    if fetch_diamond_ok is False and secrets_ok:
        steps.extend(
            [
                "API keys present but diamond still blocked "
                "(`fetch_diamond_ok=false`): add `HF_TOKEN` + accept HF "
                "`Idavidrein/gpqa`, **or** drop a real `gpqa_diamond.csv` at "
                "`/tmp/gpqa_diamond.csv` / `docs/private/gpqa_diamond.csv` / "
                f"`$ICML_DIAMOND_CSV`. Add HF to {_AUTOMATION_URL}. "
                "See `docs/ICML_HUMAN_UNBLOCK.md`.",
                "Next cron (or now): `bash scripts/icml_cron_entry.sh` — stays "
                "preflight-only until `fetch_diamond_ok`.",
                "Do **not** set STATUS: READY from offline / preflight alone.",
            ]
        )
        return steps

    # True → full cron live OK. None + secrets_ok → legacy callers (pre-Tick-274).
    if fetch_diamond_ok is True or (fetch_diamond_ok is None and secrets_ok):
        label = (
            "Cron live OK (`fetch_diamond_ok`)"
            if fetch_diamond_ok is True
            else "Secrets present"
        )
        steps.extend(
            [
                f"{label} — preferred single entry:",
                "`bash scripts/icml_cron_entry.sh` "
                "(or `python3 scripts/run_icml_live_pipeline.py --live --fetch-diamond`)",
                "Portal Save (`docs/icml_portal_save_target.json`) remains optional "
                "for warmer boots only.",
                "Do **not** set STATUS: READY from offline / preflight alone.",
            ]
        )
        return steps

    steps.extend(
        [
            "Add `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` + (`HF_TOKEN` **or** "
            "local `gpqa_diamond.csv`) to automation "
            f"{_AUTOMATION_URL} (or linked env dashboard). "
            "Accept HF `Idavidrein/gpqa` if using HF. See `docs/ICML_HUMAN_UNBLOCK.md`.",
            "Next cron (or now): `bash scripts/icml_cron_entry.sh` — auto-recovers "
            "tip and runs live when `fetch_diamond_ok` (else preflight only).",
            "Portal Save of `docs/icml_portal_save_target.json` is **optional** "
            "(Tick 265–267: uv + runtime deps bootstrap in preflight).",
            "Do **not** set STATUS: READY from offline / preflight alone.",
        ]
    )
    return steps


# --- Tick 269: ICML tip lineage (cron boots often start from main) -----------------

_TICK_HEADING_RE = re.compile(
    r"^##\s+.+\bTick\s+(\d+)\b",
    re.MULTILINE | re.IGNORECASE,
)
_TIP_REF_PREFIXES = (
    "refs/remotes/origin/cursor/icml-epistemic-results-",
    "refs/remotes/origin/cursor/icml-epistemic-evolution-",
)
# Prefer lineage that includes Tick 265–268 bootstraps; skip Portal-Save-only forks.
_TIP_LINEAGE_MARKERS = (
    "secrets-first",
    "write_icml_secrets_status",
    "ensure_icml_runtime_deps",
    "ensure_deps_before_diamond_fetch",
    "ensure_uv_on_path",
    "Astral uv",
)


def parse_latest_icml_tick(progress_text: str) -> int | None:
    """Return the newest Tick N from ``ICML_PROGRESS.md`` (newest entries at top)."""
    if not progress_text:
        return None
    match = _TICK_HEADING_RE.search(progress_text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _git_ok(args: list[str], *, cwd: Path | None = None) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd or _REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        return False, err[:400] or f"git exit {proc.returncode}"
    return True, (proc.stdout or "").strip()


def _tip_lineage_score(progress_text: str) -> int:
    """Higher = more likely the canonical secrets/bootstrap tip (not Portal-Save-only)."""
    score = 0
    lower = progress_text.lower()
    for marker in _TIP_LINEAGE_MARKERS:
        if marker.lower() in lower:
            score += 1
    # Penalize known divergent Portal-Save-only numbering collisions.
    if "portal save re-link" in lower and "secrets-first" not in lower:
        score -= 2
    return score


def list_remote_icml_tip_candidates(
    *,
    repo_root: Path | None = None,
    fetch: bool = False,
) -> list[dict]:
    """Scan remote ICML branches for ``docs/ICML_PROGRESS.md`` Tick heads."""
    root = repo_root or _REPO_ROOT
    notes: list[str] = []
    if fetch:
        ok, detail = _git_ok(
            [
                "fetch",
                "origin",
                "+refs/heads/cursor/icml-epistemic-results-*"
                ":refs/remotes/origin/cursor/icml-epistemic-results-*",
                "+refs/heads/cursor/icml-epistemic-evolution-*"
                ":refs/remotes/origin/cursor/icml-epistemic-evolution-*",
            ],
            cwd=root,
        )
        notes.append(f"fetch={'ok' if ok else 'fail'}: {detail[:200]}")

    ok, refs_out = _git_ok(
        [
            "for-each-ref",
            "--format=%(refname)\t%(committerdate:unix)\t%(objectname:short)",
            "refs/remotes/origin/cursor/icml-epistemic-results-*",
            "refs/remotes/origin/cursor/icml-epistemic-evolution-*",
        ],
        cwd=root,
    )
    if not ok:
        return []

    candidates: list[dict] = []
    for line in refs_out.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        ref, ts_s, sha = parts[0], parts[1], parts[2]
        if not any(ref.startswith(p) for p in _TIP_REF_PREFIXES):
            continue
        ok_show, progress = _git_ok(
            ["show", f"{ref}:docs/ICML_PROGRESS.md"],
            cwd=root,
        )
        if not ok_show:
            continue
        tick = parse_latest_icml_tick(progress)
        if tick is None:
            continue
        try:
            ts = int(ts_s)
        except ValueError:
            ts = 0
        candidates.append(
            {
                "ref": ref,
                "short_ref": ref.split("/", 3)[-1]
                if ref.startswith("refs/remotes/")
                else ref,
                "sha": sha,
                "tick": tick,
                "committer_unix": ts,
                "lineage_score": _tip_lineage_score(progress),
            }
        )
    candidates.sort(
        key=lambda c: (c["tick"], c["lineage_score"], c["committer_unix"]),
        reverse=True,
    )
    if notes and candidates:
        candidates[0] = {**candidates[0], "fetch_notes": notes}
    return candidates


def collect_icml_tip_status(
    *,
    repo_root: Path | None = None,
    fetch: bool = False,
) -> dict:
    """Compare local ``ICML_PROGRESS`` Tick vs highest remote ICML tip (Tick 269)."""
    root = repo_root or _REPO_ROOT
    progress_path = root / "docs" / "ICML_PROGRESS.md"
    local_tick: int | None = None
    local_text = ""
    if progress_path.is_file():
        local_text = progress_path.read_text(encoding="utf-8", errors="replace")
        local_tick = parse_latest_icml_tick(local_text)

    candidates = list_remote_icml_tip_candidates(repo_root=root, fetch=fetch)
    tip = candidates[0] if candidates else None
    remote_tick = int(tip["tick"]) if tip else None
    tip_ref = tip["ref"] if tip else None

    blockers: list[str] = []
    if local_tick is None:
        blockers.append(
            "docs/ICML_PROGRESS.md missing or has no Tick heading — "
            "cron likely booted from main; recover tip before --live"
        )
    elif remote_tick is not None and local_tick < remote_tick:
        blockers.append(
            f"local Tick {local_tick} behind remote tip Tick {remote_tick} "
            f"({tip_ref}) — recover before --live"
        )

    tip_ok = len(blockers) == 0 and local_tick is not None
    # If remotes unavailable, still OK when local progress exists (offline agent).
    if not candidates and local_tick is not None:
        tip_ok = True

    return {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tick_note": (
            "Tick 269–270: tip lineage guard — cron often boots from main; "
            "refuse --live on stale trees; recover via "
            "scripts/icml_recover_tip.py or scripts/icml_boot_recover.sh"
        ),
        "local_tick": local_tick,
        "remote_tip_tick": remote_tick,
        "remote_tip_ref": tip_ref,
        "remote_tip_sha": tip["sha"] if tip else None,
        "remote_tip_lineage_score": tip["lineage_score"] if tip else None,
        "tip_ok_for_live": tip_ok,
        "blockers": blockers,
        "recover_command": (
            "python3 scripts/icml_recover_tip.py --apply "
            "(main boot / no tip scripts: "
            "git show <tip>:scripts/icml_boot_recover.sh | bash -s -- --apply)"
        ),
        "candidates_scanned": len(candidates),
        "top_candidates": [
            {
                "ref": c["ref"],
                "tick": c["tick"],
                "sha": c["sha"],
                "lineage_score": c["lineage_score"],
            }
            for c in candidates[:5]
        ],
    }


def write_icml_tip_status(
    path: Path | None = None,
    *,
    fetch: bool = False,
    repo_root: Path | None = None,
) -> dict:
    """Write ``docs/icml_tip_status.json`` (no secrets)."""
    root = repo_root or _REPO_ROOT
    status = collect_icml_tip_status(repo_root=root, fetch=fetch)
    out = path or (root / "docs" / "icml_tip_status.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    return status
