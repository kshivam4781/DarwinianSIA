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

Tick 291: GPQA reference / evolved agents historically wrote
``total_cost_usd=0`` (unknown pricing) while recording tokens. After Tick
289 Nebius Kimi meta, blind estimate fallback under-counts live spend.
``estimate_usd_from_tokens`` recovers USD from tokens × Nebius Kimi rates;
``resolve_icml_meta_overhead`` raises default overhead for Nebius meta.

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

Tick 286: Preflight rewrites gate/pipeline/secrets/tip JSON+MD and left the
working tree dirty. When a newer tip appeared, ``icml_boot_recover.sh
--apply`` / cron entry refused recover ("Working tree dirty") and the
agent stayed on a stale Tick. ``discard_ephemeral_icml_dirt`` restores only
those ephemeral report/status paths so tip ``--apply`` can proceed; real
code edits still block apply. Also ``ensure_budget_spent_ledger_initialized``
commits a zero ledger schema when the file is absent.

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
from typing import Any, Sequence

UV_INSTALL_URL = "https://astral.sh/uv/install.sh"
_LOCAL_BIN = Path.home() / ".local" / "bin"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SIA_PKG_ROOT = _REPO_ROOT / "SIA"
_RUNTIME_PIP_PACKAGES = ("huggingface_hub", "pydantic_ai")
# Pip distribution names when they differ from the import name (Tick 289).
_RUNTIME_PIP_DIST_NAMES = {
    "pydantic_ai": "pydantic-ai",
}
_SECRET_ENV_NAMES = (
    "ANTHROPIC_API_KEY",
    "NEBIUS_API_KEY",
    "HF_TOKEN",
    "HUGGINGFACE_HUB_TOKEN",
)
# Tick 288: G2/G3/G4 must not silently use default-target (Anthropic Haiku) or
# Tinker-seeded GPQA reference — Section 6.8 + evolution_prompts require Nebius.
# Override with ICML_TARGET_AGENT_PROFILE or SIA_TARGET_AGENT_PROFILE.
DEFAULT_ICML_TARGET_AGENT_PROFILE = "kimi-nebius-target"
# Tick 291: Nebius Token Factory catalog ($/1M) for moonshotai/Kimi-K2.6.
NEBIUS_KIMI_USD_PER_MILLION = {"input": 0.95, "output": 4.0}
DEFAULT_META_OVERHEAD_ANTHROPIC = 1.25
# Nebius pydantic-ai meta/feedback uses the same expensive Kimi model for
# multi-turn codegen — 1.25× target-eval USD under-counts badly.
DEFAULT_META_OVERHEAD_NEBIUS = 3.0
# Tick 289: Meta/feedback also on Nebius (pydantic-ai) so live G2–G4 need only
# NEBIUS_API_KEY (+ HF/CSV) — Anthropic optional. Override with
# ICML_META_AGENT_PROFILE or SIA_META_AGENT_PROFILE (e.g. default-meta).
DEFAULT_ICML_META_AGENT_PROFILE = "kimi-nebius-pydantic-meta"
# Tick 293: Anthropic-era G3/G4 shape (pop4 × eval15 × max_gen5) × Nebius meta
# overhead 3.0 cannot fit full 5-seed G4 under the ~$20 ceiling once Tick 291
# reconcile meters real Kimi spend. Nebius budget-fit shape keeps PRIMARY
# (5 seeds) while shrinking per-seed cost.
# Tick 294: elite_count must be ≥2 — cost is pop×eval×gens (elite does not
# change agent-eval count); elite=1 makes crossover same-parent clones and
# collapses H2 / Condition D steering under delay-all bias (gen≥2).
# Tick 295: cost-neutral rebalance eval10/max_gen4 → eval8/max_gen5
# (3×8×5 = 3×10×4 = 120 agent-evals). Under delay-all, offline seed 22 hits
# gens30 at gen **5**; max_gen=4 would truncate PRIMARY gens30/cost30 and
# leave only two steered breeding rounds (gen2→3, gen3→4).
# Tick 296: offline re-pilot at Tick 295 shape (pop3/elite2/max_gen5) **fails**
# PRIMARY (gens30/cost30 1/5) and H5 (3/5) — pop=3 leaves only 1 non-elite
# offspring/gen and collapses diversity vs Tick 23 pop=4. Cost-neutral restore
# Tick 23 Darwinian shape: pop4 × eval5 × max_gen6 = **120** agent-evals
# (PRIMARY gens30/cost30 4/5, final 5/5, H5 5/5, mean gap ~6.15pp offline).
# Override with SIA_G3G4_* env vars. Anthropic meta keeps the historical shape.
ICML_NEBIUS_G3G4_EVAL_SUBSET = 5
ICML_NEBIUS_G3G4_POPULATION_SIZE = 4
ICML_NEBIUS_G3G4_ELITE_COUNT = 2
ICML_NEBIUS_G3G4_MAX_GEN = 6
ICML_ANTHROPIC_G3G4_EVAL_SUBSET = 15
ICML_ANTHROPIC_G3G4_POPULATION_SIZE = 4
ICML_ANTHROPIC_G3G4_ELITE_COUNT = 2
ICML_ANTHROPIC_G3G4_MAX_GEN = 5
# Gate USD estimates (include meta/feedback). Nebius defaults assume budget-fit
# shape above; Anthropic defaults keep historical $1+$4+$15=$20 stack.
DEFAULT_G2_ESTIMATE_USD_NEBIUS = 2.0
DEFAULT_G3_PAIR_ESTIMATE_USD_NEBIUS = 3.0
DEFAULT_G4_PAIR_ESTIMATE_USD_NEBIUS = 2.8
DEFAULT_G2_ESTIMATE_USD_ANTHROPIC = 1.0
DEFAULT_G3_PAIR_ESTIMATE_USD_ANTHROPIC = 4.0
DEFAULT_G4_PAIR_ESTIMATE_USD_ANTHROPIC = 3.0
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


def resolve_icml_target_agent_profile() -> str:
    """Nebius target profile for ICML G2/G3/G4 ``sia run`` commands (Tick 288).

    Prefer ``ICML_TARGET_AGENT_PROFILE``, then ``SIA_TARGET_AGENT_PROFILE``, else
    ``kimi-nebius-target`` (matches ``evolution_prompts`` Kimi-K2.6 + NEBIUS).
    """
    for key in ("ICML_TARGET_AGENT_PROFILE", "SIA_TARGET_AGENT_PROFILE"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw
    return DEFAULT_ICML_TARGET_AGENT_PROFILE


def icml_target_profile_cli_flags(
    profile: str | None = None,
) -> list[str]:
    """Return ``[--target-agent-profile, <profile>]`` for gate runners."""
    name = (profile or resolve_icml_target_agent_profile()).strip()
    if not name:
        name = DEFAULT_ICML_TARGET_AGENT_PROFILE
    return ["--target-agent-profile", name]


def _load_agent_profile_json(name_or_path: str) -> tuple[Path | None, dict | None, str]:
    """Load a bundled/path profile JSON. Returns (path, data, error)."""
    name = (name_or_path or "").strip()
    if not name:
        return None, None, "empty profile name"
    path = Path(name)
    if not path.is_file():
        path = _SIA_PKG_ROOT / "sia" / "defaults" / "profiles" / f"{name}.json"
    if not path.is_file():
        return None, None, f"profile not found: {name}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return path, None, f"profile unreadable ({name}): {exc}"
    if not isinstance(data, dict):
        return path, None, f"profile {name!r} is not a JSON object"
    return path, data, ""


def probe_icml_target_profile_nebius(
    profile: str | None = None,
) -> tuple[bool, str]:
    """True when the resolved target profile uses the Nebius provider.

    Latent live abort (Tick 288): runners checked ``NEBIUS_API_KEY`` but omitted
    ``--target-agent-profile``, so paid runs used ``default-target`` (Anthropic)
    while the GPQA seed still called Tinker. Refuse non-Nebius profiles in
    preflight so the first live G2 cannot burn budget on the wrong API.
    """
    name = (profile or resolve_icml_target_agent_profile()).strip()
    if not name:
        return False, "empty ICML target agent profile"
    _path, data, err = _load_agent_profile_json(name)
    if data is None:
        return False, err or f"target profile not found: {name}"
    provider = str(data.get("provider_id") or "").strip().lower()
    if provider != "nebius":
        return (
            False,
            f"profile {name!r} provider_id={provider!r} (want nebius; "
            "set ICML_TARGET_AGENT_PROFILE=kimi-nebius-target)",
        )
    model = str(data.get("model") or "").strip()
    return True, f"{name} → nebius ({model or 'model?'})"


def resolve_icml_meta_agent_profile() -> str:
    """Meta/feedback profile for ICML G2/G3/G4 ``sia run`` (Tick 289).

    Prefer ``ICML_META_AGENT_PROFILE``, then ``SIA_META_AGENT_PROFILE``, else
    ``kimi-nebius-pydantic-meta`` (Nebius-only; Anthropic optional).
    """
    for key in ("ICML_META_AGENT_PROFILE", "SIA_META_AGENT_PROFILE"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw
    return DEFAULT_ICML_META_AGENT_PROFILE


def icml_meta_profile_cli_flags(profile: str | None = None) -> list[str]:
    """Return ``[--meta-agent-profile, <profile>]`` for gate runners."""
    name = (profile or resolve_icml_meta_agent_profile()).strip()
    if not name:
        name = DEFAULT_ICML_META_AGENT_PROFILE
    return ["--meta-agent-profile", name]


def icml_meta_provider_id(profile: str | None = None) -> str:
    """Return ``provider_id`` for the resolved ICML meta profile (lowercased)."""
    name = (profile or resolve_icml_meta_agent_profile()).strip()
    _path, data, _err = _load_agent_profile_json(name)
    if not data:
        return ""
    return str(data.get("provider_id") or "").strip().lower()


def icml_meta_requires_anthropic(profile: str | None = None) -> bool:
    """True when live G2–G4 still need ``ANTHROPIC_API_KEY`` for the meta agent."""
    return icml_meta_provider_id(profile) == "anthropic"


def icml_human_required_secrets_phrase(
    *,
    for_fetch_diamond: bool = True,
    profile: str | None = None,
) -> str:
    """Human-facing secrets line for cron / gate Next / refuse messages (Tick 292).

    Gate logic already treats Anthropic as optional under Nebius pydantic-ai meta
    (Tick 289), but several surfaces still said ``ANTHROPIC + NEBIUS`` — that
    misled operators into waiting on a third vendor key. Keep wording in sync
    with ``collect_icml_secrets_status`` / ``docs/ICML_HUMAN_UNBLOCK.md``.
    """
    if icml_meta_requires_anthropic(profile):
        api = "ANTHROPIC_API_KEY + NEBIUS_API_KEY"
    else:
        api = (
            "NEBIUS_API_KEY "
            "(ANTHROPIC_API_KEY optional — Tick 289 Nebius pydantic-ai meta)"
        )
    if for_fetch_diamond:
        return f"{api} + (HF_TOKEN or local gpqa_diamond.csv)"
    return api


def probe_icml_meta_profile(profile: str | None = None) -> tuple[bool, str]:
    """True when the resolved meta profile is loadable and coherent for ICML.

    Default Nebius + pydantic-ai avoids OpenHands (heavy / Windows-broken) while
    keeping paid meta/feedback on ``NEBIUS_API_KEY`` only.
    """
    name = (profile or resolve_icml_meta_agent_profile()).strip()
    if not name:
        return False, "empty ICML meta agent profile"
    _path, data, err = _load_agent_profile_json(name)
    if data is None:
        return False, err or f"meta profile not found: {name}"
    provider = str(data.get("provider_id") or "").strip().lower()
    agent_impl = str(data.get("agent_impl") or "").strip().lower()
    model = str(data.get("model") or "").strip()
    if not provider:
        return False, f"meta profile {name!r} missing provider_id"
    if not agent_impl:
        return False, f"meta profile {name!r} missing agent_impl"
    if provider == "nebius" and agent_impl == "claude":
        return (
            False,
            f"meta profile {name!r} pairs claude agent_impl with nebius "
            "(use pydantic-ai or openhands)",
        )
    if provider == "anthropic" and agent_impl not in {"claude", "pydantic-ai"}:
        return (
            False,
            f"meta profile {name!r} anthropic provider with unexpected "
            f"agent_impl={agent_impl!r}",
        )
    return True, f"{name} → {provider} / {agent_impl} ({model or 'model?'})"


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


def icml_python_cli() -> str:
    """Basename of the live interpreter for operator copy-paste (Tick 323).

    Cold Linux/cloud images often have ``python3`` only (no bare ``python``
    shim). Gate Next / refuse / verify_keys strings must not say
    ``python scripts/...`` — use this (or hardcode ``python3`` on Linux docs).
    Matches finish/present ``Path(sys.executable).name`` (Tick 322).
    """
    return Path(sys.executable).name


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
        pip_names = [_RUNTIME_PIP_DIST_NAMES.get(p, p) for p in missing]
        ok_pip, pip_detail = _pip_install_user(*pip_names)
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
        notes.append("huggingface_hub + pydantic_ai already importable")

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


def estimate_usd_from_tokens(data: dict) -> float | None:
    """Estimate USD from token fields using Nebius Kimi-K2.6 rates (Tick 291).

    Used when ``total_cost_usd`` is missing/zero but live agents still recorded
    tokens (historical ``MODEL_PRICING={0,0}`` / prompt said \"set cost to 0\").
    """
    if not isinstance(data, dict):
        return None
    inp = data.get("total_input_tokens")
    out = data.get("total_output_tokens")
    reason = data.get("total_reasoning_tokens")
    input_tokens = float(inp) if isinstance(inp, (int, float)) else 0.0
    output_tokens = float(out) if isinstance(out, (int, float)) else 0.0
    reasoning_tokens = float(reason) if isinstance(reason, (int, float)) else 0.0
    if input_tokens <= 0.0 and output_tokens <= 0.0 and reasoning_tokens <= 0.0:
        # Fall back to per-question detail rows.
        for detail in data.get("details") or []:
            if not isinstance(detail, dict):
                continue
            for key, bucket in (
                ("input_tokens", "input"),
                ("output_tokens", "output"),
                ("reasoning_tokens", "output"),
            ):
                val = detail.get(key)
                if isinstance(val, (int, float)):
                    if bucket == "input":
                        input_tokens += float(val)
                    else:
                        output_tokens += float(val)
    if input_tokens <= 0.0 and output_tokens <= 0.0 and reasoning_tokens <= 0.0:
        return None
    rates = NEBIUS_KIMI_USD_PER_MILLION
    return (input_tokens / 1e6) * rates["input"] + (
        (output_tokens + reasoning_tokens) / 1e6
    ) * rates["output"]


def resolve_icml_meta_overhead(profile: str | None = None) -> float:
    """Meta/feedback overhead multiplier for budget reconcile (Tick 291).

    Override with ``SIA_META_OVERHEAD``. Default is higher for Nebius meta
    (same Kimi model as target, multi-turn tool use) than Anthropic Haiku.
    """
    raw = (os.environ.get("SIA_META_OVERHEAD") or "").strip()
    if raw:
        try:
            return max(1.0, float(raw))
        except ValueError:
            pass
    if icml_meta_provider_id(profile) == "nebius":
        return DEFAULT_META_OVERHEAD_NEBIUS
    return DEFAULT_META_OVERHEAD_ANTHROPIC


def _env_positive_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return int(default)
    try:
        return max(1, int(raw))
    except ValueError:
        return int(default)


def icml_g3g4_live_shape(profile: str | None = None) -> dict[str, int]:
    """Return G3/G4 ``eval_subset`` / pop / elite / ``max_gen`` (Tick 293–296).

    Nebius meta → budget-fit shape so 5-seed G4 + G2/G3 stay under ~$20 after
    Tick 291 Kimi metering. Anthropic meta → historical Section 21.5 shape.
    Env overrides: ``SIA_G3G4_EVAL_SUBSET``, ``SIA_G3G4_POPULATION_SIZE``,
    ``SIA_G3G4_ELITE_COUNT``, ``SIA_G3G4_MAX_GEN``.

    Tick 294: when ``population_size >= 2``, ``elite_count`` is floored at 2
    (and capped at pop). Elite does not change agent-eval cost; elite=1 makes
    crossover same-parent clones and collapses H2 under delay-all steering.

    Tick 295: briefly used eval8 / pop3 / max_gen5 (120 agent-evals) for the
    seed-22 gens30 horizon. Tick 296: offline showed pop=3 collapses PRIMARY
    / H5; Nebius defaults are now **eval5 / pop4 / elite2 / max_gen6** (still
    120 agent-evals; matches Tick 23 offline Darwinian shape).
    """
    if icml_meta_provider_id(profile) == "nebius":
        shape = {
            "eval_subset": _env_positive_int(
                "SIA_G3G4_EVAL_SUBSET", ICML_NEBIUS_G3G4_EVAL_SUBSET
            ),
            "population_size": _env_positive_int(
                "SIA_G3G4_POPULATION_SIZE", ICML_NEBIUS_G3G4_POPULATION_SIZE
            ),
            "elite_count": _env_positive_int(
                "SIA_G3G4_ELITE_COUNT", ICML_NEBIUS_G3G4_ELITE_COUNT
            ),
            "max_gen": _env_positive_int(
                "SIA_G3G4_MAX_GEN", ICML_NEBIUS_G3G4_MAX_GEN
            ),
        }
    else:
        shape = {
            "eval_subset": _env_positive_int(
                "SIA_G3G4_EVAL_SUBSET", ICML_ANTHROPIC_G3G4_EVAL_SUBSET
            ),
            "population_size": _env_positive_int(
                "SIA_G3G4_POPULATION_SIZE", ICML_ANTHROPIC_G3G4_POPULATION_SIZE
            ),
            "elite_count": _env_positive_int(
                "SIA_G3G4_ELITE_COUNT", ICML_ANTHROPIC_G3G4_ELITE_COUNT
            ),
            "max_gen": _env_positive_int(
                "SIA_G3G4_MAX_GEN", ICML_ANTHROPIC_G3G4_MAX_GEN
            ),
        }
    pop = shape["population_size"]
    elite = shape["elite_count"]
    if pop >= 2 and elite < 2:
        elite = 2
    if elite > pop:
        elite = pop
    shape["elite_count"] = elite
    return shape


def default_g2_estimate_usd(profile: str | None = None) -> float:
    """Default G2 smoke USD estimate (Tick 293: Nebius-aware)."""
    raw = (os.environ.get("SIA_G2_ESTIMATE_USD") or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    if icml_meta_provider_id(profile) == "nebius":
        return DEFAULT_G2_ESTIMATE_USD_NEBIUS
    return DEFAULT_G2_ESTIMATE_USD_ANTHROPIC


def default_g3_pair_estimate_usd(profile: str | None = None) -> float:
    """Default G3 B+D pair USD estimate (Tick 293: Nebius-aware + budget-fit)."""
    raw = (os.environ.get("SIA_G3_PAIR_ESTIMATE_USD") or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    if icml_meta_provider_id(profile) == "nebius":
        return DEFAULT_G3_PAIR_ESTIMATE_USD_NEBIUS
    return DEFAULT_G3_PAIR_ESTIMATE_USD_ANTHROPIC


def default_g4_pair_estimate_usd(profile: str | None = None) -> float:
    """Default G4 B+D pair USD estimate (Tick 293: Nebius-aware + budget-fit)."""
    raw = (os.environ.get("SIA_G4_PAIR_ESTIMATE_USD") or "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    if icml_meta_provider_id(profile) == "nebius":
        return DEFAULT_G4_PAIR_ESTIMATE_USD_NEBIUS
    return DEFAULT_G4_PAIR_ESTIMATE_USD_ANTHROPIC


def icml_diamond_n_for_stack(profile: str | None = None) -> int:
    """Diamond materialize ``n`` covering G2 smoke and G3/G4 eval_subset."""
    shape = icml_g3g4_live_shape(profile)
    return max(5, int(shape["eval_subset"]))


def _usd_from_cost_payload(data: dict) -> float | None:
    """Extract positive USD from a results.json or submission.json payload.

    Tick 291: when USD is zero/absent but tokens are present, estimate USD from
    Nebius Kimi rates so budget reconcile does not silently use gate estimates.
    """
    if not isinstance(data, dict):
        return None
    usd = data.get("total_cost_usd")
    if isinstance(usd, (int, float)) and float(usd) > 0.0:
        return float(usd)
    detail_total = 0.0
    found = False
    for detail in data.get("details") or []:
        if not isinstance(detail, dict):
            continue
        c = detail.get("cost_usd")
        if isinstance(c, (int, float)) and float(c) > 0.0:
            detail_total += float(c)
            found = True
    if found:
        return detail_total
    return estimate_usd_from_tokens(data)


def sum_run_dirs_cost_usd(run_dirs: list[Path]) -> float | None:
    """Sum ``total_cost_usd`` across ``gen_*/agent_*/results.json`` (Tick 283).

    Tick 290: also fall back to ``agent_*/results/submission.json`` when
    ``results.json`` is accuracy-only (pre-merge eval artifacts).

    Tick 291: when USD is zero but tokens exist, estimate via Nebius Kimi rates.

    Returns ``None`` when no positive USD fields are found (dry-run / missing
    artifacts). Target-eval costs only — meta/feedback spend is usually not in
    these files; callers should apply a small overhead factor.
    """
    total = 0.0
    found = False
    for run_dir in run_dirs:
        if run_dir is None:
            continue
        root = Path(run_dir)
        if not root.is_dir():
            continue
        for agent_dir in root.glob("gen_*/agent_*"):
            if not agent_dir.is_dir():
                continue
            payloads: list[dict] = []
            for rel in ("results.json", "results/submission.json"):
                path = agent_dir / rel
                if not path.is_file():
                    continue
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError, TypeError):
                    continue
                if isinstance(data, dict):
                    payloads.append(data)
            # Prefer results.json (post-Tick-290 merged) then submission.
            agent_usd = None
            for data in payloads:
                agent_usd = _usd_from_cost_payload(data)
                if agent_usd is not None:
                    break
            if agent_usd is not None:
                total += agent_usd
                found = True
    return total if found else None


def reconcile_gate_spend_usd(
    run_dirs: list[Path],
    *,
    fallback_estimate: float,
    meta_overhead: float | None = None,
) -> tuple[float, str]:
    """Pick gate spend for ``SIA_BUDGET_SPENT_USD`` (Tick 283/291).

    Prefer actual target-eval USD × ``meta_overhead`` (covers unmetered
    meta/feedback). When ``meta_overhead`` is None, use
    ``resolve_icml_meta_overhead()`` (Nebius meta → 3.0; Anthropic → 1.25).
    Fall back to the gate estimate when artifacts lack USD/tokens.
    Returns ``(amount, detail)``.
    """
    estimate = max(0.0, float(fallback_estimate))
    actual = sum_run_dirs_cost_usd(run_dirs)
    if actual is None:
        return estimate, f"estimate=${estimate:.4f} (no total_cost_usd/tokens in run artifacts)"
    overhead = resolve_icml_meta_overhead() if meta_overhead is None else max(1.0, float(meta_overhead))
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


# Per-VM greenfield boot branch for open_git_pr warn (Tick 354 persist;
# Tick 356: gitignored — survive discard / tip --apply; never commit).
ICML_CLOUD_BOOT_BRANCH_RELPATH = "docs/icml_cloud_boot_branch.txt"

# Preflight / status writers only — safe to discard before tip --apply (Tick 286).
# Tick 356: do NOT list ICML_CLOUD_BOOT_BRANCH_RELPATH here. Tick 354–355 made
# that file the durable fallback when env is unset (already-on-tip skip /
# env==tip unset). discard_ephemeral_icml_dirt previously unlinked it as
# "untracked removed", wiping the boot name right before tip --apply.
# Gitignore the path instead so porcelain never sees it and tip stays clean.
# Tick 359: do NOT list ICML_OPEN_GIT_PR_CALL_RELPATH here either. Tip HEAD
# committed call JSON with a prior-tick cloud_boot_branch (e.g. …-48b0);
# discard_ephemeral ``git restore`` re-poisoned fresh boots after tip --apply
# (same class of bug as Tick 356 for the boot file). Gitignore + exclude.
EPHEMERAL_ICML_RELPATHS: frozenset[str] = frozenset(
    {
        "docs/gate2_report.md",
        "docs/gate2_report.json",
        "docs/gate3_report.md",
        "docs/gate3_report.json",
        "docs/gate4_report.md",
        "docs/gate4_report.json",
        "docs/icml_live_pipeline_report.md",
        "docs/icml_live_pipeline_report.json",
        "docs/icml_secrets_status.json",
        "docs/icml_tip_status.json",
        "docs/icml_open_git_pr.json",
        "docs/icml_tip_pr_body.md",
    }
)


def is_ephemeral_icml_path(rel_path: str) -> bool:
    """True when ``rel_path`` is a preflight/status artifact (Tick 286)."""
    norm = rel_path.replace("\\", "/").lstrip("./")
    return norm in EPHEMERAL_ICML_RELPATHS


def porcelain_dirty_paths(repo_root: Path | None = None) -> list[str]:
    """Return repo-relative dirty paths from ``git status --porcelain``."""
    import subprocess

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain", "-uall"],
            cwd=str(root),
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    paths: list[str] = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        # XY PATH or XY ORIG -> PATH (rename)
        rest = line[3:]
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        rest = rest.strip().strip('"')
        if rest:
            paths.append(rest.replace("\\", "/"))
    return paths


def discard_ephemeral_icml_dirt(
    repo_root: Path | None = None,
) -> tuple[bool, str]:
    """Discard uncommitted changes limited to ephemeral ICML report/status files.

    Tick 286: tip ``--apply`` used to refuse any dirty tree. Preflight alone
    dirties gate/pipeline/secrets/tip reports, so a later tip could never be
    recovered mid-cron. Restoring *only* ``EPHEMERAL_ICML_RELPATHS`` keeps
    real code edits as a hard stop.

    Returns ``(ok_for_tip_apply, detail)``. ``ok_for_tip_apply`` is True when
    the tree is clean after this call (or was already clean).
    """
    import subprocess

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    dirty = porcelain_dirty_paths(root)
    if not dirty:
        return True, "working tree clean"

    ephemeral = [p for p in dirty if is_ephemeral_icml_path(p)]
    other = [p for p in dirty if not is_ephemeral_icml_path(p)]
    if other:
        # Do not touch ephemerals when real edits exist — operator must
        # commit/stash the whole tree before tip --apply.
        return False, f"non-ephemeral dirty paths block tip apply: {other[:8]}"
    if not ephemeral:
        return True, "working tree clean"

    restored: list[str] = []
    for rel in ephemeral:
        path = root / rel
        # Tracked: git restore. Untracked: unlink if present.
        try:
            tracked = subprocess.run(
                ["git", "ls-files", "--error-unmatch", rel],
                cwd=str(root),
                capture_output=True,
                text=True,
            )
            if tracked.returncode == 0:
                subprocess.run(
                    ["git", "restore", "--worktree", "--staged", "--", rel],
                    cwd=str(root),
                    check=False,
                    capture_output=True,
                    text=True,
                )
                # Older git without restore --staged combo: also checkout
                subprocess.run(
                    ["git", "checkout", "--", rel],
                    cwd=str(root),
                    check=False,
                    capture_output=True,
                    text=True,
                )
                restored.append(rel)
            elif path.is_file():
                path.unlink()
                restored.append(rel + " (untracked removed)")
        except OSError as exc:
            return False, f"failed discarding {rel}: {exc}"

    remaining = porcelain_dirty_paths(root)
    if remaining:
        non_ephem = [p for p in remaining if not is_ephemeral_icml_path(p)]
        if non_ephem:
            return (
                False,
                f"discarded {restored}; still dirty non-ephemeral: {non_ephem[:8]}",
            )
        # Only ephemeral remain (restore failed?) — try once more is useless
        return False, f"discarded {restored}; ephemeral still dirty: {remaining[:8]}"
    return True, f"discarded ephemeral dirt: {restored}"


def ensure_budget_spent_ledger_initialized(
    repo_root: Path | None = None,
) -> tuple[Path, bool]:
    """Create a zero spend ledger when missing (Tick 286). Never overwrites.

    Returns ``(path, created)``.
    """
    p = budget_spent_ledger_path(repo_root)
    if p.is_file():
        return p, False
    write_budget_spent_ledger(
        spent_usd=0.0,
        stages_complete=[],
        run_ids=[],
        detail="Tick 286: initialized zero ledger (no live spend yet)",
        path=p,
    )
    return p, True


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
            "Tick 284/285/286: persisted SIA_BUDGET_SPENT_USD across cron ticks; "
            "commit this file so cross-VM resume can skip completed G2/G3/G4 "
            "(runs/ are gitignored and do not survive fresh boots); "
            "Tick 286 ships a zero ledger when no live spend yet"
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


def main_has_icml_tip_files(*, repo_root: Path | None = None) -> bool:
    """True when ``origin/main`` (or local ``main``) contains ICML tip scripts.

    Tick 328: cron boots from ``main``. Until tip lands there, every tick must
    chicken-egg recover. This is an **operational** dual-unblock signal — it
    does **not** block ``fetch_diamond_ok`` / paid live once secrets exist
    (recover still works).
    """
    root = repo_root or _REPO_ROOT
    marker = "scripts/icml_cron_entry.sh"
    for ref in ("refs/remotes/origin/main", "origin/main", "main"):
        ok, _ = _git_ok(["cat-file", "-e", f"{ref}:{marker}"], cwd=root)
        if ok:
            return True
    return False


def _branch_from_tip_ref(tip_ref: str | None) -> str | None:
    """Map ``refs/remotes/origin/…`` / ``origin/…`` tip refs to a branch name."""
    if not tip_ref:
        return None
    ref = str(tip_ref).strip()
    for prefix in ("refs/remotes/origin/", "refs/heads/", "origin/"):
        if ref.startswith(prefix):
            return ref[len(prefix) :]
    if "/" in ref:
        return ref
    return None


def _gh_pr_list_for_head(
    branch: str,
    *,
    repo_root: Path | None = None,
) -> list[dict]:
    """Open PRs for ``--head <branch>`` via ``gh`` (Tick 330/333 helper)."""
    root = repo_root or _REPO_ROOT
    try:
        proc = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                "open",
                "--limit",
                "3",
                "--json",
                # Tick 335: also fetch mergeability so human_next can say
                # MERGEABLE/CLEAN vs CONFLICTING among 300+ draft tip PRs.
                # Tick 347: also fetch body so tip_pr_body_stale is independent
                # of tip_pr_title_stale (Tick 346 gated body refresh on title only).
                "number,url,title,body,isDraft,headRefName,mergeable,mergeStateStatus",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    try:
        rows = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(rows, list):
        return []
    out: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = row.get("url")
        number = row.get("number")
        if not url or number is None:
            continue
        mergeable = row.get("mergeable")
        merge_state = row.get("mergeStateStatus")
        out.append(
            {
                "url": str(url),
                "number": int(number),
                "title": str(row.get("title") or ""),
                # Tick 347: body for independent tip_pr_body_stale detection.
                "body": str(row.get("body") or ""),
                "is_draft": bool(row.get("isDraft")),
                "head_ref": str(row.get("headRefName") or branch),
                # Tick 335: optional; may be None if gh omits fields.
                "mergeable": str(mergeable) if mergeable is not None else None,
                "merge_state_status": (
                    str(merge_state) if merge_state is not None else None
                ),
            }
        )
    return out


def _sha_prefix_equal(a: str | None, b: str | None, *, n: int = 7) -> bool:
    """True when short/full git SHAs refer to the same commit prefix."""
    if not a or not b:
        return False
    sa = str(a).strip().lower()
    sb = str(b).strip().lower()
    if not sa or not sb:
        return False
    return sa[:n] == sb[:n]


def _tip_sha_for_pr_resolve(
    *,
    branch: str | None,
    tip_ref: str | None,
    candidates: list[dict],
    repo_root: Path | None = None,
) -> str | None:
    """Resolve the tip commit SHA used for same-SHA sibling PR fallback.

    Tick 334: greenfield cron branches are often tip-recovered locally before
    ``git push``, so ``refs/remotes/origin/<greenfield>`` may not exist yet.
    Fall back to local branch / HEAD so same-SHA sibling tip PRs still resolve.
    """
    root = repo_root or _REPO_ROOT
    if branch:
        for cand in candidates:
            if _branch_from_tip_ref(str(cand.get("ref") or "")) == branch:
                sha = str(cand.get("sha") or "") or None
                if sha:
                    return sha
    for ref in (
        tip_ref,
        (f"refs/heads/{branch}" if branch else None),
        (branch or None),
        "HEAD",
    ):
        if not ref:
            continue
        ok, out = _git_ok(["rev-parse", "--short=12", ref], cwd=root)
        if ok and out.strip():
            return out.strip()
    return None


def resolve_icml_tip_pr(
    *,
    tip_ref: str | None = None,
    repo_root: Path | None = None,
) -> dict | None:
    """Resolve the open GitHub PR for the current ICML tip branch (Tick 330/333–335).

    Returns ``{url, number, title, is_draft, head_ref, mergeable,
    merge_state_status}`` or ``None``. Uses ``gh`` when available; never
    raises. Operators otherwise face 300+ draft tip PRs with no concrete
    merge link in ``human_next``.

    Tick 333: if the tip head has no open PR yet, also try **same-SHA**
    sibling tip refs (e.g. prior tip branch / ``bc-*`` alias). Still never
    falls back to an unrelated open ICML PR (Tick 331 hazard).

    Tick 334: when tip SHA cannot be read from an unpushed
    ``refs/remotes/origin/<greenfield>`` tip_ref, fall back to local branch /
    HEAD so same-SHA sibling resolution still works after tip recover.

    Tick 335: also surfaces ``mergeable`` / ``merge_state_status`` from
    ``gh`` so ``human_next`` can say MERGEABLE/CLEAN vs CONFLICTING.
    """
    root = repo_root or _REPO_ROOT
    candidates = list_remote_icml_tip_candidates(repo_root=root, fetch=False)
    branch = _branch_from_tip_ref(tip_ref)
    if branch is None and candidates:
        branch = _branch_from_tip_ref(str(candidates[0].get("ref") or ""))
        tip_ref = str(candidates[0].get("ref") or "") or tip_ref
    if not branch:
        return None

    rows = _gh_pr_list_for_head(branch, repo_root=root)
    if rows:
        return rows[0]

    # Tip head has no open PR yet (common mid-tick before open_git_pr, or when
    # cron recovered tip onto a new greenfield branch at the same SHA).
    # Tick 333: same-SHA sibling tip refs may already have the mergeable PR.
    # Tick 334: tip_sha via local branch / HEAD when remote tip_ref is unpushed.
    tip_sha = _tip_sha_for_pr_resolve(
        branch=branch,
        tip_ref=tip_ref,
        candidates=candidates,
        repo_root=root,
    )
    if tip_sha:
        seen: set[str] = {branch}
        for cand in candidates:
            sib = _branch_from_tip_ref(str(cand.get("ref") or ""))
            if not sib or sib in seen:
                continue
            if not _sha_prefix_equal(tip_sha, str(cand.get("sha") or "")):
                continue
            seen.add(sib)
            sib_rows = _gh_pr_list_for_head(sib, repo_root=root)
            if sib_rows:
                return sib_rows[0]

    # Do **not** fall back to an arbitrary "ICML Tick" PR — that mislabels
    # tip_pr_url (Tick 331: bc-* tip without a PR briefly resolved to stale #322).
    return None


# Tick 341–342: interim 1-file AGENTS chicken-egg bootstrap onto main (not a tip PR).
ICML_AGENTS_BOOTSTRAP_BRANCH = "cursor/icml-main-agents-bootstrap"


def resolve_icml_agents_bootstrap_pr(
    *,
    repo_root: Path | None = None,
    branch: str | None = None,
) -> dict | None:
    """Resolve the open main-only AGENTS bootstrap PR (Tick 342).

    Tick 341 opened ``cursor/icml-main-agents-bootstrap`` so cron can inject
    chicken-egg recover without reviewing the full tip. Until operators merge
    it (or the full tip), ``human_next`` / secrets+tip JSON should surface the
    concrete bootstrap PR URL + ``gh`` copy-paste — Tick 341 only documented
    the branch in HUMAN_UNBLOCK, so cron logs still led with tip #337 alone.
    """
    root = repo_root or _REPO_ROOT
    head = (branch or ICML_AGENTS_BOOTSTRAP_BRANCH).strip()
    if not head:
        return None
    rows = _gh_pr_list_for_head(head, repo_root=root)
    return rows[0] if rows else None


def _merge_agents_bootstrap_human_next(pr: dict | None = None) -> str:
    """Tick 342: interim AGENTS bootstrap merge path (easier than full tip)."""
    if pr is None:
        pr = resolve_icml_agents_bootstrap_pr()
    if not pr:
        return (
            "Optional interim: merge main-only AGENTS chicken-egg bootstrap "
            f"branch `{ICML_AGENTS_BOOTSTRAP_BRANCH}` when open (Tick 341–342; "
            "1-file PR — not a tip PR). See `docs/ICML_HUMAN_UNBLOCK.md`."
        )
    merge_note = _tip_pr_mergeability_note(pr)
    cmds = _tip_pr_merge_commands(pr)
    paste = f" Copy-paste: `{' && '.join(cmds)}`." if cmds else ""
    return (
        "Optional interim (easier than full tip): merge main-only AGENTS "
        "chicken-egg bootstrap PR "
        f"#{pr['number']} {pr['url']}{merge_note} "
        f"(branch `{pr.get('head_ref') or ICML_AGENTS_BOOTSTRAP_BRANCH}`; "
        "Tick 341–342; 1-file — **not** a tip PR; does not replace merging the "
        f"tip).{paste} Agents: tip anti-churn tip PR is unchanged — still "
        "commit/`open_git_pr` on `tip_pr_commit_branch` only."
    )


def _tip_pr_mergeability_note(pr: dict) -> str:
    """Tick 335: short mergeability hint for human_next (MERGEABLE/CLEAN etc.)."""
    mergeable = str(pr.get("mergeable") or "").strip().upper()
    state = str(pr.get("merge_state_status") or "").strip().upper()
    if not mergeable and not state:
        return ""
    parts: list[str] = []
    if mergeable:
        parts.append(mergeable)
    if state and state != mergeable:
        parts.append(state)
    label = "/".join(parts)
    if mergeable == "MERGEABLE" and state in {"", "CLEAN"}:
        return f" — GitHub {label}: undraft & merge now (no conflicts)"
    if mergeable == "CONFLICTING" or state in {"DIRTY", "UNSTABLE"}:
        return f" — GitHub {label}: rebase onto main before merge"
    return f" — GitHub {label}"


_ICML_GITHUB_REPO = "kshivam4781/DarwinianSIA"


def _tip_pr_merge_commands(pr: dict | None) -> list[str]:
    """Tick 336: copy-paste ``gh`` undraft+merge for the concrete tip PR.

    Operators face 100+ open draft tip PRs; mergeability alone still requires
    clicking through the UI. Exact ``gh pr ready`` / ``gh pr merge`` commands
    land the tip on ``main`` in one shell paste.
    """
    if not pr or pr.get("number") is None:
        return []
    n = int(pr["number"])
    repo = _ICML_GITHUB_REPO
    cmds: list[str] = []
    if pr.get("is_draft"):
        cmds.append(f"gh pr ready {n} --repo {repo}")
    cmds.append(f"gh pr merge {n} --repo {repo} --merge")
    return cmds


ICML_TIP_PR_BODY_RELPATH = "docs/icml_tip_pr_body.md"
# Tick 350: minimal MCP args file (branch/title/description only) — agents load
# this instead of hunting fields inside the large open_git_pr hint JSON.
ICML_OPEN_GIT_PR_CALL_RELPATH = "docs/icml_open_git_pr_call.json"

_REFLOG_CHECKOUT_RE = re.compile(r"checkout: moving from (\S+) to (\S+)")


def _is_valid_cloud_boot_branch_name(
    boot: str | None,
    *,
    tip_commit_branch: str | None = None,
) -> bool:
    """Tick 357: boot must be a full ``cursor/*`` ref ≠ tip (reject short poison).

    Agents sometimes write a bare suffix (e.g. ``48b0``) into
    ``docs/icml_cloud_boot_branch.txt``. That poisoned the detect chain
    ahead of reflog (which still had ``cursor/icml-epistemic-results-48b0``),
    so ``open_git_pr`` warn / call JSON recorded a nonsense boot name.
    """
    name = (boot or "").strip()
    if not name or not name.startswith("cursor/"):
        return False
    tip = (tip_commit_branch or "").strip() or None
    if tip and name == tip:
        return False
    return True


def persist_cloud_boot_branch(
    boot: str | None,
    *,
    tip_commit_branch: str | None = None,
    repo_root: Path | None = None,
) -> str | None:
    """Tick 354/356/357: write gitignored ``docs/icml_cloud_boot_branch.txt`` when boot ≠ tip.

    Returns the persisted boot name, or ``None`` when skipped (empty / equals tip /
    not a full ``cursor/*`` name — Tick 357).
    """
    tip = (tip_commit_branch or "").strip() or None
    if not _is_valid_cloud_boot_branch_name(boot, tip_commit_branch=tip):
        return None
    name = (boot or "").strip()
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    path = root / ICML_CLOUD_BOOT_BRANCH_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(name + "\n", encoding="utf-8")
    return name


def _read_persisted_cloud_boot_branch(
    *,
    tip_commit_branch: str | None = None,
    repo_root: Path | None = None,
) -> str | None:
    """Tick 354/356/357: read gitignored boot file when present, valid, and ≠ tip.

    Tick 357: unlink short/invalid poison so reflog / current-branch can win.
    """
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    path = root / ICML_CLOUD_BOOT_BRANCH_RELPATH
    tip = (tip_commit_branch or "").strip() or None
    try:
        name = path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    except (OSError, IndexError):
        return None
    if not _is_valid_cloud_boot_branch_name(name, tip_commit_branch=tip):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    return name


def detect_cloud_boot_branch(
    *,
    tip_commit_branch: str | None = None,
    repo_root: Path | None = None,
) -> str | None:
    """Tick 352–357: greenfield boot branch ``open_git_pr`` defaults to when ``branch=`` omitted.

    Cloud Agent runs start on a fresh ``cursor/*`` branch (often at ``main`` SHA).
    After tip anti-churn checkout (Tick 337–351), HEAD is ``tip_pr_commit_branch``,
    but the MCP still defaults to the *boot* branch when ``branch=`` is omitted —
    opening a **new** tip PR. Surface the concrete boot name (e.g. ``…-6a00``)
    in ``docs/icml_open_git_pr_call.json`` / secrets JSON so agents see the
    mismatch vs tip (e.g. ``…-f49c``).

    Resolution order:
    1. ``ICML_CLOUD_BOOT_BRANCH`` env override (Tick 353: ``icml_cron_entry.sh``
       exports this from ``git branch --show-current`` *before* tip recover /
       anti-churn checkout, and preserves it across ``ICML_CRON_REEXEC``).
       Tick 354: **ignore** when env equals ``tip_commit_branch`` (false capture
       after an agent already checked out tip before cron).
       Tick 357: **ignore** short/non-``cursor/*`` poison names.
    2. Gitignored ``docs/icml_cloud_boot_branch.txt`` (Tick 354 persist;
       Tick 356: survives discard / tip --apply; never committed;
       Tick 357: invalid short names are unlinked so reflog can win)
    3. ``git reflog`` — checkout from ``cursor/*`` → tip, or ``main`` → ``cursor/*``
    4. Current branch when it is a greenfield ``cursor/*`` name ≠ tip

    When a non-tip boot is resolved, persist it to the ephemeral file.
    Tick 357: ``icml_checkout_tip_pr_branch.sh`` also persists *before* tip
    checkout so mid-tick agents without cron capture still keep the warn.
    """
    import subprocess

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    tip = (tip_commit_branch or "").strip() or None

    def _accept(candidate: str | None) -> str | None:
        name = (candidate or "").strip()
        if not _is_valid_cloud_boot_branch_name(name, tip_commit_branch=tip):
            return None
        return name

    env = _accept((os.environ.get("ICML_CLOUD_BOOT_BRANCH") or "").strip())
    if env:
        persist_cloud_boot_branch(env, tip_commit_branch=tip, repo_root=root)
        return env

    persisted = _read_persisted_cloud_boot_branch(
        tip_commit_branch=tip, repo_root=root
    )
    if persisted:
        return persisted

    try:
        out = subprocess.check_output(
            ["git", "reflog", "-n", "50", "--format=%gs"],
            cwd=str(root),
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        out = ""
    boot_from_main: str | None = None
    for line in out.splitlines():
        match = _REFLOG_CHECKOUT_RE.search(line)
        if not match:
            continue
        src, dst = match.group(1), match.group(2)
        if (
            tip
            and dst == tip
            and _is_valid_cloud_boot_branch_name(src, tip_commit_branch=tip)
        ):
            persist_cloud_boot_branch(src, tip_commit_branch=tip, repo_root=root)
            return src
        if (
            src in {"main", "origin/main"}
            and _is_valid_cloud_boot_branch_name(dst, tip_commit_branch=tip)
            and boot_from_main is None
        ):
            boot_from_main = dst
    if boot_from_main:
        persist_cloud_boot_branch(
            boot_from_main, tip_commit_branch=tip, repo_root=root
        )
        return boot_from_main
    try:
        cur = subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=str(root),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        cur = ""
    cur_ok = _accept(cur)
    if cur_ok:
        persist_cloud_boot_branch(cur_ok, tip_commit_branch=tip, repo_root=root)
        return cur_ok
    return None


def suggested_open_git_pr_body(
    *,
    local_tick: int | None,
    fetch_diamond_ok: bool | None = None,
    tip_pr_number: int | None = None,
) -> str:
    """Tick 346–349: secrets-first tip PR body for ``gh pr edit`` / open_git_pr.

    Tick 345 covered title-only refresh. ``gh pr view 337`` still showed a
    **Tick 336 body** after Ticks 337–345 — ``open_git_pr`` MCP does not rewrite
    title *or* body on existing tip PRs. Operators reading the PR description
    still saw merge-command hygiene instead of the PRIMARY secrets ask.

    Tick 347: body refresh is driven by ``tip_pr_body_stale`` (parsed from the
    live GitHub body), not only ``tip_pr_title_stale`` — a title-only ``gh pr
    edit`` must not drop the body-file paste.

    Tick 348: agents must also pass ``description=`` (file contents) on
    ``open_git_pr`` when ``tip_pr_body_stale`` — symmetric with Tick 344
    ``title=``. MCP may still leave GitHub body frozen on existing PRs; the
    call shape is required for any *new* tip PR and keeps the secrets-first
    body in the agent transcript / MCP args.

    Tick 349: ``write_icml_open_git_pr_hint`` also keeps the body **inline** as
    ``open_git_pr_description`` in ``docs/icml_open_git_pr.json`` (Tick 348 only
    kept a file pointer and dropped the string from JSON — agents skipped the
    extra read and never passed ``description=``).

    Tick 350: also write ``docs/icml_open_git_pr_call.json`` with the exact MCP
    args ``{branch, title, description}`` so agents pass all three verbatim
    without hunting fields in the large hint JSON.

    Tick 353: cron exports ``ICML_CLOUD_BOOT_BRANCH`` before tip recover so
    ``cloud_boot_branch`` detection does not depend on post-reset reflog.

    Tick 354: ignore env when it equals tip (false capture after tip checkout);
    persist true boot to ephemeral ``docs/icml_cloud_boot_branch.txt``.

    Tick 356: boot file is gitignored and excluded from ephemeral discard so
    tip ``--apply`` / ``discard_ephemeral_icml_dirt`` cannot wipe the durable
    fallback Tick 354–355 rely on (and cannot accidentally commit a boot name).

    Tick 355: ``icml_cron_entry.sh`` must not refresh the boot file when a
    pre-set ``ICML_CLOUD_BOOT_BRANCH`` equals tip (that clobbers the real
    greenfield boot); unset the false env and keep boot file / reflog.

    Tick 357: reject short/non-``cursor/*`` boot poison; ``icml_checkout_tip_pr_branch.sh``
    persists the current greenfield boot *before* tip checkout.

    Tick 358: after tip checkout, refresh ``docs/icml_open_git_pr_call.json`` so
    ``cloud_boot_branch`` matches the just-persisted boot (not a stale
    prior-tick value when agents skip full cron status rewrite).
    """
    tick = local_tick if local_tick is not None else 0
    n = tip_pr_number if tip_pr_number is not None else "N"
    if fetch_diamond_ok is False:
        primary = (
            f"**PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local "
            f"`gpqa_diamond.csv`) so cron can run live G2→G3→G4."
        )
    elif fetch_diamond_ok is True:
        primary = (
            "**Secrets OK** — next: `bash scripts/icml_cron_entry.sh` for live "
            "G2→G3→G4 (or undraft+merge this tip into `main` first)."
        )
    else:
        primary = (
            "Check `docs/icml_secrets_status.json` / `docs/ICML_HUMAN_UNBLOCK.md` "
            "for NEBIUS + HF/CSV gates."
        )
    return (
        f"## Summary\n"
        f"- Tick {tick}: tip PR GitHub **title and body** stay frozen when using "
        f"`open_git_pr` MCP (does **not** rewrite either on existing PRs — "
        f"Tick 345 title finding; Tick 346 body confirmation; Tick 347 "
        f"independent ``tip_pr_body_stale``; Tick 348–349 pass "
        f"``description=`` from `open_git_pr_description` in "
        f"`docs/icml_open_git_pr.json` or `{ICML_TIP_PR_BODY_RELPATH}`; "
        f"Tick 350: prefer verbatim args from "
        f"`{ICML_OPEN_GIT_PR_CALL_RELPATH}`; Tick 353–359: cron exports "
        f"`ICML_CLOUD_BOOT_BRANCH` before tip recover; Tick 354 ignores "
        f"env==tip + persists `{ICML_CLOUD_BOOT_BRANCH_RELPATH}`; Tick 355 "
        f"unsets env==tip and does not clobber the boot file with tip; "
        f"Tick 356 gitignores the boot file + excludes it from ephemeral "
        f"discard so tip --apply cannot wipe it; Tick 357 rejects short/"
        f"non-``cursor/*`` boot poison + ``icml_checkout_tip_pr_branch.sh`` "
        f"persists boot before tip checkout; Tick 358 checkout also refreshes "
        f"`{ICML_OPEN_GIT_PR_CALL_RELPATH}` so ``cloud_boot_branch`` matches "
        f"the just-persisted boot; Tick 359 gitignores call JSON + excludes "
        f"it from ephemeral discard so tip --apply cannot ``git restore`` a "
        f"stale committed boot name). "
        f"Refresh via `tip_pr_title_edit_commands` (`gh pr edit --title … "
        f"--body-file {ICML_TIP_PR_BODY_RELPATH}`).\n"
        f"- {primary}\n"
        f"- Offline PRIMARY/H5 unchanged (`1890–1904`); STATUS remains "
        f"IN_PROGRESS (not READY).\n"
        f"\n"
        f"## Human unblock\n"
        f"1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)\n"
        f"2. Optional: copy-paste `tip_pr_title_edit_commands` from "
        f"`docs/icml_open_git_pr.json` to refresh this PR's title+body\n"
        f"3. Optional: undraft+merge tip PR #{n} and/or bootstrap PR #338\n"
        f"\n"
        f"## Test plan\n"
        f"- [x] `pytest tests/test_icml_env_checks.py::"
        f"test_suggested_open_git_pr_title_secrets_first_when_stale`\n"
        f"- [x] `pytest tests/test_icml_env_checks.py::"
        f"test_tip_pr_body_stale_independent_of_title`\n"
        f"- [x] `pytest tests/test_icml_env_checks.py::"
        f"test_open_git_pr_pass_description_when_body_stale`\n"
        f"- [x] `pytest tests/test_icml_env_checks.py::"
        f"test_open_git_pr_description_inline_in_json`\n"
        f"- [x] `pytest tests/test_icml_env_checks.py::"
        f"test_open_git_pr_call_json_atomic_mcp_args`\n"
        f"- [x] `pytest tests/test_icml_env_checks.py::"
        f"test_detect_cloud_boot_branch_env_and_mismatch`\n"
        f"- [x] `pytest tests/test_icml_env_checks.py::"
        f"test_cron_entry_captures_boot_branch_before_tip_recover`\n"
        f"- [x] `pytest tests/test_icml_env_checks.py::"
        f"test_detect_cloud_boot_branch_ignores_env_eq_tip`\n"
        f"- [x] `pytest tests/test_icml_env_checks.py::"
        f"test_cron_entry_unsets_env_eq_tip_no_boot_clobber`\n"
        f"- [x] `pytest tests/test_icml_env_checks.py::"
        f"test_boot_file_gitignored_survives_ephemeral_discard`\n"
        f"- [x] `pytest tests/test_icml_env_checks.py::"
        f"test_reject_short_boot_poison_and_checkout_persists`\n"
        f"- [x] `pytest tests/test_icml_env_checks.py::"
        f"test_refresh_open_git_pr_after_tip_checkout_updates_boot`\n"
        f"- [x] `pytest tests/test_icml_env_checks.py::"
        f"test_call_json_gitignored_survives_ephemeral_discard`\n"
        f"- [x] STATUS remains IN_PROGRESS until live PRIMARY criteria pass\n"
    )


def _tip_pr_title_edit_commands(
    pr: dict | None,
    suggested_title: str | None,
    *,
    body_file: str | None = None,
    include_title: bool = True,
) -> list[str]:
    """Tick 345–347: copy-paste ``gh pr edit`` when MCP won't rewrite PR metadata.

    Tick 344 found ``open_git_pr`` updates the existing tip PR in place but does
    **not** change the GitHub title (stayed Tick 336 through 344). Tick 346:
    the GitHub **body** is likewise frozen (still Tick 336 through 345) — include
    ``--body-file`` when a secrets-first body artifact is available. Tick 347:
    title and body staleness are independent — ``include_title`` / ``body_file``
    may be set separately (body-only refresh after a title-only edit).
    """
    if not pr or pr.get("number") is None:
        return []
    n = int(pr["number"])
    parts: list[str] = [f"gh pr edit {n} --repo {_ICML_GITHUB_REPO}"]
    if include_title and suggested_title:
        # Single-quote wrap; escape any embedded single quotes for POSIX shells.
        safe = str(suggested_title).replace("'", "'\\''")
        parts.append(f"--title '{safe}'")
    if body_file:
        parts.append(f"--body-file {body_file}")
    if len(parts) == 1:
        return []
    return [" ".join(parts)]


def _tip_pr_title_edit_human_next(
    pr: dict | None,
    *,
    suggested_title: str | None,
    title_stale: bool,
    body_file: str | None = None,
    body_stale: bool = False,
) -> str | None:
    """Tick 345–347: human_next line with gh title and/or body edit when stale."""
    if not title_stale and not body_stale:
        return None
    cmds = _tip_pr_title_edit_commands(
        pr,
        suggested_title,
        body_file=body_file if body_stale else None,
        include_title=title_stale,
    )
    if not cmds or not pr:
        return None
    paste = " && ".join(cmds)
    n = pr.get("number")
    if title_stale and body_stale:
        body_note = " title **and** body"
    elif body_stale:
        body_note = " body"
    else:
        body_note = " title"
    return (
        f"Tip PR #{n}{body_note} is stale (open_git_pr MCP does **not** rewrite "
        f"GitHub title/body on existing PRs — Tick 344–349). "
        f"Copy-paste: `{paste}` (secrets-first when diamond blocked; "
        f"stale titles/bodies look superseded among 300+ drafts)."
    )


def prefer_tip_pr_commit_branch(pr: dict | None = None) -> str | None:
    """Tick 337–340/351: tip PR head_ref for commits (anti-churn).

    Cron boots a greenfield ``cursor/…`` branch every tick. Opening a *new*
    tip PR supersedes the MERGEABLE one and defeats tip→main. When the tip PR
    is usable, agents must checkout/push this ``head_ref`` and pass it to
    ``open_git_pr(branch=…)`` so the existing PR updates instead.

    Tick 338: ``icml_cron_entry.sh`` auto-checkouts this branch after writing
    tip/secrets JSON (Tick 337 left checkout as a manual script only).
    Tick 339: ``icml_boot_recover.sh --apply`` + ``icml_recover_tip.py --apply``
    also auto-checkout (chicken-egg recover alone no longer leaves greenfield
    branch names).
    Tick 340: ``open_git_pr`` MCP defaults to the *boot* branch when ``branch``
    is omitted — even after anti-churn checkout/push onto tip_pr_commit_branch.
    Agents must **never omit** ``branch=<tip_pr_commit_branch>``; see
    ``docs/icml_open_git_pr.json``.
    Tick 351: accept UNKNOWN/null/empty ``mergeable`` (GitHub often returns
    null while computing). Requiring exact ``MERGEABLE`` skipped anti-churn on
    greenfield boots — tip status wrote ``tip_pr_commit_branch=null`` while
    secrets/open_git_pr still had the head — and agents stayed on the boot
    branch / opened a new tip PR. Still refuse CONFLICTING/DIRTY.
    """
    if pr is None:
        pr = resolve_icml_tip_pr()
    if not pr:
        return None
    mergeable = str(pr.get("mergeable") or "").strip().upper()
    state = str(pr.get("merge_state_status") or "").strip().upper()
    head = str(pr.get("head_ref") or "").strip()
    if not head:
        return None
    if mergeable == "CONFLICTING" or state in {"DIRTY"}:
        return None
    # MERGEABLE, UNKNOWN, null/empty, or other non-conflicting states.
    return head


_PR_TITLE_TICK_RE = re.compile(r"\bTick\s+(\d+)\b", re.IGNORECASE)


def parse_tick_from_pr_title(title: str | None) -> int | None:
    """Extract the first ``Tick N`` integer from a tip PR title (Tick 344)."""
    if not title:
        return None
    match = _PR_TITLE_TICK_RE.search(str(title))
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def parse_tick_from_pr_body(body: str | None) -> int | None:
    """Extract the first ``Tick N`` integer from a tip PR body (Tick 347).

    Same pattern as ``parse_tick_from_pr_title``. Used so ``tip_pr_body_stale``
    does not depend on title freshness (Tick 346 gated body-file on title_stale).
    """
    return parse_tick_from_pr_title(body)


def suggested_open_git_pr_title(
    *,
    local_tick: int | None,
    fetch_diamond_ok: bool | None = None,
) -> str:
    """Tick 344: secrets-first tip PR title when live PRIMARY is still blocked.

    Tip PR #337 stayed titled ``Tick 336`` through Ticks 337–343, so among
    300+ draft tip PRs operators could treat the MERGEABLE tip as superseded.
    When ``fetch_diamond_ok`` is false, the suggested title leads with the
    PRIMARY secrets blocker (aligns with Tick 343 human_next ordering).
    """
    tick = local_tick if local_tick is not None else 0
    if fetch_diamond_ok is False:
        return (
            f"ICML Tick {tick}: add NEBIUS+HF secrets — live G2→G4 still blocked"
        )
    if fetch_diamond_ok is True:
        return f"ICML Tick {tick}: live stack ready — run cron G2→G4"
    return f"ICML Tick {tick}: epistemic evolution tip"


def build_icml_open_git_pr_hint(
    pr: dict | None = None,
    *,
    repo_root: Path | None = None,
    local_tick: int | None = None,
    fetch_diamond_ok: bool | None = None,
) -> dict | None:
    """Tick 340/344–349: open_git_pr anti-churn + title/body hint + gh edit."""
    root = repo_root or _REPO_ROOT
    if pr is None:
        pr = resolve_icml_tip_pr(repo_root=root)
    branch = prefer_tip_pr_commit_branch(pr)
    if not branch or not pr:
        return None
    if local_tick is None:
        progress_path = root / "docs" / "ICML_PROGRESS.md"
        if progress_path.is_file():
            try:
                local_tick = parse_latest_icml_tick(
                    progress_path.read_text(encoding="utf-8")
                )
            except OSError:
                local_tick = None
    if fetch_diamond_ok is None:
        # Lightweight presence check — avoid re-entering collect_icml_secrets_status
        # (which itself writes this hint).
        load_icml_dotenv()
        nebius = _secret_present("NEBIUS_API_KEY")
        anthropic = _secret_present("ANTHROPIC_API_KEY")
        hf = _secret_present("HF_TOKEN") or _secret_present("HUGGINGFACE_HUB_TOKEN")
        csv_ok = resolve_diamond_csv_path(repo_root=root) is not None
        meta_needs = icml_meta_requires_anthropic()
        secrets_ok = bool(nebius) and (bool(anthropic) if meta_needs else True)
        fetch_diamond_ok = bool(secrets_ok and (hf or csv_ok))
    tip_title = str(pr.get("title") or "")
    tip_body = str(pr.get("body") or "")
    title_tick = parse_tick_from_pr_title(tip_title)
    body_tick = parse_tick_from_pr_body(tip_body)
    suggested = suggested_open_git_pr_title(
        local_tick=local_tick, fetch_diamond_ok=fetch_diamond_ok
    )
    title_stale = bool(
        local_tick is not None
        and (title_tick is None or title_tick < local_tick)
    )
    # Tick 347: body staleness is independent of title (missing body ⇒ stale).
    body_stale = bool(
        local_tick is not None
        and (body_tick is None or body_tick < local_tick)
    )
    metadata_stale = title_stale or body_stale
    body_file = ICML_TIP_PR_BODY_RELPATH if body_stale else None
    suggested_body = (
        suggested_open_git_pr_body(
            local_tick=local_tick,
            fetch_diamond_ok=fetch_diamond_ok,
            tip_pr_number=pr.get("number"),
        )
        if body_stale
        else None
    )
    title_edit_cmds = (
        _tip_pr_title_edit_commands(
            pr,
            suggested,
            body_file=body_file,
            include_title=title_stale,
        )
        if metadata_stale
        else []
    )
    return {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tick_note": (
            "Tick 340: open_git_pr MCP defaults to the greenfield *boot* branch "
            "when `branch` is omitted — that opens a NEW tip PR even after "
            "Tick 337–339 checkout/push onto tip_pr_commit_branch. Always pass "
            "branch=<open_git_pr_branch>; never omit. "
            "Tick 344: also pass title=`suggested_open_git_pr_title` when "
            "tip_pr_title_stale (stale titles look superseded among 300+ drafts; "
            "when fetch_diamond_ok is false the suggested title leads with "
            "NEBIUS+HF secrets — PRIMARY path to READY). "
            "Tick 345: open_git_pr MCP does **not** rewrite GitHub titles on "
            "existing PRs — when tip_pr_title_stale, use "
            "`tip_pr_title_edit_commands` (`gh pr edit --title`) copy-paste. "
            "Tick 346: MCP also leaves the GitHub **body** frozen (still Tick "
            "336 through 345) — edit commands include "
            f"`--body-file {ICML_TIP_PR_BODY_RELPATH}` (secrets-first). "
            "Tick 347: ``tip_pr_body_stale`` is independent of "
            "``tip_pr_title_stale`` (gh fetches body; title-only edits no longer "
            "drop the body-file paste). "
            "Tick 348: when tip_pr_body_stale, also pass open_git_pr "
            f"description= from `{ICML_TIP_PR_BODY_RELPATH}` (symmetric with "
            "title=; MCP may still leave GitHub body frozen on existing PRs). "
            "Tick 349: ``docs/icml_open_git_pr.json`` keeps the body **inline** "
            "as ``open_git_pr_description`` (Tick 348 dropped it from JSON and "
            "left only a file pointer — agents skipped the read). "
            "Tick 350: also write ``docs/icml_open_git_pr_call.json`` with the "
            "exact MCP args ``{branch, title, description}`` — agents pass "
            "those three fields verbatim (avoids hunting inside the large "
            "hint JSON). "
            "Tick 352: call JSON also records ``cloud_boot_branch`` (the MCP "
            "default when ``branch=`` is omitted) so agents see the concrete "
            "greenfield vs tip mismatch; Cloud Agent 'correct working branch' "
            "does **not** override tip anti-churn."
        ),
        "open_git_pr_branch": branch,
        "tip_pr_commit_branch": branch,
        "tip_pr_number": pr.get("number"),
        "tip_pr_url": pr.get("url"),
        "tip_pr_title": tip_title or None,
        "tip_pr_title_tick": title_tick,
        "tip_pr_body_tick": body_tick,
        "local_tick": local_tick,
        "fetch_diamond_ok": fetch_diamond_ok,
        "tip_pr_title_stale": title_stale,
        "tip_pr_body_stale": body_stale,
        "suggested_open_git_pr_title": suggested,
        "tip_pr_body_file": body_file,
        "suggested_open_git_pr_body": suggested_body,
        # Tick 348: agents pass description= when body_stale.
        # Tick 349: also expose the body inline as open_git_pr_description.
        "open_git_pr_pass_description": bool(body_stale),
        "open_git_pr_description_file": body_file,
        "open_git_pr_description": suggested_body,
        "open_git_pr_call_file": ICML_OPEN_GIT_PR_CALL_RELPATH,
        "tip_pr_title_edit_commands": title_edit_cmds,
        "never_omit_branch": True,
        "cloud_boot_branch": None,  # filled in write_icml_open_git_pr_hint
        "omit_branch_opens_pr_on": None,
        "warning": (
            "NEVER call open_git_pr without branch= — omit defaults to the "
            f"greenfield boot branch and opens a new tip PR. Pass branch=`{branch}`. "
            "Tick 344: when tip_pr_title_stale, also pass "
            f"title=`{suggested}` (secrets-first when diamond blocked). "
            "Tick 348–349: when tip_pr_body_stale, also pass description= from "
            "`open_git_pr_description` in docs/icml_open_git_pr.json (or "
            f"`{ICML_TIP_PR_BODY_RELPATH}`) — MCP may still leave GitHub body "
            "frozen on existing PRs; still required call shape. "
            f"Tick 350: prefer `{ICML_OPEN_GIT_PR_CALL_RELPATH}` "
            "(branch/title/description verbatim). "
            "Tick 352: call JSON includes ``cloud_boot_branch`` / "
            "``omit_branch_opens_pr_on`` — Cloud Agent 'correct working branch' "
            "is the greenfield boot and does **not** override tip anti-churn. "
            "Tick 345–347: MCP may leave GitHub title/body unchanged — run "
            "`tip_pr_title_edit_commands` (`gh pr edit --title "
            f"[--body-file {ICML_TIP_PR_BODY_RELPATH}]`) to refresh; body "
            "staleness is independent of title (Tick 347)."
        ),
    }


def write_icml_open_git_pr_hint(
    path: Path | None = None,
    *,
    pr: dict | None = None,
    repo_root: Path | None = None,
    local_tick: int | None = None,
    fetch_diamond_ok: bool | None = None,
) -> dict | None:
    """Write ``docs/icml_open_git_pr.json`` (+ call JSON + tip PR body md; Tick 340/344–350)."""
    root = repo_root or _REPO_ROOT
    out = path or (root / "docs" / "icml_open_git_pr.json")
    call_path = root / ICML_OPEN_GIT_PR_CALL_RELPATH
    body_path = root / ICML_TIP_PR_BODY_RELPATH
    hint = build_icml_open_git_pr_hint(
        pr,
        repo_root=root,
        local_tick=local_tick,
        fetch_diamond_ok=fetch_diamond_ok,
    )
    if hint is None:
        for stale in (out, call_path, body_path):
            if stale.is_file():
                try:
                    stale.unlink()
                except OSError:
                    pass
        return None
    body_text = hint.get("suggested_open_git_pr_body") or hint.get(
        "open_git_pr_description"
    )
    # Tick 349: keep open_git_pr_description inline in JSON so agents can pass
    # description= without a second file read. Drop the duplicate internal key
    # suggested_open_git_pr_body (same string) to avoid double-storing in JSON;
    # the md file remains for gh --body-file paste.
    hint_for_json = {
        k: v for k, v in hint.items() if k != "suggested_open_git_pr_body"
    }
    if isinstance(body_text, str) and body_text.strip():
        hint_for_json["open_git_pr_description"] = body_text
    else:
        hint_for_json.pop("open_git_pr_description", None)
    out.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(body_text, str) and body_text.strip():
        body_path.parent.mkdir(parents=True, exist_ok=True)
        body_path.write_text(body_text, encoding="utf-8")
    else:
        if body_path.is_file():
            try:
                body_path.unlink()
            except OSError:
                pass
    # Tick 350: atomic MCP call payload — branch/title/description only.
    # Tick 352: also record cloud_boot_branch (MCP default when branch= omitted).
    branch = hint_for_json.get("open_git_pr_branch") or hint_for_json.get(
        "tip_pr_commit_branch"
    )
    title = hint_for_json.get("suggested_open_git_pr_title")
    desc = hint_for_json.get("open_git_pr_description")
    boot = detect_cloud_boot_branch(
        tip_commit_branch=str(branch) if branch else None,
        repo_root=root,
    )
    hint_for_json["cloud_boot_branch"] = boot
    hint_for_json["omit_branch_opens_pr_on"] = boot or "<greenfield-boot-branch>"
    if not isinstance(desc, str) or not desc.strip():
        tick = hint_for_json.get("local_tick") or 0
        desc = (
            f"ICML Tick {tick}: tip PR update on `{branch}` "
            "(see docs/ICML_PROGRESS.md). STATUS remains IN_PROGRESS."
        )
    if branch and title:
        note = (
            "Tick 350: pass these three fields verbatim to open_git_pr MCP "
            "(branch + title + description). Do not omit any. Prefer this "
            "file over hunting fields in docs/icml_open_git_pr.json."
        )
        if boot and boot != branch:
            note += (
                f" Tick 352–359: cloud_boot_branch=`{boot}` — omitting branch= "
                f"opens a NEW tip PR on that greenfield boot (not `{branch}`). "
                "Cloud Agent 'correct working branch' does NOT override tip "
                "anti-churn; always pass branch= from this file. "
                "Tick 353: cron exports ICML_CLOUD_BOOT_BRANCH before tip recover. "
                "Tick 354: ignores env==tip (false capture after tip checkout) + "
                f"persists `{ICML_CLOUD_BOOT_BRANCH_RELPATH}`. "
                "Tick 355: cron unsets env==tip and does not clobber the boot "
                "file with tip. Tick 356: boot file is gitignored + excluded "
                "from ephemeral discard (survives tip --apply). "
                "Tick 357: reject short/non-cursor/* boot poison; checkout "
                "script persists boot before tip switch. "
                "Tick 358: checkout also refreshes this call JSON so "
                "cloud_boot_branch matches the just-persisted boot (not a "
                "stale prior-tick value). "
                "Tick 359: this call JSON is gitignored + excluded from "
                "ephemeral discard so tip --apply cannot git-restore a stale "
                "committed boot name."
            )
        call_payload = {
            "updated_at": hint_for_json.get("updated_at"),
            "local_tick": hint_for_json.get("local_tick"),
            "tip_pr_number": hint_for_json.get("tip_pr_number"),
            "tip_pr_url": hint_for_json.get("tip_pr_url"),
            "note": note,
            "branch": branch,
            "title": title,
            "description": desc,
            "cloud_boot_branch": boot,
            "omit_branch_opens_pr_on": boot or "<greenfield-boot-branch>",
        }
        call_path.parent.mkdir(parents=True, exist_ok=True)
        call_path.write_text(
            json.dumps(call_payload, indent=2) + "\n", encoding="utf-8"
        )
        hint_for_json["open_git_pr_call_file"] = ICML_OPEN_GIT_PR_CALL_RELPATH
    out.write_text(json.dumps(hint_for_json, indent=2) + "\n", encoding="utf-8")
    return hint_for_json


def refresh_open_git_pr_after_tip_checkout(
    *,
    tip_commit_branch: str | None = None,
    repo_root: Path | None = None,
) -> dict | None:
    """Tick 358: after tip checkout (+ boot persist), rewrite open_git_pr call JSON.

    Tick 357 persisted the greenfield boot on checkout but left a *stale*
    ``docs/icml_open_git_pr_call.json`` from a prior cron (e.g.
    ``cloud_boot_branch`` still ``…-48b0`` while this boot is ``…-05af``).
    Mid-tick agents that only run ``icml_checkout_tip_pr_branch.sh`` (no full
    cron status rewrite) then read the wrong omit-branch warn. Refresh here
    so ``cloud_boot_branch`` matches the just-persisted boot file / env.
    """
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    tip = (tip_commit_branch or "").strip() or None
    pr: dict | None = None
    tip_status_path = root / "docs" / "icml_tip_status.json"
    if tip_status_path.is_file():
        try:
            d = json.loads(tip_status_path.read_text(encoding="utf-8"))
            if d.get("tip_pr_number") or d.get("tip_pr_url") or d.get(
                "tip_pr_head_ref"
            ):
                pr = {
                    "number": d.get("tip_pr_number"),
                    "url": d.get("tip_pr_url"),
                    "title": d.get("tip_pr_title"),
                    "body": d.get("tip_pr_body") or "",
                    "head_ref": d.get("tip_pr_head_ref")
                    or d.get("tip_pr_commit_branch")
                    or tip,
                    "mergeable": d.get("tip_pr_mergeable"),
                    "merge_state_status": d.get("tip_pr_merge_state_status"),
                    "is_draft": d.get("tip_pr_is_draft"),
                }
                tip = (
                    tip
                    or prefer_tip_pr_commit_branch(pr)
                    or (d.get("tip_pr_commit_branch") or None)
                )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pr = None
    if pr is None:
        try:
            pr = resolve_icml_tip_pr(tip_ref=tip, repo_root=root)
        except Exception:
            pr = None
    if pr is None and tip:
        # Minimal stub so call JSON still records branch + current boot.
        pr = {
            "number": None,
            "url": None,
            "title": None,
            "body": "",
            "head_ref": tip,
            "mergeable": "MERGEABLE",
            "merge_state_status": "CLEAN",
            "is_draft": True,
        }
    if pr is None:
        return None
    local_tick: int | None = None
    progress_path = root / "docs" / "ICML_PROGRESS.md"
    if progress_path.is_file():
        try:
            local_tick = parse_latest_icml_tick(
                progress_path.read_text(encoding="utf-8")
            )
        except OSError:
            local_tick = None
    fetch_ok: bool | None = None
    secrets_path = root / "docs" / "icml_secrets_status.json"
    if secrets_path.is_file():
        try:
            sec = json.loads(secrets_path.read_text(encoding="utf-8"))
            if "fetch_diamond_ok" in sec:
                fetch_ok = bool(sec.get("fetch_diamond_ok"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            fetch_ok = None
    return write_icml_open_git_pr_hint(
        repo_root=root,
        pr=pr,
        local_tick=local_tick,
        fetch_diamond_ok=fetch_ok,
    )


def _tip_pr_anti_churn_note(pr: dict) -> str:
    """Tick 337–352: push onto tip_pr_commit_branch; never omit open_git_pr branch=/title=/description=."""
    branch = prefer_tip_pr_commit_branch(pr)
    if not branch:
        return ""
    n = pr.get("number")
    boot = detect_cloud_boot_branch(tip_commit_branch=branch)
    boot_note = ""
    if boot and boot != branch:
        boot_note = (
            f" Tick 352: this run's cloud_boot_branch=`{boot}` — omitting "
            f"branch= opens a NEW tip PR on `{boot}` (not `{branch}`); "
            "Cloud Agent 'correct working branch' does NOT override tip "
            "anti-churn."
        )
    return (
        f" Agents/cron: do NOT open a new tip PR — checkout `{branch}` "
        f"(tip_pr_commit_branch; Tick 338–339 cron + tip recover --apply "
        f"auto-checkout via icml_cron_entry / icml_boot_recover / "
        f"icml_recover_tip) and push here so PR #{n} updates "
        "(bash scripts/icml_checkout_tip_pr_branch.sh; open_git_pr "
        f"branch=`{branch}` — Tick 340: NEVER omit branch=; open_git_pr "
        "defaults to the greenfield boot branch and would open a new tip PR; "
        "see docs/icml_open_git_pr.json; Tick 344: also pass "
        "title=`suggested_open_git_pr_title` from that JSON when "
        "tip_pr_title_stale — stale titles look superseded among 300+ drafts; "
        "secrets-first title when fetch_diamond_ok is false; Tick 348–349: also "
        "pass description= from `open_git_pr_description` in "
        f"`docs/icml_open_git_pr.json` (or `{ICML_TIP_PR_BODY_RELPATH}`) when "
        f"tip_pr_body_stale; Tick 350: prefer verbatim "
        f"`{ICML_OPEN_GIT_PR_CALL_RELPATH}` (branch/title/description); "
        "Tick 352: call JSON records ``cloud_boot_branch`` / "
        "``omit_branch_opens_pr_on``;"
        f"{boot_note} "
        "Tick 345–347: if GitHub title/body stays stale, "
        "copy-paste `tip_pr_title_edit_commands` "
        f"(`gh pr edit --title [--body-file {ICML_TIP_PR_BODY_RELPATH}]`) — "
        "open_git_pr MCP does not rewrite title or body)."
    )


def _tip_pr_merge_commands_note(pr: dict) -> str:
    """Tick 336–337: human_next suffix with gh copy-paste + anti-churn."""
    cmds = _tip_pr_merge_commands(pr)
    if not cmds:
        return ""
    paste = " && ".join(cmds)
    mergeable = str(pr.get("mergeable") or "").strip().upper()
    state = str(pr.get("merge_state_status") or "").strip().upper()
    anti = _tip_pr_anti_churn_note(pr)
    churn = (
        " Merge before next cron (~2h)."
        " Older tip PRs are superseded; merge "
        f"only #{pr['number']}."
    )
    if mergeable == "MERGEABLE" and state in {"", "CLEAN"}:
        return f" Copy-paste: `{paste}`.{anti}{churn}"
    if mergeable == "CONFLICTING" or state in {"DIRTY", "UNSTABLE"}:
        return (
            f" After rebase: `{paste}`."
            " Do not merge older superseded tip PRs."
        )
    return f" Copy-paste when ready: `{paste}`.{anti}{churn}"


def _merge_tip_to_main_human_next(pr: dict | None = None) -> str:
    """Tick 327–340: merge tip→main; URL; mergeability; gh; anti-churn."""
    base = (
        "Merge the latest ICML tip PR into `main` so cron inherits "
        "`docs/ICML_*` + `scripts/icml_cron_entry.sh` (Tick 327–340 dual "
        "unblock; `main` still has hackathon-era AGENTS without tip files). "
        "See `docs/ICML_HUMAN_UNBLOCK.md` Dual human unblock."
    )
    if not pr:
        # Lazy resolve when callers omit pr (pipeline Next / tests).
        pr = resolve_icml_tip_pr()
    if not pr:
        return base + " (tip PR URL unresolved — see open ICML tip PRs on GitHub)."
    merge_note = _tip_pr_mergeability_note(pr)
    if merge_note:
        # Tick 335: mergeability note already covers undraft-when-MERGEABLE.
        draft_note = ""
        if pr.get("is_draft") and "undraft" not in merge_note.lower():
            draft_note = " — undraft / mark Ready for review first"
    else:
        draft_note = (
            " — undraft / mark Ready for review first"
            if pr.get("is_draft")
            else ""
        )
    cmd_note = _tip_pr_merge_commands_note(pr)
    return (
        f"{base} Concrete tip PR: #{pr['number']} {pr['url']}"
        f"{merge_note}{draft_note}.{cmd_note}"
    )


def collect_icml_secrets_status() -> dict:
    """Presence-only secrets / diamond gate for live G2→G3→G4 (Tick 268/277/289).

    Does **not** include secret values. Portal Save is optional once Tick
    265–266 bootstraps succeed; live blockers are API keys + real GPQA
    (HF token **or** a local diamond CSV). Tick 289: Anthropic is required
    only when the ICML meta profile uses ``provider_id=anthropic``.

    Tick 328: also reports ``main_has_icml_tip`` and prepends merge-tip→main
    to ``human_next`` when ``main`` lacks tip files (does not affect
    ``fetch_diamond_ok``).
    """
    load_icml_dotenv()
    anthropic = _secret_present("ANTHROPIC_API_KEY")
    nebius = _secret_present("NEBIUS_API_KEY")
    hf = _secret_present("HF_TOKEN") or _secret_present("HUGGINGFACE_HUB_TOKEN")
    diamond_csv = resolve_diamond_csv_path()
    diamond_csv_ok = diamond_csv is not None
    meta_needs_anthropic = icml_meta_requires_anthropic()
    secrets_ok = bool(nebius) and (bool(anthropic) if meta_needs_anthropic else True)
    # HF needed for --fetch-diamond unless operator supplies CSV offline.
    fetch_diamond_ok = secrets_ok and (hf or diamond_csv_ok)
    # Tick 273/277: cron passes --fetch-diamond (optionally with --diamond-csv).
    cron_live_ok = fetch_diamond_ok
    blockers: list[str] = []
    if meta_needs_anthropic and not anthropic:
        blockers.append("ANTHROPIC_API_KEY missing")
    if not nebius:
        blockers.append("NEBIUS_API_KEY missing")
    if not hf and not diamond_csv_ok:
        blockers.append(
            "HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing "
            "(required for --fetch-diamond; or provide --diamond-csv / "
            "drop gpqa_diamond.csv at /tmp or docs/private/)"
        )
    main_has_tip = main_has_icml_tip_files()
    tip_pr = None if main_has_tip else resolve_icml_tip_pr()
    # Tick 342: surface interim AGENTS bootstrap PR when main still lacks tip.
    bootstrap_pr = None if main_has_tip else resolve_icml_agents_bootstrap_pr()
    human_keys = icml_human_required_secrets_phrase(for_fetch_diamond=True)
    # Tick 343: PRIMARY-first ordering — secrets unblock live G2→G4; tip/bootstrap
    # merge is hygiene (chicken-egg recover still works). When diamond is blocked,
    # lead with secrets; when secrets+HF/CSV are OK but main lacks tip, lead with
    # bootstrap/tip merge (unchanged from Tick 342).
    secrets_lines = [
        f"Add {human_keys} to automation "
        f"{_AUTOMATION_URL} (or linked env {_ENV_DASHBOARD_URL})",
        "Accept HuggingFace access for Idavidrein/gpqa with that HF token "
        "(or drop a real gpqa_diamond.csv at /tmp/gpqa_diamond.csv / "
        "docs/private/gpqa_diamond.csv / $ICML_DIAMOND_CSV to skip HF)",
    ]
    # Tick 345–347: title/body edit paste when tip PR metadata lags (MCP won't rewrite).
    progress_path = _REPO_ROOT / "docs" / "ICML_PROGRESS.md"
    local_tick: int | None = None
    if progress_path.is_file():
        try:
            local_tick = parse_latest_icml_tick(
                progress_path.read_text(encoding="utf-8")
            )
        except OSError:
            local_tick = None
    suggested_title = suggested_open_git_pr_title(
        local_tick=local_tick, fetch_diamond_ok=fetch_diamond_ok
    )
    tip_title_tick = parse_tick_from_pr_title((tip_pr or {}).get("title"))
    tip_body_tick = parse_tick_from_pr_body((tip_pr or {}).get("body"))
    tip_title_stale = bool(
        tip_pr is not None
        and local_tick is not None
        and (tip_title_tick is None or tip_title_tick < local_tick)
    )
    tip_body_stale = bool(
        tip_pr is not None
        and local_tick is not None
        and (tip_body_tick is None or tip_body_tick < local_tick)
    )
    body_file = ICML_TIP_PR_BODY_RELPATH if tip_body_stale else None
    title_edit_cmds = (
        _tip_pr_title_edit_commands(
            tip_pr,
            suggested_title,
            body_file=body_file,
            include_title=tip_title_stale,
        )
        if (tip_title_stale or tip_body_stale)
        else []
    )
    title_edit_line = _tip_pr_title_edit_human_next(
        tip_pr,
        suggested_title=suggested_title,
        title_stale=tip_title_stale,
        body_file=body_file,
        body_stale=tip_body_stale,
    )
    merge_lines: list[str] = []
    if not main_has_tip:
        # Bootstrap first (1-file, easier) then full tip merge.
        if bootstrap_pr is not None:
            merge_lines.append(_merge_agents_bootstrap_human_next(bootstrap_pr))
        merge_lines.append(_merge_tip_to_main_human_next(tip_pr))
    # Title refresh advertises secrets ask in the tip PR list — after secrets,
    # before merge hygiene when diamond is blocked.
    title_lines = [title_edit_line] if title_edit_line else []
    tail_lines = [
        "Next cron (or now): `bash scripts/icml_cron_entry.sh` "
        "(Tick 271–352 — recovers tip incl. cursor/bc-* lineage; auto-live "
        "only when fetch_diamond_ok; blocked paths print full human_next + "
        "concrete tip PR URL + Tick 335 mergeability + Tick 336 gh "
        "copy-paste merge commands + Tick 337–339 tip PR anti-churn "
        "(tip_pr_commit_branch; cron + tip recover --apply auto-checkout) + "
        "Tick 340 open_git_pr never-omit-branch (docs/icml_open_git_pr.json) + "
        "Tick 342 AGENTS bootstrap PR in human_next/JSON + "
        "Tick 343 PRIMARY-first human_next (secrets before tip/bootstrap when "
        "fetch_diamond_ok is false) + "
        "Tick 344 secrets-first suggested_open_git_pr_title when "
        "tip_pr_title_stale + "
        "Tick 345 tip_pr_title_edit_commands (`gh pr edit --title`) when MCP "
        "leaves GitHub title stale + "
        "Tick 346 tip PR body-file refresh (`--body-file "
        f"{ICML_TIP_PR_BODY_RELPATH}`) when MCP leaves GitHub body stale + "
        "Tick 347 tip_pr_body_stale independent of title_stale "
        "(body-only paste after title-only edit) + "
        "Tick 348–349 open_git_pr also pass description= from "
        "`open_git_pr_description` in docs/icml_open_git_pr.json "
        f"(or `{ICML_TIP_PR_BODY_RELPATH}`) when tip_pr_body_stale; "
        f"Tick 350 prefer `{ICML_OPEN_GIT_PR_CALL_RELPATH}` "
        "(branch/title/description verbatim); "
        "Tick 352 call JSON records ``cloud_boot_branch`` / "
        "``omit_branch_opens_pr_on`` (MCP default when branch= omitted; "
        "Cloud Agent 'correct working branch' does NOT override tip "
        "anti-churn); "
        "Tick 333 same-SHA "
        "sibling tip PR fallback; Tick 334 HEAD/local SHA fallback for "
        "unpushed greenfield tip_ref; Tick 332 HUMAN_UNBLOCK chicken-egg "
        "also scans cursor/bc-*)",
        "Portal Save of docs/icml_portal_save_target.json is optional "
        "(warm boots only; packages bootstrap without it)",
    ]
    human_next: list[str] = []
    tip_commit_branch = prefer_tip_pr_commit_branch(tip_pr)
    boot_branch = detect_cloud_boot_branch(tip_commit_branch=tip_commit_branch)
    boot_lines: list[str] = []
    if (
        tip_commit_branch
        and boot_branch
        and boot_branch != tip_commit_branch
    ):
        boot_lines.append(
            f"Cloud boot branch `{boot_branch}` ≠ tip `{tip_commit_branch}` "
            "(Tick 352). open_git_pr MUST pass "
            f"branch=`{tip_commit_branch}` from "
            f"`{ICML_OPEN_GIT_PR_CALL_RELPATH}` — omitting branch= opens a "
            f"NEW tip PR on `{boot_branch}`. Cloud Agent 'correct working "
            "branch' is the greenfield boot and does **not** override tip "
            "anti-churn."
        )
    if not fetch_diamond_ok:
        human_next.extend(secrets_lines)
        human_next.extend(boot_lines)
        human_next.extend(title_lines)
        human_next.extend(merge_lines)
    else:
        human_next.extend(merge_lines)
        human_next.extend(boot_lines)
        human_next.extend(title_lines)
        human_next.extend(secrets_lines)
    human_next.extend(tail_lines)
    return {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tick_note": (
            "Tick 268/273/277/289/292/328/329/330/331/332/333/334/335/336/337/338/339/340/341/342/343/344/345: secrets-first live gate; Portal Save "
            "optional; cron auto-live requires fetch_diamond_ok (NEBIUS + HF/CSV; "
            "ANTHROPIC only when meta provider is anthropic); "
            "human-facing cron/gate Next lines use "
            "icml_human_required_secrets_phrase; "
            ".env loaded for missing secret names; "
            "human_next prefers bash scripts/icml_cron_entry.sh; "
            "Tick 328 dual unblock also surfaces merge tip→main when "
            "main_has_icml_tip is false; Tick 329 cron prints full human_next "
            "on --preflight-only / auto / live-refuse; Tick 330 adds concrete "
            "tip PR URL (+ draft undraft note) via resolve_icml_tip_pr; "
            "Tick 331 tip lineage also scans cursor/bc-* cloud cron branches; "
            "Tick 332 HUMAN_UNBLOCK chicken-egg (+ script headers) also fetch/scan bc-*; "
            "Tick 333 same-SHA sibling tip PR fallback when tip head has no PR yet; "
            "Tick 334 HEAD/local SHA fallback when tip_ref remote is unpushed; "
            "Tick 335 tip PR mergeability (MERGEABLE/CLEAN) in human_next + JSON; "
            "Tick 336 tip PR gh copy-paste merge commands + churn warning; "
            "Tick 337 tip PR anti-churn (prefer_tip_pr_commit_branch / tip_pr_commit_branch); "
            "Tick 338 cron auto-checkout tip_pr_commit_branch after status write; "
            "Tick 339 tip recover --apply also auto-checkouts tip_pr_commit_branch "
            "(boot_recover + recover_tip; closes chicken-egg-only path); "
            "Tick 340 open_git_pr never-omit-branch (docs/icml_open_git_pr.json; "
            "MCP defaults to greenfield boot branch when branch= omitted); "
            "Tick 342 human_next/JSON surface AGENTS bootstrap PR "
            f"(`{ICML_AGENTS_BOOTSTRAP_BRANCH}`) when open; "
            "Tick 343 PRIMARY-first human_next — secrets before tip/bootstrap "
            "merge when fetch_diamond_ok is false (tip merge does not gate live); "
            "Tick 344 secrets-first suggested_open_git_pr_title when "
            "tip_pr_title_stale (stale tip PR titles look superseded); "
            "Tick 345 tip_pr_title_edit_commands (`gh pr edit --title`) when "
            "open_git_pr MCP leaves GitHub title unchanged; "
            "Tick 346 tip PR body-file refresh (`--body-file "
            f"{ICML_TIP_PR_BODY_RELPATH}`) when MCP leaves GitHub body frozen; "
            "Tick 347 tip_pr_body_stale independent of tip_pr_title_stale "
            "(gh fetches body; body-only paste after title-only edit); "
            "Tick 348–349 open_git_pr also pass description= from "
            "`open_git_pr_description` in docs/icml_open_git_pr.json "
            f"(or `{ICML_TIP_PR_BODY_RELPATH}`) when tip_pr_body_stale; "
            f"Tick 350 prefer `{ICML_OPEN_GIT_PR_CALL_RELPATH}` "
            "(branch/title/description verbatim); "
            "Tick 352 call JSON / secrets JSON record ``cloud_boot_branch`` "
            "(MCP default when branch= omitted; Cloud Agent 'correct working "
            "branch' does not override tip anti-churn)"
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
        "meta_requires_anthropic": meta_needs_anthropic,
        "meta_agent_profile": resolve_icml_meta_agent_profile(),
        "packages_bootstrapped_in_preflight": True,
        "portal_save_required_for_live": False,
        "secrets_ok_for_paid_sia": secrets_ok,
        "fetch_diamond_ok": fetch_diamond_ok,
        "cron_live_ok": cron_live_ok,
        "ready_for_live_pipeline": False,  # diamond + keys both required; caller may override
        # Tick 328: operational dual-unblock (does not gate fetch_diamond_ok).
        "main_has_icml_tip": main_has_tip,
        # Tick 330: concrete tip PR for operators (null when main already has tip).
        "tip_pr_url": (tip_pr or {}).get("url"),
        "tip_pr_number": (tip_pr or {}).get("number"),
        "tip_pr_title": (tip_pr or {}).get("title"),
        # Tick 347: keep body so open_git_pr hint rewrites stay body-stale-aware.
        "tip_pr_body": (tip_pr or {}).get("body"),
        "tip_pr_is_draft": (tip_pr or {}).get("is_draft"),
        "tip_pr_head_ref": (tip_pr or {}).get("head_ref"),
        # Tick 335: mergeability so operators know CLEAN vs CONFLICTING.
        "tip_pr_mergeable": (tip_pr or {}).get("mergeable"),
        "tip_pr_merge_state_status": (tip_pr or {}).get("merge_state_status"),
        # Tick 336: copy-paste gh undraft+merge (null/[] when main has tip).
        "tip_pr_merge_commands": _tip_pr_merge_commands(tip_pr),
        # Tick 345–347: copy-paste gh pr edit --title [--body-file] when MCP
        # leaves title/body stale (body staleness independent as of Tick 347).
        "tip_pr_title_stale": tip_title_stale,
        "tip_pr_body_stale": tip_body_stale,
        "tip_pr_title_tick": tip_title_tick,
        "tip_pr_body_tick": tip_body_tick,
        "suggested_open_git_pr_title": suggested_title,
        "tip_pr_body_file": body_file,
        "tip_pr_title_edit_commands": title_edit_cmds,
        "local_tick": local_tick,
        # Tick 337: anti-churn — commit onto this branch (null when not MERGEABLE).
        # Tick 338: cron_entry auto-checkouts this branch after status write.
        # Tick 340: open_git_pr must pass branch= this value (never omit).
        "tip_pr_commit_branch": tip_commit_branch,
        "tip_pr_anti_churn": tip_commit_branch is not None,
        "open_git_pr_branch": tip_commit_branch,
        "open_git_pr_never_omit_branch": tip_commit_branch is not None,
        # Tick 352: concrete greenfield boot branch MCP defaults to if branch= omitted.
        "cloud_boot_branch": boot_branch,
        "omit_branch_opens_pr_on": boot_branch
        or ("<greenfield-boot-branch>" if tip_commit_branch else None),
        # Tick 342: interim AGENTS bootstrap PR (null when merged / main has tip).
        "agents_bootstrap_branch": ICML_AGENTS_BOOTSTRAP_BRANCH,
        "agents_bootstrap_pr_url": (bootstrap_pr or {}).get("url"),
        "agents_bootstrap_pr_number": (bootstrap_pr or {}).get("number"),
        "agents_bootstrap_pr_is_draft": (bootstrap_pr or {}).get("is_draft"),
        "agents_bootstrap_pr_mergeable": (bootstrap_pr or {}).get("mergeable"),
        "agents_bootstrap_pr_merge_state_status": (bootstrap_pr or {}).get(
            "merge_state_status"
        ),
        "agents_bootstrap_merge_commands": _tip_pr_merge_commands(bootstrap_pr),
        "blockers": blockers,
        "human_next": human_next,
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
    # Tick 340: mirror open_git_pr anti-churn hint beside secrets/tip status.
    tip_pr = None
    if status.get("tip_pr_number") or status.get("tip_pr_url"):
        tip_pr = {
            "number": status.get("tip_pr_number"),
            "url": status.get("tip_pr_url"),
            "title": status.get("tip_pr_title"),
            "body": status.get("tip_pr_body") or "",
            "head_ref": status.get("tip_pr_head_ref")
            or status.get("tip_pr_commit_branch"),
            "mergeable": status.get("tip_pr_mergeable"),
            "merge_state_status": status.get("tip_pr_merge_state_status"),
            "is_draft": status.get("tip_pr_is_draft"),
        }
    hint = write_icml_open_git_pr_hint(
        pr=tip_pr if status.get("open_git_pr_branch") else None,
        fetch_diamond_ok=bool(status.get("fetch_diamond_ok")),
    )
    if hint:
        status["tip_pr_title"] = hint.get("tip_pr_title")
        status["tip_pr_title_tick"] = hint.get("tip_pr_title_tick")
        status["tip_pr_body_tick"] = hint.get("tip_pr_body_tick")
        status["tip_pr_title_stale"] = hint.get("tip_pr_title_stale")
        status["tip_pr_body_stale"] = hint.get("tip_pr_body_stale")
        status["suggested_open_git_pr_title"] = hint.get(
            "suggested_open_git_pr_title"
        )
        status["tip_pr_title_edit_commands"] = hint.get(
            "tip_pr_title_edit_commands"
        ) or []
        status["tip_pr_body_file"] = hint.get("tip_pr_body_file")
        status["open_git_pr_pass_description"] = hint.get(
            "open_git_pr_pass_description"
        )
        status["open_git_pr_description_file"] = hint.get(
            "open_git_pr_description_file"
        )
        status["open_git_pr_description"] = hint.get("open_git_pr_description")
        status["local_tick"] = hint.get("local_tick")
        out.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    return status


def live_pipeline_next_steps(
    *,
    secrets_ok: bool,
    tip_ok: bool | None = None,
    tip_ref: str | None = None,
    fetch_diamond_ok: bool | None = None,
    main_has_icml_tip: bool | None = None,
) -> list[str]:
    """Human-facing Next bullets — tip + secrets + HF + cron entry (Tick 268–274/328).

    Tick 274: do **not** claim live-ready on Anthropic+Nebius alone — cron and
    ``--live --fetch-diamond`` also need ``HF_TOKEN`` (``fetch_diamond_ok``).
    Tick 328: when ``main`` lacks tip files, prepend merge tip→main (dual unblock).
    """
    steps: list[str] = []
    if main_has_icml_tip is None:
        main_has_icml_tip = main_has_icml_tip_files()
    merge_steps: list[str] = []
    if main_has_icml_tip is False:
        tip_pr = resolve_icml_tip_pr(tip_ref=tip_ref)
        bootstrap_pr = resolve_icml_agents_bootstrap_pr()
        if bootstrap_pr is not None:
            merge_steps.append(_merge_agents_bootstrap_human_next(bootstrap_pr))
        merge_steps.append(_merge_tip_to_main_human_next(tip_pr))
    tip_stale_steps: list[str] = []
    if tip_ok is False:
        ref = tip_ref or "origin/cursor/icml-epistemic-results-<tip>"
        tip_stale_steps.append(
            "Stale / missing ICML tip — prefer single entry: "
            "`bash scripts/icml_cron_entry.sh` (Tick 271; recovers tip then "
            "live/preflight). Or: `python3 scripts/icml_recover_tip.py --apply` "
            f"(expected tip ≈ `{ref}`). Main boot without tip scripts: "
            f"`git show {ref}:scripts/icml_cron_entry.sh | bash -s --`. "
            "See `docs/icml_tip_status.json`."
        )

    # Explicit False → HF/CSV gap even when API keys present.
    if fetch_diamond_ok is False and secrets_ok:
        # Tick 343: PRIMARY-first — diamond/HF gap before tip merge hygiene.
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
        steps.extend(merge_steps)
        steps.extend(tip_stale_steps)
        return steps

    # True → full cron live OK. None + secrets_ok → legacy callers (pre-Tick-274).
    if fetch_diamond_ok is True or (fetch_diamond_ok is None and secrets_ok):
        label = (
            "Cron live OK (`fetch_diamond_ok`)"
            if fetch_diamond_ok is True
            else "Secrets present"
        )
        # Secrets OK: tip/bootstrap merge hygiene can lead (Tick 342).
        steps.extend(merge_steps)
        steps.extend(tip_stale_steps)
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

    # Tick 343: secrets missing → PRIMARY-first (secrets before tip/bootstrap).
    steps.extend(
        [
            "Add `NEBIUS_API_KEY` + (`HF_TOKEN` **or** local `gpqa_diamond.csv`) "
            "to automation "
            f"{_AUTOMATION_URL} (or linked env dashboard). "
            "`ANTHROPIC_API_KEY` is optional with Tick 289 Nebius pydantic-ai meta "
            "(required only if `ICML_META_AGENT_PROFILE=default-meta`). "
            "Accept HF `Idavidrein/gpqa` if using HF. See `docs/ICML_HUMAN_UNBLOCK.md`.",
            "Next cron (or now): `bash scripts/icml_cron_entry.sh` — auto-recovers "
            "tip and runs live when `fetch_diamond_ok` (else preflight only).",
            "Portal Save of `docs/icml_portal_save_target.json` is **optional** "
            "(Tick 265–267: uv + runtime deps bootstrap in preflight).",
            "Do **not** set STATUS: READY from offline / preflight alone.",
        ]
    )
    steps.extend(merge_steps)
    steps.extend(tip_stale_steps)
    return steps


# --- Tick 269: ICML tip lineage (cron boots often start from main) -----------------

_TICK_HEADING_RE = re.compile(
    r"^##\s+.+\bTick\s+(\d+)\b",
    re.MULTILINE | re.IGNORECASE,
)
_TIP_REF_PREFIXES = (
    "refs/remotes/origin/cursor/icml-epistemic-results-",
    "refs/remotes/origin/cursor/icml-epistemic-evolution-",
    # Tick 331: cloud automation cron now boots on cursor/bc-<uuid>-<hash>
    # branches (not only icml-epistemic-results-*). Include them when they
    # carry ICML_PROGRESS (filtered below) so tip lineage does not stall at
    # the last results-* tip while newer work lives only on bc-* PRs.
    "refs/remotes/origin/cursor/bc-",
)
_TIP_FETCH_REFSPECS = (
    "+refs/heads/cursor/icml-epistemic-results-*"
    ":refs/remotes/origin/cursor/icml-epistemic-results-*",
    "+refs/heads/cursor/icml-epistemic-evolution-*"
    ":refs/remotes/origin/cursor/icml-epistemic-evolution-*",
    "+refs/heads/cursor/bc-*"
    ":refs/remotes/origin/cursor/bc-*",
)
_TIP_FOR_EACH_REF_PATTERNS = (
    "refs/remotes/origin/cursor/icml-epistemic-results-*",
    "refs/remotes/origin/cursor/icml-epistemic-evolution-*",
    "refs/remotes/origin/cursor/bc-*",
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
            ["fetch", "origin", *_TIP_FETCH_REFSPECS],
            cwd=root,
        )
        notes.append(f"fetch={'ok' if ok else 'fail'}: {detail[:200]}")

    ok, refs_out = _git_ok(
        [
            "for-each-ref",
            "--format=%(refname)\t%(committerdate:unix)\t%(objectname:short)",
            *_TIP_FOR_EACH_REF_PATTERNS,
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

    main_has_tip = main_has_icml_tip_files(repo_root=root)
    tip_pr = None if main_has_tip else resolve_icml_tip_pr(tip_ref=tip_ref, repo_root=root)
    tip_commit_branch = prefer_tip_pr_commit_branch(tip_pr)
    boot_branch = detect_cloud_boot_branch(
        tip_commit_branch=tip_commit_branch, repo_root=root
    )
    bootstrap_pr = (
        None if main_has_tip else resolve_icml_agents_bootstrap_pr(repo_root=root)
    )

    return {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tick_note": (
            "Tick 269–270/328/330/331/332/333/334/335/336/337/338/339/340/342/343/344/345: tip lineage guard — cron often boots from "
            "main; refuse --live on stale trees; recover via "
            "scripts/icml_recover_tip.py or scripts/icml_boot_recover.sh; "
            "Tick 328 reports main_has_icml_tip (merge tip→main dual unblock); "
            "Tick 330 resolves concrete tip_pr_url via gh; "
            "Tick 331 also scans cursor/bc-* cloud cron branches as tip candidates; "
            "Tick 332 HUMAN_UNBLOCK chicken-egg (+ script headers) also fetch/scan bc-*; "
            "Tick 333 same-SHA sibling tip PR fallback when tip head has no PR yet; "
            "Tick 334 HEAD/local SHA fallback when tip_ref remote is unpushed; "
            "Tick 335 tip PR mergeability (MERGEABLE/CLEAN) in human_next + JSON; "
            "Tick 336 tip PR gh copy-paste merge commands + churn warning; "
            "Tick 337 tip PR anti-churn (prefer_tip_pr_commit_branch / tip_pr_commit_branch); "
            "Tick 338 cron auto-checkout tip_pr_commit_branch after status write; "
            "Tick 339 tip recover --apply also auto-checkouts tip_pr_commit_branch "
            "(boot_recover + recover_tip); "
            "Tick 340 open_git_pr never-omit-branch (docs/icml_open_git_pr.json); "
            "Tick 342 agents_bootstrap_pr_* fields when AGENTS bootstrap PR is open; "
            "Tick 343 secrets status human_next is PRIMARY-first when "
            "fetch_diamond_ok is false (see collect_icml_secrets_status); "
            "Tick 344 secrets-first suggested_open_git_pr_title when tip_pr_title_stale; "
            "Tick 345 tip_pr_title_edit_commands (`gh pr edit --title`) when MCP "
            "leaves GitHub title unchanged; "
            "Tick 346 tip PR body-file refresh (`--body-file "
            f"{ICML_TIP_PR_BODY_RELPATH}`) when MCP leaves GitHub body frozen; "
            "Tick 347 tip_pr_body_stale independent of tip_pr_title_stale; "
            "Tick 348–349 open_git_pr also pass description= from "
            "`open_git_pr_description` in docs/icml_open_git_pr.json "
            f"(or `{ICML_TIP_PR_BODY_RELPATH}`) when tip_pr_body_stale; "
            f"Tick 350 prefer `{ICML_OPEN_GIT_PR_CALL_RELPATH}` "
            "(branch/title/description verbatim); "
            "Tick 352 cloud_boot_branch / omit_branch_opens_pr_on "
            "(MCP default when branch= omitted)"
        ),
        "local_tick": local_tick,
        "remote_tip_tick": remote_tick,
        "remote_tip_ref": tip_ref,
        "remote_tip_sha": tip["sha"] if tip else None,
        "remote_tip_lineage_score": tip["lineage_score"] if tip else None,
        "tip_ok_for_live": tip_ok,
        # Tick 328: advisory — tip recover still works; prefer merge tip→main.
        "main_has_icml_tip": main_has_tip,
        # Tick 330: concrete PR for operators facing 300+ draft tip PRs.
        "tip_pr_url": (tip_pr or {}).get("url"),
        "tip_pr_number": (tip_pr or {}).get("number"),
        "tip_pr_title": (tip_pr or {}).get("title"),
        # Tick 347: keep body for independent tip_pr_body_stale on hint rewrite.
        "tip_pr_body": (tip_pr or {}).get("body"),
        "tip_pr_is_draft": (tip_pr or {}).get("is_draft"),
        "tip_pr_head_ref": (tip_pr or {}).get("head_ref"),
        # Tick 335: mergeability so operators know CLEAN vs CONFLICTING.
        "tip_pr_mergeable": (tip_pr or {}).get("mergeable"),
        "tip_pr_merge_state_status": (tip_pr or {}).get("merge_state_status"),
        # Tick 336: copy-paste gh undraft+merge (null/[] when main has tip).
        "tip_pr_merge_commands": _tip_pr_merge_commands(tip_pr),
        # Tick 337: anti-churn — commit onto this branch (null when not MERGEABLE).
        # Tick 338: cron_entry auto-checkouts this branch after status write.
        # Tick 340: open_git_pr must pass branch= this value (never omit).
        "tip_pr_commit_branch": tip_commit_branch,
        "tip_pr_anti_churn": tip_commit_branch is not None,
        "open_git_pr_branch": tip_commit_branch,
        "open_git_pr_never_omit_branch": tip_commit_branch is not None,
        # Tick 352: concrete greenfield boot branch MCP defaults to if branch= omitted.
        "cloud_boot_branch": boot_branch,
        "omit_branch_opens_pr_on": boot_branch
        or ("<greenfield-boot-branch>" if tip_commit_branch else None),
        # Tick 342: interim AGENTS bootstrap PR (null when merged / main has tip).
        "agents_bootstrap_branch": ICML_AGENTS_BOOTSTRAP_BRANCH,
        "agents_bootstrap_pr_url": (bootstrap_pr or {}).get("url"),
        "agents_bootstrap_pr_number": (bootstrap_pr or {}).get("number"),
        "agents_bootstrap_pr_is_draft": (bootstrap_pr or {}).get("is_draft"),
        "agents_bootstrap_pr_mergeable": (bootstrap_pr or {}).get("mergeable"),
        "agents_bootstrap_pr_merge_state_status": (bootstrap_pr or {}).get(
            "merge_state_status"
        ),
        "agents_bootstrap_merge_commands": _tip_pr_merge_commands(bootstrap_pr),
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
    # Tick 340: keep open_git_pr hint in sync with tip status.
    tip_pr = None
    if status.get("open_git_pr_branch"):
        tip_pr = {
            "number": status.get("tip_pr_number"),
            "url": status.get("tip_pr_url"),
            "title": status.get("tip_pr_title"),
            # Tick 347: preserve body so tip_pr_body_stale stays accurate when
            # re-writing the open_git_pr hint from tip status.
            "body": status.get("tip_pr_body") or "",
            "head_ref": status.get("tip_pr_head_ref")
            or status.get("tip_pr_commit_branch"),
            "mergeable": status.get("tip_pr_mergeable"),
            "merge_state_status": status.get("tip_pr_merge_state_status"),
            "is_draft": status.get("tip_pr_is_draft"),
        }
    hint = write_icml_open_git_pr_hint(
        pr=tip_pr,
        repo_root=root,
        local_tick=status.get("local_tick"),
    )
    if hint:
        status["tip_pr_title"] = hint.get("tip_pr_title")
        status["tip_pr_title_tick"] = hint.get("tip_pr_title_tick")
        status["tip_pr_body_tick"] = hint.get("tip_pr_body_tick")
        status["tip_pr_title_stale"] = hint.get("tip_pr_title_stale")
        status["tip_pr_body_stale"] = hint.get("tip_pr_body_stale")
        status["suggested_open_git_pr_title"] = hint.get(
            "suggested_open_git_pr_title"
        )
        status["tip_pr_title_edit_commands"] = hint.get(
            "tip_pr_title_edit_commands"
        ) or []
        status["tip_pr_body_file"] = hint.get("tip_pr_body_file")
        status["open_git_pr_pass_description"] = hint.get(
            "open_git_pr_pass_description"
        )
        status["open_git_pr_description_file"] = hint.get(
            "open_git_pr_description_file"
        )
        status["open_git_pr_description"] = hint.get("open_git_pr_description")
        out.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    return status


# --- Tick 298: committed gate-recipe ↔ live-shape lock -----------------------------
# Tick 297 failure mode: code defaults moved to pop4×eval5×max_gen6 while committed
# gate3/4/pipeline reports + Section 21.7 still advertised collapsed pop3 recipes.
# These helpers lock operator-facing artifacts to ``icml_g3g4_live_shape()``.

_SHAPE_FLAG_KEYS = (
    ("--population_size", "population_size"),
    ("--elite_count", "elite_count"),
    ("--max_gen", "max_gen"),
    ("--eval_subset", "eval_subset"),
)


def extract_sia_shape_flags(argv: Sequence[str] | list[str]) -> dict[str, int] | None:
    """Parse ``--population_size`` / ``--elite_count`` / ``--max_gen`` / ``--eval_subset``.

    Returns ``None`` when the argv is not a Darwinian ``sia run`` (or is G2-shaped
    smoke with pop≤2). Used to ignore non-G3/G4 examples in mixed docs.
    """
    args = [str(a) for a in argv]
    if "sia" not in args or "run" not in args:
        return None
    if "--darwinian" not in args:
        return None
    out: dict[str, int] = {}
    for flag, key in _SHAPE_FLAG_KEYS:
        if flag not in args:
            return None
        idx = args.index(flag)
        if idx + 1 >= len(args):
            return None
        try:
            out[key] = int(args[idx + 1])
        except ValueError:
            return None
    # G2 smoke is intentionally smaller; only lock G3/G4-scale recipes.
    if out.get("population_size", 0) < 3 or out.get("max_gen", 0) < 3:
        return None
    return out


def _argv_from_shell_line(line: str) -> list[str]:
    """Best-effort tokenize a single ``sia run …`` shell line (no pipes/redirs)."""
    # Strip leading list markers / numbering from markdown report lines.
    cleaned = re.sub(r"^\s*\d+\.\s*", "", line.strip())
    cleaned = cleaned.strip("`")
    if "sia" not in cleaned:
        return []
    # Keep from first ``sia`` token onward (drop python -m wrapper path noise).
    parts = cleaned.split()
    try:
        start = parts.index("sia")
    except ValueError:
        return []
    return parts[start:]


def iter_shape_flag_dicts_from_text(text: str) -> list[dict[str, int]]:
    """Extract G3/G4-scale Darwinian shape dicts from free text / markdown."""
    found: list[dict[str, int]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        if "sia" not in raw or "--population_size" not in raw:
            i += 1
            continue
        # Join shell continuation lines ending with ``\``.
        chunk = raw.rstrip()
        while chunk.endswith("\\") and i + 1 < len(lines):
            chunk = chunk[:-1].rstrip() + " " + lines[i + 1].strip()
            i += 1
            chunk = chunk.rstrip()
        argv = _argv_from_shell_line(chunk.replace("\\", " "))
        shape = extract_sia_shape_flags(argv)
        if shape is not None:
            found.append(shape)
        i += 1
    return found


def iter_shape_flag_dicts_from_commands(
    commands: Sequence[Sequence[str]] | None,
) -> list[dict[str, int]]:
    """Extract G3/G4-scale shapes from gate-report JSON ``commands`` arrays."""
    found: list[dict[str, int]] = []
    if not commands:
        return found
    for cmd in commands:
        shape = extract_sia_shape_flags(list(cmd))
        if shape is not None:
            found.append(shape)
    return found


def committed_g3g4_recipes_match_live_shape(
    *,
    repo_root: Path | None = None,
    profile: str | None = None,
) -> tuple[bool, list[str]]:
    """Return whether committed gate/Section-21.7 recipes match live G3/G4 shape.

    Tick 298: locks ``docs/gate3_report.json``, ``docs/gate4_report.json``,
    ``docs/icml_live_pipeline_report.md`` note, and Section 21.7 Condition B/D
    examples so a future shape change cannot ship with stale operator recipes.
    """
    root = repo_root or _REPO_ROOT
    expected = icml_g3g4_live_shape(profile)
    problems: list[str] = []

    for rel in ("docs/gate3_report.json", "docs/gate4_report.json"):
        path = root / rel
        if not path.is_file():
            problems.append(f"missing {rel}")
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{rel}: {exc}")
            continue
        shapes = iter_shape_flag_dicts_from_commands(payload.get("commands"))
        if not shapes:
            problems.append(f"{rel}: no G3/G4-scale sia run commands to check")
            continue
        for i, got in enumerate(shapes):
            if got != expected:
                problems.append(
                    f"{rel} commands[{i}] shape {got} != live {expected}"
                )

    pipeline_md = root / "docs" / "icml_live_pipeline_report.md"
    if pipeline_md.is_file():
        text = pipeline_md.read_text(encoding="utf-8")
        note_re = re.compile(
            r"eval_subset\s*=\s*(\d+)\s+pop\s*=\s*(\d+)\s+"
            r"elite\s*=\s*(\d+)\s+max_gen\s*=\s*(\d+)",
            re.IGNORECASE,
        )
        match = note_re.search(text)
        if match is None:
            problems.append(
                "docs/icml_live_pipeline_report.md: missing Tick-shape note "
                "(eval_subset=… pop=… elite=… max_gen=…)"
            )
        else:
            got = {
                "eval_subset": int(match.group(1)),
                "population_size": int(match.group(2)),
                "elite_count": int(match.group(3)),
                "max_gen": int(match.group(4)),
            }
            if got != expected:
                problems.append(
                    f"docs/icml_live_pipeline_report.md shape note {got} "
                    f"!= live {expected}"
                )
    else:
        problems.append("missing docs/icml_live_pipeline_report.md")

    master = root / "docs" / "HACKATHON_MASTER_PLAN.md"
    if master.is_file():
        text = master.read_text(encoding="utf-8")
        # Only the Section 21.7 Condition B/D examples (not historical chronicle).
        sec = text
        marker = "### 21.7 Suggested cheap GPQA commands"
        if marker in text:
            sec = text.split(marker, 1)[1].split("### 21.8", 1)[0]
        shapes = iter_shape_flag_dicts_from_text(sec)
        if len(shapes) < 2:
            problems.append(
                "Section 21.7: expected ≥2 G3/G4-scale Condition B/D sia run "
                f"examples; found {len(shapes)}"
            )
        for i, got in enumerate(shapes):
            if got != expected:
                problems.append(
                    f"Section 21.7 G3/G4 example[{i}] shape {got} != live {expected}"
                )
    else:
        problems.append("missing docs/HACKATHON_MASTER_PLAN.md")

    return (len(problems) == 0, problems)


# --- Tick 300: committed offline Bvd summary ↔ live-shape lock ---------------------
# Tick 23 artifacts used eval_subset=3 while live G3/G4 is eval5 (same pop4×max_gen6).
# Paper/gate offline tables must advertise the shape we will spend $20 on.


def _offline_id_range_strings(ids: Sequence[int]) -> list[str]:
    """Human-facing ID range spellings (en-dash / hyphen, bare / backticked)."""
    nums = [int(x) for x in ids]
    if not nums:
        return []
    lo, hi = min(nums), max(nums)
    if lo == hi:
        bare = [str(lo)]
    else:
        bare = [f"{lo}–{hi}", f"{lo}-{hi}"]
    out: list[str] = []
    for b in bare:
        out.append(b)
        out.append(f"`{b}`")
    return out


def _text_cites_any(text: str, variants: Sequence[str]) -> bool:
    return any(v and v in text for v in variants)


def committed_offline_bvd_matches_live_shape(
    *,
    repo_root: Path | None = None,
    profile: str | None = None,
) -> tuple[bool, list[str]]:
    """Return whether ``docs/offline_bvd_summary.json`` shape matches live G3/G4.

    Tick 300: after a Nebius shape change, refuse to treat stale eval=3 offline
    PRIMARY tables as live-shape evidence. Summary must carry an explicit
    ``shape`` block matching ``icml_g3g4_live_shape()``.

    Tick 301: also require paper_artifacts / ICML_READY / Section 12 / case study
    to cite the summary's current B/D run ID ranges (not superseded Tick-23 IDs
    as the "latest" offline pilot).

    Tick 302: require ``figures`` to list existing Fig 1–2 PNGs (Tick 300 left
    ``figures: []`` when matplotlib was absent, so paper could cite stale PNGs).
    """
    root = repo_root or _REPO_ROOT
    expected = icml_g3g4_live_shape(profile)
    problems: list[str] = []
    path = root / "docs" / "offline_bvd_summary.json"
    if not path.is_file():
        return False, ["missing docs/offline_bvd_summary.json"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"docs/offline_bvd_summary.json: {exc}"]

    shape = payload.get("shape")
    if not isinstance(shape, dict):
        problems.append(
            "docs/offline_bvd_summary.json: missing shape "
            "{eval_subset,population_size,elite_count,max_gen} "
            "(Tick 300 live-shape lock)"
        )
        return False, problems

    got = {
        "eval_subset": int(shape.get("eval_subset", -1)),
        "population_size": int(shape.get("population_size", -1)),
        "elite_count": int(shape.get("elite_count", -1)),
        "max_gen": int(shape.get("max_gen", -1)),
    }
    if got != expected:
        problems.append(
            f"docs/offline_bvd_summary.json shape {got} != live {expected}"
        )

    # Tick 302: paper Figs 1–2 must be recorded and present on disk.
    figs = payload.get("figures")
    if not isinstance(figs, list) or len(figs) < 2:
        problems.append(
            "docs/offline_bvd_summary.json: figures must list ≥2 paths "
            "(Tick 302 fig lock; was empty when matplotlib missing)"
        )
    else:
        fig_names = {Path(str(f)).name for f in figs}
        for required in ("fig1_learning_curves.png", "fig2_mechanism.png"):
            if required not in fig_names:
                problems.append(
                    f"docs/offline_bvd_summary.json figures: missing {required} "
                    "(Tick 302)"
                )
        for f in figs:
            fp = Path(str(f))
            if not fp.is_absolute():
                fp = root / fp
            if not fp.is_file() or fp.stat().st_size < 1000:
                problems.append(
                    f"docs/offline_bvd_summary.json figures: missing/empty "
                    f"file {f} (Tick 302)"
                )
        paper = root / "docs" / "paper_artifacts.md"
        if paper.is_file():
            paper_text = paper.read_text(encoding="utf-8")
            for required in ("fig1_learning_curves.png", "fig2_mechanism.png"):
                if required not in paper_text:
                    problems.append(
                        f"docs/paper_artifacts.md: missing figure cite "
                        f"{required} (Tick 302)"
                    )

    # Gate3 offline narrative table must also advertise the live eval_subset.
    gate3 = root / "docs" / "gate3_report.md"
    if gate3.is_file():
        text = gate3.read_text(encoding="utf-8")
        start = text.find("<!-- OFFLINE_G3_PILOT_START -->")
        end = text.find("<!-- OFFLINE_G3_PILOT_END -->")
        block = text[start:end] if start != -1 and end != -1 else ""
        # Table row like: | B | … | 4 | 2 | 6 | 5 | `1890–1894` |
        row_re = re.compile(
            r"\|\s*B\s*\|[^|]*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|",
            re.IGNORECASE,
        )
        m = row_re.search(block)
        if m is None:
            problems.append(
                "docs/gate3_report.md offline block: missing B shape table row "
                "(pop|elite|max_gen|eval_subset)"
            )
        else:
            table_got = {
                "population_size": int(m.group(1)),
                "elite_count": int(m.group(2)),
                "max_gen": int(m.group(3)),
                "eval_subset": int(m.group(4)),
            }
            if table_got != expected:
                problems.append(
                    f"docs/gate3_report.md offline B row {table_got} != live {expected}"
                )

    # Tick 301: paper pack / READY / Section 12 / case study must cite current IDs.
    b_ids = [int(x) for x in (payload.get("b_run_ids") or [])]
    d_ids = [int(x) for x in (payload.get("d_run_ids") or [])]
    if len(b_ids) < 1 or len(d_ids) < 1:
        problems.append(
            "docs/offline_bvd_summary.json: missing b_run_ids / d_run_ids "
            "(Tick 301 paper-ID lock)"
        )
    else:
        b_variants = _offline_id_range_strings(b_ids)
        d_variants = _offline_id_range_strings(d_ids)
        case_run = f"run_{min(d_ids)}"
        case_path = root / "docs" / "case_study_offline.md"
        if case_path.is_file():
            case_text = case_path.read_text(encoding="utf-8")
            if case_run not in case_text and f"runs/{case_run}" not in case_text:
                problems.append(
                    f"docs/case_study_offline.md: missing current case study "
                    f"{case_run} (Tick 301)"
                )
        else:
            problems.append("missing docs/case_study_offline.md")

        paper = root / "docs" / "paper_artifacts.md"
        if paper.is_file():
            paper_text = paper.read_text(encoding="utf-8")
            if not _text_cites_any(paper_text, b_variants):
                problems.append(
                    "docs/paper_artifacts.md: missing current offline B ID range "
                    f"{b_variants[0]} (Tick 301)"
                )
            if not _text_cites_any(paper_text, d_variants):
                problems.append(
                    "docs/paper_artifacts.md: missing current offline D ID range "
                    f"{d_variants[0]} (Tick 301)"
                )
            # Case-study summary must point at the live-shape run, not only
            # superseded Tick-23 IDs (e.g. run_1840 while summary is 1900).
            cs_idx = paper_text.find("## Case study (offline)")
            cs_block = paper_text[cs_idx : cs_idx + 800] if cs_idx != -1 else ""
            if cs_block and case_run not in cs_block:
                problems.append(
                    "docs/paper_artifacts.md case study summary: missing "
                    f"{case_run} (stale Tick-23 ID drift; Tick 301)"
                )
        else:
            problems.append("missing docs/paper_artifacts.md")

        ready = root / "docs" / "ICML_READY.md"
        if ready.is_file():
            ready_text = ready.read_text(encoding="utf-8")
            # PRIMARY evidence line should cite current ranges.
            if not _text_cites_any(ready_text, b_variants) or not _text_cites_any(
                ready_text, d_variants
            ):
                problems.append(
                    "docs/ICML_READY.md: PRIMARY evidence missing current "
                    f"offline B/D ranges {b_variants[0]} / {d_variants[0]} "
                    "(Tick 301)"
                )
            # VALIDITY / mechanism evidence must not advertise superseded
            # D range as the sole current offline H5 pilot when IDs moved.
            # Require current D range (or case_run) near H5 evidence.
            h5_idx = ready_text.find("### 3. VALIDITY")
            h5_block = ready_text[h5_idx : h5_idx + 600] if h5_idx != -1 else ""
            if h5_block and not _text_cites_any(h5_block, d_variants):
                problems.append(
                    "docs/ICML_READY.md VALIDITY evidence: missing current "
                    f"offline D range {d_variants[0]} (Tick 301)"
                )
        else:
            problems.append("missing docs/ICML_READY.md")

        master = root / "docs" / "HACKATHON_MASTER_PLAN.md"
        if master.is_file():
            master_text = master.read_text(encoding="utf-8")
            # Section 12 offline pilot row — find the table cell after the
            # component name and require current ID ranges.
            row_m = re.search(
                r"\|\s*Offline B vs D case-study pilot\s*\|[^|]*\|([^|]*)\|",
                master_text,
            )
            if row_m is None:
                problems.append(
                    "docs/HACKATHON_MASTER_PLAN.md Section 12: missing "
                    "Offline B vs D case-study pilot row (Tick 301)"
                )
            else:
                notes = row_m.group(1)
                if not _text_cites_any(notes, b_variants) or not _text_cites_any(
                    notes, d_variants
                ):
                    problems.append(
                        "docs/HACKATHON_MASTER_PLAN.md Section 12 offline "
                        f"pilot row missing current IDs {b_variants[0]} / "
                        f"{d_variants[0]} (Tick 301)"
                    )

    return (len(problems) == 0, problems)
