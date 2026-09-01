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


# Preflight / status writers only — safe to discard before tip --apply (Tick 286).
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


def collect_icml_secrets_status() -> dict:
    """Presence-only secrets / diamond gate for live G2→G3→G4 (Tick 268/277/289).

    Does **not** include secret values. Portal Save is optional once Tick
    265–266 bootstraps succeed; live blockers are API keys + real GPQA
    (HF token **or** a local diamond CSV). Tick 289: Anthropic is required
    only when the ICML meta profile uses ``provider_id=anthropic``.
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
    human_keys = icml_human_required_secrets_phrase(for_fetch_diamond=True)
    return {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tick_note": (
            "Tick 268/273/277/289/292: secrets-first live gate; Portal Save optional; "
            "cron auto-live requires fetch_diamond_ok (NEBIUS + HF/CSV; "
            "ANTHROPIC only when meta provider is anthropic); "
            "human-facing cron/gate Next lines use "
            "icml_human_required_secrets_phrase; "
            ".env loaded for missing secret names; "
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
        "meta_requires_anthropic": meta_needs_anthropic,
        "meta_agent_profile": resolve_icml_meta_agent_profile(),
        "packages_bootstrapped_in_preflight": True,
        "portal_save_required_for_live": False,
        "secrets_ok_for_paid_sia": secrets_ok,
        "fetch_diamond_ok": fetch_diamond_ok,
        "cron_live_ok": cron_live_ok,
        "ready_for_live_pipeline": False,  # diamond + keys both required; caller may override
        "blockers": blockers,
        "human_next": [
            f"Add {human_keys} to automation "
            f"{_AUTOMATION_URL} (or linked env {_ENV_DASHBOARD_URL})",
            "Accept HuggingFace access for Idavidrein/gpqa with that HF token "
            "(or drop a real gpqa_diamond.csv at /tmp/gpqa_diamond.csv / "
            "docs/private/gpqa_diamond.csv / $ICML_DIAMOND_CSV to skip HF)",
            "Next cron (or now): `bash scripts/icml_cron_entry.sh` "
            "(Tick 271–292 — recovers tip; auto-live only when fetch_diamond_ok)",
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
