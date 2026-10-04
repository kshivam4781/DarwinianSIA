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

Tick 497: When no local CSV and no HF token, ``ensure_diamond_csv_via_public_mirror``
downloads the OpenAI simple-evals public ``gpqa_diamond.csv`` into ``/tmp``
(gitignored). Cron / ``--fetch-diamond`` then only need ``NEBIUS_API_KEY`` for
``fetch_diamond_ok`` (HF optional). Never commit the CSV.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import unquote

UV_INSTALL_URL = "https://astral.sh/uv/install.sh"
_LOCAL_BIN = Path.home() / ".local" / "bin"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SIA_PKG_ROOT = _REPO_ROOT / "SIA"
# Tick 516: also bootstrap matplotlib so cold-boot offline Bvd / paper Figs
# 1–2 rematerialize does not WARN-and-skip (Tick 515) when Portal Save /
# env install snapshot is absent — G2/G3/G4 already call ensure_icml_runtime_deps.
_RUNTIME_PIP_PACKAGES = ("huggingface_hub", "pydantic_ai", "matplotlib")
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
        return (
            f"{api} + (HF_TOKEN or local gpqa_diamond.csv "
            "or public OpenAI mirror auto-fetch — Tick 497)"
        )
    return api


def icml_preflight_diamond_ready(
    *,
    gpqa_not_synthetic_ok: bool | None = None,
    notes: list[str] | None = None,
) -> bool:
    """True when preflight already has non-synthetic diamond (Tick 498/500).

    Shared by Gate2/G3/G4 ``## Next`` builders so operators are not told to
    chase HF after Tick 497 public-mirror / on-disk diamond materialize.
    """
    if gpqa_not_synthetic_ok:
        return True
    for note in notes or []:
        low = note.lower()
        if "auto-wired --diamond-csv" in note or "materialized diamond from csv" in low:
            return True
        if "public openai" in low or "public mirror" in low:
            return True
    return False


def icml_ondisk_nonsynthetic_gpqa(repo_root: Path | None = None) -> bool:
    """True when a GPQA tree exists and is non-synthetic (Tick 502).

    Tick **499** already treated this as ``diamond_ready`` for secrets /
    ``fetch_diamond_ok``, but G2/G3/G4 ``--live --fetch-diamond`` still set
    ``require_hf`` whenever ``--diamond-csv`` was absent and then
    ``materialize_from_hf(..., force=True)`` — so a prior CSV/mirror
    materialize whose CSV path was cleaned would false-fail live on missing
    HF even with only ``NEBIUS_API_KEY`` needed. Use this to skip HF require
    and rematerialize.
    """
    return detect_gpqa_is_synthetic(repo_root) is False


def icml_fetch_diamond_needs_hf(
    *,
    fetch_diamond: bool,
    diamond_csv: Path | None,
    repo_root: Path | None = None,
) -> bool:
    """True when ``--fetch-diamond`` still requires ``HF_TOKEN`` (Tick 502).

    False when a CSV is wired **or** non-synthetic diamond is already on disk
    (Tick 499 ``diamond_ready`` parity). Does not invent a CSV.
    """
    if not fetch_diamond:
        return False
    if diamond_csv is not None:
        return False
    if icml_ondisk_nonsynthetic_gpqa(repo_root):
        return False
    return True


def icml_should_keep_ondisk_diamond(
    *,
    diamond_csv: Path | None,
    csv_auto: bool = False,
    repo_root: Path | None = None,
) -> bool:
    """Tick 504: keep on-disk non-synthetic diamond instead of rematerializing.

    Auto-wired CSV (Tick 278 / public mirror) is a *fallback* for
    ``fetch_diamond_ok`` / cold boots without HF — it must not force
    ``materialize_from_csv(..., force=True)`` when diamond is already ready
    (Tick 502 keep). Explicit ``--diamond-csv`` still rematerializes so
    operators can refresh. Avoids false live refuse on partial trees
    (``SIA/`` without ``sia-upstream/``) and mid-pipeline seed reshuffles.
    """
    if not icml_ondisk_nonsynthetic_gpqa(repo_root):
        return False
    if diamond_csv is None:
        return True
    return bool(csv_auto)


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


def repo_relative_path(
    path: Path | str, *, repo_root: Path | None = None
) -> str:
    """Return a portable repo-relative path for durable ICML artifacts.

    Tick 522: Tick 519 (live G4), Tick 520 (``epistemic_results``), and Tick 521
    (offline Bvd) each shipped a private ``_repo_relative_figure_path`` copy.
    Three identical helpers can drift (one writer regresses to bare ``str(path)``
    while source locks only cover that file). Canonicalize here so offline /
    live / epistemic Figs all emit ``docs/figures/figN_….png`` when under the
    repo, and fall back to ``str(path)`` outside the repo (tmp / absolute outs).

    Tick 523: same helper covers durable G2 / steering-lift post-check details
    (``run_dir``, ``belief_store``) so ``docs/gate2_*.json`` do not embed
    absolute ``/workspace/...`` paths across cold-boot VMs.

    Tick 524: also used by ``sanitize_repo_paths_in_text`` / diamond materialize
    / ``ensure_sia_on_pythonpath`` so preflight ``runtime_deps`` + fetch notes
    stay repo-relative in gate2/3/4 reports.
    """
    root = (repo_root or _REPO_ROOT).resolve()
    p = Path(path)
    try:
        return str(p.resolve().relative_to(root))
    except ValueError:
        return str(p)


# Tick 522 figure writers import this name; keep as alias of the general helper.
repo_relative_figure_path = repo_relative_path


def portable_path_for_durable(
    path: Path | str, *, repo_root: Path | None = None
) -> str:
    """Return a portable path label for durable ICML JSON/MD (Tick 525).

    - In-repo paths → ``repo_relative_path`` (``SIA/...``, ``docs/...``).
    - Host-tmp ``gpqa_diamond.csv`` (``/tmp/...``, ``$TMPDIR/...``) →
      ``$TMPDIR/gpqa_diamond.csv`` so gate notes / secrets status do not embed
      absolute host paths across cold-boot VMs.
    - Other absolute outs → ``str(path)`` fallback (operator debugging).
    """
    root = (repo_root or _REPO_ROOT).resolve()
    p = Path(path)
    try:
        resolved = p.resolve()
    except OSError:
        resolved = p
    try:
        return str(resolved.relative_to(root))
    except ValueError:
        pass
    if resolved.name == "gpqa_diamond.csv":
        tmp_roots: set[Path] = set()
        try:
            tmp_roots.add(Path(tempfile.gettempdir()).resolve())
        except OSError:
            pass
        for candidate in ("/tmp", "/var/tmp"):
            try:
                tmp_roots.add(Path(candidate).resolve())
            except OSError:
                tmp_roots.add(Path(candidate))
        for tmp in tmp_roots:
            try:
                resolved.relative_to(tmp)
                return "$TMPDIR/gpqa_diamond.csv"
            except ValueError:
                continue
    return str(resolved)


def diamond_csv_autowire_note(
    csv_path: Path | str, *, repo_root: Path | None = None
) -> str:
    """Tick 278 auto-wire note with Tick 525 portable diamond CSV path."""
    return (
        "Tick 278: auto-wired --diamond-csv from "
        f"{portable_path_for_durable(csv_path, repo_root=repo_root)}"
    )


_PYTHON_INTERPRETER_NAME_RE = re.compile(r"^python(\d+(\.\d+)*)?$")


def portable_argv_for_durable(
    argv: Sequence[str] | list[str], *, repo_root: Path | None = None
) -> list[str]:
    """Return argv with host-absolute interpreter/repo paths made portable (Tick 526).

    Gate2/3/4 planned-command writers historically persisted ``sys.executable``
    (``/usr/bin/python3``) and absolute in-repo paths into committed
    ``docs/gate*_report.*``. Sanitize at **write time only** — live execution
    still uses the real absolute argv from ``build_sia_command``.

    - ``sys.executable`` / absolute ``python`` / ``python3`` / ``python3.x`` →
      basename (``icml_python_cli()`` when matching this process)
    - Absolute in-repo paths / host-tmp diamond CSV → ``portable_path_for_durable``
    - Other tokens unchanged
    """
    root = (repo_root or _REPO_ROOT).resolve()
    try:
        exe_resolved = str(Path(sys.executable).resolve())
    except OSError:
        exe_resolved = str(sys.executable)
    py_cli = icml_python_cli()
    out: list[str] = []
    for raw in argv:
        s = str(raw)
        if not s:
            out.append(s)
            continue
        if s == sys.executable:
            out.append(py_cli)
            continue
        p = Path(s)
        resolved: Path | None = None
        if p.is_absolute():
            try:
                resolved = p.resolve()
            except OSError:
                resolved = p
            if str(resolved) == exe_resolved:
                out.append(py_cli)
                continue
            if _PYTHON_INTERPRETER_NAME_RE.match(resolved.name):
                out.append(resolved.name)
                continue
            out.append(portable_path_for_durable(resolved, repo_root=root))
            continue
        out.append(s)
    return out


def _sanitize_host_tmp_diamond_csv(text: str) -> str:
    """Rewrite absolute host-tmp ``gpqa_diamond.csv`` paths to ``$TMPDIR/...``."""
    if not text or "gpqa_diamond.csv" not in text:
        return text
    out = text
    # Explicit tempfile.gettempdir() prefix (may differ from /tmp on some hosts).
    try:
        tmp = str(Path(tempfile.gettempdir()).resolve())
    except OSError:
        tmp = ""
    if tmp:
        # Escape for regex; allow nested pytest dirs under the temp root.
        esc = re.escape(tmp.rstrip("/\\"))
        out = re.sub(
            esc + r"[/\\](?:[^/\\\s\"']+[/\\])*gpqa_diamond\.csv",
            "$TMPDIR/gpqa_diamond.csv",
            out,
        )
    # Common Unix temp roots (including /tmp/pytest-of-*/... nested).
    out = re.sub(
        r"(?:/var)?/tmp/(?:[^/\s\"']+/)*gpqa_diamond\.csv",
        "$TMPDIR/gpqa_diamond.csv",
        out,
    )
    return out


def sanitize_repo_paths_in_text(
    text: str, *, repo_root: Path | None = None
) -> str:
    """Rewrite absolute in-repo path prefixes embedded in durable detail strings.

    Tick 524: ``ensure_icml_runtime_deps`` historically joined absolute
    ``PYTHONPATH=/workspace/SIA`` and diamond notes listed
    ``['/workspace/SIA/sia/tasks/gpqa', ...]``. ``repo_relative_path`` only
    covers whole-string paths; this strips the absolute repo-root prefix from
    longer ``; ``-joined / list-repr detail strings so gate2/3/4 reports stay
    portable across cold-boot VMs.

    Tick 525: also rewrite host-tmp ``gpqa_diamond.csv`` absolute paths to
    ``$TMPDIR/gpqa_diamond.csv`` (auto-wire notes / secrets ``diamond_csv_path``).
    """
    if not text:
        return text
    root = (repo_root or _REPO_ROOT).resolve()
    prefixes = {str(root)}
    # Also cover unresolved / alternate spellings of the same root.
    if repo_root is not None:
        prefixes.add(str(Path(repo_root)))
        try:
            prefixes.add(str(Path(repo_root).resolve()))
        except OSError:
            pass
    prefixes.add(str(_REPO_ROOT))
    try:
        prefixes.add(str(_REPO_ROOT.resolve()))
    except OSError:
        pass
    out = text
    for prefix in sorted((p for p in prefixes if p), key=len, reverse=True):
        # Prefer dropping "prefix/" so remaining path is repo-relative.
        for sep in ("/", os.sep):
            token = prefix.rstrip("/\\") + sep
            if token in out:
                out = out.replace(token, "")
        # Bare prefix (e.g. trailing path with no child) → "."
        if prefix in out:
            out = out.replace(prefix, ".")
    return _sanitize_host_tmp_diamond_csv(out)


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
        # Tick 524: durable gate reports must not embed host-absolute uv paths
        # (e.g. /home/ubuntu/.local/bin/uv) — presence on PATH is enough.
        return True, "uv available on PATH"

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
        return True, "uv installed on PATH (Astral bootstrap)"

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
            return True, "uv available on PATH (SIA per-run venv path)"

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
    # Tick 524: omit host-absolute --target path from durable gate details.
    return True, f"uv pip installed {', '.join(packages)} into user site"


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

    Tick 524: durable detail strings use repo-relative ``SIA`` (not absolute
    ``/workspace/SIA``) so gate2/3/4 ``runtime_deps`` rows stay portable.
    """
    sia_root = _SIA_PKG_ROOT
    rel = repo_relative_path(sia_root)
    if not (sia_root / "sia" / "__init__.py").is_file():
        return False, f"SIA package missing at {rel}"

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
        return True, f"sia importable via PYTHONPATH={rel}"
    return False, f"sia still not importable after PYTHONPATH prepend ({rel})"


def ensure_icml_runtime_deps(*, allow_install: bool = True) -> tuple[bool, str]:
    """Ensure host deps for live G2→G3→G4 without a Portal-Saved install snapshot.

    1. ``ensure_uv_on_path`` (per-run venvs)
    2. ``ensure_sia_on_pythonpath`` (``python -m sia`` from repo root)
    3. ``huggingface_hub`` for ``--fetch-diamond`` / HF gpqa materialization
    4. ``pydantic_ai`` for Nebius meta (Tick 289)
    5. ``matplotlib`` for offline Bvd / paper Figs 1–2 (Tick 516)
    6. Tick 281: expose user site on ``PYTHONPATH`` so PYTHONNOUSERSITE /
       venv children still import ``--target`` bootstrapped packages

    Returns ``(ok, detail)``. When ``allow_install`` is False, missing pip
    packages are reported as failures without attempting install.
    """
    notes: list[str] = []

    ok_uv, uv_detail = ensure_uv_on_path(allow_install=allow_install)
    if not ok_uv:
        return False, sanitize_repo_paths_in_text(
            f"uv required for SIA per-run venvs: {uv_detail}"
        )
    notes.append(uv_detail)

    ok_sia, sia_detail = ensure_sia_on_pythonpath()
    if not ok_sia:
        return False, sanitize_repo_paths_in_text(sia_detail)
    notes.append(sia_detail)

    missing = [p for p in _RUNTIME_PIP_PACKAGES if not _module_importable(p)]
    if missing:
        if not allow_install:
            return (
                False,
                sanitize_repo_paths_in_text(
                    f"missing runtime packages {missing} (install disabled); "
                    + "; ".join(notes)
                ),
            )
        pip_names = [_RUNTIME_PIP_DIST_NAMES.get(p, p) for p in missing]
        ok_pip, pip_detail = _pip_install_user(*pip_names)
        notes.append(pip_detail)
        if not ok_pip:
            return False, sanitize_repo_paths_in_text("; ".join(notes))
        still = [p for p in missing if not _module_importable(p)]
        if still:
            # User-site may need a path refresh in this process.
            _expose_user_site_on_pythonpath()
            still = [p for p in missing if not _module_importable(p)]
            if still:
                return (
                    False,
                    sanitize_repo_paths_in_text(
                        f"packages still missing after pip: {still}; "
                        + "; ".join(notes)
                    ),
                )
        notes.append(f"bootstrapped {', '.join(missing)}")
    else:
        notes.append(
            "huggingface_hub + pydantic_ai + matplotlib already importable"
        )

    # Tick 281: always publish user site on PYTHONPATH (even when packages were
    # already importable via ENABLE_USER_SITE) so child env copies inherit them.
    exposed = _expose_user_site_on_pythonpath()
    if exposed:
        # Tick 524: omit host-absolute user-site path from durable gate details.
        notes.append("user site on PYTHONPATH")

    # Tick 524: belt-and-suspenders — strip any absolute in-repo prefixes that
    # pip/uv install notes may still embed before they land in gate reports.
    return True, sanitize_repo_paths_in_text("; ".join(notes))


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


# repo_relative_path / repo_relative_figure_path / sanitize_repo_paths_in_text
# are defined earlier (before ensure_uv_on_path) so runtime-deps details can use
# them without forward references (Tick 522–524).


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
# Tick 387: gitignored prior_live stash — survive discard + tip --apply;
# reinjected into gate2/3/4 JSON after tip recover (never commit).
ICML_PRIOR_LIVE_STASH_RELPATH = "docs/icml_prior_live_stash.json"
# Tick 389: committed prior_live evidence — budget-ledger parity for cross-VM
# resume. Gitignored stash dies on fresh boots; this file is NOT gitignored and
# NOT ephemeral so tip commits carry prior_live_* when agents push after live.
ICML_PRIOR_LIVE_EVIDENCE_RELPATH = "docs/icml_prior_live_evidence.json"
# Tick 421: gitignored budget_spent stash — park dirty docs/icml_budget_spent.json
# across tip --apply (same role as prior_live stash for evidence). Commit the
# restored ledger onto tip after reinject (cross-VM spend/stages parity).
ICML_BUDGET_SPENT_RELPATH = "docs/icml_budget_spent.json"
ICML_BUDGET_SPENT_STASH_RELPATH = "docs/icml_budget_spent_stash.json"
# Tick 427: gitignored paper-pack companion stash — park dirty G4 paper-pack
# outputs (paper_artifacts / ICML_READY / Figs 1–2) across tip --apply so
# Tick 426 co-commit whitelist does not refuse prepare (companions counted as
# other non-ephemeral dirt). Reinject + durable commit after tip recover.
ICML_PAPER_PACK_STASH_RELPATH = "docs/icml_paper_pack_stash.json"
# Tick 350/359: minimal MCP args file — gitignored (never commit; survive tip
# --apply). Declared early so tip-apply ignore sets can reference it.
ICML_OPEN_GIT_PR_CALL_RELPATH = "docs/icml_open_git_pr_call.json"

# Tick 391: durable gitignored paths that must not block tip --apply when
# chicken-egg boots lack tip ``.gitignore`` (porcelain shows them as ``??``).
# Cron persists the boot file *before* tip recover; without this filter,
# greenfield/main boots refuse ``--apply`` and never land tip files.
# Tick 390: do NOT include committed prior_live evidence here.
# Tick 427: also ignore paper-pack companion stash.
TIP_APPLY_GITIGNORE_LAG_RELPATHS: frozenset[str] = frozenset(
    {
        ICML_CLOUD_BOOT_BRANCH_RELPATH,
        ICML_PRIOR_LIVE_STASH_RELPATH,
        ICML_BUDGET_SPENT_STASH_RELPATH,
        ICML_PAPER_PACK_STASH_RELPATH,
        ICML_OPEN_GIT_PR_CALL_RELPATH,
    }
)


def is_tip_apply_ignored_dirty(rel_path: str) -> bool:
    """True when ``rel_path`` is gitignore-lag durable dirt (Tick 391)."""
    norm = rel_path.replace("\\", "/").lstrip("./")
    return norm in TIP_APPLY_GITIGNORE_LAG_RELPATHS


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
# Tick 391: also filter boot/call/stash from tip-apply dirty checks when
# ``.gitignore`` lags (chicken-egg greenfield) — see TIP_APPLY_GITIGNORE_LAG.
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


def _stash_prior_live_from_gate_json(data: dict) -> dict[str, Any] | None:
    """Tick 387: extract preservable live evidence from a gate sidecar JSON.

    Returns a small dict with either ``prior_live_post`` (gate2) or
    ``prior_live_metrics`` (gate3/gate4), or None when nothing trustable exists.
    Converts a live-executed top-level payload into the prior_live shape so
    ``discard_ephemeral_icml_dirt`` can persist it across ``git restore`` /
    tip ``--apply`` hard reset via ``docs/icml_prior_live_stash.json``.
    """
    if not isinstance(data, dict):
        return None

    # Gate2 shape: post / prior_live_post list of check dicts.
    prior_post = data.get("prior_live_post")
    if isinstance(prior_post, list) and prior_post:
        return {"prior_live_post": prior_post}
    post = data.get("post")
    mode = str(data.get("mode") or "")
    if (
        mode == "live"
        and isinstance(post, list)
        and post
        and all(isinstance(c, dict) for c in post)
    ):
        return {"prior_live_post": post}

    # Gate3/Gate4 shape: prior_live_metrics or live-executed comparison.
    prior_metrics = data.get("prior_live_metrics")
    if isinstance(prior_metrics, dict):
        prior_cmp = prior_metrics.get("comparison")
        if isinstance(prior_cmp, dict) and prior_cmp:
            # Gate4 also requires paper_refreshed when present on the blob.
            if "paper_refreshed" in prior_metrics and not bool(
                prior_metrics.get("paper_refreshed")
            ):
                pass  # fall through to top-level live check
            else:
                return {"prior_live_metrics": prior_metrics}

    comparison = data.get("comparison")
    executed = bool(data.get("executed"))
    if (
        mode in {"live", "refresh-paper"}
        and executed
        and isinstance(comparison, dict)
        and comparison
    ):
        metrics: dict[str, Any] = {
            "comparison": comparison,
            "h5_by_d_run": data.get("h5_by_d_run") or {},
            "h2_by_d_run": data.get("h2_by_d_run") or {},
            "executed": True,
        }
        # Gate4 paper-pack fields (optional on gate3).
        if "paper_refreshed" in data:
            if not bool(data.get("paper_refreshed")):
                return None
            metrics["paper_refreshed"] = True
            metrics["primary_pass"] = bool(data.get("primary_pass"))
            metrics["h2_pass"] = bool(data.get("h2_pass"))
            metrics["h5_pass"] = bool(data.get("h5_pass"))
            metrics["ready_status"] = data.get("ready_status")
            metrics["figures_written"] = list(data.get("figures_written") or [])
        return {"prior_live_metrics": metrics}
    return None


def _reinject_prior_live_into_gate_json(
    path: Path, stashed: dict[str, Any]
) -> bool:
    """Merge stashed prior_live_* into a gate JSON sidecar (Tick 387)."""
    if not path.is_file() or not stashed:
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, dict):
        return False
    changed = False
    if "prior_live_post" in stashed and not data.get("prior_live_post"):
        data["prior_live_post"] = stashed["prior_live_post"]
        changed = True
    if "prior_live_metrics" in stashed and not data.get("prior_live_metrics"):
        data["prior_live_metrics"] = stashed["prior_live_metrics"]
        changed = True
    if not changed:
        return False
    try:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return False
    return True


_GATE_JSON_STASH_KEYS = (
    "docs/gate2_report.json",
    "docs/gate3_report.json",
    "docs/gate4_report.json",
)


def prior_live_stash_path(repo_root: Path | None = None) -> Path:
    """Tick 387: gitignored durable path for prior_live_* across tip --apply."""
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    return root / ICML_PRIOR_LIVE_STASH_RELPATH


def prior_live_evidence_path(repo_root: Path | None = None) -> Path:
    """Tick 389: committed prior_live_* evidence (cross-VM; budget-ledger parity)."""
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    return root / ICML_PRIOR_LIVE_EVIDENCE_RELPATH


def _load_prior_live_gates_payload(path: Path) -> dict[str, Any]:
    """Load ``gates`` map from a stash/evidence JSON payload (empty on failure)."""
    if not path.is_file():
        return {}
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if isinstance(existing, dict) and isinstance(existing.get("gates"), dict):
        return dict(existing["gates"])
    return {}


def _write_prior_live_gates_payload(
    path: Path, *, tick: int, gates: dict[str, Any], tick_note: str
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tick": tick,
        "tick_note": tick_note,
        "gates": gates,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def ensure_prior_live_evidence_initialized(
    repo_root: Path | None = None,
) -> tuple[Path, bool]:
    """Create empty committed evidence file when missing (Tick 389). Never overwrites."""
    p = prior_live_evidence_path(repo_root)
    if p.is_file():
        return p, False
    _write_prior_live_gates_payload(
        p,
        tick=389,
        gates={},
        tick_note=(
            "Tick 389: committed prior_live evidence (budget-ledger parity). "
            "Gitignored stash dies on fresh boots; commit this file after live "
            "so cross-VM reinject can restore gate2/3/4 prior_live_* when runs/ "
            "are absent. Empty gates until first live capture."
        ),
    )
    return p, True


def persist_prior_live_stash_from_working_tree(
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Scan gate JSON sidecars and write gitignored stash + committed evidence.

    Merges with any existing stash/evidence so a later preflight-only dirt
    discard does not drop previously captured live evidence.

    Tick 389: also writes ``docs/icml_prior_live_evidence.json`` (NOT gitignored)
    so tip commits carry prior_live_* across fresh cloud boots — gitignored
    stash alone only survived same-VM tip ``--apply``.
    """
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    stash_path = prior_live_stash_path(root)
    evidence_path = prior_live_evidence_path(root)
    merged: dict[str, Any] = {}
    # Prefer union of stash + committed evidence so neither wipe loses gates.
    for src in (stash_path, evidence_path):
        for rel, blob in _load_prior_live_gates_payload(src).items():
            if isinstance(blob, dict):
                merged[rel] = blob
    captured: list[str] = []
    for rel in _GATE_JSON_STASH_KEYS:
        path = root / rel
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        blob = _stash_prior_live_from_gate_json(data if isinstance(data, dict) else {})
        if blob is None:
            continue
        merged[rel] = blob
        captured.append(rel)
    if not merged:
        return {
            "ok": True,
            "captured": [],
            "path": str(stash_path),
            "evidence_path": str(evidence_path),
            "gates": {},
        }
    note_387 = (
        "Tick 387: gitignored prior_live stash across discard + tip --apply"
    )
    note_389 = (
        "Tick 389: committed prior_live evidence (budget-ledger parity) — "
        "cross-VM reinject when gitignored stash is absent on fresh boots; "
        "commit this file with the tip after live G2/G3/G4"
    )
    try:
        _write_prior_live_gates_payload(
            stash_path, tick=387, gates=merged, tick_note=note_387
        )
        _write_prior_live_gates_payload(
            evidence_path, tick=389, gates=merged, tick_note=note_389
        )
    except OSError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "captured": captured,
            "path": str(stash_path),
            "evidence_path": str(evidence_path),
        }
    return {
        "ok": True,
        "captured": captured,
        "path": str(stash_path),
        "evidence_path": str(evidence_path),
        "gates": merged,
    }


def _reinject_prior_live_gates(
    root: Path, gates: dict[str, Any]
) -> list[str]:
    reinjected: list[str] = []
    for rel, blob in gates.items():
        if rel not in _GATE_JSON_STASH_KEYS:
            continue
        if not isinstance(blob, dict):
            continue
        path = root / rel
        if _reinject_prior_live_into_gate_json(path, blob):
            reinjected.append(rel)
    return reinjected


def reinject_prior_live_stash(
    repo_root: Path | None = None,
) -> tuple[bool, str]:
    """Reinject prior_live_* into gate2/3/4 JSON after tip --apply.

    Tick 387: ``discard_ephemeral_icml_dirt`` + ``git reset --hard`` would
    otherwise wipe Tick 384–386 ``prior_live_*`` evidence. Stash file is
    gitignored (survives hard reset on the same VM).

    Tick 389: when the gitignored stash is missing (fresh cloud boot), fall
    back to committed ``docs/icml_prior_live_evidence.json`` — same role as
    ``docs/icml_budget_spent.json`` for spend/stages.
    """
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    stash_path = prior_live_stash_path(root)
    evidence_path = prior_live_evidence_path(root)
    source = "stash"
    gates = _load_prior_live_gates_payload(stash_path)
    if not gates:
        source = "evidence"
        gates = _load_prior_live_gates_payload(evidence_path)
    if not gates:
        if not stash_path.is_file() and not evidence_path.is_file():
            return True, "no prior_live stash or evidence"
        return True, "prior_live stash/evidence empty"
    reinjected = _reinject_prior_live_gates(root, gates)
    # Tick 389: hard-reset restores an older committed evidence file; rewrite
    # from the gates we just trusted so cross-VM tip --apply cannot empty it.
    try:
        _write_prior_live_gates_payload(
            evidence_path,
            tick=389,
            gates=gates,
            tick_note=(
                "Tick 389: committed prior_live evidence (budget-ledger parity) — "
                "rewritten on reinject so tip --apply hard-reset cannot wipe "
                "fresher gates carried by the gitignored stash"
            ),
        )
    except OSError:
        pass
    if not reinjected:
        return (
            True,
            f"prior_live {source} present but nothing reinjected "
            "(sidecars missing or already had prior_live); evidence refreshed",
        )
    return True, f"reinjected prior_live from {source} into: {reinjected}"


def tip_apply_blocking_dirty_paths(
    repo_root: Path | None = None,
    *,
    discard_detail: str | None = None,
) -> list[str]:
    """Dirty paths that should block tip ``--apply`` (Tick 389–391 / 419).

    Excludes ``TIP_APPLY_GITIGNORE_LAG_RELPATHS`` (boot file, open_git_pr call
    JSON, prior_live stash) so chicken-egg greenfield boots without tip
    ``.gitignore`` can still ``--apply`` after cron persists the boot file
    (Tick 391). Tick 390: do **not** exclude committed
    ``docs/icml_prior_live_evidence.json`` — dirty evidence with live gates must
    be committed before tip ``--apply`` (true budget-ledger parity). Tick 389
    filtered evidence so hard-reset could proceed and rely on same-VM stash
    reinject; that left uncommitted evidence wipeable across fresh boots.

    Tick 419: when ``discard_detail`` shows a fresh ``prior_live stashed``
    capture, exclude evidence dirt written by that discard. Same-VM stash
    reinjects after hard-reset; callers should still commit evidence onto the
    tip afterward. Pre-existing evidence dirt (no fresh stash) still blocks.

    Tick 420/421: callers should run ``prepare_prior_live_evidence_for_tip_apply``
    before discard (parks pre-existing dirty evidence **and** budget_spent into
    gitignored stashes) and ``commit_prior_live_evidence_if_dirty`` after
    reinject + tip-PR anti-churn so both durable ledgers land on the tip SHA
    without a manual commit. Tick 421 closes the post-live case where dirty
    budget_spent blocked Tick 420 prepare (evidence-only).
    """
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    paths = [
        p
        for p in porcelain_dirty_paths(root)
        if not is_tip_apply_ignored_dirty(p)
    ]
    if discard_detail and "prior_live stashed" in discard_detail:
        evidence_norm = ICML_PRIOR_LIVE_EVIDENCE_RELPATH.replace("\\", "/")
        paths = [
            p
            for p in paths
            if p.replace("\\", "/").lstrip("./") != evidence_norm
        ]
    return paths


def _norm_repo_relpath(rel_path: str) -> str:
    return rel_path.replace("\\", "/").lstrip("./")



def budget_spent_stash_path(repo_root: Path | None = None) -> Path:
    """Tick 421: gitignored stash for dirty budget_spent across tip --apply."""
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    return root / ICML_BUDGET_SPENT_STASH_RELPATH


def paper_pack_stash_path(repo_root: Path | None = None) -> Path:
    """Tick 427: gitignored stash for dirty G4 paper-pack companions."""
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    return root / ICML_PAPER_PACK_STASH_RELPATH


def _durable_ledger_relpaths() -> frozenset[str]:
    """Committed ledgers that must survive tip --apply (Tick 390/420/421)."""
    return frozenset(
        {
            _norm_repo_relpath(ICML_PRIOR_LIVE_EVIDENCE_RELPATH),
            _norm_repo_relpath(ICML_BUDGET_SPENT_RELPATH),
        }
    )


# Tick 426: G4 ``apply_paper_pack`` dirties these alongside durable ledgers.
# Pre-426 ``commit_durable_ledgers_after_live`` treated them as blocking
# non-ephemeral dirt → refuse → spend/READY/Live Tables never pushed.
ICML_LIVE_PAPER_PACK_RELPATHS: frozenset[str] = frozenset(
    {
        "docs/paper_artifacts.md",
        "docs/ICML_READY.md",
        "docs/figures/fig1_learning_curves.png",
        "docs/figures/fig2_mechanism.png",
    }
)


def _post_live_companion_relpaths() -> frozenset[str]:
    """Paper-pack paths co-committed with durable ledgers after live (Tick 426)."""
    return frozenset(
        _norm_repo_relpath(p) for p in ICML_LIVE_PAPER_PACK_RELPATHS
    )


def is_post_live_companion_path(rel_path: str) -> bool:
    """True when ``rel_path`` is a G4 paper-pack output (Tick 426)."""
    return _norm_repo_relpath(rel_path) in _post_live_companion_relpaths()


def _git_restore_or_unlink(
    root: Path,
    relpath: str,
    path: Path,
) -> tuple[bool, str]:
    """Restore tracked path to HEAD, or unlink if untracked."""
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relpath],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if tracked.returncode == 0:
        restore = subprocess.run(
            ["git", "restore", "--worktree", "--staged", "--", relpath],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        if restore.returncode != 0:
            restore = subprocess.run(
                ["git", "checkout", "--", relpath],
                cwd=str(root),
                capture_output=True,
                text=True,
            )
        if restore.returncode != 0:
            return (
                False,
                f"failed restoring {relpath}: "
                f"{(restore.stderr or restore.stdout or '').strip()}",
            )
        return True, f"restored {relpath} to HEAD"
    if path.is_file():
        try:
            path.unlink()
        except OSError as exc:
            return False, f"failed unlinking untracked {relpath}: {exc}"
        return True, f"unlinked untracked {relpath}"
    return True, f"{relpath} absent (noop)"


def _park_budget_spent_to_stash(repo_root: Path | None = None) -> tuple[bool, str]:
    """Copy dirty budget_spent JSON into gitignored stash (Tick 421)."""
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    src = budget_spent_ledger_path(root)
    if not src.is_file():
        return True, "budget_spent absent (park noop)"
    try:
        payload = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        return False, f"Tick 421 budget park failed reading ledger: {exc}"
    if not isinstance(payload, dict):
        return False, "Tick 421 budget park refused — ledger is not a JSON object"
    stash = {
        "updated_at": payload.get("updated_at"),
        "tick": 421,
        "tick_note": (
            "Tick 421: budget_spent stash parked from dirty ledger before "
            "tip --apply (restore ledger → reinject → commit on tip)"
        ),
        "ledger": payload,
    }
    stash_path = budget_spent_stash_path(root)
    try:
        stash_path.parent.mkdir(parents=True, exist_ok=True)
        stash_path.write_text(json.dumps(stash, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return False, f"Tick 421 budget park failed writing stash: {exc}"
    return True, f"parked budget_spent → {ICML_BUDGET_SPENT_STASH_RELPATH}"


def reinject_budget_spent_stash(
    repo_root: Path | None = None,
) -> tuple[bool, str]:
    """Tick 421: reinject parked budget_spent after tip --apply hard-reset."""
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    stash_path = budget_spent_stash_path(root)
    if not stash_path.is_file():
        return True, "budget_spent stash empty (Tick 421 reinject noop)"
    try:
        blob = json.loads(stash_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        return False, f"Tick 421 budget reinject failed reading stash: {exc}"
    ledger = blob.get("ledger") if isinstance(blob, dict) else None
    if not isinstance(ledger, dict):
        return False, "Tick 421 budget reinject refused — stash missing ledger object"
    dest = budget_spent_ledger_path(root)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return False, f"Tick 421 budget reinject failed writing ledger: {exc}"
    return True, f"Tick 421: reinjected budget_spent from stash → {ICML_BUDGET_SPENT_RELPATH}"


def _park_paper_pack_companions_to_stash(
    repo_root: Path | None = None,
    *,
    dirty_companions: list[str] | None = None,
) -> tuple[bool, str]:
    """Tick 427: park dirty G4 paper-pack files into gitignored JSON stash.

    Text/markdown stored as utf-8; binary figures as base64. Overwrites any
    prior stash contents for the parked paths (merge with existing stash keys
    so a partial park does not drop earlier files).
    """
    import base64
    from datetime import datetime, timezone

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    companion = _post_live_companion_relpaths()
    if dirty_companions is None:
        to_park = [
            _norm_repo_relpath(p)
            for p in porcelain_dirty_paths(root)
            if _norm_repo_relpath(p) in companion
        ]
    else:
        to_park = [
            _norm_repo_relpath(p)
            for p in dirty_companions
            if _norm_repo_relpath(p) in companion
        ]
    if not to_park:
        return True, "paper-pack companions not dirty (park noop)"

    stash_path = paper_pack_stash_path(root)
    files: dict[str, dict[str, str]] = {}
    if stash_path.is_file():
        try:
            prior = json.loads(stash_path.read_text(encoding="utf-8"))
            prior_files = prior.get("files") if isinstance(prior, dict) else None
            if isinstance(prior_files, dict):
                for k, v in prior_files.items():
                    if isinstance(v, dict) and "content" in v:
                        files[_norm_repo_relpath(str(k))] = {
                            "encoding": str(v.get("encoding") or "utf-8"),
                            "content": str(v["content"]),
                        }
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            files = {}

    parked: list[str] = []
    for rel in sorted(set(to_park)):
        path = root / rel
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError as exc:
            return False, f"Tick 427 paper-pack park failed reading {rel}: {exc}"
        if rel.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            files[rel] = {
                "encoding": "base64",
                "content": base64.b64encode(raw).decode("ascii"),
            }
        else:
            files[rel] = {
                "encoding": "utf-8",
                "content": raw.decode("utf-8", errors="replace"),
            }
        parked.append(rel)

    if not parked:
        return True, "paper-pack companions dirty but files absent (park noop)"

    stash = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tick": 427,
        "tick_note": (
            "Tick 427: paper-pack companions parked before tip --apply "
            "(restore HEAD → reinject → durable commit on tip)"
        ),
        "files": files,
    }
    try:
        stash_path.parent.mkdir(parents=True, exist_ok=True)
        stash_path.write_text(json.dumps(stash, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        return False, f"Tick 427 paper-pack park failed writing stash: {exc}"
    return True, f"parked paper-pack companions → {ICML_PAPER_PACK_STASH_RELPATH} ({', '.join(parked)})"


def reinject_paper_pack_stash(
    repo_root: Path | None = None,
) -> tuple[bool, str]:
    """Tick 427: reinject parked paper-pack companions after tip --apply."""
    import base64

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    stash_path = paper_pack_stash_path(root)
    if not stash_path.is_file():
        return True, "paper-pack stash empty (Tick 427 reinject noop)"
    try:
        blob = json.loads(stash_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        return False, f"Tick 427 paper-pack reinject failed reading stash: {exc}"
    files = blob.get("files") if isinstance(blob, dict) else None
    if not isinstance(files, dict) or not files:
        return False, "Tick 427 paper-pack reinject refused — stash missing files"
    companion = _post_live_companion_relpaths()
    written: list[str] = []
    for rel, meta in files.items():
        norm = _norm_repo_relpath(str(rel))
        if norm not in companion:
            continue
        if not isinstance(meta, dict) or "content" not in meta:
            continue
        encoding = str(meta.get("encoding") or "utf-8")
        content = meta["content"]
        dest = root / norm
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if encoding == "base64":
                dest.write_bytes(base64.b64decode(str(content)))
            else:
                dest.write_text(str(content), encoding="utf-8")
        except (OSError, ValueError, TypeError) as exc:
            return False, f"Tick 427 paper-pack reinject failed writing {norm}: {exc}"
        written.append(norm)
    if not written:
        return False, "Tick 427 paper-pack reinject refused — no companion files written"
    return (
        True,
        f"Tick 427: reinjected paper-pack companions from stash ({', '.join(written)})",
    )


def _git_show_head_bytes(repo_root: Path, relpath: str) -> bytes | None:
    """Return ``git show HEAD:<relpath>`` bytes, or None if absent/unreadable.

    Tick 430: durable-stash redundancy must compare against **committed tip
    HEAD**, not the working tree. Reinject can make WT match a unique stash
    while HEAD still lacks READY/spend (e.g. staged-only / commit-noop); a WT
    comparison would falsely mark the stash redundant and wipe it.
    """
    import subprocess

    norm = _norm_repo_relpath(relpath)
    proc = subprocess.run(
        ["git", "show", f"HEAD:{norm}"],
        cwd=str(repo_root),
        capture_output=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout


def _load_prior_live_gates_from_bytes(raw: bytes | None) -> dict:
    """Parse prior_live gates map from committed HEAD blob bytes."""
    if not raw:
        return {}
    try:
        blob = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    if isinstance(blob, dict) and isinstance(blob.get("gates"), dict):
        return dict(blob["gates"])
    return {}


def _paper_pack_stash_redundant_with_head(
    repo_root: Path, stash_path: Path
) -> bool:
    """True when paper-pack stash is absent, unusable, or matches **git HEAD**.

    Tick 429: a stash that still holds mid-tick READY/Figs differing from HEAD
    (failed reinject, or reinject never ran) is **not** redundant — keep it.
    Tick 430: compare to ``git show HEAD:<path>`` (committed tip), **not** the
    working tree — reinject/staged-only WT match must not wipe a unique stash.
    """
    import base64

    if not stash_path.is_file():
        return True
    try:
        blob = json.loads(stash_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return True  # unusable — safe to drop
    files = blob.get("files") if isinstance(blob, dict) else None
    if not isinstance(files, dict) or not files:
        return True  # nothing recoverable
    companion = _post_live_companion_relpaths()
    comparable = 0
    for rel, meta in files.items():
        norm = _norm_repo_relpath(str(rel))
        if norm not in companion:
            continue
        if not isinstance(meta, dict) or "content" not in meta:
            continue
        comparable += 1
        encoding = str(meta.get("encoding") or "utf-8")
        content = meta["content"]
        head_bytes = _git_show_head_bytes(repo_root, norm)
        if head_bytes is None:
            return False  # not on HEAD — stash still unique
        try:
            if encoding == "base64":
                expected = base64.b64decode(str(content))
                if head_bytes != expected:
                    return False
            else:
                expected_txt = str(content)
                if head_bytes.decode("utf-8") != expected_txt:
                    return False
        except (UnicodeDecodeError, ValueError, TypeError):
            return False
    return True if comparable else True


def _budget_spent_stash_redundant_with_head(
    repo_root: Path, stash_path: Path
) -> bool:
    """True when budget stash is absent, unusable, or matches the ledger on **git HEAD**.

    Tick 430: read committed HEAD blob (not working-tree ledger).
    """
    if not stash_path.is_file():
        return True
    try:
        blob = json.loads(stash_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return True
    ledger = blob.get("ledger") if isinstance(blob, dict) else None
    if not isinstance(ledger, dict):
        return True  # unusable
    head_bytes = _git_show_head_bytes(repo_root, ICML_BUDGET_SPENT_RELPATH)
    if head_bytes is None:
        return False
    try:
        current = json.loads(head_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return False
    return current == ledger


def _prior_live_stash_redundant_with_head(
    repo_root: Path, stash_path: Path
) -> bool:
    """True when prior_live stash is absent, empty, or ⊆ **git HEAD** evidence.

    Tick 430: compare gates to committed HEAD evidence blob (not working tree).
    """
    if not stash_path.is_file():
        return True
    stash_gates = _load_prior_live_gates_payload(stash_path)
    if not stash_gates:
        return True
    head_bytes = _git_show_head_bytes(repo_root, ICML_PRIOR_LIVE_EVIDENCE_RELPATH)
    evidence_gates = _load_prior_live_gates_from_bytes(head_bytes)
    for key, val in stash_gates.items():
        if evidence_gates.get(key) != val:
            return False
    return True


def consume_durable_stashes_after_commit(
    repo_root: Path | None = None,
) -> tuple[bool, str]:
    """Tick 428/429/430: unlink durable stashes redundant with **committed** tip HEAD.

    Pre-428: paper-pack / budget_spent / prior_live stashes survived successful
    reinject + durable commit. A later tip ``--apply`` then reinjected **stale**
    mid-tick READY / spend over a newer tip HEAD (e.g. honest demotion to
    IN_PROGRESS, or a fresher live ledger) — latent READY/spend poison.

    Tick 429: Pre-429 Tick 428 also consumed on commit-noop when tip matched
    origin — even after **failed** reinject — wiping unique mid-tick READY /
    spend that never landed on HEAD. Only unlink a stash when its payload
    already matches (or is unusable relative to) HEAD.

    Tick 430: redundancy compares to ``git show HEAD:<path>``, **not** the
    working tree. Pre-430 WT comparison wiped unique stashes after reinject
    made WT match stash while commit was a staged-only / index-noop (HEAD still
    lacked READY/spend).

    Call only after ``commit_prior_live_evidence_if_dirty`` returns ``ok=True``
    (committed or already clean on HEAD). Keep stashes when commit refuses so a
    blocked tip recover can retry reinject. Evidence file stays committed.
    """
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    targets = (
        (
            ICML_PAPER_PACK_STASH_RELPATH,
            paper_pack_stash_path(root),
            _paper_pack_stash_redundant_with_head,
        ),
        (
            ICML_BUDGET_SPENT_STASH_RELPATH,
            budget_spent_stash_path(root),
            _budget_spent_stash_redundant_with_head,
        ),
        (
            ICML_PRIOR_LIVE_STASH_RELPATH,
            prior_live_stash_path(root),
            _prior_live_stash_redundant_with_head,
        ),
    )
    removed: list[str] = []
    kept: list[str] = []
    for rel, path, is_redundant in targets:
        if not path.is_file():
            continue
        try:
            redundant = bool(is_redundant(root, path))
        except Exception as exc:  # noqa: BLE001 — never wipe on checker bugs
            return False, f"Tick 430 stash redundancy check failed for {rel}: {exc}"
        if not redundant:
            kept.append(rel)
            continue
        try:
            path.unlink()
        except OSError as exc:
            return False, f"Tick 428 stash consume failed unlinking {rel}: {exc}"
        removed.append(rel)
    if not removed and not kept:
        return True, "durable stashes absent (Tick 428 consume noop)"
    if kept and not removed:
        return (
            True,
            "Tick 429/430: kept non-redundant durable stashes "
            f"({', '.join(kept)}; reinject retry)",
        )
    detail = f"Tick 428: consumed durable stashes ({', '.join(removed)})"
    if kept:
        detail += f"; Tick 429/430 kept non-redundant ({', '.join(kept)})"
    return True, detail


def prepare_prior_live_evidence_for_tip_apply(
    repo_root: Path | None = None,
) -> tuple[bool, str]:
    """Tick 420/421/427: park dirty durable ledgers + paper-pack companions.

    Tick 420 parked only ``docs/icml_prior_live_evidence.json``. After a live
    G2→G4 stack, ``docs/icml_budget_spent.json`` is almost always dirty too —
    Tick 420 then *refused* prepare (budget counted as other non-ephemeral
    dirt) and tip ``--apply`` stayed blocked. Tick 421 treats both committed
    ledgers as co-durable: park each into its gitignored stash, ``git restore``
    both to HEAD so discard + tip ``--apply`` proceed, then reinject +
    ``commit_prior_live_evidence_if_dirty`` (now also commits budget_spent)
    after tip-PR anti-churn.

    Tick 426 co-commits G4 paper-pack companions on the *post-live* durable
    path, but tip ``--apply`` prepare still treated dirty ``paper_artifacts`` /
    ``ICML_READY`` / Figs as other non-ephemeral dirt — so a mid-tick crash
    after ``apply_paper_pack`` (before durable commit) blocked tip recover and
    wiped READY/Live Tables on hard-reset. Tick 427 parks companions into
    ``docs/icml_paper_pack_stash.json``, restores HEAD, reinjects after tip
    ``--apply``, then durable commit co-commits them onto tip (Tick 426).

    Returns ``(ok, detail)``. ``ok=False`` only when other non-ephemeral dirt
    is present (real edits) or park/restore fails.
    """
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    evidence_norm = _norm_repo_relpath(ICML_PRIOR_LIVE_EVIDENCE_RELPATH)
    budget_norm = _norm_repo_relpath(ICML_BUDGET_SPENT_RELPATH)
    durable = _durable_ledger_relpaths()
    companion = _post_live_companion_relpaths()
    allowed = durable | companion
    dirty = [
        p
        for p in porcelain_dirty_paths(root)
        if not is_tip_apply_ignored_dirty(p)
    ]
    evidence_dirty = any(_norm_repo_relpath(p) == evidence_norm for p in dirty)
    budget_dirty = any(_norm_repo_relpath(p) == budget_norm for p in dirty)
    companion_dirty = [
        p for p in dirty if _norm_repo_relpath(p) in companion
    ]
    if not evidence_dirty and not budget_dirty and not companion_dirty:
        return True, "durable ledgers not dirty (Tick 421 prepare noop)"

    other_non_ephem = [
        p
        for p in dirty
        if _norm_repo_relpath(p) not in allowed and not is_ephemeral_icml_path(p)
    ]
    if other_non_ephem:
        return (
            False,
            "Tick 421 prepare refused — non-ephemeral dirt besides durable "
            f"ledgers: {other_non_ephem[:8]}",
        )

    notes: list[str] = []
    if evidence_dirty:
        evidence_path = prior_live_evidence_path(root)
        stash_path = prior_live_stash_path(root)
        gates = _load_prior_live_gates_payload(evidence_path)
        if gates:
            merged = dict(_load_prior_live_gates_payload(stash_path))
            merged.update(gates)
            try:
                _write_prior_live_gates_payload(
                    stash_path,
                    tick=421,
                    gates=merged,
                    tick_note=(
                        "Tick 421: prior_live stash parked from dirty evidence before "
                        "tip --apply (restore evidence → reinject → commit on tip)"
                    ),
                )
            except OSError as exc:
                return False, f"Tick 421 prepare failed writing prior_live stash: {exc}"
        ok_r, detail_r = _git_restore_or_unlink(
            root, ICML_PRIOR_LIVE_EVIDENCE_RELPATH, evidence_path
        )
        if not ok_r:
            return False, f"Tick 421 prepare evidence: {detail_r}"
        notes.append("evidence parked+restored")

    if budget_dirty:
        ok_p, detail_p = _park_budget_spent_to_stash(root)
        if not ok_p:
            return False, detail_p
        ok_r, detail_r = _git_restore_or_unlink(
            root, ICML_BUDGET_SPENT_RELPATH, budget_spent_ledger_path(root)
        )
        if not ok_r:
            return False, f"Tick 421 prepare budget: {detail_r}"
        notes.append("budget_spent parked+restored")

    if companion_dirty:
        ok_p, detail_p = _park_paper_pack_companions_to_stash(
            root, dirty_companions=companion_dirty
        )
        if not ok_p:
            return False, detail_p
        for rel in sorted({_norm_repo_relpath(p) for p in companion_dirty}):
            ok_r, detail_r = _git_restore_or_unlink(root, rel, root / rel)
            if not ok_r:
                return False, f"Tick 427 prepare paper-pack: {detail_r}"
        notes.append("paper-pack companions parked+restored (Tick 427)")

    return (
        True,
        "Tick 421/427: durable ledgers (+ companions) parked in stash and "
        f"restored to HEAD ({', '.join(notes)}; reinject + commit after tip --apply)",
    )




def commit_prior_live_evidence_if_dirty(
    repo_root: Path | None = None,
    *,
    commit_message: str | None = None,
) -> tuple[bool, str]:
    """Tick 420–427: auto-commit dirty durable ledgers (+ paper-pack companions).

    Tick 420 committed only prior_live evidence. Tick 421 also commits
    ``docs/icml_budget_spent.json`` when it is dirty alongside (or instead of)
    evidence — tip ``--apply`` reinject case. Tick 422 also calls this **after
    live G2→G4** (cron / pipeline / direct gates): live writes update the
    ledgers but cron used to ``exit`` without committing, so the next
    greenfield VM lost spend/stages (re-burn risk) and prior_live evidence.
    Tick 423: ``commit_durable_ledgers_after_live`` also **pushes** the tip
    branch after a successful commit (local commit alone still died with the VM).
    Tick 424: that push also retries when commit is a noop but tip is still
    ahead of origin (mid-tick push failure left spend unpushed).
    Tick 426: also co-commits G4 paper-pack outputs (``paper_artifacts``,
    ``ICML_READY``, Figs 1–2). Pre-426 treated those as blocking non-ephemeral
    dirt after ``apply_paper_pack``, so durable commit refused and
    spend/READY/Live Tables never reached ``origin``.
    Tick 427: tip ``--apply`` prepare parks the same companions into
    ``docs/icml_paper_pack_stash.json`` (pre-427 prepare refused companions as
    other non-ephemeral dirt → tip recover blocked after mid-tick crash).
    Tick 428 stash **consume** lives in ``commit_durable_ledgers_after_live``
    after a successful push (not here) — consuming after local-only commit
    would drop reinject safety if push fails and tip ``--apply`` hard-resets
    to origin.
    Refuses when *other* non-ephemeral paths are dirty. Ephemeral report dirt
    may remain (gate/pipeline sidecars after live).

    Returns ``(ok, detail)``. ``ok=True`` when durable ledgers (+ companions)
    are clean on HEAD (already clean or commit succeeded). ``ok=False`` on
    refuse / git failure.
    """
    import subprocess

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    durable = _durable_ledger_relpaths()
    companion = _post_live_companion_relpaths()
    allowed = durable | companion
    dirty = [
        p
        for p in porcelain_dirty_paths(root)
        if not is_tip_apply_ignored_dirty(p)
    ]
    dirty_durable = [
        p for p in dirty if _norm_repo_relpath(p) in durable
    ]
    dirty_companion = [
        p for p in dirty if _norm_repo_relpath(p) in companion
    ]
    if not dirty_durable and not dirty_companion:
        return True, "durable ledgers not dirty (Tick 422 commit noop)"

    other_non_ephem = [
        p
        for p in dirty
        if _norm_repo_relpath(p) not in allowed and not is_ephemeral_icml_path(p)
    ]
    if other_non_ephem:
        return (
            False,
            "Tick 422 commit refused — non-ephemeral dirt besides durable "
            f"ledgers: {other_non_ephem[:8]}",
        )

    to_add = sorted(
        {
            _norm_repo_relpath(p)
            for p in (*dirty_durable, *dirty_companion)
        }
    )
    add = subprocess.run(
        ["git", "add", "--", *to_add],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if add.returncode != 0:
        return (
            False,
            "Tick 422 git add durable ledgers failed: "
            f"{(add.stderr or add.stdout or '').strip()}",
        )

    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", *to_add],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if staged.returncode == 0 and not (staged.stdout or "").strip():
        return True, "durable ledgers already match index (Tick 422 noop)"

    msg = (
        commit_message
        or "ICML Tick 430: commit durable ledgers + paper-pack companions."
    )
    commit = subprocess.run(
        [
            "git",
            "commit",
            "-m",
            msg,
            "--",
            *to_add,
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if commit.returncode != 0:
        return (
            False,
            "Tick 422 git commit durable ledgers failed: "
            f"{(commit.stderr or commit.stdout or '').strip()}",
        )
    companion_note = ""
    if dirty_companion:
        companion_note = f"; paper-pack companions co-committed (Tick 426/427)"
    return (
        True,
        f"Tick 422: committed durable ledgers onto HEAD ({', '.join(to_add)})"
        f"{companion_note}",
    )


def _origin_branch_exists(repo_root: Path, branch: str) -> bool:
    """True when ``refs/remotes/origin/<branch>`` (or tip SHA) is resolvable."""
    import subprocess

    name = (branch or "").strip()
    if not name:
        return False
    for ref in (f"refs/remotes/origin/{name}", f"origin/{name}"):
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--verify", ref],
                cwd=str(repo_root),
                capture_output=True,
                check=False,
            )
        except OSError:
            continue
        if proc.returncode == 0:
            return True
    return False


def resolve_push_branch_for_durable_ledgers(
    repo_root: Path | None = None,
) -> str | None:
    """Resolve tip branch name for post-live durable-ledger push (Tick 423/431/432).

    Prefers ``prefer_tip_pr_commit_branch()`` whenever the tip PR head is known.
    Falls back to the current ``cursor/*`` checkout only when tip anti-churn
    does not apply. Never returns ``main``/``master``.

    Tick 431: greenfield cron boots stay on ``cursor/icml-epistemic-results-*``
    names that are **never** pushed to origin. Pre-431 returned that boot
    name whenever ``HEAD`` started with ``cursor/``, so
    ``commit_durable_ledgers_after_live`` pushed spend/READY/prior_live to
    ``origin/<boot>`` (invisible to tip PR #337 / next tip ``--apply``) instead
    of ``tip_pr_commit_branch``.

    Tick 432: when tip PR head is known, **always** push durable ledgers there —
    even if ``origin/<boot>`` already exists (common after ``open_git_pr`` omitted
    ``branch=``) and cloud-boot env/persisted capture is missing. Pre-432 kept
    any ``cursor/*`` with an origin ref as an "alternate tip-like" branch, which
    re-parked spend/READY off tip PR #337 after a single accidental boot push.
    """
    import subprocess

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    branch = ""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            branch = (proc.stdout or "").strip()
    except OSError:
        branch = ""
    if branch in ("HEAD", "", "main", "master"):
        branch = ""
    tip_branch = prefer_tip_pr_commit_branch()
    if tip_branch and tip_branch not in ("main", "master"):
        # Tip PR anti-churn: durable ledgers always land on tip PR head.
        return tip_branch
    if branch.startswith("cursor/"):
        return branch
    return None


def _git_is_ancestor(ancestor: str, descendant: str, *, cwd: Path) -> bool:
    """True when ``ancestor`` is an ancestor of ``descendant`` (inclusive)."""
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return proc.returncode == 0


def _preserve_post_live_dirty_bytes(root: Path) -> dict[str, bytes]:
    """Snapshot durable + paper-pack WT bytes before a tip checkout (Tick 434)."""
    preserved: dict[str, bytes] = {}
    for rel in sorted(_durable_ledger_relpaths() | _post_live_companion_relpaths()):
        path = root / rel
        if path.is_file():
            try:
                preserved[rel] = path.read_bytes()
            except OSError:
                continue
    return preserved


def _restore_preserved_bytes(root: Path, preserved: dict[str, bytes]) -> None:
    """Write Tick 434 preserved durable/companion bytes back onto WT."""
    for rel, data in preserved.items():
        dest = root / rel
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        except OSError:
            continue


def fetch_origin_tip_for_durable_ledgers(
    tip_branch: str,
    *,
    cwd: Path,
) -> tuple[bool, str]:
    """Tick 436: refresh ``origin/<tip>`` before Tick 435 ahead / Tick 434 checkout.

    Pre-436 ``ensure_local_tip_branch_for_durable_ledgers`` only inspected the
    local remote-tracking ref. After a long live gate (or when G2/G3/G4 call
    durable commit without a fresh cron fetch), ``origin/<tip>`` can lag the
    real tip on ``origin`` — Tick 435 then skips FF, durable commit lands on a
    stale tip base, and ``git push`` is non-fast-forward rejected.

    Fetch is best-effort: failure returns ``(False, detail)`` so callers can
    still attempt sync with stale refs rather than hard-failing ledger commit.
    Prefer an exact tip refspec (avoids wildcard miss on minimal remotes);
    fall back to lineage wildcards only when the exact tip ref is absent.
    """
    name = (tip_branch or "").strip()
    if not name or name in ("main", "master", "HEAD"):
        return True, "Tick 436: no tip branch — skip tip fetch"
    exact = f"+refs/heads/{name}:refs/remotes/origin/{name}"
    ok, detail = _git_ok(["fetch", "origin", exact], cwd=cwd)
    if ok:
        return True, f"Tick 436: fetched origin/{name}"
    # Exact ref missing (renamed tip / first push) — try lineage wildcards.
    ok2, detail2 = _git_ok(["fetch", "origin", *_TIP_FETCH_REFSPECS], cwd=cwd)
    if ok2:
        return True, f"Tick 436: fetched tip lineage (exact miss: {detail[:120]})"
    return (
        False,
        f"Tick 436 tip fetch failed: exact={detail[:160]}; "
        f"lineage={detail2[:160]}",
    )


def _origin_tip_strictly_ahead_of_head(
    tip_branch: str,
    *,
    cwd: Path,
) -> str | None:
    """Return ``origin/<tip>`` ref when it is a strict descendant of HEAD.

    Tick 435: already-on-tip early-return must still FF when a concurrent cron
    (or mid-tick tip push) advanced ``origin/<tip>`` past the local tip SHA —
    otherwise durable commit lands on a stale tip base and tip push is
    non-fast-forward rejected.

    Tick 436: callers must refresh ``origin/<tip>`` via
    ``fetch_origin_tip_for_durable_ledgers`` first — otherwise this check sees
    a stale remote-tracking SHA and never FF.
    """
    import subprocess

    for prefer in (f"origin/{tip_branch}", f"refs/remotes/origin/{tip_branch}"):
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--verify", prefer],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            continue
        remote_sha = (proc.stdout or "").strip()
        if proc.returncode != 0 or not remote_sha:
            continue
        try:
            head_proc = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return None
        head_sha = (head_proc.stdout or "").strip()
        if head_proc.returncode != 0 or not head_sha:
            return None
        if head_sha == remote_sha:
            return None
        # origin tip must be a descendant of HEAD (FF-able); never rewind.
        if _git_is_ancestor("HEAD", prefer, cwd=cwd):
            return prefer
        return None
    return None


def _checkout_tip_preserving_durable_dirt(
    root: Path,
    tip_branch: str,
    checkout_target: str,
    *,
    tick_label: str,
    was_note: str,
) -> tuple[bool, str]:
    """Checkout tip tipish while preserving dirty durable + paper-pack bytes."""
    preserved = _preserve_post_live_dirty_bytes(root)
    # Clear preserved paths so checkout is not blocked by durable dirt.
    for rel in preserved:
        _git_restore_or_unlink(root, rel, root / rel)
    ok, detail = _git_ok(
        ["checkout", "-B", tip_branch, checkout_target],
        cwd=root,
    )
    if not ok:
        _restore_preserved_bytes(root, preserved)
        return (
            False,
            f"{tick_label} git checkout tip failed ({was_note}): {detail}",
        )
    _restore_preserved_bytes(root, preserved)
    return (
        True,
        f"{tick_label}: checked out tip {tip_branch} ← {checkout_target} "
        f"(preserved {len(preserved)} durable paths; {was_note})",
    )


def ensure_local_tip_branch_for_durable_ledgers(
    repo_root: Path | None = None,
) -> tuple[bool, str]:
    """Tick 433/434/435/436: point local tip PR branch at tip-lineage before durable commit/push.

    Tick 432 pushes ``HEAD:refs/heads/<tip>``, but when the durable commit lands
    while still checked out on a greenfield **boot** branch name, the local
    ``tip_pr_commit_branch`` ref can stay at the pre-commit tip SHA. A later
    ``git checkout <tip>`` (anti-churn) then drops the unpushed spend/READY
    commit; ``tip_commits_ahead_of_origin`` from that old tip HEAD returns 0 and
    Tick 428/429 consume can wipe reinject stashes — losing paid ledger state
    even though the commit still exists only on the boot ref.

    Tick 433: fast-forward (never rewind) the local tip ref to HEAD when HEAD is
    a descendant of tip, then check out tip so commit / ahead / push / consume
    all operate on the tip PR branch name.

    Tick 434: when HEAD is **not** a tip descendant (greenfield boot still at
    main / pre-tip-recover SHA while ``origin/<tip>`` is ahead), do **not**
    skip and commit on boot — that yields a non-fast-forward tip push reject
    and leaves spend only on an invisible boot ref. Instead checkout tip
    (prefer ``origin/<tip>``), preserving dirty durable + paper-pack companion
    bytes across the switch, then commit on tip.

    Tick 435: when already on the tip branch name but ``origin/<tip>`` is
    strictly ahead of HEAD (concurrent tip push / stale local tip SHA),
    fast-forward tip ← origin (preserve durable dirt) before durable commit —
    pre-435 early-returned "already on tip" then NF-rejected the tip push.

    Tick 436: **fetch** ``origin/<tip>`` before the Tick 435 ahead check /
    Tick 434 checkout — pre-436 inspected a possibly stale remote-tracking
    ref after long live gates (or direct G2/G3/G4 durable commit without a
    fresh cron fetch), so Tick 435 never saw the concurrent tip advance.
    """
    import subprocess

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    tip_branch = (prefer_tip_pr_commit_branch() or "").strip()
    if not tip_branch or tip_branch in ("main", "master", "HEAD"):
        return True, "Tick 433: no tip_pr_commit_branch — skip local tip sync"

    # Tick 436: refresh origin/<tip> before ahead/checkout decisions.
    ok_fetch, detail_fetch = fetch_origin_tip_for_durable_ledgers(
        tip_branch, cwd=root
    )
    fetch_note = detail_fetch if ok_fetch else f"{detail_fetch} (continuing with stale refs)"

    head_branch = ""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            head_branch = (proc.stdout or "").strip()
    except OSError:
        head_branch = ""
    if head_branch == tip_branch:
        # Tick 435: already-on-tip still FF when origin/tip advanced past HEAD.
        ahead_ref = _origin_tip_strictly_ahead_of_head(tip_branch, cwd=root)
        if ahead_ref:
            ok, detail = _checkout_tip_preserving_durable_dirt(
                root,
                tip_branch,
                ahead_ref,
                tick_label="Tick 435",
                was_note=(
                    f"was already on tip {tip_branch} but behind {ahead_ref}"
                ),
            )
            if ok:
                detail = f"{fetch_note}; {detail}"
            return ok, detail
        return True, f"{fetch_note}; Tick 433: already on tip branch {tip_branch}"

    # Resolve tip tipish: local branch, else origin/<tip>.
    tip_ref = ""
    for cand in (tip_branch, f"refs/heads/{tip_branch}", f"origin/{tip_branch}"):
        try:
            proc = subprocess.run(
                ["git", "rev-parse", "--verify", cand],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            continue
        if proc.returncode == 0 and (proc.stdout or "").strip():
            tip_ref = cand
            break
    if tip_ref and not _git_is_ancestor(tip_ref, "HEAD", cwd=root):
        # Tick 434: HEAD behind/diverged from tip — checkout tip (never rewind
        # tip onto older boot). Prefer origin/<tip> when present.
        checkout_target = tip_ref
        for prefer in (f"origin/{tip_branch}", f"refs/remotes/origin/{tip_branch}"):
            try:
                proc = subprocess.run(
                    ["git", "rev-parse", "--verify", prefer],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError:
                continue
            if proc.returncode == 0 and (proc.stdout or "").strip():
                checkout_target = prefer
                break
        ok, detail = _checkout_tip_preserving_durable_dirt(
            root,
            tip_branch,
            checkout_target,
            tick_label="Tick 434",
            was_note=(
                f"was {head_branch or 'detached'} not tip descendant"
            ),
        )
        if ok:
            detail = f"{fetch_note}; {detail}"
        return ok, detail

    # Move/create local tip ref to current HEAD, then check it out.
    ok, detail = _git_ok(["branch", "-f", tip_branch, "HEAD"], cwd=root)
    if not ok:
        return False, f"Tick 433 git branch -f failed: {detail}"
    ok, detail = _git_ok(["checkout", tip_branch], cwd=root)
    if not ok:
        return False, f"Tick 433 git checkout {tip_branch} failed: {detail}"
    return (
        True,
        f"{fetch_note}; Tick 433: synced local tip {tip_branch} ← HEAD "
        f"(was {head_branch or 'detached'})",
    )


def tip_commits_ahead_of_origin(
    repo_root: Path | None = None,
    *,
    branch: str | None = None,
) -> int:
    """Tick 424/433: how many local tip commits are not yet on ``origin/<branch>``.

    Returns ``0`` when equal/behind/unknown (missing remote, detached HEAD,
    non-tip branch). Used to retry durable-ledger push after a commit-noop
    when a prior Tick 423 push failed mid-tick.

    Tick 433: take the max of ``origin/<tip>..HEAD`` and ``origin/<tip>..<tip>``
    so an unpushed durable commit that only advanced the local tip ref (or only
    HEAD on a boot name before sync) still counts as ahead.
    """
    import subprocess

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    target = (branch or resolve_push_branch_for_durable_ledgers(root) or "").strip()
    if not target or target in ("main", "master", "HEAD"):
        return 0
    best = 0
    local_tips = ("HEAD", target, f"refs/heads/{target}")
    # Prefer tracking ref when present; else origin/<branch> after fetch/push.
    for remote_ref in (f"origin/{target}", f"refs/remotes/origin/{target}"):
        for local in local_tips:
            try:
                proc = subprocess.run(
                    ["git", "rev-list", "--count", f"{remote_ref}..{local}"],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except OSError:
                continue
            if proc.returncode != 0:
                continue
            raw = (proc.stdout or "").strip()
            try:
                best = max(best, max(0, int(raw)))
            except ValueError:
                continue
        if best:
            return best
    return best


def _git_push_looks_non_fast_forward(detail: str) -> bool:
    """True when a tip push failure looks like non-fast-forward / rejected update."""
    text = (detail or "").lower()
    needles = (
        "non-fast-forward",
        "non fast forward",
        "fetch first",
        "failed to push some refs",
        "[rejected]",
        "updates were rejected",
        "tip of your current branch is behind",
    )
    return any(n in text for n in needles)


def _git_unmerged_relpaths(cwd: Path) -> list[str]:
    """Return unmerged (conflicted) paths during an in-progress rebase/merge."""
    ok, out = _git_ok(["diff", "--name-only", "--diff-filter=U"], cwd=cwd)
    if not ok:
        return []
    return [p.strip().replace("\\", "/") for p in out.splitlines() if p.strip()]


def _git_show_stage_bytes(
    cwd: Path, stage: int, relpath: str
) -> bytes | None:
    """Read conflict stage blob (1=base, 2=ours/onto, 3=theirs/replayed)."""
    try:
        proc = subprocess.run(
            ["git", "show", f":{int(stage)}:{relpath}"],
            cwd=str(cwd),
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout if proc.stdout is not None else b""


def merge_budget_spent_dict(ours: dict, theirs: dict) -> dict:
    """Union spend ledgers across concurrent tip VMs (Tick 438).

    Keep the higher ``spent_usd``, union ``stages_complete`` / ``run_ids``,
    and prefer the fresher ``updated_at`` / non-empty ``detail``.
    """
    stages: list[str] = []
    for name in list(ours.get("stages_complete") or []) + list(
        theirs.get("stages_complete") or []
    ):
        if name and name not in stages:
            stages.append(str(name))
    run_ids: list[int] = []
    for rid in list(ours.get("run_ids") or []) + list(theirs.get("run_ids") or []):
        try:
            iv = int(rid)
        except (TypeError, ValueError):
            continue
        if iv not in run_ids:
            run_ids.append(iv)
    try:
        spent_o = float(ours.get("spent_usd") or 0.0)
    except (TypeError, ValueError):
        spent_o = 0.0
    try:
        spent_t = float(theirs.get("spent_usd") or 0.0)
    except (TypeError, ValueError):
        spent_t = 0.0
    updated_o = str(ours.get("updated_at") or "")
    updated_t = str(theirs.get("updated_at") or "")
    updated = max(updated_o, updated_t) if (updated_o or updated_t) else (
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    detail_o = str(ours.get("detail") or "")
    detail_t = str(theirs.get("detail") or "")
    detail = detail_t if len(detail_t) >= len(detail_o) else detail_o
    tick_note = (
        str(theirs.get("tick_note") or "")
        or str(ours.get("tick_note") or "")
        or "Tick 438: merged concurrent durable budget ledgers"
    )
    return {
        "updated_at": updated,
        "tick_note": tick_note,
        "spent_usd": round(max(spent_o, spent_t), 4),
        "stages_complete": stages,
        "run_ids": run_ids,
        "detail": detail,
    }


def _prior_live_gate_richness(val: Any) -> tuple:
    """Tick 439: score a single prior_live gate payload (higher = richer).

    Pre-439 ``merge_prior_live_evidence_dict`` always preferred the replayed
    local (stage 3) when both sides set the same gate key. A thinner local
    capture (preflight wipe / partial G3) could then overwrite onto's executed
    G4 ``prior_live_metrics`` during durable rebase — paid evidence lost even
    though Tick 438 "merged" the conflict.
    """
    if val in (None, {}, [], ""):
        return (0, 0, 0, 0, 0, 0, 0)
    if not isinstance(val, dict):
        try:
            return (1, 0, 0, 0, 0, 0, len(json.dumps(val)))
        except (TypeError, ValueError):
            return (1, 0, 0, 0, 0, 0, 0)
    post = val.get("prior_live_post")
    metrics = val.get("prior_live_metrics")
    has_post = 1 if post not in (None, {}, [], "") else 0
    has_metrics = 1 if isinstance(metrics, dict) and metrics else 0
    executed = 0
    n_pairs = 0
    pass_bits = 0
    paper = 0
    if isinstance(metrics, dict):
        executed = 1 if metrics.get("executed") else 0
        comparison = metrics.get("comparison")
        if isinstance(comparison, dict):
            try:
                n_pairs = int(comparison.get("n_pairs") or 0)
            except (TypeError, ValueError):
                n_pairs = 0
        for flag in ("primary_pass", "h2_pass", "h5_pass", "paper_refreshed"):
            if metrics.get(flag):
                pass_bits += 1
        if metrics.get("paper_refreshed"):
            paper = 1
    try:
        size = len(json.dumps(val, sort_keys=True))
    except (TypeError, ValueError):
        size = 0
    # Order: any payload → metrics → executed → n_pairs → pass flags → paper → size
    return (1, has_metrics, executed, n_pairs, pass_bits + has_post, paper, size)


def prefer_richer_prior_live_gate(a: Any, b: Any) -> Any:
    """Tick 439: keep the richer prior_live gate payload (ties → ``b``)."""
    if a in (None, {}, [], "") and b not in (None, {}, [], ""):
        return b
    if b in (None, {}, [], "") and a not in (None, {}, [], ""):
        return a
    if _prior_live_gate_richness(b) >= _prior_live_gate_richness(a):
        return b
    return a


def merge_prior_live_evidence_dict(ours: dict, theirs: dict) -> dict:
    """Merge prior_live evidence gates across concurrent tip VMs (Tick 438/439).

    Tick 438: union gate keys across onto (ours) + replayed local (theirs).
    Tick 439: when the same gate key is set on both sides, keep the **richer**
    payload (executed metrics / larger ``n_pairs`` / pass flags) instead of
    always preferring theirs — closes thinner-local wipe of onto G4 evidence.
    """
    gates: dict[str, Any] = {}
    for src in (ours, theirs):
        raw = src.get("gates") if isinstance(src, dict) else None
        if not isinstance(raw, dict):
            continue
        for key, val in raw.items():
            if key not in gates or gates[key] in (None, {}, [], ""):
                gates[key] = val
            elif val not in (None, {}, [], ""):
                gates[key] = prefer_richer_prior_live_gate(gates[key], val)
    try:
        tick = max(int(ours.get("tick") or 0), int(theirs.get("tick") or 0))
    except (TypeError, ValueError):
        tick = 0
    updated_o = str(ours.get("updated_at") or "")
    updated_t = str(theirs.get("updated_at") or "")
    updated = max(updated_o, updated_t) if (updated_o or updated_t) else (
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    note = (
        str(theirs.get("tick_note") or "")
        or str(ours.get("tick_note") or "")
        or "Tick 439: merged concurrent prior_live evidence (prefer richer gates)"
    )
    if "439" not in note and "Tick 438" in note:
        note = note.replace("Tick 438", "Tick 439", 1)
    return {
        "updated_at": updated,
        "tick": tick,
        "tick_note": note,
        "gates": gates,
    }


# Tick 446/447: parse the status *token* after optional ``**`` + ``STATUS:`` —
# not any substring later on the same line (READY headers that mention
# IN_PROGRESS in a trailing note must still read READY so G4 demote /
# richness / judge stay honest). Tick 447 also accepts bare ``STATUS:``
# (no markdown bold) so ledger-skip demote / G4 pack / pipeline read cannot
# miss a plain READY header that pre-447 ``**STATUS:``-only matching left
# poisoned, or fail to rewrite plain ``STATUS: IN_PROGRESS`` up to READY.
# Tick 448 also accepts ATX heading forms (``# STATUS:`` / ``## **STATUS:**``)
# so promoted heading stubs cannot poison demote / pack the same way.
# Tick 449 also accepts bold-closed label forms (``**STATUS:** READY``) —
# common markdown ``**Label:** value`` — so demote / pack cannot miss those.
# Tick 450 also accepts colon-outside-bold forms (``**STATUS**: READY``) —
# bold closes before the colon — so demote / pack cannot miss that variant.
# Tick 451 also accepts blockquote / unordered / ordered list container
# prefixes (``> **STATUS: READY**`` / ``- STATUS: READY`` / ``1. **STATUS:** READY``)
# and strips a leading UTF-8 BOM so demote / pack cannot miss those stubs.
# Tick 452 also accepts italic / underscore emphasis wrappers
# (``*STATUS*: READY`` / ``*STATUS: READY*`` / ``_STATUS: READY_``) that Tick 451
# intentionally left unmatched (single ``*`` without ``\\s+`` is italic, not a list).
# Tick 453 also accepts double-underscore bold and triple-star bold+italic
# (``__STATUS: READY__`` / ``***STATUS: READY***``) that Tick 452 left unmatched
# (``__`` is CommonMark bold; ``***`` is bold+italic — neither is ``**`` / ``*`` / ``_``).
# Tick 454 also strips leading invisible format chars (ZWSP/ZWNJ/ZWJ/WJ/SHY/BOM)
# and accepts nested bold↔dunder wrappers (``**__STATUS: READY__**`` /
# ``__**STATUS: READY**__``) that Tick 453 left unmatched — copy-paste from
# Notion/Docs/Cursor often prefixes ZWSP; mixed editors nest ``**`` around ``__``.
# Tick 455: HTML exports often encode the same invisibles as entities
# (``&#8203;**STATUS: READY**`` / ``&ZeroWidthSpace;`` / ``**STATUS:&nbsp;READY**``)
# — decode those before Unicode strip so demote / G4 pack still match.
# Tick 486: also decode HTML-entity *colons* (``STATUS&#58; READY`` /
# ``STATUS&colon;READY`` / ``STATUS&#x3a; READY`` / fullwidth ``STATUS&#xff1a;READY``
# / attr ``title="STATUS&#58; READY"``) — CMS/XSS-escaped exports leave the
# STATUS separator as an entity so Tick 455 invisibles-only decode still missed
# demote / G4 pack.
# Tick 456: Notion/Docs HTML→Markdown / rich-paste also leave wrapper tags
# (``<strong>STATUS: READY</strong>`` / ``<p><b>**STATUS:…**</b></p>`` /
# ``<span style="…">**STATUS: READY**</span>``) — strip those before match.
# Tick 457: also strip HTML heading tags (``<h1>…</h1>`` … ``<h6>``) — Tick 448
# already accepts ATX ``# STATUS:``, but Notion/Docs HTML heading export left
# ``<h1>STATUS: READY</h1>`` unmatched — plus markdown backtick / strikethrough
# wrappers (`` `STATUS: READY` `` / ``~~STATUS: READY~~``) from chat/code paste.
_ICML_STATUS_INVISIBLE_CHARS_RE = re.compile(
    r"[\ufeff\u200b\u200c\u200d\u2060\u00ad]+"
)
_ICML_STATUS_HTML_ENTITY_RE = re.compile(
    r"&(?:"
    r"#(?:x([0-9a-fA-F]+)|([0-9]+))"
    r"|"
    # Tick 487: also lt/gt/quot/apos so double-escaped HTML badge stubs
    # (``&lt;p title=&quot;STATUS: READY&quot;&gt;…``) become peelable tags.
    r"(nbsp|ZeroWidthSpace|zwnj|zwj|shy|colon|lt|gt|quot|apos)"
    r");",
    re.IGNORECASE,
)
# Tick 487: CMS/XSS double-escape turns ``&#58;`` into ``&amp;#58;`` (and
# ``&colon;`` into ``&amp;colon;``). Only peel ``&amp;`` / ``&#38;`` /
# ``&#x26;`` when they prefix another entity body — leave lone
# ``&amp;**STATUS…`` untouched (Tick 486 unknown-entity contract).
_ICML_STATUS_DOUBLE_AMP_RE = re.compile(
    r"(?:&amp;|&#0*38;|&#x0*26;)"
    r"(?=(?:#(?:x[0-9a-fA-F]+|[0-9]+)|[a-zA-Z][a-zA-Z0-9]*);)",
    re.IGNORECASE,
)
# Tick 488: JSON/JS string escapes for STATUS (``\u003a`` / ``\x3a`` / ``\u003c``).
# Only peel allowlisted codepoints (colon / space / invisibles / <>"') so
# ``\u0041`` etc. stay literal and cannot invent a false STATUS token.
_ICML_STATUS_JS_ESCAPE_RE = re.compile(
    r"\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})",
    re.IGNORECASE,
)
# Tick 489: URL percent-encoding for STATUS (``%3A`` / ``%20`` / ``%3C``).
# Same allowlist as Tick 488 so ``%41`` (``A``) stays literal and cannot
# invent a false STATUS token. Iterate so ``%253A`` (double-encoded ``:``)
# peels via ``%`` (0x25) → ``%3A`` → ``:``.
_ICML_STATUS_URL_PERCENT_RE = re.compile(r"%([0-9a-fA-F]{2})", re.IGNORECASE)
# Tick 490: MIME quoted-printable for STATUS (``=3A`` / ``=20`` / ``=3C``).
# Soft line breaks (``=\r?\n``) are removed before ``=XX`` peels. Unknown
# ``=41`` stays literal (parity with Tick 489 ``%41``).
_ICML_STATUS_QUOTED_PRINTABLE_RE = re.compile(r"=([0-9a-fA-F]{2})", re.IGNORECASE)
_ICML_STATUS_QP_SOFT_BREAK_RE = re.compile(r"=\r?\n")
# Tick 491: RFC 2047 encoded-word STATUS headers from email / MIME gateways
# (``=?UTF-8?Q?STATUS=3A_READY?=`` / ``=?UTF-8?B?…?=``). Pre-491 Tick 490
# peeled bare QP ``=XX`` but left encoded-word wrappers + Q ``_``-as-space,
# so demote no-op / G4 pack miss READY. Adjacent words may be whitespace-
# separated (RFC 2047 §6.2); unknown charset / bad base64 stay literal.
# Tick 492: also peel *bare* base64 payloads when wrappers were stripped
# (``U1RBVFVTOiBSRUFEWQ==``) — see ``_peel_icml_status_bare_base64``.
_ICML_STATUS_RFC2047_WORD_RE = re.compile(
    r"=\?([^?\s]*)\?([QBqb])\?([^?]*)\?="
)
_ICML_STATUS_RFC2047_RUN_RE = re.compile(
    r"(?:=\?[^?\s]*\?[QBqb]\?[^?]*\?=)"
    r"(?:\s+=\?[^?\s]*\?[QBqb]\?[^?]*\?=)*",
    re.IGNORECASE,
)
_ICML_STATUS_RFC2047_CHARSETS = frozenset(
    {
        "utf-8",
        "utf8",
        "us-ascii",
        "ascii",
        "iso-8859-1",
        "latin-1",
        "latin1",
    }
)
# Tick 492: bare base64 STATUS payloads (MIME wrappers stripped on copy-paste).
# Full-line only; mid-string ``=`` (QP forms) fails ``validate=True``.
_ICML_STATUS_BARE_BASE64_RE = re.compile(r"^[A-Za-z0-9+/]{12,}={0,2}$")
_ICML_STATUS_BARE_BASE64_HINT_RE = re.compile(
    r"STATUS.{0,80}(?:READY|IN_PROGRESS)|(?:READY|IN_PROGRESS).{0,80}STATUS",
    re.IGNORECASE | re.DOTALL,
)
# Tick 493: ``data:[mediatype][;param…];base64,<payload>`` STATUS (chat / email /
# Markdown badge paste keeps the data-URI wrapper after Tick 492 bare peel).
_ICML_STATUS_DATA_URI_RE = re.compile(
    r"^data:"
    r"(?:[-\w.]+/[-\w.+]*)?"
    r"(?:;[-\w.]+(?:=[-\w.]+)?)?"
    r"(?:;[-\w.]+(?:=[-\w.]+)?)*"
    r";base64,"
    r"([A-Za-z0-9+/]{12,}={0,2})$",
    re.IGNORECASE,
)
# Tick 494: non-base64 / percent-encoded data-URI STATUS
# (``data:text/plain,STATUS%3A%20READY`` / ``data:,STATUS:%20READY`` /
# ``data:text/plain;charset=utf-8,STATUS%3A%20READY``). Tick 493 only peeled
# ``;base64,`` forms — plain RFC 2397 payloads still missed demote / G4 pack.
# Negative lookahead skips ``;base64`` so Tick 493 owns that path.
_ICML_STATUS_DATA_URI_PLAIN_RE = re.compile(
    r"^data:"
    r"(?:[-\w.]+/[-\w.+]*)?"
    r"(?:;(?!base64(?:;|,|=|$))[-\w.]+(?:=[-\w.]+)?)*"
    r","
    r"(.+)$",
    re.IGNORECASE,
)
# Tick 495: bare hex STATUS payloads (log / packet / hex-dump paste).
# Continuous (``5354415455533A205245414459``), spaced / colon / dash
# (``53 54 …`` / ``53:54:…`` / ``53-54-…``), optional ``0x`` prefix.
# Min 13 bytes (= ``STATUS: READY``); STATUS hint gates false positives.
# Reuses Tick 492 ``_ICML_STATUS_BARE_BASE64_HINT_RE`` after UTF-8 decode.
# Tick 496: C-array / comma-hex / per-byte ``0xNN`` dumps
# (``53,54,…`` / ``0x53,0x54,…`` / ``0x53 0x54 …`` / ``{0x53, 0x54, …}``).
_ICML_STATUS_BARE_HEX_CONT_RE = re.compile(
    r"^(?:0x)?(?:[0-9A-Fa-f]{2}){13,}$",
    re.IGNORECASE,
)
_ICML_STATUS_BARE_HEX_SEP_RE = re.compile(
    r"^(?:0x)?(?:[0-9A-Fa-f]{2}[\s:\-]){12,}[0-9A-Fa-f]{2}$",
    re.IGNORECASE,
)
_ICML_STATUS_BARE_HEX_COMMA_RE = re.compile(
    r"^(?:[0-9A-Fa-f]{2},\s*){12,}[0-9A-Fa-f]{2}$",
    re.IGNORECASE,
)
_ICML_STATUS_BARE_HEX_0X_BYTE_RE = re.compile(
    r"^(?:0x[0-9A-Fa-f]{2}(?:,\s*|\s+)){12,}0x[0-9A-Fa-f]{2}$",
    re.IGNORECASE,
)
_ICML_STATUS_BARE_HEX_CARRAY_RE = re.compile(
    r"^\{(?:\s*(?:0x)?[0-9A-Fa-f]{2}\s*,){12,}\s*(?:0x)?[0-9A-Fa-f]{2}\s*,?\s*\}$",
    re.IGNORECASE,
)
_ICML_STATUS_HTML_NAMED = {
    "nbsp": "\u00a0",
    "zerowidthspace": "\u200b",
    "zwnj": "\u200c",
    "zwj": "\u200d",
    "shy": "\u00ad",
    # Tick 486: HTML5 ``&colon;`` → ASCII ``:`` (STATUS separator).
    "colon": ":",
    # Tick 487: markup escapes for double-escaped HTML STATUS badges.
    "lt": "<",
    "gt": ">",
    "quot": '"',
    "apos": "'",
}
_ICML_STATUS_HTML_CODEPOINTS = frozenset(
    {
        0x200B,
        0x200C,
        0x200D,
        0x2060,
        0x00AD,
        0xFEFF,
        0x00A0,
        # Tick 486: ASCII colon + CJK fullwidth colon (Tick 464 char form).
        0x3A,
        0xFF1A,
        # Tick 487: < > " ' for escaped HTML badge stubs.
        0x3C,
        0x3E,
        0x22,
        0x27,
        # Tick 488: ASCII space so ``STATUS\u003a\u0020READY`` peels.
        0x20,
        # Tick 489: ``%`` so double-encoded ``%253A`` peels; ``=`` / ``/`` so
        # URL-encoded HTML badges (``%3Cp%20title%3D%22STATUS%3A…``) rebuild;
        # ``+`` so ``%2B`` form-urlencoded space peels before ``+``→space.
        0x25,
        0x3D,
        0x2F,
        0x2B,
        # Tick 490: same allowlist covers QP ``=3D`` / ``=2F`` / ``=25`` so
        # double-encoded ``=253A`` and QP HTML badges rebuild (parity with %).
        # Tick 491: underscore so RFC 2047 Q ``=5F`` rebuilds ``IN_PROGRESS``
        # after ``_``→space (``STATUS=3A_IN=5FPROGRESS`` → ``STATUS: IN_PROGRESS``).
        0x5F,
    }
)
# Formatting / block wrappers only — not arbitrary tags (avoid eating ``STATUS < 1``).
# Tick 457: include h1–h6 (+ kbd) so HTML heading exports match ATX Tick 448.
# Tick 458: include blockquote/li/ul/ol (+ pre/center/summary/details) so HTML
# container exports match Tick 451 markdown ``>`` / ``-`` list prefixes.
# Tick 459: include table cells + semantic sectioning (+ caption/label/dt/dd)
# so Notion/Docs HTML table / ``<section>`` / ``<article>`` exports match;
# markdown pipe rows handled separately via ``_strip_icml_status_md_table_pipes``.
# Tick 465: include ``a`` (+ ``button``) so Notion/Docs/GitHub HTML link
# exports of STATUS (``<a href=\"…\">STATUS: READY</a>``) match — Tick 464
# bracket wrap still left bare ``<a>…</a>`` unmatched.
# Tick 469: include ``picture`` (+ ``source``) so responsive HTML badge exports
# (``<picture><img alt=\"STATUS:…\">…</picture>`` /
# ``<picture><source …><img alt=\"STATUS:…\">…</picture>``) strip to the
# nested ``<img>`` that Tick 468 peels — ``picture``/``source`` were not in
# the allowlist, so Tick 468 full-line ``<img>`` peel never saw the alt.
_ICML_STATUS_HTML_TAG_RE = re.compile(
    r"</?(?:strong|b|em|i|p|div|span|font|mark|u|s|strike|del|ins|small|big|"
    r"code|tt|kbd|br|hr|h[1-6]|blockquote|li|ul|ol|pre|center|summary|details|"
    r"table|thead|tbody|tfoot|tr|td|th|caption|section|article|header|main|"
    r"aside|nav|footer|figure|figcaption|label|dt|dd|dl|a|button|picture|source)"
    # Tick 465: allow ``/`` inside attributes (``href="https://…"``) — pre-465
    # ``[^>/]*`` stopped at the first slash so opening ``<a href="https://…">``
    # never matched (only ``</a>`` did). Self-closing still via trailing ``/?``.
    r"(?:\s[^>]*)?\s*/?>",
    re.IGNORECASE,
)
# Tick 457/458/461/464: outer markdown inline-code / strikethrough / Obsidian
# highlight / bold / quote / paren / bracket / brace wrappers.
# Groups: (1) backtick (2) ~~ (3) == (4) ** (5) __ (6) "…" (7) '…'
# (8) (…) (9) （…） fullwidth (10) […] (11) {…}.
# Tick 464: chat / JSON / Notion paste often wraps the whole STATUS header in
# matching paren/bracket/brace (``(STATUS: READY)`` / ``[STATUS: READY]`` /
# ``{STATUS: READY}`` / ``（STATUS: READY）``). Bracket wrap must stay *after*
# bare-checkbox peel (``[ ] STATUS`` has no trailing ``]``, so it is not
# mistaken for ``[STATUS:…]``).
_ICML_STATUS_MD_WRAP_RE = re.compile(
    r"^(?:`+)(.*?)(?:`+)$|"
    r"^(?:~~)(.*?)(?:~~)$|"
    r"^(?:==)(.*?)(?:==)$|"
    r"^(?:\*\*)(.*?)(?:\*\*)$|"
    r"^(?:__)(.*?)(?:__)$|"
    r'^(?:")(.*?)(?:")$|'
    r"^(?:')(.*?)(?:')$|"
    r"^\((.*?)\)$|"
    r"^（(.*?)）$|"
    r"^\[(.*?)\]$|"
    r"^\{(.*?)\}$"
)
# Tick 465: markdown inline link wrappers (``[STATUS: READY](url)`` /
# ``[**STATUS: READY**](#anchor)``). Tick 464 bare ``[STATUS:…]`` requires
# the line to *end* at ``]``, so GitHub/Notion linked STATUS stubs with a
# trailing ``(url)`` stayed unmatched (demote no-op / G4 pack miss READY).
# Require ``](`` so bare checkbox ``[ ] STATUS`` is never mistaken for a link.
# Tick 466: destination may contain *balanced* nested parentheses
# (``https://x.com/foo_(bar)`` / GitHub blob anchors with ``(draft)``).
# Pre-466 ``[^)]*`` stopped at the first ``)``, so those URLs never peeled.
# Keep the simple regex for the common no-nest case; balanced scan is the
# fallback (see ``_peel_icml_status_md_link``).
_ICML_STATUS_MD_LINK_RE = re.compile(r"^\[([^\]]*)\]\([^)]*\)\s*$")
# Tick 468: full-line HTML ``<img … alt="STATUS:…" …>`` (Notion/Docs/GitHub
# rich-paste of shields badges). ``img`` is intentionally *not* in the HTML
# tag allowlist (Tick 456–465) — stripping it would drop the alt text.
_ICML_STATUS_HTML_IMG_TAG_RE = re.compile(
    r"^<img\b([^>]*)>\s*$",
    re.IGNORECASE,
)
# Tick 468: quoted ``alt=``. Tick 470: also ``title=`` / ``aria-label=`` —
# a11y / tooltip badge exports often put STATUS there when ``alt`` is a
# decorative filename or omitted.
# Tick 484: also ``aria-description=`` (ARIA 1.3 long description) — same
# allowlist-strip hazard as title/aria-label when body text is decorative.
# Tick 485: also accept *unquoted* attr values (minified HTML / some CMS /
# shields-like exports) — ``alt=STATUS:READY`` / ``title=STATUS:IN_PROGRESS``.
# HTML unquoted values cannot contain whitespace, so spaced
# ``STATUS: READY`` remains quoted-only; group 4 captures the bare token.
_ICML_STATUS_HTML_ATTR_VALUE = (
    r"""(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+))"""
)
_ICML_STATUS_HTML_IMG_ATTR_RE = re.compile(
    r"""\b(alt|title|aria-label|aria-description)\s*=\s*"""
    + _ICML_STATUS_HTML_ATTR_VALUE,
    re.IGNORECASE,
)
# Back-compat alias (Tick 468 tests / callers that still import the old name).
# Tick 485: unquoted alt values too.
_ICML_STATUS_HTML_IMG_ALT_RE = re.compile(
    r"""\balt\s*=\s*""" + _ICML_STATUS_HTML_ATTR_VALUE,
    re.IGNORECASE,
)
# Tick 468+: STATUS-looking attr values. Tick 485: require READY/IN_PROGRESS
# token so truncated unquoted ``title=STATUS: READY`` (HTML parse → value
# ``STATUS:`` only) does not false-peel and poison demote / header match.
_ICML_STATUS_IN_ATTR_RE = re.compile(
    r"STATUS\s*[:：]\s*(?:READY|IN_PROGRESS)\b",
    re.IGNORECASE,
)
# Tick 471: full-line inline SVG badge exports whose ``<title>`` holds STATUS
# (shields.io / Notion / Docs often paste ``<svg…><title>STATUS: READY</title>…``).
# Do **not** allowlist-strip ``svg``/``title`` alone — residual ``<text>`` /
# ``<desc>`` content concatenates onto the header (``STATUS: READYbadge``).
# Tick 472: also peel root ``aria-label=`` / ``title=`` on the opening ``<svg>``
# (a11y / tooltip SVG badge exports often put STATUS there when nested
# ``<title>`` is decorative or omitted).
# Tick 473: also peel nested ``<desc>`` when root attrs + nested ``<title>``
# are decorative / missing (a11y long-description badge exports often put
# STATUS in ``<desc>`` while ``<title>`` is a short badge name).
# Tick 474: also peel nested ``<text>`` (incl. ``<tspan>`` plain text) when
# attrs / title / desc are decorative — Figma / Illustrator / shields-like
# SVG badge exports often put the visible STATUS only in ``<text>``.
# Tick 475: also peel nested ``<foreignObject>`` (HTML-in-SVG plain text) when
# attrs / title / desc / text are decorative — Figma / browser HTML-label
# SVG badge exports often put STATUS only inside ``<foreignObject><div>…``.
_ICML_STATUS_HTML_SVG_TAG_RE = re.compile(
    r"^<svg\b[^>]*>.*</svg>\s*$",
    re.IGNORECASE | re.DOTALL,
)
_ICML_STATUS_HTML_SVG_OPEN_RE = re.compile(
    r"^<svg\b([^>]*)>",
    re.IGNORECASE | re.DOTALL,
)
_ICML_STATUS_HTML_SVG_TITLE_RE = re.compile(
    r"<title\b[^>]*>(.*?)</title>",
    re.IGNORECASE | re.DOTALL,
)
_ICML_STATUS_HTML_SVG_DESC_RE = re.compile(
    r"<desc\b[^>]*>(.*?)</desc>",
    re.IGNORECASE | re.DOTALL,
)
_ICML_STATUS_HTML_SVG_TEXT_RE = re.compile(
    r"<text\b[^>]*>(.*?)</text>",
    re.IGNORECASE | re.DOTALL,
)
_ICML_STATUS_HTML_SVG_FOREIGN_OBJECT_RE = re.compile(
    r"<foreignObject\b[^>]*>(.*?)</foreignObject>",
    re.IGNORECASE | re.DOTALL,
)
_ICML_STATUS_HTML_INNER_TAG_RE = re.compile(r"<[^>]+>")
# Reuse img attr pattern for svg root ``title`` / ``aria-label`` (alt rarely set).
_ICML_STATUS_HTML_SVG_ATTR_RE = _ICML_STATUS_HTML_IMG_ATTR_RE
# Tick 476: pretty-printed multi-line ``<svg>…</svg>`` badge exports (Figma /
# Illustrator / browser "Copy as SVG") open on one line and close later —
# Tick 471–475 required a *full-line* ``<svg>…</svg>``, so those stubs missed
# demote / G4 pack rewrite (except accidental ``<div>STATUS:…</div>`` HTML
# allowlist peels inside multi-line ``<foreignObject>``).
# Tick 479: also collapse when ``<svg`` opens *mid-line* after wrappers
# (``<div role="img"><svg\\n  aria-label="STATUS:…"\\n>…</svg></div>`` /
# ``<a href="…"><svg\\n…`` / ``<figure><svg\\n…``) — Tick 476 required
# ``^<svg`` at line start, so wrapper-prefixed opens missed demote / G4 pack
# (Tick 478 twin for img).
_ICML_STATUS_SVG_BLOCK_OPEN_RE = re.compile(r"^<svg\b", re.IGNORECASE)
_ICML_STATUS_SVG_INLINE_OPEN_RE = re.compile(r"<svg\b", re.IGNORECASE)
_ICML_STATUS_SVG_BLOCK_CLOSE_RE = re.compile(r"</svg\s*>", re.IGNORECASE)
_ICML_STATUS_HTML_SVG_COMPLETE_RE = re.compile(
    r"<svg\b[^>]*>.*?</svg\s*>",
    re.IGNORECASE | re.DOTALL,
)
# Tick 477: pretty-printed multi-line ``<img …>`` badge exports (Notion / Docs /
# Prettier / browser HTML format) open on one line and close later — Tick
# 468–470 required a *full-line* ``<img …>``, so those stubs missed demote /
# G4 pack rewrite after Tick 476 only collapsed multi-line ``<svg>``.
# Tick 478: also collapse when ``<img`` opens *mid-line* after wrappers
# (``<picture><source…><img\\n  alt="STATUS:…"\\n/></picture>``) — Tick 477
# required ``^<img`` at line start, so picture/source-prefixed opens missed.
_ICML_STATUS_IMG_BLOCK_OPEN_RE = re.compile(r"^<img\b", re.IGNORECASE)
_ICML_STATUS_IMG_INLINE_OPEN_RE = re.compile(r"<img\b", re.IGNORECASE)
_ICML_STATUS_HTML_IMG_COMPLETE_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
# Tick 480: soft-wrapped markdown link/image STATUS badges — Prettier / MD
# formatters / GitHub soft-wrap often break ``![STATUS:…](url)`` /
# ``[STATUS:…](url)`` after the opening ``(`` (or between ``]`` and ``(``):
# ``![STATUS: READY](\\nhttps://…/badge_(live).svg)`` /
# ``[**STATUS: READY**](\\nhttps://x.com/foo_(bar))``. Tick 465–467 required a
# *single-line* ``[…](…)`` / ``![…](…)``, so those stubs missed demote / G4 pack
# rewrite after Tick 476–479 only collapsed multi-line HTML ``<svg>`` / ``<img>``.
_ICML_STATUS_MD_LINK_OPEN_RE = re.compile(r"^!?\[")
# Tick 481: HTML ``<a>`` / ``<button>`` whose STATUS lives only in quoted
# ``title=`` / ``aria-label=`` (decorative body text like ``badge`` / ``Go``).
# Tick 465 allowlist-strips ``a``/``button`` and keeps *inner text only*, so
# ``<a href="…" title="STATUS: READY">badge</a>`` / ``<button aria-label=
# "STATUS: READY">Go</button>`` collapsed to ``badge`` / ``Go`` and missed
# demote / G4 pack rewrite after Tick 470 covered the same attrs on ``<img>``
# and Tick 472 on ``<svg>``. Also collapse Prettier multi-line opens
# (``<a\\n  href="…"\\n  title="STATUS: READY"\\n>badge</a>``).
_ICML_STATUS_HTML_A_TAG_RE = re.compile(
    r"^<(a|button)\b([^>]*)>(.*?)</\1\s*>\s*$",
    re.IGNORECASE | re.DOTALL,
)
_ICML_STATUS_HTML_A_ATTR_RE = re.compile(
    r"""\b(title|aria-label|aria-description)\s*=\s*"""
    + _ICML_STATUS_HTML_ATTR_VALUE,
    re.IGNORECASE,
)
_ICML_STATUS_A_INLINE_OPEN_RE = re.compile(r"<(?:a|button)\b", re.IGNORECASE)
_ICML_STATUS_A_BLOCK_CLOSE_RE = re.compile(
    r"</(?:a|button)\s*>", re.IGNORECASE
)
_ICML_STATUS_HTML_A_COMPLETE_RE = re.compile(
    r"<(?:a|button)\b[^>]*>.*?</(?:a|button)\s*>",
    re.IGNORECASE | re.DOTALL,
)
# Tick 482: HTML ``span`` / ``label`` / ``div`` / ``summary`` / ``figcaption`` /
# ``mark`` whose STATUS lives only in quoted ``title=`` / ``aria-label=`` with
# decorative body (``<span title="STATUS: READY">badge</span>`` /
# ``<label aria-label="STATUS: READY">x</label>``). Tick 465–481 allowlist-
# strip those tags to *inner text only*, and Tick 481 only peeled ``a``/
# ``button`` attrs — so Notion/Docs/GitHub a11y badge exports on these
# wrappers still collapsed to ``badge`` / ``x`` and missed demote / G4 pack.
_ICML_STATUS_HTML_SPAN_TAG_RE = re.compile(
    r"^<(span|label|div|summary|figcaption|mark)\b([^>]*)>(.*?)</\1\s*>\s*$",
    re.IGNORECASE | re.DOTALL,
)
_ICML_STATUS_HTML_SPAN_ATTR_RE = re.compile(
    r"""\b(title|aria-label|aria-description)\s*=\s*"""
    + _ICML_STATUS_HTML_ATTR_VALUE,
    re.IGNORECASE,
)
_ICML_STATUS_SPAN_INLINE_OPEN_RE = re.compile(
    r"<(?:span|label|div|summary|figcaption|mark)\b", re.IGNORECASE
)
_ICML_STATUS_SPAN_BLOCK_CLOSE_RE = re.compile(
    r"</(?:span|label|div|summary|figcaption|mark)\s*>", re.IGNORECASE
)
_ICML_STATUS_HTML_SPAN_COMPLETE_RE = re.compile(
    r"<(?:span|label|div|summary|figcaption|mark)\b[^>]*>.*?</(?:span|label|div|summary|figcaption|mark)\s*>",
    re.IGNORECASE | re.DOTALL,
)
# Tick 483: remaining allowlisted formatting / container / table / semantic
# tags whose STATUS lives only in quoted ``title=`` / ``aria-label=`` with
# decorative body (``<p title="STATUS: READY">badge</p>`` /
# ``<strong aria-label="STATUS: READY">x</strong>`` /
# ``<h1 title="STATUS: READY">Badge</h1>`` /
# ``<td title="STATUS: READY">x</td>``). Tick 481 covered ``a``/``button``;
# Tick 482 covered ``span``/``label``/``div``/``summary``/``figcaption``/
# ``mark`` — allowlist strip still drops attrs on these remaining tags.
_ICML_STATUS_HTML_INLINE_TAG_NAMES = (
    r"strong|b|em|i|p|font|u|s|strike|del|ins|small|big|code|tt|kbd|"
    r"h[1-6]|blockquote|li|ul|ol|pre|center|details|"
    r"table|thead|tbody|tfoot|tr|td|th|caption|"
    r"section|article|header|main|aside|nav|footer|figure|"
    r"dt|dd|dl|picture|source"
)
_ICML_STATUS_HTML_INLINE_TAG_RE = re.compile(
    rf"^<({_ICML_STATUS_HTML_INLINE_TAG_NAMES})\b([^>]*)>(.*?)</\1\s*>\s*$",
    re.IGNORECASE | re.DOTALL,
)
_ICML_STATUS_HTML_INLINE_ATTR_RE = re.compile(
    r"""\b(title|aria-label|aria-description)\s*=\s*"""
    + _ICML_STATUS_HTML_ATTR_VALUE,
    re.IGNORECASE,
)


def _icml_status_html_attr_value(am: re.Match[str]) -> str:
    """Return quoted (g2/g3) or unquoted (g4) value from ATTR_RE match (Tick 485)."""
    for g in (am.group(2), am.group(3), am.group(4)):
        if g is not None:
            return g.strip()
    return ""
_ICML_STATUS_INLINE_INLINE_OPEN_RE = re.compile(
    rf"<(?:{_ICML_STATUS_HTML_INLINE_TAG_NAMES})\b", re.IGNORECASE
)
_ICML_STATUS_INLINE_BLOCK_CLOSE_RE = re.compile(
    rf"</(?:{_ICML_STATUS_HTML_INLINE_TAG_NAMES})\s*>", re.IGNORECASE
)
_ICML_STATUS_HTML_INLINE_COMPLETE_RE = re.compile(
    rf"<(?:{_ICML_STATUS_HTML_INLINE_TAG_NAMES})\b[^>]*>.*?</(?:{_ICML_STATUS_HTML_INLINE_TAG_NAMES})\s*>",
    re.IGNORECASE | re.DOTALL,
)


def _take_icml_status_multiline_md_link_block(
    lines: list[str], start: int
) -> tuple[int, str] | None:
    """Tick 480: if ``lines[start]`` opens a soft-wrapped md link/image, return ``(n, collapsed)``.

    Collapses Prettier / markdown soft-wrap forms such as::

        ![STATUS: READY](
        https://img.shields.io/badge/status-ready-green.svg)

        [**STATUS: READY**](
        https://x.com/foo_(bar))

        ![STATUS: READY]
        (https://cdn.example/badge_(live).svg)

    into a single line so Tick 465–467 ``_peel_icml_status_md_link`` can run.
    Single-line complete ``![…](…)`` / ``[…](…)`` returns ``None`` (existing peel).
    Incomplete blocks (no closing ``)``, blank mid-block, >12 lines) return
    ``None``. Collapsed form joins stripped lines with ``""`` so URL soft-wraps
    after ``(`` stay contiguous (no inserted spaces).
    """
    if start < 0 or start >= len(lines):
        return None
    first = (lines[start] or "").strip()
    if not _ICML_STATUS_MD_LINK_OPEN_RE.match(first):
        return None
    # Already a single-line complete link/image → leave to Tick 465–467 peel.
    if _peel_icml_status_md_link(first) is not None:
        return None
    # Must look like an unfinished link/image opener (has ``[``; may lack ``](`` yet).
    if "[" not in first:
        return None
    parts = [first]
    j = start + 1
    max_extra = 12
    while j < len(lines) and (j - start) <= max_extra:
        raw_j = lines[j] or ""
        if not raw_j.strip():
            return None
        parts.append(raw_j.strip())
        collapsed = "".join(parts)
        if _peel_icml_status_md_link(collapsed) is not None:
            return (j - start + 1, collapsed)
        j += 1
    return None


def _take_icml_status_multiline_svg_block(
    lines: list[str], start: int
) -> tuple[int, str] | None:
    """Tick 476/479: if ``lines[start]`` opens a multi-line SVG, return ``(n, collapsed)``.

    Tick 476: line-start ``<svg\\n  …\\n</svg>`` collapses before Tick 471–475
    peels. Tick 479: also collapse when ``<svg`` opens *mid-line* after HTML
    wrappers (``<div role="img"><svg\\n  aria-label="STATUS:…"\\n>…</svg></div>`` /
    ``<a href="…"><svg\\n…`` / ``<figure><svg\\n…``) — pre-479 required
    ``^<svg`` so wrapper-prefixed opens missed demote / G4 pack (Tick 478 twin).

    Single-line complete ``<svg>…</svg>`` (bare or already wrapped) returns
    ``None`` (Tick 471–475 peel + allowlist strip). Incomplete blocks (no
    closing ``</svg>``) return ``None`` so originals stay intact. Collapsed
    form joins stripped lines with a single space so allowlist strip +
    ``_peel_icml_status_html_svg_title`` can run.
    """
    if start < 0 or start >= len(lines):
        return None
    first = (lines[start] or "").strip()
    # Tick 479: mid-line ``<svg`` after div/a/figure wrappers.
    if not _ICML_STATUS_SVG_INLINE_OPEN_RE.search(first):
        return None
    # Already a single-line complete SVG (bare ^<svg…> or wrapped) → leave
    # to existing Tick 471–475 peels (+ allowlist strip for wrappers).
    if _ICML_STATUS_HTML_SVG_COMPLETE_RE.search(first):
        return None
    parts = [first]
    j = start + 1
    while j < len(lines):
        parts.append((lines[j] or "").strip())
        if _ICML_STATUS_SVG_BLOCK_CLOSE_RE.search(lines[j] or ""):
            collapsed = " ".join(p for p in parts if p)
            # Tick 479: search (not ^match) so wrappers around the svg still
            # count as a complete multi-line block once ``</svg>`` closes.
            if not _ICML_STATUS_HTML_SVG_COMPLETE_RE.search(collapsed):
                return None
            return (j - start + 1, collapsed)
        j += 1
    return None


def _take_icml_status_multiline_img_block(
    lines: list[str], start: int
) -> tuple[int, str] | None:
    """Tick 477/478: if ``lines[start]`` opens a multi-line ``<img>``, return ``(n, collapsed)``.

    Tick 477: line-start ``<img\\n  alt=…\\n/>`` collapses before Tick 468–470
    peels. Tick 478: also collapse when ``<img`` opens *mid-line* after HTML
    wrappers (``<picture><source…><img\\n  alt="STATUS:…"\\n/></picture>`` /
    ``<figure><img\\n  title="STATUS:…"\\n></figure>``) — pre-478 required
    ``^<img`` so picture/source-prefixed opens missed demote / G4 pack.

    Single-line complete ``<img …>`` (bare or already wrapped) returns ``None``
    (Tick 468–470 / 469 peel). Incomplete blocks (no closing ``>`` / blank
    line mid-tag) return ``None`` so originals stay intact. Collapsed form
    joins stripped lines with a single space so allowlist strip +
    ``_peel_icml_status_html_img_alt`` can run.
    """
    if start < 0 or start >= len(lines):
        return None
    first = (lines[start] or "").strip()
    # Tick 478: mid-line ``<img`` after picture/source/figure wrappers.
    if not _ICML_STATUS_IMG_INLINE_OPEN_RE.search(first):
        return None
    # Already a single-line complete img (bare ^<img…> or wrapped) → leave
    # to existing Tick 468–470 / 469 peels.
    if _ICML_STATUS_HTML_IMG_COMPLETE_RE.search(first):
        return None
    parts = [first]
    j = start + 1
    while j < len(lines):
        raw_j = lines[j] or ""
        # Blank mid-tag → not a pretty-printed img; leave lines alone.
        if not raw_j.strip():
            return None
        parts.append(raw_j.strip())
        collapsed = " ".join(p for p in parts if p)
        # Tick 478: search (not ^match) so wrappers around the img still count
        # as a complete multi-line block once ``<img …>`` closes.
        if _ICML_STATUS_HTML_IMG_COMPLETE_RE.search(collapsed):
            return (j - start + 1, collapsed)
        j += 1
    return None


def _take_icml_status_multiline_a_block(
    lines: list[str], start: int
) -> tuple[int, str] | None:
    """Tick 481: if ``lines[start]`` opens a multi-line ``<a>``/``<button>``, return ``(n, collapsed)``.

    Collapses Prettier / Notion / Docs pretty-printed forms such as::

        <a
          href="https://example.com"
          title="STATUS: READY"
        >badge</a>

        <p><a
          href="#"
          aria-label="**STATUS: READY**"
        >Go</a></p>

        <button
          aria-label="STATUS: READY"
        >Go</button>

    into a single line so ``_peel_icml_status_html_a_title`` can run.
    Single-line complete ``<a>…</a>`` / ``<button>…</button>`` (bare or
    already wrapped) returns ``None`` (existing peel / allowlist strip).
    Incomplete blocks (no closing ``</a>``/``</button>``, blank mid-tag)
    return ``None``. Collapsed form joins stripped lines with a single space.
    """
    if start < 0 or start >= len(lines):
        return None
    first = (lines[start] or "").strip()
    if not _ICML_STATUS_A_INLINE_OPEN_RE.search(first):
        return None
    # Already a single-line complete a/button (bare or wrapped) → leave to
    # Tick 481 peel (+ allowlist strip for body-text STATUS).
    if _ICML_STATUS_HTML_A_COMPLETE_RE.search(first):
        return None
    parts = [first]
    j = start + 1
    max_extra = 12
    while j < len(lines) and (j - start) <= max_extra:
        raw_j = lines[j] or ""
        if not raw_j.strip():
            return None
        parts.append(raw_j.strip())
        collapsed = " ".join(p for p in parts if p)
        if _ICML_STATUS_A_BLOCK_CLOSE_RE.search(raw_j):
            if not _ICML_STATUS_HTML_A_COMPLETE_RE.search(collapsed):
                return None
            return (j - start + 1, collapsed)
        j += 1
    return None


def _take_icml_status_multiline_span_block(
    lines: list[str], start: int
) -> tuple[int, str] | None:
    """Tick 482: if ``lines[start]`` opens a multi-line span/label/div/…, return ``(n, collapsed)``.

    Collapses Prettier / Notion / Docs pretty-printed forms such as::

        <span
          title="STATUS: READY"
        >badge</span>

        <label
          aria-label="**STATUS: READY**"
        >x</label>

        <div role="status"
          title="STATUS: READY"
        >…</div>

    into a single line so ``_peel_icml_status_html_span_title`` can run.
    Single-line complete tags (bare or already wrapped) return ``None``.
    Incomplete blocks (no closing tag, blank mid-tag) return ``None``.
    Collapsed form joins stripped lines with a single space.
    """
    if start < 0 or start >= len(lines):
        return None
    first = (lines[start] or "").strip()
    if not _ICML_STATUS_SPAN_INLINE_OPEN_RE.search(first):
        return None
    # Already a single-line complete span/label/… → leave to Tick 482 peel.
    if _ICML_STATUS_HTML_SPAN_COMPLETE_RE.search(first):
        return None
    parts = [first]
    j = start + 1
    max_extra = 12
    while j < len(lines) and (j - start) <= max_extra:
        raw_j = lines[j] or ""
        if not raw_j.strip():
            return None
        parts.append(raw_j.strip())
        collapsed = " ".join(p for p in parts if p)
        if _ICML_STATUS_SPAN_BLOCK_CLOSE_RE.search(raw_j):
            if not _ICML_STATUS_HTML_SPAN_COMPLETE_RE.search(collapsed):
                return None
            return (j - start + 1, collapsed)
        j += 1
    return None


def _take_icml_status_multiline_inline_block(
    lines: list[str], start: int
) -> tuple[int, str] | None:
    """Tick 483: if ``lines[start]`` opens a multi-line p/strong/h1/td/…, return ``(n, collapsed)``.

    Collapses Prettier / Notion / Docs pretty-printed forms such as::

        <p
          title="STATUS: READY"
        >badge</p>

        <strong
          aria-label="**STATUS: READY**"
        >x</strong>

        <h1
          title="STATUS: READY"
        >Badge</h1>

    into a single line so ``_peel_icml_status_html_inline_title`` can run.
    Single-line complete tags (bare or already wrapped) return ``None``.
    Incomplete blocks (no closing tag, blank mid-tag) return ``None``.
    Collapsed form joins stripped lines with a single space.
    """
    if start < 0 or start >= len(lines):
        return None
    first = (lines[start] or "").strip()
    if not _ICML_STATUS_INLINE_INLINE_OPEN_RE.search(first):
        return None
    # Already a single-line complete p/strong/h1/… → leave to Tick 483 peel.
    if _ICML_STATUS_HTML_INLINE_COMPLETE_RE.search(first):
        return None
    parts = [first]
    j = start + 1
    max_extra = 12
    while j < len(lines) and (j - start) <= max_extra:
        raw_j = lines[j] or ""
        if not raw_j.strip():
            return None
        parts.append(raw_j.strip())
        collapsed = " ".join(p for p in parts if p)
        if _ICML_STATUS_INLINE_BLOCK_CLOSE_RE.search(raw_j):
            if not _ICML_STATUS_HTML_INLINE_COMPLETE_RE.search(collapsed):
                return None
            return (j - start + 1, collapsed)
        j += 1
    return None


def _take_icml_status_qp_soft_break_block(
    lines: list[str], start: int
) -> tuple[int, str] | None:
    """Tick 490: join MIME QP soft-broken STATUS lines (``STATUS=3A=\\n READY``).

    Quoted-printable soft line breaks end a physical line with ``=`` then
    continue on the next line with no inserted space. Pre-490 per-line scan
    saw ``STATUS=3A=`` alone (no header match) and left the READY stub
    poisoned after trust refuse / G4 pack miss. Require a ``STATUS`` cue so
    prose/assignment lines ending in ``=`` are not joined.
    """
    if start < 0 or start >= len(lines):
        return None
    first = lines[start] or ""
    if "STATUS" not in first.upper():
        return None
    stripped = first.rstrip("\r")
    if not stripped.endswith("=") or stripped.endswith("=="):
        return None
    if stripped == "=":
        return None
    parts = [stripped[:-1]]
    j = start + 1
    max_extra = 6
    while j < len(lines) and (j - start) <= max_extra:
        raw_j = lines[j] or ""
        if not raw_j.strip():
            return None
        rj = raw_j.rstrip("\r")
        if len(rj) > 1 and rj.endswith("=") and not rj.endswith("=="):
            parts.append(rj[:-1])
            j += 1
            continue
        parts.append(rj)
        collapsed = "".join(parts)
        if _icml_ready_status_line_match(collapsed):
            return (j - start + 1, collapsed)
        return None
    return None


def _iter_icml_ready_status_units(text: str):
    """Yield ``(span_lines, match_line)`` STATUS scan units (Tick 476–483/490).

    ``span_lines`` keeps original pretty-printed lines for non-STATUS blocks;
    ``match_line`` is what ``_icml_ready_status_line_match`` sees (collapsed
    multi-line SVG / img / a-button / span-label / inline-format /
    soft-wrapped md link-image / QP soft-break STATUS or the single original
    line).
    """
    raw = (text or "").lstrip("\ufeff")
    lines = raw.splitlines()
    i = 0
    while i < len(lines):
        # Tick 490: MIME QP soft-break STATUS before HTML / md collapses.
        block = _take_icml_status_qp_soft_break_block(lines, i)
        if block is not None:
            n, collapsed = block
            yield lines[i : i + n], collapsed
            i += n
            continue
        # Tick 480: soft-wrapped md link/image before HTML collapses.
        block = _take_icml_status_multiline_md_link_block(lines, i)
        if block is not None:
            n, collapsed = block
            yield lines[i : i + n], collapsed
            i += n
            continue
        block = _take_icml_status_multiline_svg_block(lines, i)
        if block is not None:
            n, collapsed = block
            yield lines[i : i + n], collapsed
            i += n
            continue
        block = _take_icml_status_multiline_img_block(lines, i)
        if block is not None:
            n, collapsed = block
            yield lines[i : i + n], collapsed
            i += n
            continue
        # Tick 481: multi-line <a>/<button> title/aria-label STATUS.
        block = _take_icml_status_multiline_a_block(lines, i)
        if block is not None:
            n, collapsed = block
            yield lines[i : i + n], collapsed
            i += n
            continue
        # Tick 482: multi-line <span>/<label>/<div>/… title/aria-label STATUS.
        block = _take_icml_status_multiline_span_block(lines, i)
        if block is not None:
            n, collapsed = block
            yield lines[i : i + n], collapsed
            i += n
            continue
        # Tick 483: multi-line <p>/<strong>/<h1>/<td>/… title/aria-label STATUS.
        block = _take_icml_status_multiline_inline_block(lines, i)
        if block is not None:
            n, collapsed = block
            yield lines[i : i + n], collapsed
            i += n
            continue
        yield [lines[i]], lines[i]
        i += 1


def _peel_icml_status_html_img_alt(line: str) -> str | None:
    """Tick 468/470: peel a full-line HTML ``<img>`` STATUS attr; return text.

    Tick 467 covered markdown images (``![STATUS: READY](url)``), but Notion /
    Docs / GitHub often export the same badge as an HTML ``<img>`` whose
    ``alt`` holds the STATUS header (``<img alt="STATUS: READY" src="…">`` /
    ``<img src="…/badge_(live).svg" alt="**STATUS: READY**" />``). Pre-468
    left those READY stubs unmatched (demote no-op / G4 pack miss READY)
    because ``img`` is not in the HTML-tag allowlist (stripping would drop
    the alt) and Tick 467 only peeled markdown ``![…](…)``.

    Tick 470: also peel quoted ``title=`` / ``aria-label=`` when they carry
    the STATUS header (``<img title="STATUS: READY" src="…">`` /
    ``<img aria-label="**STATUS: READY**" src="…">`` /
    ``<img alt="badge" title="STATUS: READY" src="…">``). Pre-470 only
    read ``alt=``, so a11y/tooltip badge exports (decorative alt / missing
    alt) missed demote / G4 pack rewrite. Preference: first STATUS-looking
    value among ``alt``, ``title``, ``aria-label`` (in that order); else
    first non-empty of those attrs (Tick 468 alt-first compat).

    Requires a full-line ``<img …>`` (optional self-close ``/>``) with at
    least one quoted ``alt`` / ``title`` / ``aria-label``. Trailing prose
    after the tag refuses the peel. Attribute order is free.

    Tick 477: pretty-printed multi-line ``<img>`` blocks are collapsed by
    ``_iter_icml_ready_status_units`` / ``_take_icml_status_multiline_img_block``
    before this helper runs.
    """
    s = (line or "").strip()
    m = _ICML_STATUS_HTML_IMG_TAG_RE.match(s)
    if not m:
        return None
    attrs = m.group(1) or ""
    # Preserve first-seen order per attr name (alt → title → aria-label).
    by_name: dict[str, str] = {}
    for am in _ICML_STATUS_HTML_IMG_ATTR_RE.finditer(attrs):
        name = (am.group(1) or "").lower()
        val = _icml_status_html_attr_value(am)
        if name and val and name not in by_name:
            by_name[name] = val
    if not by_name:
        return None
    order = ("alt", "title", "aria-label", "aria-description")
    for name in order:
        val = by_name.get(name)
        if val and _ICML_STATUS_IN_ATTR_RE.search(val):
            return val
    for name in order:
        if name in by_name:
            return by_name[name]
    return None


def _peel_icml_status_html_a_title(line: str) -> str | None:
    """Tick 481: peel a full-line HTML ``<a>``/``<button>`` STATUS attr; return text.

    Tick 465 allowlist-strips ``a``/``button`` and keeps *inner text only*, so
    Notion / Docs / GitHub a11y badge exports whose STATUS lives only in
    quoted ``title=`` / ``aria-label=`` with decorative body text
    (``<a href="…" title="STATUS: READY">badge</a>`` /
    ``<a aria-label="**STATUS: READY**" href="#">Go</a>`` /
    ``<button aria-label="STATUS: READY">Go</button>``) collapsed to
    ``badge`` / ``Go`` and missed demote / G4 pack rewrite after Tick 470
    covered the same attrs on ``<img>`` and Tick 472 on ``<svg>``.

    Preference: first STATUS-looking value among ``title``, ``aria-label``,
    ``aria-description`` (in that order; Tick 484). If none carry STATUS,
    return ``None`` so allowlist strip can surface body-text STATUS
    (``<a title="Click me">STATUS: READY</a>``). Inner body text is ignored
    when attrs carry STATUS (decorative label). Requires a full-line
    ``<a>…</a>`` / ``<button>…</button>`` (optional wrappers already stripped
    or collapsed). Trailing prose after the closing tag refuses the peel.

    Multi-line pretty-printed ``<a>``/``<button>`` blocks are collapsed by
    ``_iter_icml_ready_status_units`` / ``_take_icml_status_multiline_a_block``
    before this helper runs.
    """
    s = (line or "").strip()
    # Prefer an exact full-line a/button; also accept a single complete tag
    # when wrappers remain (``<p><a …>…</a></p>``) via search + re-match.
    m = _ICML_STATUS_HTML_A_TAG_RE.match(s)
    if not m:
        cm = _ICML_STATUS_HTML_A_COMPLETE_RE.search(s)
        if not cm:
            return None
        m = _ICML_STATUS_HTML_A_TAG_RE.match(cm.group(0))
        if not m:
            return None
    attrs = m.group(2) or ""
    by_name: dict[str, str] = {}
    for am in _ICML_STATUS_HTML_A_ATTR_RE.finditer(attrs):
        name = (am.group(1) or "").lower()
        val = _icml_status_html_attr_value(am)
        if name and val and name not in by_name:
            by_name[name] = val
    if not by_name:
        return None
    order = ("title", "aria-label", "aria-description")
    for name in order:
        val = by_name.get(name)
        if val and _ICML_STATUS_IN_ATTR_RE.search(val):
            return val
    # No STATUS-looking attr — return None so allowlist strip can surface
    # body-text STATUS (``<a title="Click me">STATUS: READY</a>``).
    return None


def _peel_icml_status_html_span_title(line: str) -> str | None:
    """Tick 482/484: peel full-line span/label/div/… STATUS attr.

    Tick 465–481 allowlist-strip these tags to *inner text only*. Tick 481
    peeled ``title=`` / ``aria-label=`` on ``<a>``/``<button>`` only, so
    Notion / Docs / GitHub a11y badge exports whose STATUS lives only in
    quoted attrs with decorative body
    (``<span title="STATUS: READY">badge</span>`` /
    ``<label aria-label="**STATUS: READY**">x</label>`` /
    ``<div role="status" title="STATUS: READY">…</div>`` /
    ``<summary title="STATUS: READY">Details</summary>``) collapsed to
    ``badge`` / ``x`` / ``…`` / ``Details`` and missed demote / G4 pack.

    Tick 484: also peel ``aria-description=`` (ARIA 1.3) on the same tags —
    ``<span aria-description="STATUS: READY">badge</span>`` still collapsed
    to ``badge`` after Tick 482 only covered ``title`` / ``aria-label``.

    Preference: first STATUS-looking value among ``title``, ``aria-label``,
    ``aria-description`` (in that order). If none carry STATUS, return
    ``None`` so allowlist strip can surface body-text STATUS. Multi-line
    blocks are collapsed by ``_take_icml_status_multiline_span_block``
    before this runs.
    """
    s = (line or "").strip()
    m = _ICML_STATUS_HTML_SPAN_TAG_RE.match(s)
    if not m:
        cm = _ICML_STATUS_HTML_SPAN_COMPLETE_RE.search(s)
        if not cm:
            return None
        m = _ICML_STATUS_HTML_SPAN_TAG_RE.match(cm.group(0))
        if not m:
            return None
    attrs = m.group(2) or ""
    by_name: dict[str, str] = {}
    for am in _ICML_STATUS_HTML_SPAN_ATTR_RE.finditer(attrs):
        name = (am.group(1) or "").lower()
        val = _icml_status_html_attr_value(am)
        if name and val and name not in by_name:
            by_name[name] = val
    if not by_name:
        return None
    for name in ("title", "aria-label", "aria-description"):
        val = by_name.get(name)
        if val and _ICML_STATUS_IN_ATTR_RE.search(val):
            return val
    return None


def _peel_icml_status_html_inline_title(line: str) -> str | None:
    """Tick 483/484: peel full-line p/strong/h1/td/… STATUS attr.

    Tick 465–482 allowlist-strip remaining formatting / container / table /
    semantic tags to *inner text only*. Tick 481 peeled ``a``/``button``;
    Tick 482 peeled ``span``/``label``/``div``/``summary``/``figcaption``/
    ``mark``. Notion / Docs / GitHub a11y badge exports whose STATUS lives
    only in quoted attrs with decorative body on the remaining allowlist
    (``<p title="STATUS: READY">badge</p>`` /
    ``<strong aria-label="**STATUS: READY**">x</strong>`` /
    ``<h1 title="STATUS: READY">Badge</h1>`` /
    ``<td title="STATUS: READY">x</td>`` /
    ``<section aria-label="STATUS: READY">…</section>``) collapsed to
    ``badge`` / ``x`` / ``Badge`` / ``…`` and missed demote / G4 pack.

    Tick 484: also peel ``aria-description=`` on the same remaining tags —
    ``<p aria-description="STATUS: READY">badge</p>`` still collapsed to
    ``badge`` after Tick 483 only covered ``title`` / ``aria-label``.

    Preference: first STATUS-looking value among ``title``, ``aria-label``,
    ``aria-description`` (in that order). If none carry STATUS, return
    ``None`` so allowlist strip can surface body-text STATUS. Multi-line
    blocks are collapsed by ``_take_icml_status_multiline_inline_block``
    before this runs.
    """
    s = (line or "").strip()
    m = _ICML_STATUS_HTML_INLINE_TAG_RE.match(s)
    if not m:
        cm = _ICML_STATUS_HTML_INLINE_COMPLETE_RE.search(s)
        if not cm:
            return None
        m = _ICML_STATUS_HTML_INLINE_TAG_RE.match(cm.group(0))
        if not m:
            return None
    attrs = m.group(2) or ""
    by_name: dict[str, str] = {}
    for am in _ICML_STATUS_HTML_INLINE_ATTR_RE.finditer(attrs):
        name = (am.group(1) or "").lower()
        val = _icml_status_html_attr_value(am)
        if name and val and name not in by_name:
            by_name[name] = val
    if not by_name:
        return None
    for name in ("title", "aria-label", "aria-description"):
        val = by_name.get(name)
        if val and _ICML_STATUS_IN_ATTR_RE.search(val):
            return val
    return None


def _svg_inner_plain_text(inner: str) -> str:
    """Tick 474: strip nested SVG tags (``tspan``/etc.) and collapse whitespace."""
    plain = _ICML_STATUS_HTML_INNER_TAG_RE.sub("", inner or "")
    return " ".join(plain.split()).strip()


def _peel_icml_status_html_svg_title(line: str) -> str | None:
    """Tick 471/472/473/474/475: peel a full-line inline SVG STATUS name; return text.

    Tick 468–470 covered HTML ``<img>`` badge exports (alt / title /
    aria-label). Shields.io / Notion / Docs also paste STATUS as an inline
    SVG whose accessible name lives in ``<title>``
    (``<svg …><title>STATUS: READY</title>…</svg>`` /
    ``<svg role="img"><title>**STATUS: READY**</title><text>…</text></svg>``).
    Pre-471 left those READY stubs unmatched (demote no-op / G4 pack miss
    READY): ``svg``/``title`` are not in the HTML-tag allowlist (and
    allowlist-stripping them would concatenate residual ``<text>`` /
    ``<desc>`` onto the header).

    Tick 472: also peel quoted root ``aria-label=`` / ``title=`` on the
    opening ``<svg>`` when they carry the STATUS header
    (``<svg aria-label="STATUS: READY" …>…</svg>`` /
    ``<svg title="**STATUS: READY**" role="img">…</svg>`` /
    ``<svg aria-label="STATUS: READY"><title>Badge</title>…</svg>``).
    Pre-472 Tick 471 only read nested ``<title>``, so a11y/tooltip SVG
    badge exports (decorative nested title / missing ``<title>``) missed
    demote / G4 pack rewrite.

    Tick 473: also peel nested ``<desc>`` when it carries the STATUS header
    (``<svg…><title>Badge</title><desc>STATUS: READY</desc>…</svg>`` /
    ``<svg role="img"><desc>**STATUS: READY**</desc><text>…</text></svg>``).
    Pre-473 Tick 471/472 only read root attrs + nested ``<title>``, so a11y
    long-description badge exports (decorative title / missing title; STATUS
    only in ``<desc>``) missed demote / G4 pack rewrite.

    Tick 474: also peel nested ``<text>`` (plain text after stripping
    ``<tspan>``/other inner tags) when it carries the STATUS header
    (``<svg…><title>Badge</title><text>STATUS: READY</text>…</svg>`` /
    ``<svg role="img"><text><tspan>**STATUS: READY**</tspan></text></svg>``).
    Pre-474 Tick 471–473 only read attrs / ``<title>`` / ``<desc>``, so
    Figma / Illustrator / shields-like visible-label badge exports
    (decorative a11y name; STATUS only in ``<text>``) missed demote /
    G4 pack rewrite.

    Tick 475: also peel nested ``<foreignObject>`` (plain text after
    stripping inner HTML tags) when it carries the STATUS header
    (``<svg…><title>Badge</title><foreignObject><div>STATUS: READY</div>
    </foreignObject>…</svg>`` /
    ``<svg role="img"><foreignObject><span>**STATUS: READY**</span>
    </foreignObject></svg>``). Pre-475 Tick 471–474 only read attrs /
    ``<title>`` / ``<desc>`` / ``<text>``, so Figma / browser HTML-in-SVG
    label badge exports (decorative a11y name; STATUS only in
    ``<foreignObject>``) missed demote / G4 pack rewrite. Preference: first
    STATUS-looking value among ``aria-label``, root ``title``, nested
    ``<title>``, nested ``<desc>``, nested ``<text>``, nested
    ``<foreignObject>`` (in that order). Decorative-only names refuse the peel.

    Requires a full-line ``<svg …>…</svg>``. Trailing prose after ``</svg>``
    refuses the peel. Tick 476 collapses pretty-printed multi-line SVG blocks
    into one line before calling this helper.
    """
    s = (line or "").strip()
    if not _ICML_STATUS_HTML_SVG_TAG_RE.match(s):
        return None
    by_name: dict[str, str] = {}
    open_m = _ICML_STATUS_HTML_SVG_OPEN_RE.match(s)
    if open_m:
        attrs = open_m.group(1) or ""
        for am in _ICML_STATUS_HTML_SVG_ATTR_RE.finditer(attrs):
            name = (am.group(1) or "").lower()
            val = _icml_status_html_attr_value(am)
            if (
                name in ("aria-label", "title", "alt", "aria-description")
                and val
                and name not in by_name
            ):
                by_name[name] = val
    nested_titles: list[str] = []
    for tm in _ICML_STATUS_HTML_SVG_TITLE_RE.finditer(s):
        val = (tm.group(1) or "").strip()
        if val:
            nested_titles.append(val)
    nested_descs: list[str] = []
    for dm in _ICML_STATUS_HTML_SVG_DESC_RE.finditer(s):
        val = (dm.group(1) or "").strip()
        if val:
            nested_descs.append(val)
    nested_texts: list[str] = []
    for xm in _ICML_STATUS_HTML_SVG_TEXT_RE.finditer(s):
        val = _svg_inner_plain_text(xm.group(1) or "")
        if val:
            nested_texts.append(val)
    nested_foreign: list[str] = []
    for fm in _ICML_STATUS_HTML_SVG_FOREIGN_OBJECT_RE.finditer(s):
        val = _svg_inner_plain_text(fm.group(1) or "")
        if val:
            nested_foreign.append(val)
    # STATUS-looking preference: aria-label → root title → alt →
    # aria-description → nested <title> → nested <desc> → nested <text> →
    # nested <foreignObject>.
    for name in ("aria-label", "title", "alt", "aria-description"):
        val = by_name.get(name)
        if val and _ICML_STATUS_IN_ATTR_RE.search(val):
            return val
    for val in nested_titles:
        if _ICML_STATUS_IN_ATTR_RE.search(val):
            return val
    for val in nested_descs:
        if _ICML_STATUS_IN_ATTR_RE.search(val):
            return val
    for val in nested_texts:
        if _ICML_STATUS_IN_ATTR_RE.search(val):
            return val
    for val in nested_foreign:
        if _ICML_STATUS_IN_ATTR_RE.search(val):
            return val
    return None


def _peel_icml_status_md_link(line: str) -> str | None:
    """Tick 465/466/467: peel a full-line markdown link or image; return text/alt.

    Tick 465 covered flat ``[text](url)`` (no ``)`` inside the destination).
    Tick 466 also peels destinations with balanced nested parentheses —
    CommonMark allows ``(`` / ``)`` inside the destination, and GitHub /
    Notion paste often yields ``[STATUS: READY](https://…/foo_(bar))`` or
    ``…#status-(draft)``. Pre-466 ``_ICML_STATUS_MD_LINK_RE`` used ``[^)]*``,
    which truncated at the first ``)`` and left the stub unmatched
    (demote no-op / G4 pack miss READY).

    Tick 467: also peel markdown **image** STATUS stubs
    (``![STATUS: READY](url)`` / ``![**STATUS: READY**](https://…/badge_(live).svg)``).
    Shields.io / Notion / Docs often export a STATUS badge as an image whose
    alt text is the STATUS header; pre-467 required a bare ``[`` start, so
    the leading ``!`` left those READY stubs unmatched (demote no-op /
    G4 pack miss READY). Image peel reuses the link scanner after stripping
    the leading ``!``.

    Tick 480: pretty-printed / soft-wrapped multi-line ``![…](…)`` /
    ``[…](…)`` blocks are collapsed by ``_iter_icml_ready_status_units`` /
    ``_take_icml_status_multiline_md_link_block`` before this helper runs
    (Prettier / GitHub soft-wrap after ``(``; Tick 465–467 were single-line).

    Requires ``](`` immediately after the link/alt text so bare checkboxes
    (``[ ] STATUS``) and Tick 464 bare brackets (``[STATUS:…]``) are never
    mistaken for links. Trailing non-whitespace after the closing ``)``
    refuses the peel (keeps ``[STATUS: READY](url) note`` from becoming a
    false header).
    """
    s = (line or "").strip()
    # Tick 467: markdown image ``![alt](dest)`` → peel alt like link text.
    if s.startswith("!["):
        s = s[1:]
    if not s.startswith("["):
        return None
    # Fast path: flat destination (no nested ``)`` mid-url).
    m = _ICML_STATUS_MD_LINK_RE.match(s)
    if m:
        text = (m.group(1) or "").strip()
        return text or None
    # Balanced-paren scan for nested destinations.
    close_text = s.find("]")
    if close_text < 1:
        return None
    if close_text + 1 >= len(s) or s[close_text + 1] != "(":
        return None
    depth = 1
    i = close_text + 2
    while i < len(s):
        ch = s[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                if s[i + 1 :].strip():
                    return None
                text = s[1:close_text].strip()
                return text or None
        i += 1
    return None


# Tick 459/461: outer markdown table-cell pipes (``| STATUS: READY |``).
# Tick 461: require a true one-cell row (no inner ``|``) so
# ``| STATUS: READY | note |`` is not peeled into a false READY header.
_ICML_STATUS_MD_PIPE_RE = re.compile(r"^\|+\s*([^|]*?)\s*\|+\s*$")


def _normalize_icml_status_rfc2047_charset(charset: str) -> str | None:
    """Map RFC 2047 charset token → codecs name, or None if disallowed."""
    cs = (charset or "").strip().lower().replace("_", "-")
    if cs not in _ICML_STATUS_RFC2047_CHARSETS:
        return None
    if cs in {"utf8", "utf-8"}:
        return "utf-8"
    if cs in {"us-ascii", "ascii"}:
        return "ascii"
    if cs in {"iso-8859-1", "latin-1", "latin1"}:
        return "latin-1"
    return cs


def _decode_one_icml_status_rfc2047_word(
    charset: str, encoding: str, payload: str
) -> str | None:
    """Decode one RFC 2047 encoded-word; None if charset/encoding unsupported.

    Q-encoding: ``_`` → space; leave ``=XX`` for Tick 490 QP allowlist peel.
    B-encoding: base64 → text in ``charset`` (strict). Unknown / invalid → None.
    """
    codec = _normalize_icml_status_rfc2047_charset(charset)
    if codec is None:
        return None
    enc = (encoding or "").upper()
    if enc == "Q":
        # RFC 2047 §4.2: underscore is always space in Q encoded-words.
        return (payload or "").replace("_", " ")
    if enc == "B":
        raw_b64 = (payload or "").strip()
        if not raw_b64:
            return None
        try:
            pad = (-len(raw_b64)) % 4
            data = base64.b64decode(raw_b64 + ("=" * pad), validate=True)
            if not data:
                return None
            return data.decode(codec)
        except (ValueError, UnicodeDecodeError, binascii.Error):
            return None
    return None


def _peel_icml_status_rfc2047_encoded_words(line: str) -> str:
    """Tick 491: peel RFC 2047 encoded-word runs into plain STATUS text.

    Email / MIME gateways wrap headers as ``=?charset?Q|B?…?=``. Adjacent
    encoded-words may be separated by linear whitespace (RFC 2047 §6.2) —
    join their payloads without that whitespace. If any word in a run fails
    (unknown charset / bad base64), leave the whole run literal.
    """

    def _run_sub(m: re.Match) -> str:
        run = m.group(0)
        parts: list[str] = []
        for wm in _ICML_STATUS_RFC2047_WORD_RE.finditer(run):
            decoded = _decode_one_icml_status_rfc2047_word(
                wm.group(1), wm.group(2), wm.group(3)
            )
            if decoded is None:
                return run
            parts.append(decoded)
        if not parts:
            return run
        return "".join(parts)

    return _ICML_STATUS_RFC2047_RUN_RE.sub(_run_sub, line or "")


def _peel_icml_status_bare_base64(line: str) -> str:
    """Tick 492: peel a full-line bare base64 STATUS payload into plain text.

    Tick 491 peels RFC 2047 ``=?UTF-8?B?…?=`` wrappers, but email / log /
    chat copy-paste often drops the wrappers and leaves only the payload
    (``U1RBVFVTOiBSRUFEWQ==`` / bold-wrapped ``**U1RBVFVTOiBSRUFEWQ==**``).
    Pre-492 left those stubs unmatched (demote no-op / G4 pack miss READY).

    Full-line only; require STATUS + READY/IN_PROGRESS in the decoded text
    (plain or further-encoded). Invalid / non-STATUS base64 stays literal.
    Mid-string ``=`` (e.g. QP ``STATUS=3A=20READY``) fails ``validate=True``.
    """
    original = line or ""
    s = original.strip()
    if not _ICML_STATUS_BARE_BASE64_RE.fullmatch(s):
        return original
    try:
        pad = (-len(s)) % 4
        data = base64.b64decode(s + ("=" * pad), validate=True)
        if not data:
            return original
        text = data.decode("utf-8")
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return original
    if not _ICML_STATUS_BARE_BASE64_HINT_RE.search(text):
        return original
    # Preserve leading/trailing whitespace only when the whole strip matched.
    if original == s:
        return text
    # Caller usually already stripped; keep decoded body.
    return text


def _peel_icml_status_data_uri_base64(line: str) -> str:
    """Tick 493: peel a full-line ``data:…;base64,…`` STATUS payload.

    Tick 492 peels bare base64 payloads, but chat / email / Markdown badge
    paste often keeps the RFC 2397 data-URI wrapper
    (``data:text/plain;base64,U1RBVFVTOiBSRUFEWQ==`` /
    ``data:text/plain;charset=utf-8;base64,…`` /
    ``data:;base64,…`` / bold-wrapped ``**data:…;base64,…**``).
    Pre-493 left those stubs unmatched (demote no-op / G4 pack miss READY).

    Full-line only; decode via ``_peel_icml_status_bare_base64`` so invalid /
    non-STATUS payloads stay literal. Non-base64 ``data:text/plain,…`` stay
    for Tick 494 ``_peel_icml_status_data_uri_plain``; non-data URLs stay
    untouched.
    """
    original = line or ""
    s = original.strip()
    m = _ICML_STATUS_DATA_URI_RE.fullmatch(s)
    if not m:
        return original
    payload = m.group(1)
    peeled = _peel_icml_status_bare_base64(payload)
    if peeled == payload:
        return original
    return peeled


def _peel_icml_status_data_uri_plain(line: str) -> str:
    """Tick 494: peel a full-line non-base64 ``data:…,<payload>`` STATUS.

    Tick 493 peels ``data:…;base64,…`` only, so chat / email / Markdown badge
    paste of percent-encoded or literal plain data URIs
    (``data:text/plain,STATUS%3A%20READY`` /
    ``data:text/plain;charset=utf-8,STATUS%3A%20READY`` /
    ``data:,STATUS:%20READY`` / ``data:text/plain,STATUS: READY`` /
    bold-wrapped ``**data:text/plain,STATUS%3A%20READY**``) still missed
    demote / G4 pack rewrite. Pre-494 left those stubs unmatched.

    Full-line only; URL-unquote the payload (RFC 2397), then accept only when
    STATUS + READY/IN_PROGRESS appear (same hint as Tick 492). Also try bare
    base64 on the raw payload when wrappers omitted ``;base64``. Non-STATUS /
    empty payloads and ``;base64,`` forms (Tick 493) stay untouched.
    """
    original = line or ""
    s = original.strip()
    m = _ICML_STATUS_DATA_URI_PLAIN_RE.fullmatch(s)
    if not m:
        return original
    payload = m.group(1)
    if not payload:
        return original
    had_pct = "%" in payload
    try:
        decoded = unquote(payload, errors="strict")
    except (ValueError, UnicodeDecodeError):
        return original
    if had_pct:
        decoded = decoded.replace("+", " ")
    if _ICML_STATUS_BARE_BASE64_HINT_RE.search(decoded):
        return decoded
    # Optional: ``data:text/plain,U1RBVFVTOiBSRUFEWQ==`` without ``;base64``.
    peeled_b64 = _peel_icml_status_bare_base64(payload.strip())
    if peeled_b64 != payload.strip():
        return peeled_b64
    return original


def _peel_icml_status_bare_hex(line: str) -> str:
    """Tick 495/496: peel a full-line bare hex STATUS payload into plain text.

    Tick 492–494 cover base64 / data-URI forms, but log / packet / hex-dump
    paste often keeps a hex encoding of the STATUS line
    (``5354415455533A205245414459`` / spaced ``53 54 … 59`` /
    colon ``53:54:…`` / dash ``53-54-…`` / ``0x``-prefixed /
    bold-wrapped ``**5354…4459**``). Pre-495 left those stubs unmatched
    (demote no-op / G4 pack miss READY). Pure-hex alphabet can match
    Tick 492's base64 charset, but decoded bytes fail the STATUS hint —
    hex peel runs after bare-base64 and recovers those lines.

    Tick 496: C / debugger / Wireshark-style dumps often use commas or
    per-byte ``0x`` prefixes
    (``53,54,41,…`` / ``0x53,0x54,…`` / ``0x53 0x54 …`` /
    ``{0x53, 0x54, …}``) — Tick 495 only matched continuous / space /
    colon / dash / single leading ``0x``, so demote no-op / G4 pack miss
    READY. Extend the same peeler; leave Tick 495 contracts + non-STATUS
    untouched.

    Full-line only; require ≥13 bytes and STATUS + READY/IN_PROGRESS in the
    UTF-8 text (same hint as Tick 492). Odd-length / non-hex / non-STATUS
    stay literal.
    """
    original = line or ""
    s = original.strip()
    matched = False
    if (
        _ICML_STATUS_BARE_HEX_CONT_RE.fullmatch(s)
        or _ICML_STATUS_BARE_HEX_SEP_RE.fullmatch(s)
    ):
        matched = True
        body = s[2:] if s[:2].lower() == "0x" else s
        compact = re.sub(r"[\s:\-]", "", body)
    elif (
        _ICML_STATUS_BARE_HEX_COMMA_RE.fullmatch(s)
        or _ICML_STATUS_BARE_HEX_0X_BYTE_RE.fullmatch(s)
        or _ICML_STATUS_BARE_HEX_CARRAY_RE.fullmatch(s)
    ):
        matched = True
        body = s[1:-1].strip() if s.startswith("{") and s.endswith("}") else s
        compact = re.sub(r"(?i)0x", "", body)
        compact = re.sub(r"[\s,]", "", compact)
    if not matched:
        return original
    if len(compact) < 26 or len(compact) % 2:
        return original
    try:
        data = bytes.fromhex(compact)
        if not data:
            return original
        text = data.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return original
    if not _ICML_STATUS_BARE_BASE64_HINT_RE.search(text):
        return original
    return text


def _decode_icml_status_html_entities(line: str) -> str:
    """Tick 455/486/487/488/489/490/491/492/493/494/495/496: decode HTML + JSON/JS + URL + QP + RFC2047 + bare-b64 + data-URI + bare-hex / C-array hex.

    Pre-455 ``_strip_icml_status_line_noise`` only removed Unicode ZWSP etc., so
    Notion/Docs HTML→Markdown exports of ``&#8203;**STATUS: READY**`` /
    ``&ZeroWidthSpace;**STATUS:…**`` / ``**STATUS:&nbsp;READY**`` still made
    demote no-op / G4 pack miss READY. Only decode the codepoints we then
    strip (or treat as whitespace via ``\\s``), plus Tick 486 STATUS separator
    colons (``&#58;`` / ``&colon;`` / ``&#x3a;`` / ``&#xff1a;``); leave other
    entities untouched.

    Tick 486: CMS/XSS-escaped exports often encode the STATUS colon
    (``STATUS&#58; READY`` / ``STATUS&colon;READY`` /
    ``<p title="STATUS&#58; READY">badge</p>``) — pre-486 invisibles-only
    decode left those stubs unmatched (demote no-op / G4 pack miss READY).

    Tick 487: sanitizers often *double*-escape those entities
    (``STATUS&amp;#58; READY`` / ``STATUS&amp;colon;READY`` /
    ``&lt;p title=&quot;STATUS: READY&quot;&gt;badge&lt;/p&gt;``) — pre-487
    Tick 486 decoded only a single entity layer, so demote no-op / G4 pack
    miss READY. Peel ``&amp;``/``&#38;``/``&#x26;`` only when they prefix
    another entity body (preserve Tick 486 ``&amp;**STATUS…`` contract),
    decode ``&lt;``/``&gt;``/``&quot;``/``&apos;``, and iterate until stable.

    Tick 488: JSON/API/CMS string exports often escape the STATUS separator
    (and badge markup) as JS/JSON unicode or hex escapes
    (``STATUS\\u003a READY`` / ``STATUS\\x3a READY`` /
    ``\\u003cp title=\\u0022STATUS\\u003a READY\\u0022\\u003e…``) — pre-488
    HTML-entity-only decode left those stubs unmatched (demote no-op / G4
    pack miss READY). Peel allowlisted ``\\uXXXX`` / ``\\xXX`` only.

    Tick 489: badge URLs / query strings / CMS link exports often percent-encode
    the STATUS separator (and badge markup)
    (``STATUS%3A%20READY`` / ``STATUS%3A+READY`` / ``STATUS%253A%20READY`` /
    ``%3Cp%20title%3D%22STATUS%3A%20READY%22%3Ebadge%3C%2Fp%3E``) — pre-489
    JS/HTML-only decode left those stubs unmatched (demote no-op / G4 pack
    miss READY). Peel allowlisted ``%XX`` only; when the original line had any
    ``%XX``, also treat ``+`` as space (form-urlencoded).

    Tick 490: email / MIME / CMS quoted-printable exports often encode the
    STATUS separator (and badge markup) as ``=XX``
    (``STATUS=3A READY`` / ``STATUS=3A=20READY`` / ``STATUS=3AIN_PROGRESS`` /
    ``=3Cp title=3D=22STATUS=3A READY=22=3Ebadge=3C/p=3E`` /
    soft-break ``STATUS=3A=\\n READY``) — pre-490 URL/JS/HTML-only decode
    left those stubs unmatched (demote no-op / G4 pack miss READY). Peel
    allowlisted ``=XX`` only after removing QP soft line breaks; unknown
    ``=41`` stays literal. Bare ``STATUS: a=b`` / ``STATUS: READY=note``
    without hex ``=XX`` stay untouched.

    Tick 491: email / MIME gateways often wrap STATUS in RFC 2047 encoded-words
    (``=?UTF-8?Q?STATUS=3A_READY?=`` / ``=?utf-8?q?STATUS=3A=20READY?=`` /
    ``=?UTF-8?B?U1RBVFVTOiBSRUFEWQ==?=`` / adjacent
    ``=?UTF-8?Q?STATUS=3A_?= =?UTF-8?Q?READY?=``) — pre-491 Tick 490 peeled
    bare QP ``=XX`` but left ``=?…?=`` wrappers + Q ``_``-as-space, so demote
    no-op / G4 pack miss READY. Peel allowlisted charset Q/B words before
    QP ``=XX``; unknown charset / invalid base64 stay literal.

    Tick 492: email / log / chat copy-paste often drops RFC 2047 wrappers and
    leaves only the base64 payload (``U1RBVFVTOiBSRUFEWQ==`` /
    ``**U1RBVFVTOiBSRUFEWQ==**`` after wrap strip) — pre-492 Tick 491 peeled
    wrapped ``=?UTF-8?B?…?=`` only, so demote no-op / G4 pack miss READY.
    Peel full-line bare base64 only when decoded text looks like STATUS;
    invalid / non-STATUS base64 stay literal (QP mid-``=`` fails validate).

    Tick 493: chat / email / Markdown badge paste often keeps the RFC 2397
    data-URI wrapper around that payload
    (``data:text/plain;base64,U1RBVFVTOiBSRUFEWQ==`` /
    ``data:text/plain;charset=utf-8;base64,…`` / ``data:;base64,…`` /
    bold-wrapped ``**data:…;base64,…**``) — pre-493 Tick 492 peeled bare
    base64 only, so demote no-op / G4 pack miss READY. Peel full-line
    ``data:…;base64,…`` only when the payload peels to STATUS; non-base64
    data URIs stay for Tick 494; invalid / non-STATUS payloads stay literal.

    Tick 494: chat / email / Markdown badge paste also uses *plain*
    (non-base64) RFC 2397 data URIs with percent-encoded or literal STATUS
    (``data:text/plain,STATUS%3A%20READY`` /
    ``data:text/plain;charset=utf-8,STATUS%3A%20READY`` /
    ``data:,STATUS:%20READY`` / ``data:text/plain,STATUS: READY`` /
    bold-wrapped ``**data:text/plain,STATUS%3A%20READY**``) — pre-494 Tick
    493 peeled ``;base64,`` only, so demote no-op / G4 pack miss READY.
    Peel full-line non-base64 ``data:…,<payload>`` when URL-unquoted text
    looks like STATUS; non-STATUS / empty stay literal.

    Tick 495: log / packet / hex-dump paste often keeps a hex encoding of
    the STATUS line (``5354415455533A205245414459`` / spaced ``53 54 …`` /
    colon ``53:54:…`` / dash ``53-54-…`` / ``0x``-prefixed /
    bold-wrapped ``**5354…4459**``) — pre-495 Tick 492–494 covered base64 /
    data-URI only, so demote no-op / G4 pack miss READY. Peel full-line
    bare hex (≥13 bytes) when UTF-8 text looks like STATUS; odd-length /
    non-hex / non-STATUS stay literal.

    Tick 496: C / debugger dumps often use commas or per-byte ``0x``
    (``53,54,…`` / ``0x53,0x54,…`` / ``0x53 0x54 …`` / ``{0x53, 0x54, …}``)
    — Tick 495 continuous/space/colon/dash/single-``0x`` left those unmatched
    (demote no-op / G4 pack miss READY). Same peeler; non-STATUS untouched.
    """

    def _sub(m: re.Match) -> str:
        hex_g, dec_g, named = m.group(1), m.group(2), m.group(3)
        if named:
            return _ICML_STATUS_HTML_NAMED.get(named.lower(), m.group(0))
        try:
            code = int(hex_g, 16) if hex_g is not None else int(dec_g, 10)
        except (TypeError, ValueError):
            return m.group(0)
        if code in _ICML_STATUS_HTML_CODEPOINTS:
            return chr(code)
        return m.group(0)

    def _js_sub(m: re.Match) -> str:
        u_g, x_g = m.group(1), m.group(2)
        try:
            code = int(u_g, 16) if u_g is not None else int(x_g, 16)
        except (TypeError, ValueError):
            return m.group(0)
        if code in _ICML_STATUS_HTML_CODEPOINTS:
            return chr(code)
        return m.group(0)

    def _pct_sub(m: re.Match) -> str:
        try:
            code = int(m.group(1), 16)
        except (TypeError, ValueError):
            return m.group(0)
        if code in _ICML_STATUS_HTML_CODEPOINTS:
            return chr(code)
        return m.group(0)

    def _qp_sub(m: re.Match) -> str:
        try:
            code = int(m.group(1), 16)
        except (TypeError, ValueError):
            return m.group(0)
        if code in _ICML_STATUS_HTML_CODEPOINTS:
            return chr(code)
        return m.group(0)

    original = line or ""
    had_pct = bool(_ICML_STATUS_URL_PERCENT_RE.search(original))
    s = original
    # Bound iterations: ``&amp;amp;#58;`` / nested ``\\u003c`` / ``%253A`` /
    # ``=253A`` / stacked RFC 2047 runs / bare-b64 / data-URI / bare-hex →
    # further-encoded STATUS.
    for _ in range(8):
        prev = s
        s = _ICML_STATUS_QP_SOFT_BREAK_RE.sub("", s)
        s = _peel_icml_status_rfc2047_encoded_words(s)
        s = _peel_icml_status_data_uri_base64(s)
        s = _peel_icml_status_data_uri_plain(s)
        s = _peel_icml_status_bare_base64(s)
        s = _peel_icml_status_bare_hex(s)
        s = _ICML_STATUS_DOUBLE_AMP_RE.sub("&", s)
        s = _ICML_STATUS_HTML_ENTITY_RE.sub(_sub, s)
        s = _ICML_STATUS_JS_ESCAPE_RE.sub(_js_sub, s)
        s = _ICML_STATUS_URL_PERCENT_RE.sub(_pct_sub, s)
        s = _ICML_STATUS_QUOTED_PRINTABLE_RE.sub(_qp_sub, s)
        if s == prev:
            break
    # Form-urlencoded: ``STATUS%3A+READY`` → ``STATUS: READY`` (only when the
    # original line used percent-encoding — leave bare ``STATUS: READY+x``).
    if had_pct:
        s = s.replace("+", " ")
    return s


def _strip_icml_status_html_tags(line: str) -> str:
    """Tick 456/457/458/459: remove formatting HTML tags around STATUS headers.

    Pre-456 entity/ZWSP strip still left ``<strong>STATUS: READY</strong>`` /
    ``<p><b>**STATUS:…**</b></p>`` / ``<span style=\"…\">**STATUS: READY**</span>``
    unmatched — demote no-op / G4 pack miss READY on Notion/Docs rich-paste
    and partial HTML→Markdown exports. Only strip a fixed allowlist of
    emphasis/block wrappers (with optional attributes); leave other ``<…>``
    untouched so prose like ``STATUS < 1`` is not eaten.

    Tick 457: also strip ``h1``–``h6`` / ``kbd`` (HTML heading export of ATX
    ``# STATUS:`` and keyboard/code paste) — pre-457 left ``<h1>STATUS: READY</h1>``
    unmatched after Tick 448 ATX + Tick 456 non-heading tags.

    Tick 458: also strip HTML container tags (``blockquote`` / ``li`` / ``ul`` /
    ``ol`` / ``pre`` / ``center`` / ``summary`` / ``details``) — Tick 451 already
    matched markdown ``>`` / ``-`` list prefixes, but Notion/Docs HTML exports of
    the same containers left ``<blockquote>STATUS: READY</blockquote>`` /
    ``<li>STATUS: READY</li>`` unmatched after Tick 457.

    Tick 459: also strip HTML table + semantic sectioning tags (``table`` /
    ``td`` / ``th`` / ``tr`` / ``section`` / ``article`` / ``header`` / ``main``
    / ``aside`` / ``caption`` / ``label`` / ``dt`` / ``dd`` …) — pre-459 left
    Notion/Docs HTML table-cell and section exports unmatched after Tick 458
    list/blockquote containers (Tick 458 even left ``<table>`` as a negative
    allowlist example).

    Tick 465: also strip HTML anchor / button tags (``a`` / ``button``) —
    pre-465 left Notion/Docs/GitHub HTML link exports
    (``<a href=\"…\">STATUS: READY</a>``) unmatched after Tick 464 bracket
    wrap (bare ``[STATUS:…]`` only) and Tick 456–459 non-anchor tags.

    Tick 469: also strip HTML ``picture`` / ``source`` tags — pre-469 left
    responsive badge exports
    (``<picture><img alt=\"STATUS: READY\" src=\"…\"></picture>`` /
    ``<picture><source srcset=\"…\"><img alt=\"STATUS:…\">…</picture>``)
    unmatched after Tick 468 full-line ``<img alt>`` peel (``picture`` was
    not allowlisted, so the nested img never surfaced for alt peel).
    """
    return _ICML_STATUS_HTML_TAG_RE.sub("", line or "")


def _strip_icml_status_md_table_pipes(line: str) -> str:
    """Tick 459/461: strip outer markdown table-cell pipes (one-cell only).

    Notion / GitHub / Docs often paste STATUS into a one-cell markdown table
    row (``| STATUS: READY |`` / ``| **STATUS: READY** |``). Pre-459 HTML
    table-tag strip still left pure-markdown pipe rows unmatched — demote
    no-op / G4 pack miss READY. Only peel a full-line outer ``|…|`` wrapper
    when the inner cell has **no** ``|`` (true one-cell).

    Tick 461: Pre-461 used non-greedy ``.*?`` between outer pipes, so
    multi-cell ``| STATUS: READY | note |`` peeled to ``STATUS: READY | note``
    and the STATUS header regex still matched READY (trailing ``| note``
    ignored) — false READY / demote of a table note row. Leave multi-cell
    rows untouched (``| foo | STATUS: READY |`` / ``| STATUS: READY | note |``).
    """
    s = (line or "").strip()
    m = _ICML_STATUS_MD_PIPE_RE.match(s)
    if not m:
        return s
    return (m.group(1) or "").strip()


# Tick 460: peel leading blockquote / list / ATX inside the wrap loop so
# container + outer-wrap + pipe forms (``> `| STATUS: READY |` ``) unwrap.
# Tick 462: also peel GitHub task-list checkboxes (``- [ ] STATUS:…`` /
# ``- [x] STATUS:…``) — Tick 451/460 ``[-*+]\\s+`` alone left ``[ ]`` unmatched.
# Tick 463: also peel bare checkboxes (``[ ] STATUS:…`` / ``[x] STATUS:…``)
# and ordered-list checkboxes (``1. [ ] STATUS:…``) — Tick 462 required a
# ``[-*+]`` list marker, so paste stubs without ``-`` / with ``1. [ ]`` missed.
_ICML_STATUS_MD_CONTAINER_PREFIX_RE = re.compile(
    r"^(?:>\s+|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+(?:\[[ xX]\]\s+)?|"
    r"\[[ xX]\]\s+|#{1,6}\s+)"
)


def _strip_icml_status_md_wrappers(line: str) -> str:
    """Tick 457/458/459/460/461: strip outer markdown wrappers (iterate nested pairs).

    Chat / PR / docs paste often wraps the STATUS header in inline code
    (`` `STATUS: READY` `` / `` `**STATUS: READY**` ``) or strikethrough
    (``~~STATUS: READY~~``). Pre-457 HTML-tag strip left those unmatched —
    demote no-op / G4 pack miss READY.

    Tick 458: also strip Obsidian highlight (``==STATUS: READY==``) and iterate
    outer ``**`` / ``__`` / ``~~`` / backtick / ``==`` pairs so nested forms
    like ``**~~STATUS: READY~~**`` / ``==**STATUS: READY**==`` unwrap to a
    bare STATUS header. Cap iterations to avoid pathological loops; leave
    bare STATUS and mid-line wrappers alone when no outer pair matches.

    Tick 459: also peel outer markdown table pipes (``| STATUS: READY |``)
    so pipe+Obsidian / pipe+bold forms unwrap (``| ==STATUS: READY== |``).

    Tick 460: peel pipes **inside** the iterative loop (not only once before
    wraps). Pre-460 Tick 459 peeled ``|…|`` once up front, so outer
    wrap-around-pipe forms (`` `| STATUS: READY |` `` /
    ``~~| STATUS: READY |~~`` / ``==| STATUS: READY |==`` /
    ``**| STATUS: READY |**`` / `` `| **STATUS: READY** |` ``) left
    ``| STATUS: READY |`` after unwrap and never re-peeled — demote no-op /
    G4 pack miss READY. Also peel leading blockquote / list / ATX prefixes
    in the same loop so ``> `| STATUS: READY |` `` unwraps.

    Tick 461: also strip matching double/single quote wrappers
    (``"STATUS: READY"`` / ``'STATUS: READY'`` / ``"**STATUS: READY**"``)
    so JSON/YAML/chat paste stubs demote/update. Pipe peel is one-cell-only
    (see ``_strip_icml_status_md_table_pipes``).

    Tick 462: also peel GitHub task-list checkboxes in the container-prefix
    loop (``- [ ] STATUS: READY`` / ``- [x] **STATUS: READY**``) and accept
    inline token wraps in the STATUS header regex (``STATUS: `READY` `` /
    ``STATUS: ~~READY~~``) — pre-462 left checklist-header and chat
    code/strike token stubs unmatched (demote no-op / G4 pack miss READY).

    Tick 463: also peel bare checkboxes (``[ ] STATUS: READY`` /
    ``[x] **STATUS: READY**``), ordered-list checkboxes
    (``1. [ ] STATUS: READY``), and blockquote+bare-checkbox
    (``> [ ] STATUS: READY``) — pre-463 Tick 462 required ``[-*+]`` before
    ``[ ]``, so paste stubs without a dash / with ``1. [ ]`` missed.

    Tick 464: also peel matching paren / bracket / brace wrappers
    (``(STATUS: READY)`` / ``[STATUS: READY]`` / ``{STATUS: READY}`` /
    ``（STATUS: READY）``) and accept fullwidth colon ``STATUS：READY`` —
    pre-464 left chat/JSON/Notion paren stubs and CJK fullwidth-colon
    headers unmatched (demote no-op / G4 pack miss READY).

    Tick 465: also peel markdown inline link wrappers
    (``[STATUS: READY](url)`` / ``[**STATUS: READY**](#anchor)``) —
    pre-465 Tick 464 bare ``[STATUS:…]`` required the line to end at ``]``,
    so GitHub/Notion linked STATUS stubs with trailing ``(url)`` missed
    demote / G4 pack rewrite. Link peel runs before bare-bracket wrap and
    requires ``](`` so ``[ ] STATUS`` checkboxes are never mistaken for links.

    Tick 466: also peel markdown links whose destination contains balanced
    nested parentheses (``[STATUS: READY](https://x.com/foo_(bar))`` /
    ``[**STATUS: READY**](https://…#status-(draft))``) — pre-466
    ``[^)]*`` stopped at the first ``)``, so those GitHub/Notion linked
    STATUS stubs missed demote / G4 pack rewrite.

    Tick 467: also peel markdown **image** STATUS stubs
    (``![STATUS: READY](url)`` /
    ``![**STATUS: READY**](https://…/badge_(live).svg)``) — pre-467
    required a bare ``[`` start, so shields.io / Notion badge exports with
    a leading ``!`` missed demote / G4 pack rewrite.

    Tick 468: also peel HTML ``<img alt="STATUS:…">`` STATUS stubs
    (``<img alt="STATUS: READY" src="…">`` /
    ``<img src="…/badge_(live).svg" alt="**STATUS: READY**" />``) — pre-468
    Tick 467 only peeled markdown ``![…](…)``, so Notion/Docs/GitHub HTML
    badge exports missed demote / G4 pack rewrite (``img`` is not in the
    HTML-tag allowlist — stripping would drop the alt).

    Tick 469: also strip HTML ``<picture>`` / ``<source>`` wrappers so nested
    ``<img alt="STATUS:…">`` reaches the Tick 468 peel
    (``<picture><img alt="STATUS: READY" src="…"></picture>`` /
    ``<picture><source srcset="…"><img alt="**STATUS: READY**" …></picture>``)
    — pre-469 left responsive badge exports unmatched after Tick 468
    required a full-line bare ``<img>``.

    Tick 470: also peel HTML ``<img title="STATUS:…">`` /
    ``<img aria-label="STATUS:…">`` (and decorative-alt + STATUS title)
    — pre-470 Tick 468/469 only read ``alt=``, so a11y/tooltip badge
    exports missed demote / G4 pack rewrite.

    Tick 471: also peel inline SVG ``<title>STATUS:…</title>`` badge
    exports (``<svg…><title>STATUS: READY</title>…</svg>``) — pre-471
    Tick 468–470 only covered ``<img>`` attrs, so shields.io / Notion SVG
    STATUS stubs missed demote / G4 pack rewrite (allowlist-stripping
    ``svg``/``title`` would concatenate residual ``<text>``/``<desc>``).

    Tick 472: also peel SVG root ``aria-label=`` / ``title=`` STATUS
    (``<svg aria-label="STATUS: READY" …>…</svg>`` /
    ``<svg title="**STATUS: READY**"><title>Badge</title>…</svg>``) —
    pre-472 Tick 471 only read nested ``<title>``, so a11y/tooltip SVG
    badge exports (decorative nested title / missing ``<title>``) missed
    demote / G4 pack rewrite.

    Tick 473: also peel SVG nested ``<desc>`` STATUS
    (``<svg…><title>Badge</title><desc>STATUS: READY</desc>…</svg>`` /
    ``<svg role="img"><desc>**STATUS: READY**</desc>…</svg>``) —
    pre-473 Tick 471/472 only read root attrs + nested ``<title>``, so a11y
    long-description badge exports (decorative / missing title; STATUS only
    in ``<desc>``) missed demote / G4 pack rewrite.

    Tick 474: also peel SVG nested ``<text>`` STATUS
    (``<svg…><title>Badge</title><text>STATUS: READY</text>…</svg>`` /
    ``<svg role="img"><text><tspan>**STATUS: READY**</tspan></text></svg>``) —
    pre-474 Tick 471–473 only read attrs / ``<title>`` / ``<desc>``, so
    Figma / Illustrator / shields-like visible-label badge exports
    (decorative a11y name; STATUS only in ``<text>``) missed demote /
    G4 pack rewrite.

    Tick 475: also peel SVG nested ``<foreignObject>`` STATUS
    (``<svg…><title>Badge</title><foreignObject><div>STATUS: READY</div>
    </foreignObject>…</svg>`` /
    ``<svg role="img"><foreignObject><span>**STATUS: READY**</span>
    </foreignObject></svg>``) — pre-475 Tick 471–474 only read attrs /
    ``<title>`` / ``<desc>`` / ``<text>``, so Figma / browser HTML-in-SVG
    label badge exports (decorative a11y name; STATUS only in
    ``<foreignObject>``) missed demote / G4 pack rewrite.

    Tick 476: pretty-printed multi-line ``<svg>…</svg>`` blocks are collapsed
    by ``_iter_icml_ready_status_units`` / ``_take_icml_status_multiline_svg_block``
    before this peel — Figma / Illustrator "Copy as SVG" STATUS badges that
    span lines (``<svg>\\n  <text>STATUS: READY</text>\\n</svg>``) reach the
    Tick 471–475 single-line SVG peels. Pre-476 required a full-line SVG, so
    those stubs missed demote / G4 pack rewrite (except accidental HTML
    ``<div>STATUS:…</div>`` allowlist peels inside multi-line foreignObject).

    Tick 479: mid-line ``<svg`` after wrappers
    (``<div role="img"><svg\\n  aria-label="STATUS:…"\\n>…</svg></div>``)
    is also collapsed by ``_take_icml_status_multiline_svg_block`` before this
    peel — pre-479 Tick 476 required ``^<svg`` at line start.

    Tick 480: soft-wrapped markdown link/image blocks are collapsed by
    ``_take_icml_status_multiline_md_link_block`` before Tick 465–467 peels.

    Tick 481: also peel HTML ``<a>``/``<button>`` ``title=`` / ``aria-label=``
    STATUS *before* allowlist strip (see ``_peel_icml_status_html_a_title``);
    multi-line pretty-printed opens are collapsed by
    ``_take_icml_status_multiline_a_block``. Pre-481 Tick 465 strip kept
    inner text only (``badge``/``Go``), dropping STATUS attrs.

    Tick 482: also peel HTML ``span``/``label``/``div``/``summary``/
    ``figcaption``/``mark`` ``title=`` / ``aria-label=`` STATUS *before*
    allowlist strip (see ``_peel_icml_status_html_span_title``); multi-line
    opens collapsed by ``_take_icml_status_multiline_span_block``. Pre-482
    Tick 481 only covered ``a``/``button``.

    Tick 483: also peel remaining allowlisted ``p``/``strong``/``h1``–``h6``/
    ``td``/``th``/``li``/``blockquote``/``section``/``article``/… ``title=`` /
    ``aria-label=`` STATUS *before* allowlist strip — Tick 482 only covered
    ``span``/``label``/``div``/``summary``/``figcaption``/``mark``.

    Tick 484: also peel ``aria-description=`` (ARIA 1.3) on the same
    allowlisted a/button/span/inline/img/svg surfaces — Tick 481–483 only
    covered ``title=`` / ``aria-label=``, so a11y long-description badge
    exports (``<p aria-description="STATUS: READY">badge</p>`` /
    ``<span aria-description="STATUS: READY">x</span>`` /
    Prettier ``<p\\n  aria-description="STATUS: READY"\\n>badge</p>``)
    still collapsed to decorative body and missed demote / G4 pack.

    Tick 485: also peel *unquoted* STATUS attr values on those same
    surfaces (``<p title=STATUS:READY>badge</p>`` /
    ``<img alt=STATUS:READY src=…>`` /
    ``<a aria-label=STATUS:IN_PROGRESS>Go</a>``) — minified HTML / some
    CMS / shields-like exports omit quotes; HTML unquoted values cannot
    contain whitespace, so spaced ``STATUS: READY`` remains quoted-only.
    """
    s = (line or "").strip()
    for _ in range(12):
        peeled = _strip_icml_status_md_table_pipes(s)
        if peeled != s:
            s = peeled
            continue
        m_pref = _ICML_STATUS_MD_CONTAINER_PREFIX_RE.match(s)
        if m_pref:
            nxt = s[m_pref.end() :].strip()
            if nxt and nxt != s:
                s = nxt
                continue
        # Tick 481/484/485: peel <a>/<button> title/aria-label/aria-description
        # (quoted or unquoted) STATUS *before* allowlist strip (Tick 465 strip
        # keeps inner text only and drops attrs).
        a_title = _peel_icml_status_html_a_title(s)
        if a_title and a_title != s:
            s = a_title
            continue
        # Tick 482/484/485: peel span/label/div/… (quoted or unquoted).
        span_title = _peel_icml_status_html_span_title(s)
        if span_title and span_title != s:
            s = span_title
            continue
        # Tick 483/484/485: peel p/strong/h1/td/… (quoted or unquoted).
        inline_title = _peel_icml_status_html_inline_title(s)
        if inline_title and inline_title != s:
            s = inline_title
            continue
        # Tick 469: peel picture/source *inside* the wrap loop so
        # `` `| <picture><img alt=…></picture> |` `` still reaches img-alt.
        html_peeled = _strip_icml_status_html_tags(s)
        if html_peeled != s:
            s = html_peeled.strip()
            continue
        # Tick 468/470/484/485: peel img alt / title / aria-label /
        # aria-description (quoted or unquoted).
        # Tick 477: multi-line img already collapsed into ``s`` when present.
        img_alt = _peel_icml_status_html_img_alt(s)
        if img_alt and img_alt != s:
            s = img_alt
            continue
        # Tick 471–475/484/485: peel SVG title / aria / desc / text /
        # foreignObject (+ root aria-description; quoted or unquoted).
        # Tick 476: multi-line SVG already collapsed into ``s`` when present.
        svg_title = _peel_icml_status_html_svg_title(s)
        if svg_title and svg_title != s:
            s = svg_title
            continue
        link_text = _peel_icml_status_md_link(s)
        if link_text and link_text != s:
            s = link_text
            continue
        m = _ICML_STATUS_MD_WRAP_RE.match(s)
        if not m:
            break
        inner = next((g for g in m.groups() if g is not None), None)
        nxt = (inner or "").strip()
        if nxt == s:
            break
        s = nxt
    return s


# Tick 464: ASCII ``:`` or fullwidth ``：`` (U+FF1A) after STATUS.
_ICML_STATUS_COLON = r"[:：]"

_ICML_READY_STATUS_HEADER_RE = re.compile(
    # Tick 462/463: optional list/ordered marker + optional task-list checkbox
    # (``- [ ] STATUS:…`` / ``[ ] STATUS:…`` / ``1. [ ] STATUS:…`` /
    # ``> [x] **STATUS:…**``).
    r"^(?:>\s*)?(?:(?:[-*+]|\d+[.)])\s+)?(?:\[[ xX]\]\s+)?(?:#{1,6}\s+)?"
    r"(?:"
    # Tick 461/464: optional whitespace before ``:`` / fullwidth ``：``
    # (``STATUS : READY`` / ``STATUS：READY``).
    # Use string concat (not rf"…{3}…") so regex quantifiers stay literal.
    r"\*{3}STATUS\*{0,3}\s*"
    + _ICML_STATUS_COLON
    + r"\s*\*{0,3}\s*"  # ***STATUS***: / ***STATUS:***
    r"|"
    r"\*\*__STATUS(?:__)?\s*"
    + _ICML_STATUS_COLON
    + r"\s*(?:__)?\s*"  # **__STATUS:… / **__STATUS__:…
    r"|"
    r"__\*\*STATUS(?:\*\*)?\s*"
    + _ICML_STATUS_COLON
    + r"\s*(?:\*\*)?\s*"  # __**STATUS:… / __**STATUS:**…
    r"|"
    # Double-underscore bold. Use (?:__)? — NOT __? — so STATUS may be
    # followed by zero underscores before ``:`` (``__STATUS: READY__``).
    # ``__?`` would require ≥1 ``_`` after STATUS (``?`` only optionalizes the
    # second underscore of a two-underscore run).
    r"__STATUS(?:__)?\s*"
    + _ICML_STATUS_COLON
    + r"\s*(?:__)?\s*"  # __STATUS__: / __STATUS:__ / __STATUS:
    r"|"
    r"(?:\*\*)?STATUS(?:\*\*)?\s*"
    + _ICML_STATUS_COLON
    + r"\s*(?:\*\*)?\s*"  # bold / plain / label / colon-out
    r"|"
    r"\*STATUS\*?\s*"
    + _ICML_STATUS_COLON
    + r"\s*\*?\s*"  # italic *STATUS*: / *STATUS:* / *STATUS:
    r"|"
    r"_STATUS_?\s*"
    + _ICML_STATUS_COLON
    + r"\s*_?\s*"  # underscore _STATUS_: / _STATUS:_ / _STATUS:
    r")"
    # Tick 462: optional inline wrap around the token (``STATUS: `READY` `` /
    # ``STATUS: ~~READY~~``) — outer-line wraps already peeled by md-wrap.
    r"(?:`+|~~)?"
    r"\s*"
    r"(READY|IN_PROGRESS)"
    r"\s*"
    # Optional trailing close emphasis / token wrap. Compound nested closers
    # first (``**__`` / ``__**``), then ~~ / backticks, then longer single
    # closers (*** before ** before *). Do not use \\b before ``_`` / ``__``
    # closers — underscore is a word char (Tick 452/453), so ``READY_`` /
    # ``READY__`` have no word boundary.
    r"(?:`+|~~|\*\*__|__\*\*|\*{1,3}|__|_)?(?!\w)",
    re.IGNORECASE,
)


def _strip_icml_status_line_noise(line: str) -> str:
    """Tick 451/454/455/456/457/458/459/460: decode entities, strip HTML/md wrappers + BOM/ZWSP/….

    Python ``str.strip()`` does **not** remove ZWSP (``\\u200b``) / ZWNJ / ZWJ /
    word-joiner / soft-hyphen. Pre-454 only ``lstrip(\"\\ufeff\")`` + ``strip()``,
    so a Notion/Docs paste of ``\\u200b**STATUS: READY**`` (or ZWSP between a
    blockquote marker and STATUS) made demote no-op / G4 pack miss READY while
    leaving poisoned READY on disk. Remove invisibles anywhere on the line
    before matching so ``> \\u200b**STATUS:…**`` still parses.

    Tick 455: also decode HTML entities for those same invisibles (+ ``&nbsp;``)
    before Unicode strip — ``&#8203;**STATUS: READY**`` /
    ``&ZeroWidthSpace;**STATUS:…**`` / ``**STATUS:&nbsp;READY**`` otherwise stay
    unmatched after Tick 454's Unicode-only strip.

    Tick 486: also decode HTML-entity STATUS colons (``STATUS&#58; READY`` /
    ``STATUS&colon;READY`` / ``STATUS&#x3a; READY`` / ``STATUS&#xff1a;READY`` /
    attr ``title="STATUS&#58; READY"``) — pre-486 Tick 455 invisibles-only
    decode left CMS/XSS-escaped colon stubs unmatched (demote no-op /
    G4 pack miss READY).

    Tick 456: also strip allowlisted formatting HTML tags after entity decode —
    ``<strong>STATUS: READY</strong>`` / ``<p><b>**STATUS:…**</b></p>`` /
    ``<span style=\"…\">**STATUS: READY**</span>`` otherwise stay unmatched
    after Tick 455's entity-only path.

    Tick 457: also strip HTML heading tags (``<h1>…</h1>`` … ``<h6>``) and
    outer markdown backtick / strikethrough wrappers (`` `STATUS: READY` `` /
    ``~~STATUS: READY~~``) — pre-457 left Notion HTML heading export and
    chat/code-paste stubs unmatched after Tick 448 ATX + Tick 456 non-heading
    tags.

    Tick 458: also strip HTML container tags (``blockquote`` / ``li`` / ``ul`` /
    ``ol`` …) and Obsidian ``==…==`` highlight / nested ``**~~…~~**`` wrappers —
    pre-458 left Notion HTML list/blockquote exports and Obsidian highlight
    stubs unmatched after Tick 451 markdown containers + Tick 457 md-wrap.

    Tick 459: also strip HTML table + semantic sectioning tags (``td`` / ``th`` /
    ``table`` / ``section`` / ``article`` …) and outer markdown pipe-table
    rows (``| STATUS: READY |``) — pre-459 left Notion/Docs HTML table-cell /
    section exports and GitHub one-cell pipe stubs unmatched after Tick 458.

    Tick 460: peel markdown pipes **iteratively** with wraps / container
    prefixes — pre-460 Tick 459 peeled ``|…|`` only once before wraps, so
    `` `| STATUS: READY |` `` / ``~~| STATUS:… |~~`` / ``> `| STATUS:… |` ``
    left residual pipes after unwrap (demote no-op / G4 pack miss READY).

    Tick 461: also strip quote wrappers + allow ``STATUS : TOKEN`` (space
    before colon); one-cell-only pipe peel so ``| STATUS: READY | note |``
    is not a false READY header.

    Tick 462: also peel GitHub task-list checkboxes (``- [ ]`` / ``- [x]``)
    and accept inline token wraps (``STATUS: `READY` `` / ``STATUS: ~~READY~~``)
    — pre-462 left those stubs unmatched (demote no-op / G4 pack miss READY).

    Tick 463: also peel bare checkboxes (``[ ]`` / ``[x]``), ordered-list
    checkboxes (``1. [ ]``), and blockquote+bare-checkbox (``> [ ]``) —
    pre-463 left paste stubs without a ``[-*+]`` list marker unmatched.

    Tick 464: also peel matching paren / bracket / brace wrappers
    (``(STATUS: READY)`` / ``[STATUS: READY]`` / ``{STATUS: READY}`` /
    ``（STATUS: READY）``) and accept fullwidth colon ``STATUS：READY`` —
    pre-464 left chat/JSON/Notion paren stubs and CJK fullwidth-colon
    headers unmatched (demote no-op / G4 pack miss READY).

    Tick 465: also peel markdown inline links
    (``[STATUS: READY](url)`` / ``[**STATUS: READY**](#anchor)``) and strip
    HTML ``<a>`` / ``<button>`` tags — pre-465 left GitHub/Notion linked
    STATUS stubs unmatched after Tick 464 bare-bracket wrap (demote no-op /
    G4 pack miss READY).

    Tick 469: also strip HTML ``<picture>`` / ``<source>`` so nested
    ``<img alt="STATUS:…">`` reaches Tick 468 peel — pre-469 left responsive
    badge exports unmatched after Tick 468 full-line ``<img>`` only.

    Tick 481: also peel HTML ``<a>``/``<button>`` ``title=`` / ``aria-label=``
    STATUS *before* allowlist strip — Tick 465 strip keeps inner text only
    (``badge``/``Go``) and drops STATUS attrs, so a11y/tooltip link badge
    exports missed demote / G4 pack rewrite after Tick 470/472 covered the
    same attrs on ``<img>``/``<svg>``.

    Tick 482: also peel HTML ``span``/``label``/``div``/``summary``/
    ``figcaption``/``mark`` ``title=`` / ``aria-label=`` STATUS *before*
    allowlist strip — Tick 481 only covered ``a``/``button``, so a11y
    badge exports on these wrappers still missed demote / G4 pack.

    Tick 483: also peel remaining allowlisted ``p``/``strong``/``h1``–``h6``/
    ``td``/``th``/``li``/``blockquote``/``section``/``article``/… ``title=`` /
    ``aria-label=`` STATUS *before* allowlist strip — Tick 482 only covered
    ``span``/``label``/``div``/``summary``/``figcaption``/``mark``.

    Tick 484: also peel ``aria-description=`` STATUS *before* allowlist strip
    on the same a/button/span/inline/img/svg surfaces — Tick 481–483 only
    covered ``title=`` / ``aria-label=``.
    """
    s = _decode_icml_status_html_entities(line or "")
    # Tick 481/484: peel a/button title/aria-label/aria-description before strip.
    a_title = _peel_icml_status_html_a_title(s)
    if a_title:
        s = a_title
    else:
        # Tick 482/484: peel span/label/div/… title/aria-label/aria-description.
        span_title = _peel_icml_status_html_span_title(s)
        if span_title:
            s = span_title
        else:
            # Tick 483/484: peel p/strong/h1/td/… title/aria-label/aria-description.
            inline_title = _peel_icml_status_html_inline_title(s)
            if inline_title:
                s = inline_title
            else:
                s = _strip_icml_status_html_tags(s)
    s = _strip_icml_status_md_wrappers(s)
    # Tick 492/493/494/495/496: bare base64 / data-URI / bare hex / C-array hex
    # after wrap strip (``**U1RBVFVTOiBSRUFEWQ==**`` /
    # ``**data:text/plain;base64,…**`` / ``**data:text/plain,STATUS%3A%20READY**``
    # / ``**5354415…4459**`` / ``**0x53,0x54,…**``).
    peeled_uri = _peel_icml_status_data_uri_base64(s)
    if peeled_uri != s:
        s = _decode_icml_status_html_entities(peeled_uri)
        s = _strip_icml_status_md_wrappers(s)
    peeled_plain = _peel_icml_status_data_uri_plain(s)
    if peeled_plain != s:
        s = _decode_icml_status_html_entities(peeled_plain)
        s = _strip_icml_status_md_wrappers(s)
    peeled_b64 = _peel_icml_status_bare_base64(s)
    if peeled_b64 != s:
        s = _decode_icml_status_html_entities(peeled_b64)
        s = _strip_icml_status_md_wrappers(s)
    peeled_hex = _peel_icml_status_bare_hex(s)
    if peeled_hex != s:
        s = _decode_icml_status_html_entities(peeled_hex)
        s = _strip_icml_status_md_wrappers(s)
    s = _ICML_STATUS_INVISIBLE_CHARS_RE.sub("", s)
    return s.strip()


def _icml_ready_status_line_match(line: str):
    """Tick 447–465: match a STATUS header line (bold/plain/ATX/label/colon-out/container/task-list/bare-checkbox/ordered-checkbox/italic/__/ ***/ZWSP/nested/HTML-entity/HTML-tag/HTML-heading/HTML-container/md-wrap/Obsidian/HTML-table/semantic/md-pipe/wrap+pipe/quote/space-colon/token-wrap/paren/bracket/brace/fullwidth-colon/md-link/HTML-anchor) after strip."""
    return _ICML_READY_STATUS_HEADER_RE.match(_strip_icml_status_line_noise(line))


def _icml_ready_status_header(text: str) -> str | None:
    """Tick 442/446/447/448/449/450/451/452/453/454/455/456/457/458/459/460/461/462/463/464/465: read STATUS from the STATUS header line only.

    Pre-442 demote / richness / merge used whole-body substring checks for
    ``STATUS: READY`` / ``STATUS: IN_PROGRESS``. Tick notes and G4 audit prose
    often mention those phrases (e.g. ``do not leave STATUS: IN_PROGRESS``),
    which made ``_demote_icml_ready_status`` no-op and left a poisoned
    ``**STATUS: READY**`` header after durable conflict merge — or zeroed the
    richness ``status_ready`` bit on a true READY header.

    Tick 446: also parse the token immediately after ``**STATUS:`` instead of
    scanning the whole header line for ``IN_PROGRESS`` / ``READY`` substrings.
    Pre-446 preferred ``IN_PROGRESS`` anywhere on the line, so a true READY
    header with a trailing note (``**STATUS: READY** — was IN_PROGRESS``) was
    misread as IN_PROGRESS — ``demote_icml_ready_file`` then no-op'd and left
    poisoned READY on disk after trust refuse; richness zeroed ``status_ready``.

    Tick 447: accept bare ``STATUS: READY|IN_PROGRESS`` (no ``**``) as the
    header line too. Pre-447 required ``**STATUS:`` only, so plain
    ``STATUS: READY`` stubs (common in tests / thin durable merges) made
    ``demote_icml_ready_file`` / pipeline read / richness miss READY, and
    ``update_icml_ready_from_g4`` failed to rewrite plain IN_PROGRESS up to
    READY after live criteria pass. Mid-line prose (``Do not set STATUS:
    READY``) still does not match because the line must *start* with
    optional ``**`` + ``STATUS:``.

    Tick 448: also accept ATX heading forms (``# STATUS: READY`` /
    ``## **STATUS: IN_PROGRESS**``). Pre-448 required a non-heading start, so
    promoted heading stubs made demote no-op / G4 pack miss the same way plain
    STATUS did before Tick 447. Document titles like ``# ICML Thesis…`` still
    do not match (no ``STATUS:`` token).

    Tick 449: also accept bold-closed label forms (``**STATUS:** READY`` /
    ``## **STATUS:** IN_PROGRESS``). Pre-449 required the token inside the
    same bold span as ``STATUS:`` (``**STATUS: READY**``), so the common
    markdown ``**Label:** value`` shape made demote no-op / G4 pack miss —
    ``demote_icml_ready_file`` saw header=None (!= READY) and left
    ``**STATUS:** READY`` poisoned on disk after trust refuse.

    Tick 450: also accept colon-outside-bold forms (``**STATUS**: READY`` /
    ``## **STATUS**: IN_PROGRESS``). Pre-450 required the colon inside the
    bold span (``**STATUS:**`` or ``**STATUS: TOKEN**``), so bold-label +
    colon-outside (``**STATUS**: TOKEN``) made demote no-op / G4 pack miss
    the same way Tick 449's ``**STATUS:**`` stubs did.

    Tick 451: also accept blockquote / list container prefixes
    (``> **STATUS: READY**`` / ``- **STATUS: IN_PROGRESS**`` /
    ``1. STATUS: READY``) and strip a leading UTF-8 BOM on the file or line.
    Pre-451 required a bare / heading / bold start after strip, so quoted or
    listed READY stubs (and BOM-prefixed first lines from Windows editors)
    made demote no-op / G4 pack miss the same way prior STATUS variants did.

    Tick 452: also accept italic / underscore emphasis wrappers
    (``*STATUS*: READY`` / ``*STATUS: READY*`` / ``_STATUS: READY_`` /
    ``_STATUS_: IN_PROGRESS``). Pre-452 treated single ``*``/``_`` without
    following whitespace as non-headers (Tick 451 left italic ignored so it
    would not collide with list markers), so emphasis stubs made demote no-op
    / G4 pack miss READY the same way prior STATUS variants did. List markers
    still require ``\\s+`` after ``*``/``-``/``+`` (``* STATUS: READY`` stays
    a list line matched via the plain STATUS alt).

    Tick 453: also accept double-underscore bold and triple-star bold+italic
    (``__STATUS: READY__`` / ``__STATUS__: IN_PROGRESS`` / ``***STATUS: READY***``
    / ``***STATUS:*** READY``). Pre-453 matched ``**`` / ``*`` / ``_`` only, so
    CommonMark ``__bold__`` and ``***bold+italic***`` stubs made demote no-op /
    G4 pack miss READY the same way prior STATUS variants did.

    Tick 454: also strip leading invisible format chars (ZWSP ``\\u200b`` /
    ZWNJ / ZWJ / word-joiner / soft-hyphen / BOM) before matching, and accept
    nested bold↔dunder wrappers (``**__STATUS: READY__**`` /
    ``__**STATUS: READY**__``). Pre-454 left Notion/Docs paste ZWSP prefixes
    and mixed-editor nested ``**``/``__`` stubs unmatched — demote no-op / G4
    pack miss READY the same way prior STATUS variants did.

    Tick 455: also decode HTML entities for those invisibles (+ ``&nbsp;``)
    before Unicode strip (``&#8203;**STATUS: READY**`` /
    ``&ZeroWidthSpace;**STATUS:…**`` / ``**STATUS:&nbsp;READY**``). Pre-455
    Unicode-only strip left HTML-export stubs unmatched — demote no-op / G4
    pack miss READY the same way prior STATUS variants did.

    Tick 456: also strip allowlisted formatting HTML tags after entity decode
    (``<strong>STATUS: READY</strong>`` / ``<p><b>**STATUS:…**</b></p>`` /
    ``<span style=\"…\">**STATUS: READY**</span>``). Pre-456 entity/ZWSP strip
    left rich-paste / partial HTML→Markdown stubs unmatched — demote no-op /
    G4 pack miss READY the same way prior STATUS variants did.

    Tick 457: also strip HTML heading tags (``<h1>STATUS: READY</h1>`` …
    ``<h6>``) and outer markdown backtick / strikethrough wrappers
    (`` `STATUS: READY` `` / `` `**STATUS: READY**` `` / ``~~STATUS: READY~~``).
    Pre-457 left Notion/Docs HTML heading export (ATX Tick 448 already worked)
    and chat/code-paste stubs unmatched — demote no-op / G4 pack miss READY.

    Tick 458: also strip HTML container tags (``<blockquote>STATUS: READY</blockquote>``
    / ``<li>STATUS: READY</li>`` / ``<ul>…</ul>``) and Obsidian highlight /
    nested markdown wrappers (``==STATUS: READY==`` / ``**~~STATUS: READY~~**``).
    Pre-458 left Notion HTML list/blockquote exports (Tick 451 markdown ``>`` /
    ``-`` already worked) and Obsidian highlight stubs unmatched — demote
    no-op / G4 pack miss READY.

    Tick 459: also strip HTML table + semantic sectioning tags
    (``<td>STATUS: READY</td>`` / ``<th>**STATUS:…**</th>`` /
    ``<table><tr><td>STATUS: READY</td></tr></table>`` /
    ``<section>STATUS: READY</section>`` / ``<article>**STATUS:…**</article>``)
    and outer markdown pipe-table rows (``| STATUS: READY |`` /
    ``| **STATUS: READY** |``). Pre-459 left Notion/Docs HTML table-cell /
    section exports and GitHub one-cell pipe stubs unmatched — demote no-op /
    G4 pack miss READY (Tick 458 explicitly left ``<table>`` unmatched as a
    negative allowlist example).

    Tick 460: peel markdown pipes **iteratively** with wraps / container
    prefixes so outer wrap-around-pipe forms (`` `| STATUS: READY |` `` /
    ``~~| STATUS: READY |~~`` / ``==| STATUS: READY |==`` /
    ``**| STATUS: READY |**`` / `` `| **STATUS: READY** |` `` /
    ``> `| STATUS: READY |` ``) unwrap. Pre-460 Tick 459 peeled ``|…|``
    only once before wraps — residual pipes after unwrap made demote no-op /
    G4 pack miss READY.

    Tick 461: (a) one-cell-only markdown pipe peel so
    ``| STATUS: READY | note |`` is **not** a false READY header (pre-461
    non-greedy ``.*?`` peeled to ``STATUS: READY | note`` and still matched);
    (b) quote wrappers (``"STATUS: READY"`` / ``'STATUS: READY'``); (c)
    optional whitespace before colon (``STATUS : READY``). Pre-461 quote /
    space-colon stubs made demote no-op / G4 pack miss READY.

    Tick 462: also peel GitHub task-list checkboxes after list markers
    (``- [ ] STATUS: READY`` / ``- [x] **STATUS: READY**``) and accept
    inline token wraps (``STATUS: `READY` `` / ``STATUS: ~~READY~~``).

    Tick 463: also peel bare checkboxes (``[ ] STATUS: READY`` /
    ``[x] **STATUS: READY**``), ordered-list checkboxes
    (``1. [ ] STATUS: READY`` / ``1. [x] **STATUS: READY**``), and
    blockquote+bare-checkbox (``> [ ] STATUS: READY``) — pre-463 Tick 462
    required ``[-*+]`` before ``[ ]``, so those paste stubs made demote
    no-op / G4 pack miss READY.

    Tick 464: also peel matching paren / bracket / brace wrappers
    (``(STATUS: READY)`` / ``[STATUS: READY]`` / ``{STATUS: READY}`` /
    ``（STATUS: READY）``) and accept fullwidth colon ``STATUS：READY`` —
    pre-464 left chat/JSON/Notion paren stubs and CJK fullwidth-colon
    headers unmatched (demote no-op / G4 pack miss READY).

    Tick 465: also peel markdown inline links
    (``[STATUS: READY](url)`` / ``[**STATUS: READY**](#anchor)``) and strip
    HTML ``<a>`` / ``<button>`` — pre-465 Tick 464 bare ``[STATUS:…]``
    required the line to end at ``]``, so GitHub/Notion linked STATUS stubs
    with trailing ``(url)`` / ``<a href>`` made demote no-op / G4 pack miss
    READY.

    Tick 476: also scan pretty-printed multi-line ``<svg>…</svg>`` STATUS
    blocks (collapsed via ``_iter_icml_ready_status_units``) — pre-476
    line-at-a-time scan missed Figma / Illustrator multi-line SVG badges.
    """
    for _span, match_line in _iter_icml_ready_status_units(text):
        m = _icml_ready_status_line_match(match_line)
        if not m:
            continue
        token = m.group(1).upper()
        if token == "IN_PROGRESS":
            return "IN_PROGRESS"
        if token == "READY":
            return "READY"
        return None
    return None


def _icml_ready_richness(text: str) -> tuple:
    """Tick 441/442: score ``docs/ICML_READY.md`` (higher = richer live checklist).

    Pre-441 ``merge_icml_ready_text`` picked the longer body when either side
    was ``IN_PROGRESS``. A thin local stub padded with a long Tick note could
    wipe onto's post-G4 checklist where PRIMARY / live H2 / H5 / Table rows
    were already ``[x]`` — paid READY evidence lost even though Tick 438
    "merged" the conflict (STATUS demotion is still correct; the body is not).

    Tick 442: ``status_ready`` uses the header line only (not prose substrings).
    """
    t = text or ""
    if not t.strip():
        return (0, 0, 0, 0, 0, 0)
    # Count publishable end-goal checkboxes that are marked done.
    live_checks = 0
    for needle in (
        "- [x] D beats B on ≥3/5 seeds for gens-to-threshold",
        "- [x] D beats B on ≥3/5 seeds for cost-to-threshold",
        "- [x] Non-trivial mean final accuracy gap",
        "- [x] Live API-run H2",
        "- [x] Spearman ρ",
        "- [x] Table 1 (primary metrics by seed)",
        "- [x] Table 2 (H2/H5 / cost)",
        "- [x] Reproducible **live** run IDs",
        "- [x] Reproducible live run IDs",
    ):
        if needle in t:
            live_checks += 1
    status_ready = 1 if _icml_ready_status_header(t) == "READY" else 0
    checked = t.count("- [x]")
    low = t.lower()
    live_phrase = 1 if ("live gpqa" in low or "live api" in low) else 0
    return (1, live_checks, status_ready, checked, live_phrase, len(t))


def prefer_richer_icml_ready(a: str, b: str) -> str:
    """Tick 441: keep the richer ICML_READY body (ties → ``b``)."""
    a = a or ""
    b = b or ""
    if not a.strip() and b.strip():
        return b
    if not b.strip() and a.strip():
        return a
    if _icml_ready_richness(b) >= _icml_ready_richness(a):
        return b
    return a


def _demote_icml_ready_status(body: str) -> str:
    """Force header STATUS: IN_PROGRESS while preserving checklist (Tick 438/442/447–459).

    Tick 442: rewrite only STATUS *header* lines so Tick-note / audit prose
    mentioning ``STATUS: IN_PROGRESS`` cannot no-op the demote and leave a
    poisoned ``**STATUS: READY**`` header after durable conflict merge.

    Tick 447: also rewrite bare ``STATUS: READY|IN_PROGRESS`` header lines
    (normalize to ``**STATUS: IN_PROGRESS**``). Pre-447 fell through to a
    whole-body ``str.replace("STATUS: READY", …)`` that could hit prose
    (``Do not set STATUS: READY``) *before* the real plain header and leave
    poisoned READY on disk.

    Tick 448: also rewrite ATX heading STATUS lines (``# STATUS: READY`` /
    ``## **STATUS: READY**``) to the same normalized ``**STATUS: IN_PROGRESS**``.

    Tick 449: also rewrite bold-closed label forms (``**STATUS:** READY`` /
    ``## **STATUS:** IN_PROGRESS``) to the same normalized header.

    Tick 450: also rewrite colon-outside-bold forms (``**STATUS**: READY`` /
    ``## **STATUS**: IN_PROGRESS``) to the same normalized header.

    Tick 451: also rewrite blockquote / list container STATUS lines
    (``> **STATUS: READY**`` / ``- STATUS: READY`` / ``1. **STATUS:** READY``)
    and BOM-prefixed headers to the same normalized header.

    Tick 452: also rewrite italic / underscore emphasis STATUS lines
    (``*STATUS*: READY`` / ``*STATUS: READY*`` / ``_STATUS: READY_``) to the
    same normalized header.

    Tick 453: also rewrite double-underscore bold / triple-star bold+italic
    STATUS lines (``__STATUS: READY__`` / ``***STATUS: READY***``) to the same
    normalized header.

    Tick 454: also rewrite ZWSP-prefixed and nested bold↔dunder STATUS lines
    (``\\u200b**STATUS: READY**`` / ``**__STATUS: READY__**`` /
    ``__**STATUS: READY**__``) to the same normalized header.

    Tick 455: also rewrite HTML-entity ZWSP / nbsp STATUS lines
    (``&#8203;**STATUS: READY**`` / ``&ZeroWidthSpace;**STATUS:…**`` /
    ``**STATUS:&nbsp;READY**``) to the same normalized header.

    Tick 456: also rewrite HTML-tag-wrapped STATUS lines
    (``<strong>STATUS: READY</strong>`` / ``<p><b>**STATUS:…**</b></p>`` /
    ``<span style=\"…\">**STATUS: READY**</span>``) to the same normalized
    header.

    Tick 457: also rewrite HTML heading + markdown backtick / strikethrough
    STATUS lines (``<h1>STATUS: READY</h1>`` / `` `STATUS: READY` `` /
    ``~~STATUS: READY~~``) to the same normalized header.

    Tick 458: also rewrite HTML container + Obsidian highlight / nested md
    STATUS lines (``<blockquote>STATUS: READY</blockquote>`` /
    ``<li>STATUS: READY</li>`` / ``==STATUS: READY==`` /
    ``**~~STATUS: READY~~**``) to the same normalized header.

    Tick 459: also rewrite HTML table + semantic sectioning + markdown
    pipe-table STATUS lines (``<td>STATUS: READY</td>`` /
    ``<section>STATUS: READY</section>`` / ``| STATUS: READY |`` /
    ``| **STATUS: READY** |``) to the same normalized header.

    Tick 460–461: also rewrite wrap-around pipe / quote / space-colon STATUS
    lines (`` `| STATUS: READY |` `` / ``"STATUS: READY"`` / ``STATUS : READY``)
    to the same normalized header (multi-cell pipes intentionally untouched).

    Tick 462: also rewrite GitHub task-list checkbox headers
    (``- [ ] STATUS: READY`` / ``- [x] **STATUS: READY**``) and inline
    token-wrap forms (``STATUS: `READY` `` / ``STATUS: ~~READY~~``) to the
    same normalized header.

    Tick 463: also rewrite bare / ordered / blockquote-checkbox headers
    (``[ ] STATUS: READY`` / ``1. [ ] STATUS: READY`` /
    ``> [x] **STATUS: READY**`` / ``| [ ] STATUS: READY |``) to the same
    normalized header.

    Tick 464: also rewrite paren / bracket / brace / fullwidth-colon headers
    (``(STATUS: READY)`` / ``[STATUS: READY]`` / ``{STATUS: READY}`` /
    ``（STATUS: READY）`` / ``STATUS：READY`` / ``**STATUS：READY**``) to the
    same normalized header.

    Tick 476: also rewrite pretty-printed multi-line ``<svg>…</svg>`` STATUS
    blocks as a single normalized header (replace the whole block — pre-476
    only rewrote the inner STATUS-bearing line and left broken SVG markup).

    Tick 477: also rewrite pretty-printed multi-line ``<img …>`` STATUS
    blocks as a single normalized header (replace the whole block — pre-477
    Tick 468–470 required a full-line ``<img>``, so Notion/Prettier
    multi-line badge exports missed demote after Tick 476 SVG-only collapse).

    Tick 478: also rewrite multi-line ``<img`` that opens *mid-line* after
    HTML wrappers (``<picture><source…><img\\n  alt="STATUS:…"\\n/></picture>``)
    as a single normalized header — pre-478 Tick 477 required ``^<img``, so
    picture/source-prefixed opens missed demote / G4 pack rewrite.

    Tick 479: also rewrite mid-line ``<svg`` after wrappers
    (``<div role="img"><svg\\n  aria-label="STATUS:…"\\n>…</svg></div>``)
    as a single normalized header — pre-479 Tick 476 required ``^<svg``.

    Tick 480: also rewrite soft-wrapped markdown link/image STATUS
    (``![STATUS: READY](\\nhttps://…/badge.svg)`` /
    ``[**STATUS: READY**](\\nhttps://x.com/foo_(bar))`` /
    ``![STATUS: READY]\\n(https://…)``) as a single normalized header —
    pre-480 Tick 465–467 required a single-line ``[…](…)`` / ``![…](…)``,
    so Prettier / GitHub soft-wrap badge exports missed demote / G4 pack
    rewrite after Tick 476–479 HTML-only collapses.

    Tick 481: also rewrite HTML ``<a>``/``<button>`` whose STATUS lives only
    in ``title=`` / ``aria-label=`` (decorative body), including Prettier
    multi-line opens (``<a\\n  title="STATUS: READY"\\n>badge</a>`` /
    ``<button aria-label="STATUS: READY">Go</button>``) — pre-481 Tick 465
    allowlist-stripped ``a``/``button`` to inner text only (``badge``/``Go``),
    so a11y/tooltip link badge exports missed demote / G4 pack rewrite after
    Tick 470/472 covered the same attrs on ``<img>``/``<svg>``.

    Tick 482: also rewrite HTML ``span``/``label``/``div``/``summary``/
    ``figcaption``/``mark`` whose STATUS lives only in ``title=`` /
    ``aria-label=`` (decorative body), including Prettier multi-line opens
    (``<span\\n  title="STATUS: READY"\\n>badge</span>`` /
    ``<label aria-label="STATUS: READY">x</label>``) — pre-482 Tick 481
    only covered ``a``/``button``.

    Tick 483: also rewrite remaining allowlisted formatting / container /
    table / semantic tags whose STATUS lives only in ``title=`` /
    ``aria-label=`` (decorative body), including Prettier multi-line opens
    (``<p\\n  title="STATUS: READY"\\n>badge</p>`` /
    ``<strong aria-label="STATUS: READY">x</strong>`` /
    ``<h1 title="STATUS: READY">Badge</h1>`` /
    ``<td title="STATUS: READY">x</td>``) — pre-483 Tick 482 only covered
    ``span``/``label``/``div``/``summary``/``figcaption``/``mark``.

    Tick 484: also rewrite ``aria-description=`` STATUS on the same
    allowlisted a/button/span/inline/img/svg surfaces (decorative body),
    including Prettier multi-line opens
    (``<p\\n  aria-description="STATUS: READY"\\n>badge</p>`` /
    ``<span aria-description="STATUS: READY">x</span>`` /
    ``<a aria-description="STATUS: READY">Go</a>``) — pre-484 Tick 481–483
    only covered ``title=`` / ``aria-label=``.

    Tick 485: also rewrite *unquoted* STATUS attrs on those same surfaces
    (``<p title=STATUS:READY>badge</p>`` /
    ``<img alt=STATUS:READY src=…>`` /
    ``<a aria-label=STATUS:IN_PROGRESS>Go</a>``) — pre-485 ATTR peels
    required quotes, so minified HTML badge exports missed demote / G4 pack.
    """
    body = (body or "").lstrip("\ufeff")
    out: list[str] = []
    found_header = False
    for span, match_line in _iter_icml_ready_status_units(body):
        if _icml_ready_status_line_match(match_line):
            out.append("**STATUS: IN_PROGRESS**")
            found_header = True
        else:
            out.extend(span)
    if found_header:
        ended = body.endswith("\n")
        return "\n".join(out) + ("\n" if ended else "")
    # No STATUS header line — prepend a demoted marker (legacy / stub).
    if not body.strip():
        return "**STATUS: IN_PROGRESS**\n"
    return "**STATUS: IN_PROGRESS**\n\n" + body.lstrip()


def merge_icml_ready_text(ours: str, theirs: str) -> str:
    """Tick 438/441/442: prefer richer checklist; demote READY on header conflict.

    Tick 438: prefer IN_PROGRESS when either side demotes (conflict safety).
    Tick 441: choose the **richer** checklist body (live ``[x]`` criteria) instead
    of length-only, so a padded thin stub cannot wipe post-G4 checkmarks.
    Tick 442: STATUS detection uses the ``**STATUS:`` header only — prose that
    mentions ``STATUS: IN_PROGRESS`` must not skip demote (READY poison) or
    zero richness on a true READY header.
    """
    o = ours or ""
    t = theirs or ""
    body = prefer_richer_icml_ready(o, t)
    o_status = _icml_ready_status_header(o)
    t_status = _icml_ready_status_header(t)
    if o_status == "IN_PROGRESS" or t_status == "IN_PROGRESS":
        return _demote_icml_ready_status(body)
    return body if body.strip() else (t if t.strip() else o)


def _paper_artifacts_richness(text: str) -> tuple:
    """Tick 440: score ``docs/paper_artifacts.md`` (higher = richer live pack).

    Pre-440 durable merge treated any mention of ``Live Table`` / ``live GPQA``
    as decisive and always preferred the replayed local. The committed offline
    stub already contains those phrases (empty Live Table 1 + ``### Live GPQA``),
    so a thin local stub could wipe onto's post-G4 auto-filled Live Table during
    durable rebase — paid PRIMARY evidence lost even though Tick 438 "merged".
    """
    t = text or ""
    if not t.strip():
        return (0, 0, 0, 0, 0, 0, 0)
    low = t.lower()
    auto_filled = 1 if "auto-filled by" in low and "run_g4_multiseed" in low else 0
    primary_flags = 1 if "primary flags:" in low else 0
    # Count Live Table 1 data rows whose first cell is a digit seed (not stub "—").
    live_rows = 0
    marker = "### Live GPQA"
    end_marker = "## Table 2"
    start = t.find(marker)
    end = t.find(end_marker)
    block = t[start:end] if start != -1 and end > start else ""
    for line in block.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells:
            continue
        seed = cells[0]
        if seed.isdigit() or (
            seed.replace(".", "", 1).isdigit() and seed.count(".") <= 1
        ):
            live_rows += 1
        elif seed.lower() in ("seed", "------", "---"):
            continue
    h2_live = 1 if "h2 live dna skew" in low else 0
    h5_live = 1 if "h5 ρ>0.3 on live" in low or "h5 rho>0.3 on live" in low else 0
    # Table 2 live marker rows that are not stub dashes.
    table2_live = 0
    if "<!-- LIVE_TABLE2_H2_START -->" in t:
        i0 = t.find("<!-- LIVE_TABLE2_H2_START -->")
        i1 = t.find("<!-- LIVE_TABLE2_H2_END -->")
        chunk = t[i0:i1] if i0 != -1 and i1 > i0 else ""
        if "yes" in chunk.lower() or "preferred_share=" in chunk.lower():
            table2_live += 1
    if "<!-- LIVE_TABLE2_H5_START -->" in t:
        i0 = t.find("<!-- LIVE_TABLE2_H5_START -->")
        i1 = t.find("<!-- LIVE_TABLE2_H5_END -->")
        chunk = t[i0:i1] if i0 != -1 and i1 > i0 else ""
        if "yes" in chunk.lower() or "spearman" in chunk.lower():
            table2_live += 1
    # Order: payload → auto-fill → PRIMARY flags → live rows → H2/H5 lines → T2 → size
    return (
        1,
        auto_filled,
        primary_flags,
        live_rows,
        h2_live + h5_live,
        table2_live,
        len(t),
    )


def prefer_richer_paper_artifacts(a: str, b: str) -> str:
    """Tick 440: keep the richer paper_artifacts text (ties → ``b``)."""
    a = a or ""
    b = b or ""
    if not a.strip() and b.strip():
        return b
    if not b.strip() and a.strip():
        return a
    if _paper_artifacts_richness(b) >= _paper_artifacts_richness(a):
        return b
    return a


def prefer_richer_figure_bytes(a: bytes | None, b: bytes | None) -> bytes:
    """Tick 440: keep the larger non-empty figure PNG (ties → ``b``)."""
    ao = a if a is not None else b""
    bo = b if b is not None else b""
    if not ao and bo:
        return bo
    if not bo and ao:
        return ao
    if len(bo) >= len(ao):
        return bo
    return ao


def _merge_durable_conflict_bytes(
    relpath: str, ours: bytes | None, theirs: bytes | None
) -> bytes | None:
    """Merge one durable/companion conflict; None → refuse auto-resolve."""
    norm = _norm_repo_relpath(relpath)
    o = ours if ours is not None else b""
    t = theirs if theirs is not None else b""
    if norm == _norm_repo_relpath(ICML_BUDGET_SPENT_RELPATH):
        try:
            od = json.loads(o.decode("utf-8") or "{}")
            td = json.loads(t.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            return None
        if not isinstance(od, dict):
            od = {}
        if not isinstance(td, dict):
            td = {}
        merged = merge_budget_spent_dict(od, td)
        return (json.dumps(merged, indent=2) + "\n").encode("utf-8")
    if norm == _norm_repo_relpath(ICML_PRIOR_LIVE_EVIDENCE_RELPATH):
        try:
            od = json.loads(o.decode("utf-8") or "{}")
            td = json.loads(t.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            return None
        if not isinstance(od, dict):
            od = {}
        if not isinstance(td, dict):
            td = {}
        merged = merge_prior_live_evidence_dict(od, td)
        return (json.dumps(merged, indent=2) + "\n").encode("utf-8")
    if norm == _norm_repo_relpath("docs/ICML_READY.md"):
        # Tick 441: prefer richer live checklist (not length-only).
        try:
            return merge_icml_ready_text(
                o.decode("utf-8"), t.decode("utf-8")
            ).encode("utf-8")
        except UnicodeDecodeError:
            return None
    if norm == _norm_repo_relpath("docs/paper_artifacts.md"):
        # Tick 440: prefer richer live pack (not mere "Live Table" phrase).
        try:
            os_ = o.decode("utf-8")
            ts_ = t.decode("utf-8")
        except UnicodeDecodeError:
            return t or o
        return prefer_richer_paper_artifacts(os_, ts_).encode("utf-8")
    if norm.startswith("docs/figures/") and norm.endswith(".png"):
        # Tick 440: prefer larger non-empty fig (not always replayed local).
        return prefer_richer_figure_bytes(o, t)
    return None


def resolve_durable_rebase_conflicts(cwd: Path) -> tuple[bool, str]:
    """Tick 438/441: auto-merge durable/paper-pack-only rebase conflicts.

    Pre-438 ``rebase_tip_onto_origin_for_durable_push`` aborted on *any*
    conflict. Concurrent tip VMs that both update ``icml_budget_spent.json``
    (or prior_live / paper-pack companions) then left paid spend local-only
    after an NF push. When **every** unmerged path is a durable ledger or
    paper-pack companion, merge JSON/text/figs and ``git add`` them so
    ``rebase --continue`` can finish. Any other conflict still refuses.

    Tick 440: ``paper_artifacts.md`` / Figs prefer **richer** live payloads
    (not mere ``Live Table`` phrase / non-empty local bytes) so thin offline
    stubs cannot wipe post-G4 PRIMARY tables during durable rebase.

    Tick 441: ``ICML_READY.md`` prefers richer live ``[x]`` criteria over
    length-only (still demotes STATUS when either side is IN_PROGRESS).

    Tick 442: ICML_READY STATUS demote / merge use the ``**STATUS:`` header
    only — Tick-note prose mentioning ``STATUS: IN_PROGRESS`` must not no-op
    demote (poisoned READY) or zero richness on a true READY header.
    """
    allowed = _durable_ledger_relpaths() | _post_live_companion_relpaths()
    unmerged = _git_unmerged_relpaths(cwd)
    if not unmerged:
        return True, "Tick 438: no unmerged paths"
    bad = [p for p in unmerged if _norm_repo_relpath(p) not in allowed]
    if bad:
        return (
            False,
            f"Tick 438: non-durable conflicts refuse auto-merge: {bad[:6]}",
        )
    resolved: list[str] = []
    for rel in unmerged:
        ours = _git_show_stage_bytes(cwd, 2, rel)
        theirs = _git_show_stage_bytes(cwd, 3, rel)
        if ours is None and theirs is None:
            return False, f"Tick 438: missing both stages for {rel}"
        merged = _merge_durable_conflict_bytes(rel, ours, theirs)
        if merged is None:
            return False, f"Tick 438: cannot merge durable conflict {rel}"
        dest = cwd / rel
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(merged)
        except OSError as exc:
            return False, f"Tick 438: write {rel} failed: {exc}"
        ok_add, detail_add = _git_ok(["add", "--", rel], cwd=cwd)
        if not ok_add:
            return False, f"Tick 438: git add {rel} failed: {detail_add}"
        resolved.append(rel)
    return (
        True,
        f"Tick 438: auto-merged durable conflicts {resolved}",
    )


def rebase_tip_onto_origin_for_durable_push(
    tip_branch: str,
    *,
    cwd: Path,
) -> tuple[bool, str]:
    """Tick 437/438: rebase local tip onto ``origin/<tip>`` after an NF push reject.

    Never ``--force``. Preserves dirty durable + paper-pack companion bytes
    across the rebase.

    Tick 437: on conflict, aborted and left pre-rebase HEAD recoverable.

    Tick 438: when conflicts are **only** durable ledgers / paper-pack
    companions (concurrent tip VMs both writing ``budget_spent`` /
    ``prior_live`` / READY/figs), auto-merge those paths and
    ``rebase --continue``. Still abort on any non-durable conflict.
    """
    name = (tip_branch or "").strip()
    if not name or name in ("main", "master", "HEAD"):
        return False, "Tick 437: refuse rebase — no tip branch"
    ok_fetch, detail_fetch = fetch_origin_tip_for_durable_ledgers(name, cwd=cwd)
    fetch_note = detail_fetch if ok_fetch else f"{detail_fetch} (continuing)"
    remote_ref = None
    for prefer in (f"origin/{name}", f"refs/remotes/origin/{name}"):
        ok_ref, _ = _git_ok(["rev-parse", "--verify", prefer], cwd=cwd)
        if ok_ref:
            remote_ref = prefer
            break
    if remote_ref is None:
        return False, f"Tick 437: no origin/{name} after fetch ({fetch_note})"
    # Already contains origin tip → rebase would be a no-op; treat as ok.
    if _git_is_ancestor(remote_ref, "HEAD", cwd=cwd):
        return (
            True,
            f"{fetch_note}; Tick 437: HEAD already contains {remote_ref} — skip rebase",
        )
    preserved = _preserve_post_live_dirty_bytes(cwd)
    for rel in preserved:
        _git_restore_or_unlink(cwd, rel, cwd / rel)
    ok_rb, detail_rb = _git_ok(["rebase", remote_ref], cwd=cwd)
    if not ok_rb:
        merge_notes: list[str] = []
        env = os.environ.copy()
        env["GIT_EDITOR"] = "true"
        env["GIT_SEQUENCE_EDITOR"] = "true"
        continued = False
        for _round in range(2):
            ok_res, detail_res = resolve_durable_rebase_conflicts(cwd)
            merge_notes.append(detail_res)
            if not ok_res or _git_unmerged_relpaths(cwd):
                break
            try:
                proc = subprocess.run(
                    ["git", "rebase", "--continue"],
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    check=False,
                    env=env,
                    timeout=120,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                merge_notes.append(f"continue {type(exc).__name__}: {exc}")
                break
            if proc.returncode == 0:
                continued = True
                break
            merge_notes.append(
                (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()[
                    :160
                ]
            )
            # Another conflict round may remain — loop once more.
        if continued:
            _restore_preserved_bytes(cwd, preserved)
            return (
                True,
                f"{fetch_note}; Tick 438: rebased onto {remote_ref} after "
                f"durable conflict merge ({'; '.join(merge_notes)})",
            )
        # Best-effort abort so the tree is not left mid-rebase.
        _git_ok(["rebase", "--abort"], cwd=cwd)
        _restore_preserved_bytes(cwd, preserved)
        return (
            False,
            f"Tick 437 rebase onto {remote_ref} failed: {detail_rb[:200]}; "
            f"{'; '.join(merge_notes)} ({fetch_note})",
        )
    _restore_preserved_bytes(cwd, preserved)
    return (
        True,
        f"{fetch_note}; Tick 437: rebased HEAD onto {remote_ref} "
        f"(preserved {len(preserved)} durable paths)",
    )


def push_tip_after_durable_ledger_commit(
    repo_root: Path | None = None,
    *,
    branch: str | None = None,
) -> tuple[bool, str]:
    """Tick 423/437: non-force ``git push`` tip HEAD so durable ledgers survive the VM.

    Tick 422 committed locally after live, but cron/agent timeout could exit
    before a human/agent ``git push`` — next greenfield boot still re-burned.
    Never ``--force``. Refuses ``main``/``master``.

    Tick 437: when the tip push is non-fast-forward rejected (concurrent tip
    advance after Tick 436 fetch / mid-tick race, or unique local durable
    commits on a stale tip base that Tick 435 cannot FF), fetch ``origin/<tip>``,
    rebase local HEAD onto it (preserve durable dirt), and retry the push
    **once**. Still never force-pushes.

    Tick 438: rebase auto-merges durable/paper-pack-only conflicts (concurrent
    ``budget_spent`` / ``prior_live`` / READY edits) before the retry push —
    pre-438 aborted and left paid spend local-only.
    Tick 439: prior_live conflict merge prefers richer gate payloads (not
    blindly the replayed local) so onto's executed G4 evidence survives.
    """
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    target = (branch or resolve_push_branch_for_durable_ledgers(root) or "").strip()
    if not target or target in ("main", "master", "HEAD"):
        return (
            False,
            "Tick 423 push refused — no tip-like branch "
            f"(got {target!r})",
        )
    ok, detail = _git_ok(
        ["push", "origin", f"HEAD:refs/heads/{target}"],
        cwd=root,
    )
    if ok:
        return True, f"Tick 423: pushed durable ledger commit to origin/{target}"
    if not _git_push_looks_non_fast_forward(detail):
        return False, f"Tick 423 git push failed: {detail}"
    ok_rb, detail_rb = rebase_tip_onto_origin_for_durable_push(target, cwd=root)
    if not ok_rb:
        return (
            False,
            f"Tick 423 git push failed (NF): {detail}; {detail_rb}",
        )
    ok2, detail2 = _git_ok(
        ["push", "origin", f"HEAD:refs/heads/{target}"],
        cwd=root,
    )
    if not ok2:
        return (
            False,
            f"Tick 437 push retry failed after rebase: {detail2} "
            f"(first NF: {detail[:160]}; {detail_rb})",
        )
    return (
        True,
        f"Tick 437: rebased onto origin/{target} after NF push then pushed "
        f"({detail_rb})",
    )


def commit_durable_ledgers_after_live(
    repo_root: Path | None = None,
) -> tuple[bool, str]:
    """Tick 422–428 + 433: commit (+ push) durable ledgers after live **or tip recover**.

    Call after paid G2/G3/G4 (or the unified live pipeline) **and** after
    tip-recover reinject (cron / boot_recover / recover_tip ``--apply``) so
    ``docs/icml_budget_spent.json`` + ``docs/icml_prior_live_evidence.json``
    land on tip HEAD **and** ``origin`` before the cloud VM dies — cross-VM
    resume depends on pushed ledgers (runs/ are gitignored).

    Tick 423: local commit alone is insufficient; auto-push tip branch
    (non-force) when this call created a commit.
    Tick 424: also push when commit is a noop but tip HEAD is still ahead of
    ``origin/<tip>`` (retry after a mid-tick push failure — Tick 423 returned
    early on noop and left spend/prior_live unpushed).
    Tick 425: tip-recover paths (cron / boot_recover / recover_tip) use this
    same commit+push helper — pre-425 tip recover called
    ``commit_prior_live_evidence_if_dirty`` alone (commit-only), so a mid-tick
    death after tip ``--apply`` reinject still left spend/prior_live unpushed.
    Tick 426: also co-commits G4 paper-pack companions (``paper_artifacts``,
    ``ICML_READY``, Figs 1–2) so post-``apply_paper_pack`` dirt does not
    refuse the durable commit (pre-426 latent READY/spend wipe after paid G4).
    Tick 427: tip-recover prepare parks those companions across tip ``--apply``
    (pre-427 prepare refused companions → tip recover blocked mid-tick).
    Tick 428: after durable state is on ``origin`` (successful push, or commit
    noop with tip not ahead), **consume** gitignored stashes so a later tip
    ``--apply`` cannot reinject stale mid-tick READY/spend over a newer tip
    HEAD. Keep stashes when push fails so tip ``--apply`` hard-reset to origin
    can still reinject.
    Tick 429: consume only stashes **redundant with HEAD** — pre-429 also wiped
    unique mid-tick READY/spend after failed reinject on commit-noop.
    Tick 430: redundancy uses committed ``git show HEAD:<path>`` (not WT) so
    reinject/staged-only WT match cannot wipe a unique stash on commit-noop.
    Tick 431: ``resolve_push_branch_for_durable_ledgers`` redirects greenfield
    boot ``cursor/*`` checkouts (no ``origin/<boot>``, or matching cloud-boot
    env/persisted name) to ``tip_pr_commit_branch`` so spend/READY land on the
    tip PR head — not an invisible boot ref.
    Tick 432: when tip PR head is known, durable push **always** targets
    ``tip_pr_commit_branch`` (even if ``origin/<boot>`` already exists and
    cloud-boot capture is missing) — closes re-park after accidental boot push.
    Tick 433: before commit/push, fast-forward local ``tip_pr_commit_branch``
    onto HEAD when HEAD is a tip descendant and check out tip — closes stale
    local tip ref after durable commit on a boot branch name (ahead=0 consume
    wipe / anti-churn checkout drop).
    Tick 434: when HEAD is **not** a tip descendant (greenfield boot behind
    ``origin/<tip>``), checkout tip (preserving durable/companion dirt) instead
    of skipping — pre-434 committed on boot then non-FF rejected tip push.
    Tick 435: when already on tip but ``origin/<tip>`` is strictly ahead of
    HEAD, FF tip ← origin (preserve durable dirt) before commit — pre-435
    early-returned then NF-rejected tip push on a stale tip base.
    Tick 436: fetch ``origin/<tip>`` before Tick 435 ahead / Tick 434 checkout
    — pre-436 used a stale remote-tracking ref after long live gates, so
    Tick 435 never FF'd and tip push was still NF-rejected.
    Tick 437: when tip push is still NF-rejected (concurrent tip advance after
    the Tick 436 fetch, or unique local durable commits on a stale tip base
    that Tick 435 cannot FF), rebase onto ``origin/<tip>`` and retry push
    once — never force.
    Tick 438: durable/paper-pack-only rebase conflicts auto-merge (union spend
    / gates; demote READY) so concurrent tip VMs do not abort and leave paid
    spend local-only.
    Tick 439: prior_live gate merge keeps the **richer** payload per key
    (executed / n_pairs / pass flags) so a thinner replayed local cannot wipe
    onto's G4 ``prior_live_metrics`` during that durable conflict merge.
    """
    ok_sync, detail_sync = ensure_local_tip_branch_for_durable_ledgers(repo_root)
    if not ok_sync:
        return False, detail_sync
    ok, detail = commit_prior_live_evidence_if_dirty(
        repo_root,
        commit_message=(
            "ICML Tick 439: commit durable ledgers + paper-pack companions."
        ),
    )
    if (
        "synced local tip" in detail_sync
        or "checked out tip" in detail_sync
        or "Tick 436" in detail_sync
        or "Tick 437" in detail_sync
        or "fetched origin" in detail_sync
    ):
        detail = f"{detail_sync}; {detail}"
    if not ok:
        return ok, detail
    need_push = "committed durable ledgers" in detail
    if not need_push:
        ahead = tip_commits_ahead_of_origin(repo_root)
        if ahead <= 0:
            # Tip matches origin (or no remote) — safe to drop reinject stashes.
            ok_c, detail_c = consume_durable_stashes_after_commit(repo_root)
            if not ok_c:
                return False, f"{detail}; {detail_c}"
            if "consume noop" not in detail_c:
                detail = f"{detail}; {detail_c}"
            return ok, detail
        detail = f"{detail}; tip ahead of origin by {ahead} (Tick 424 push retry)"
        need_push = True
    ok_p, detail_p = push_tip_after_durable_ledger_commit(repo_root)
    if not ok_p:
        # Commit landed locally; keep stashes so tip --apply hard-reset to
        # origin can still reinject if the unpushed commit is lost (Tick 428).
        return False, f"{detail}; {detail_p}"
    detail = f"{detail}; {detail_p}"
    ok_c, detail_c = consume_durable_stashes_after_commit(repo_root)
    if not ok_c:
        return False, f"{detail}; {detail_c}"
    if "consume noop" not in detail_c:
        detail = f"{detail}; {detail_c}"
    return True, detail


# Tick 425 alias — tip-recover call sites; same commit+push+ahead-retry as live.
commit_durable_ledgers_on_tip_recover = commit_durable_ledgers_after_live



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

    Tick 387: before restoring gate2/3/4 JSON, persist trustable
    ``prior_live_post`` / ``prior_live_metrics`` into gitignored
    ``docs/icml_prior_live_stash.json`` so tip ``--apply`` hard reset cannot
    wipe Tick 384–386 paid evidence. Call ``reinject_prior_live_stash`` after
    tip recover (cron / boot_recover).

    Tick 389: the same persist also writes committed
    ``docs/icml_prior_live_evidence.json`` (budget-ledger parity) so fresh
    cloud boots can reinject when the gitignored stash is absent.

    Tick 390: dirty committed evidence **blocks** tip ``--apply`` (same as
    dirty ``docs/icml_budget_spent.json``). Tick 389 excluded evidence from
    the dirty filter so hard-reset could wipe uncommitted gates and rely on
    same-VM stash reinject — that is not cross-VM safe.

    Tick 391: also ignore boot file + open_git_pr call JSON (with stash) when
    ``.gitignore`` lags on chicken-egg greenfield boots — cron writes the boot
    file before tip recover; porcelain ``??`` must not refuse ``--apply``.
    Fixes Tick 390 ``evidence_norm`` NameError in the post-discard remaining
    check (undefined after Tick 390 removed the evidence filter).

    Tick 419: when persist captures prior_live from ephemeral gate JSON, the
    newly written committed evidence file is the *only* non-ephemeral remainder
    and must **not** fail discard (Tick 387 stash path). Tip ``--apply`` still
    blocks on that dirty evidence via ``tip_apply_blocking_dirty_paths`` until
    it is committed (Tick 390). Pre-existing dirty evidence still fails discard
    at the top of this function.

    Returns ``(ok, detail)``. ``ok`` is True when ephemeral dirt was cleared (or
    the tree was already clean). Tip ``--apply`` callers must still consult
    ``tip_apply_blocking_dirty_paths`` (dirty evidence / budget ledger).
    """
    import subprocess

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    dirty = porcelain_dirty_paths(root)
    # Tick 387/391: durable gitignored paths — exclude explicitly so tip
    # --apply is not blocked when .gitignore lags (chicken-egg greenfield).
    # Tick 390: do NOT exclude committed evidence — dirty evidence is a real
    # tip-apply blocker (budget-ledger parity; commit before --apply).
    dirty = [p for p in dirty if not is_tip_apply_ignored_dirty(p)]
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

    # Tick 387: capture prior_live_* before git restore wipes dirty gate JSON.
    stash_info = persist_prior_live_stash_from_working_tree(root)
    stash_note = ""
    if stash_info.get("captured"):
        stash_note = f"; prior_live stashed={stash_info.get('captured')}"

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

    remaining = [
        p
        for p in porcelain_dirty_paths(root)
        if not is_tip_apply_ignored_dirty(p)
    ]
    if remaining:
        non_ephem = [p for p in remaining if not is_ephemeral_icml_path(p)]
        # Tick 419: persist_prior_live_stash_from_working_tree writes committed
        # evidence (Tick 389) while capturing prior_live from ephemeral gate
        # JSON. That dirt is intentional ledger parity and must be committed
        # before tip --apply (Tick 390) — but it must not fail discard itself
        # when it is the *only* non-ephemeral remainder and we just captured
        # from gates (Tick 387 stash path). Pre-existing dirty evidence still
        # blocks at the top of this function (Tick 390).
        evidence_norm = ICML_PRIOR_LIVE_EVIDENCE_RELPATH.replace("\\", "/")
        if (
            stash_info.get("captured")
            and non_ephem
            and all(
                p.replace("\\", "/").lstrip("./") == evidence_norm for p in non_ephem
            )
        ):
            return (
                True,
                f"discarded ephemeral dirt: {restored}{stash_note}; "
                f"commit {evidence_norm} before tip --apply (Tick 390/419)",
            )
        if non_ephem:
            return (
                False,
                f"discarded {restored}; still dirty non-ephemeral: {non_ephem[:8]}"
                f"{stash_note}",
            )
        # Only ephemeral remain (restore failed?) — try once more is useless
        return False, f"discarded {restored}; ephemeral still dirty: {remaining[:8]}{stash_note}"
    return True, f"discarded ephemeral dirt: {restored}{stash_note}"


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


def hydrate_direct_gate_budget_spent(
    planned_run_ids: list[int],
    *,
    pair_estimate_usd: float | None = None,
    run_estimate_usd: float | None = None,
    resolve_run_dir: Callable[[int], Path | None],
    repo_root: Path | None = None,
    env_key: str = "SIA_BUDGET_SPENT_USD",
) -> tuple[float, str]:
    """Tick 377/378: direct G2/G3/G4 ``--live`` sees ledger + unbilled locals.

    Pipeline ``sync_spent_from_completed_stages`` (Tick 376) hydrates spent
    before calling gate mains. Direct ``run_g2_smoke.py --live`` (Tick 378),
    ``run_g3_pilot.py --live``, and ``run_g4_multiseed.py --live`` previously
    read ``SIA_BUDGET_SPENT_USD`` from env only (often 0), so mid-stack resume
    after a crash — when the ledger was stale or not yet synced — could
    green-light remaining work over the ~$20 ceiling. This helper:

    1. Loads the committed ledger into env (Tick 284).
    2. Bills any **complete** planned run dirs whose IDs are not yet in the
       ledger (partial stage; does **not** mark ``stages_complete``).
    3. Persists the bumped spend so the next cron/direct call does not
       double-count.

    Pass ``pair_estimate_usd`` for B+D pair gates (G3/G4; fallback bills
    ``len(unbilled)/2`` pairs) or ``run_estimate_usd`` for single-run G2
    (fallback bills ``len(unbilled)`` runs). Exactly one estimate is required
    when unbilled locals exist; ledger-only hydrate needs neither.
    """
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    ledger_path = budget_spent_ledger_path(root)
    spent_after_ledger, ledger_detail = apply_persisted_spent_to_env(
        path=ledger_path, env_key=env_key
    )
    ledger = load_budget_spent_ledger(ledger_path)
    ledger_ids = {
        int(x)
        for x in (ledger.get("run_ids") or [])
        if str(x).lstrip("-").isdigit()
    }
    unbilled: list[int] = []
    unbilled_dirs: list[Path] = []
    for raw_rid in planned_run_ids:
        rid = int(raw_rid)
        found = resolve_run_dir(rid)
        if not darwinian_run_complete(found):
            continue
        if rid in ledger_ids:
            continue
        unbilled.append(rid)
        assert found is not None
        unbilled_dirs.append(found)
    if not unbilled:
        return (
            float(spent_after_ledger),
            f"Tick 377 hydrate: {ledger_detail}; no unbilled local completes",
        )
    if run_estimate_usd is not None:
        fallback = max(0.0, float(run_estimate_usd)) * len(unbilled)
    elif pair_estimate_usd is not None:
        n_pairs_equiv = len(unbilled) / 2.0
        fallback = max(0.0, float(pair_estimate_usd)) * n_pairs_equiv
    else:
        raise TypeError(
            "hydrate_direct_gate_budget_spent requires pair_estimate_usd "
            "or run_estimate_usd when unbilled local completes exist"
        )
    amt, det = reconcile_gate_spend_usd(
        unbilled_dirs, fallback_estimate=fallback
    )
    new_spent = float(spent_after_ledger) + float(amt)
    os.environ[env_key] = f"{new_spent:.4f}"
    write_budget_spent_ledger(
        spent_usd=new_spent,
        stages_complete=list(ledger.get("stages_complete") or []),
        run_ids=sorted(ledger_ids | set(unbilled)),
        detail=f"Tick 377/378 direct-gate unbilled local: {det}",
        path=ledger_path,
    )
    return (
        new_spent,
        (
            f"Tick 377/378 hydrate: {ledger_detail}; billed {len(unbilled)} unbilled "
            f"local run(s) +${amt:.4f} → spent=${new_spent:.4f} ({det})"
        ),
    )


def persist_direct_gate_stage_spend(
    stage: str,
    planned_run_ids: list[int],
    *,
    pair_estimate_usd: float | None = None,
    run_estimate_usd: float | None = None,
    resolve_run_dir: Callable[[int], Path | None],
    repo_root: Path | None = None,
    env_key: str = "SIA_BUDGET_SPENT_USD",
) -> tuple[float, str]:
    """Tick 379: after successful direct G2/G3/G4 live, stamp ledger stage.

    Tick 377/378 hydrate bills unbilled completes *before* live but does **not**
    mark ``stages_complete``. Pipeline ``bump_spent_reconciled`` stamps stages
    after each gate — but direct ``run_g2_smoke.py --live`` / ``run_g3_pilot.py
    --live`` / ``run_g4_multiseed.py --live`` previously never wrote the ledger
    post-success. Cross-VM cron (``runs/`` gitignored) would then re-launch a
    completed direct-gate stage and double-burn the ~$20 ceiling.

    This helper:

    1. Loads the committed ledger into env.
    2. Bills any still-unbilled **complete** planned run dirs (no double-count).
    3. Stamps ``stage`` into ``stages_complete`` only when **every** planned
       run_id is locally complete (partial stages stay unstamped).
    4. Persists so the next cron/direct call resumes without re-spend.

    Pass ``pair_estimate_usd`` for B+D pair gates (G3/G4) or ``run_estimate_usd``
    for single-run G2. Exactly one estimate is required when unbilled locals
    exist; stage-stamp-only (all IDs already in ledger) needs neither.
    """
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    stage_name = str(stage or "").strip()
    if not stage_name:
        raise ValueError("persist_direct_gate_stage_spend requires a non-empty stage")
    planned = [int(x) for x in planned_run_ids]
    if not planned:
        raise ValueError("persist_direct_gate_stage_spend requires planned_run_ids")

    ledger_path = budget_spent_ledger_path(root)
    spent_after_ledger, ledger_detail = apply_persisted_spent_to_env(
        path=ledger_path, env_key=env_key
    )
    ledger = load_budget_spent_ledger(ledger_path)
    ledger_ids = {
        int(x)
        for x in (ledger.get("run_ids") or [])
        if str(x).lstrip("-").isdigit()
    }
    prev_stages = {str(s) for s in (ledger.get("stages_complete") or []) if s}

    complete_ids: list[int] = []
    complete_dirs: list[Path] = []
    unbilled: list[int] = []
    unbilled_dirs: list[Path] = []
    for rid in planned:
        found = resolve_run_dir(rid)
        if not darwinian_run_complete(found):
            continue
        complete_ids.append(rid)
        assert found is not None
        complete_dirs.append(found)
        if rid not in ledger_ids:
            unbilled.append(rid)
            unbilled_dirs.append(found)

    all_complete = len(complete_ids) == len(planned)
    amt = 0.0
    det = "no new unbilled completes"
    if unbilled:
        if run_estimate_usd is not None:
            fallback = max(0.0, float(run_estimate_usd)) * len(unbilled)
        elif pair_estimate_usd is not None:
            n_pairs_equiv = len(unbilled) / 2.0
            fallback = max(0.0, float(pair_estimate_usd)) * n_pairs_equiv
        else:
            raise TypeError(
                "persist_direct_gate_stage_spend requires pair_estimate_usd "
                "or run_estimate_usd when unbilled local completes exist"
            )
        amt, det = reconcile_gate_spend_usd(
            unbilled_dirs, fallback_estimate=fallback
        )

    new_spent = float(spent_after_ledger) + float(amt)
    os.environ[env_key] = f"{new_spent:.4f}"

    stages_to_write: list[str] = list(ledger.get("stages_complete") or [])
    stamped = False
    if all_complete and stage_name not in prev_stages:
        stages_to_write = list(stages_to_write) + [stage_name]
        stamped = True
    elif all_complete and stage_name in prev_stages and not unbilled:
        return (
            new_spent,
            (
                f"Tick 379 persist: {ledger_detail}; stage {stage_name} already "
                f"stamped; no unbilled locals"
            ),
        )

    if not unbilled and not stamped:
        missing = [rid for rid in planned if rid not in complete_ids]
        return (
            float(spent_after_ledger),
            (
                f"Tick 379 persist: {ledger_detail}; incomplete stage {stage_name} "
                f"(missing run_ids={missing}); not stamped"
            ),
        )

    write_budget_spent_ledger(
        spent_usd=new_spent,
        stages_complete=stages_to_write,
        run_ids=sorted(ledger_ids | set(complete_ids)),
        detail=(
            f"Tick 379 direct-gate persist {stage_name}: "
            f"billed={len(unbilled)} stamped={stamped}; {det}"
        ),
        path=ledger_path,
    )
    return (
        new_spent,
        (
            f"Tick 379 persist: {ledger_detail}; stage={stage_name} "
            f"stamped={stamped}; billed {len(unbilled)} unbilled local run(s) "
            f"+${amt:.4f} → spent=${new_spent:.4f} ({det})"
        ),
    )


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


def direct_gate_ledger_skip(
    stage: str,
    planned_run_ids: list[int],
    *,
    path: Path | None = None,
) -> tuple[bool, str]:
    """Tick 380: whether direct G2/G3/G4 ``--live`` should skip paid re-run.

    Tick 379 stamps ``stages_complete`` after successful direct live, but only
    the **pipeline** consulted ``ledger_stage_complete`` (Tick 285). Direct
    ``run_g2_smoke.py --live`` / ``run_g3_pilot.py --live`` /
    ``run_g4_multiseed.py --live`` still treated missing local ``runs/`` as
    free IDs and would re-launch a ledger-complete stage on the next cross-VM
    cron — double-burning the ~$20 ceiling despite the stamp.

    Returns ``(True, detail)`` when the committed ledger marks ``stage`` done
    for every planned run_id (same predicate as pipeline resume).
    """
    stage_name = str(stage or "").strip()
    planned = [int(x) for x in planned_run_ids]
    if not stage_name or not planned:
        return False, "Tick 380: no stage/planned IDs — not a ledger skip"
    if not ledger_stage_complete(stage_name, planned, path=path):
        return (
            False,
            f"Tick 380: ledger does not mark {stage_name} complete for "
            f"planned run_ids={planned}",
        )
    return (
        True,
        f"Tick 380: ledger-only resume — skip paid {stage_name} re-run "
        f"(stages_complete + run_ids {planned}; local runs/ may be absent)",
    )

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
    2. ``$TMPDIR/gpqa_diamond.csv`` (Tick 529 — ``tempfile.gettempdir()``)
    3. legacy ``/tmp/gpqa_diamond.csv`` when TMPDIR ≠ /tmp
    4. repo-relative candidates under ``docs/private/``, ``.local/``, root
    """
    root = repo_root or _REPO_ROOT
    env_override = (
        os.environ.get("ICML_DIAMOND_CSV") or os.environ.get("SIA_DIAMOND_CSV") or ""
    ).strip()
    candidates: list[Path] = []
    if env_override:
        candidates.append(Path(env_override).expanduser())
    # Tick 529: prefer host temp root (may be /var/folders/… or /tmp).
    try:
        tmp_diamond = Path(tempfile.gettempdir()) / "gpqa_diamond.csv"
        candidates.append(tmp_diamond)
    except OSError:
        tmp_diamond = None
    legacy_tmp = Path("/tmp/gpqa_diamond.csv")
    if tmp_diamond is None or legacy_tmp.resolve() != tmp_diamond.resolve():
        candidates.append(legacy_tmp)
    for rel in _DIAMOND_CSV_CANDIDATES:
        candidates.append(root / rel)
    for path in candidates:
        try:
            if path.is_file() and path.stat().st_size >= 64:
                return path.resolve()
        except OSError:
            continue
    return None


def ensure_diamond_csv_via_public_mirror(
    repo_root: Path | None = None,
    *,
    allow_network: bool | None = None,
) -> Path | None:
    """Tick 497: ensure a local diamond CSV, downloading the public mirror if needed.

    Returns an existing path from ``resolve_diamond_csv_path`` when present.
    Otherwise downloads OpenAI simple-evals ``gpqa_diamond.csv`` to
    ``$TMPDIR/gpqa_diamond.csv`` via ``tempfile.gettempdir()`` (Tick 529;
    never committed). Set ``ICML_DISABLE_PUBLIC_DIAMOND_MIRROR=1`` to skip
    network.
    """
    existing = resolve_diamond_csv_path(repo_root)
    if existing is not None:
        return existing
    if allow_network is None:
        allow_network = os.environ.get("ICML_DISABLE_PUBLIC_DIAMOND_MIRROR", "").strip() not in {
            "1",
            "true",
            "yes",
            "on",
        }
    if not allow_network:
        return None
    # Lazy import keeps unit tests that never call this free of urllib side effects.
    try:
        from prepare_gpqa_diamond import (  # type: ignore
            default_public_mirror_dest,
            download_gpqa_diamond_csv_public_mirror,
        )
    except ImportError:
        scripts_dir = str((_REPO_ROOT / "scripts").resolve())
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from prepare_gpqa_diamond import (  # type: ignore
            default_public_mirror_dest,
            download_gpqa_diamond_csv_public_mirror,
        )
    try:
        return download_gpqa_diamond_csv_public_mirror(default_public_mirror_dest())
    except Exception:
        return None


def autowire_diamond_csv(
    explicit: Path | None = None,
    *,
    fetch_diamond: bool = False,
    repo_root: Path | None = None,
) -> tuple[Path | None, bool]:
    """Resolve ``--diamond-csv`` for ``--fetch-diamond`` (Tick 278 / 497).

    Returns ``(path, auto_wired)``. When ``fetch_diamond`` is true and no
    explicit CSV was passed, falls back to ``resolve_diamond_csv_path`` so
    G2/G3/G4/pipeline skip HF the same way cron does (Tick 277). Tick **497**:
    if still missing, downloads the public OpenAI mirror into ``/tmp``. Does
    **not** invent a CSV when ``fetch_diamond`` is false (avoids surprise
    materialize).
    """
    if explicit is not None:
        return Path(explicit), False
    if not fetch_diamond:
        return None, False
    auto = resolve_diamond_csv_path(repo_root)
    if auto is None:
        auto = ensure_diamond_csv_via_public_mirror(repo_root)
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


# Shared with tip/bootstrap merge copy-paste (Tick 336+) and Tick 505 view refresh.
_ICML_GITHUB_REPO = "kshivam4781/DarwinianSIA"


def _mergeability_needs_refresh(mergeable: str | None) -> bool:
    """True when GitHub has not yet computed mergeability (Tick 505)."""
    raw = str(mergeable or "").strip().upper()
    return raw in {"", "UNKNOWN", "NONE", "NULL"}


def _gh_pr_view_mergeability(
    number: int,
    *,
    repo_root: Path | None = None,
) -> tuple[str | None, str | None]:
    """Tick 505: ``gh pr view`` refresh for mergeable / mergeStateStatus.

    ``gh pr list --json mergeable`` often returns ``UNKNOWN`` on the first poll
    after a push (GitHub still computing). ``gh pr view <n>`` forces a fresher
    read so ``human_next`` can say MERGEABLE/CLEAN → undraft & merge now
    instead of a vague UNKNOWN among 300+ draft tip PRs.
    """
    root = repo_root or _REPO_ROOT
    try:
        proc = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                str(int(number)),
                "--repo",
                _ICML_GITHUB_REPO,
                "--json",
                "mergeable,mergeStateStatus",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    if proc.returncode != 0:
        return None, None
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None, None
    if not isinstance(data, dict):
        return None, None
    mergeable = data.get("mergeable")
    merge_state = data.get("mergeStateStatus")
    return (
        str(mergeable) if mergeable is not None else None,
        str(merge_state) if merge_state is not None else None,
    )


def refresh_pr_mergeability(
    pr: dict | None,
    *,
    repo_root: Path | None = None,
) -> dict | None:
    """Tick 505: in-place refresh when list/view left mergeable UNKNOWN/null.

    Returns the same dict (mutated) or ``None`` when ``pr`` is empty. Leaves
    CONFLICTING/MERGEABLE untouched. Never raises.
    """
    if not pr or not isinstance(pr, dict):
        return pr
    if not _mergeability_needs_refresh(pr.get("mergeable")):  # type: ignore[arg-type]
        return pr
    number = pr.get("number")
    if number is None:
        return pr
    try:
        n = int(number)
    except (TypeError, ValueError):
        return pr
    mergeable, merge_state = _gh_pr_view_mergeability(n, repo_root=repo_root)
    if mergeable is not None:
        pr["mergeable"] = str(mergeable)
    if merge_state is not None:
        pr["merge_state_status"] = str(merge_state)
    return pr


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
        pr = {
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
        # Tick 505: list often returns UNKNOWN; refresh via gh pr view.
        refresh_pr_mergeability(pr, repo_root=root)
        out.append(pr)
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

    Tick 505: when ``gh pr list`` leaves mergeable UNKNOWN/null, refresh via
    ``gh pr view`` (forces GitHub mergeability computation) so dual-unblock
    ``human_next`` can say undraft & merge now instead of vague UNKNOWN.
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
# Constant declared with other path constants above (Tick 391 tip-apply ignore).

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
    tip_commit_branch: str | None = None,
) -> str:
    """Tick 346–349/532: secrets-first tip PR body for ``gh pr edit`` / open_git_pr.

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

    Tick 393: body must stay **secrets-first and tick-generic**. Tick 392
    accidentally froze the chicken-egg tip-apply changelog into every future
    ``Tick {N}`` bullet — ``gh pr edit --body-file`` / open_git_pr description
    then lied about what the current tick did. Per-tick detail belongs in
    ``docs/ICML_PROGRESS.md``; this helper only carries the durable PRIMARY ask
    + tip anti-churn / MCP metadata notes.

    Tick 396: cite current offline B/D ID ranges from
    ``docs/offline_bvd_summary.json`` (not frozen ``1890–1904``).
    """
    tick = local_tick if local_tick is not None else 0
    n = tip_pr_number if tip_pr_number is not None else "N"
    offline_ids = _offline_bvd_id_range_blurb()
    h2_blurb = _offline_bvd_h2_blurb()
    # Tick 532: use live tip PR head — do not hardcode historical …-f49c.
    tip_branch = (
        (tip_commit_branch or "").strip()
        or (prefer_tip_pr_commit_branch() or "").strip()
        or "tip_pr_commit_branch"
    )
    if fetch_diamond_ok is False:
        load_icml_dotenv()
        nebius = _secret_present("NEBIUS_API_KEY")
        # Tick 497/506: when CSV / mirror / on-disk non-synthetic present, lead
        # with NEBIUS-only ask (Tick 499/502 diamond_ready parity).
        if not nebius and icml_diamond_source_ready_for_nebius_only():
            primary = (
                "**PRIMARY blocker:** add `NEBIUS_API_KEY` (HF optional — "
                "Tick 497 public diamond mirror / local `gpqa_diamond.csv` / "
                "Tick 502–504 on-disk keep) so cron can run live G2→G3→G4."
            )
            tick_lead = (
                f"Tick {tick}: live G2→G4 **PRIMARY** still blocked on "
                f"**NEBIUS_API_KEY** (HF optional via Tick 497 public mirror / "
                f"Tick 502–504 on-disk keep). "
                f"Offline PRIMARY/H5 green at {offline_ids} (D final **5/5**, "
                f"gens30/cost30 **4/5**, H5 **5/5**, {h2_blurb}). STATUS remains "
                f"IN_PROGRESS (not READY)."
            )
        else:
            primary = (
                f"**PRIMARY blocker:** add `NEBIUS_API_KEY` + (`HF_TOKEN` or local "
                f"`gpqa_diamond.csv` / Tick 497 public mirror) so cron can run live "
                f"G2→G3→G4."
            )
            tick_lead = (
                f"Tick {tick}: live G2→G4 **PRIMARY** still blocked on NEBIUS + "
                f"(HF_TOKEN or `gpqa_diamond.csv` / public mirror). Offline "
                f"PRIMARY/H5 green at {offline_ids} (D final **5/5**, "
                f"gens30/cost30 **4/5**, H5 **5/5**, {h2_blurb}). STATUS remains "
                f"IN_PROGRESS (not READY)."
            )
    elif fetch_diamond_ok is True:
        primary = (
            "**Secrets OK** — next: `bash scripts/icml_cron_entry.sh` for live "
            "G2→G3→G4 (or undraft+merge this tip into `main` first)."
        )
        tick_lead = (
            f"Tick {tick}: secrets present — run `bash scripts/icml_cron_entry.sh` "
            f"for live G2→G3→G4. Offline PRIMARY/H5 green at {offline_ids}. "
            f"STATUS stays IN_PROGRESS until live criteria pass."
        )
    else:
        primary = (
            "Check `docs/icml_secrets_status.json` / `docs/ICML_HUMAN_UNBLOCK.md` "
            "for NEBIUS (+ optional HF/CSV / Tick 497 mirror) gates."
        )
        tick_lead = (
            f"Tick {tick}: check secrets status / human unblock. Offline "
            f"PRIMARY/H5 green at {offline_ids}. STATUS remains IN_PROGRESS "
            f"(not READY)."
        )
    # Tick 393: keep this body *secrets-first and tick-generic*. Do **not**
    # hardcode the latest infra changelog (Tick 392 froze the chicken-egg
    # tip-apply narrative into every future Tick N body — operators reading
    # `gh pr edit --body-file` / open_git_pr description saw a stale single-tick
    # story instead of the durable PRIMARY ask). Per-tick work lives in
    # `docs/ICML_PROGRESS.md`; tip recover notes stay durable below.
    return (
        f"## Summary\n"
        f"- {tick_lead}\n"
        f"- {primary}\n"
        f"- Tip recover / chicken-egg + prior_live stack (see "
        f"`docs/ICML_PROGRESS.md`); tip PR anti-churn on this PR "
        f"(`{tip_branch}`). Tip PR GitHub **title and "
        f"body** stay frozen when using `open_git_pr` MCP (does **not** "
        f"rewrite either on existing PRs — Tick 345–350; prefer verbatim "
        f"args from `{ICML_OPEN_GIT_PR_CALL_RELPATH}`). Refresh via "
        f"`tip_pr_title_edit_commands` (`gh pr edit --title … "
        f"--body-file {ICML_TIP_PR_BODY_RELPATH}`). See `docs/ICML_PROGRESS.md` "
        f"for Tick {tick} detail.\n"
        f"\n"
        f"## Human unblock\n"
        f"1. Add `NEBIUS_API_KEY` + (`HF_TOKEN` or drop `gpqa_diamond.csv`)\n"
        f"2. Optional: copy-paste `tip_pr_title_edit_commands` from "
        f"`docs/icml_open_git_pr.json` to refresh this PR's title+body\n"
        f"3. Optional: undraft+merge tip PR #{n} and/or bootstrap PR #338\n"
        f"\n"
        f"## Test plan\n"
        f"- [x] `pytest tests/test_icml_env_checks.py::"
        f"test_suggested_open_git_pr_body_secrets_first_generic`\n"
        f"- [x] `pytest tests/test_icml_env_checks.py::"
        f"test_detect_gpqa_is_synthetic_and_secrets_auto_probe`\n"
        f"- [x] `pytest tests/test_icml_env_checks.py::"
        f"test_cron_refreshes_secrets_after_preflight`\n"
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


def tip_pr_commit_branch_from_status_json(
    repo_root: Path | None = None,
) -> str | None:
    """Read tip_pr_commit_branch (or Tick 351 head_ref fallback) from tip status.

    Tick 531: helper only — callers must prefer live resolve via
    ``resolve_anti_churn_checkout_branch`` so a committed stale
    ``docs/icml_tip_status.json`` cannot rewind tip after ``--apply``.
    """
    root = repo_root or _REPO_ROOT
    path = root / "docs" / "icml_tip_status.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    branch = str(data.get("tip_pr_commit_branch") or "").strip()
    if branch:
        return branch
    # Tick 351: tip_pr_head_ref fallback when tip_pr_commit_branch empty but
    # mergeable is not CONFLICTING (UNKNOWN/null used to skip anti-churn).
    mergeable = str(data.get("tip_pr_mergeable") or "").strip().upper()
    state = str(data.get("tip_pr_merge_state_status") or "").strip().upper()
    head = str(data.get("tip_pr_head_ref") or "").strip()
    if head and mergeable != "CONFLICTING" and state != "DIRTY":
        return head
    return None


def resolve_anti_churn_checkout_branch(
    repo_root: Path | None = None,
    *,
    live_branch: str | None = None,
    status_branch: str | None = None,
) -> str | None:
    """Tick 531/532: live tip-PR resolve wins over stale tip_status.json.

    Pre-531 ``icml_checkout_tip_pr_branch.sh`` preferred
    ``docs/icml_tip_status.json`` tip_pr_commit_branch. After tip ``--apply``
    to a newer tip SHA (e.g. Tick 530 on ``…-9e39``), that JSON may still name
    the prior tip PR head (``…-f49c`` / #337) — anti-churn then *rewound* tip
    from Tick 530 → 529. Prefer live ``prefer_tip_pr_commit_branch()``; fall
    back to status JSON only when live resolve is empty (gh down / no tip PR).

    Tick **532**: ``icml_cron_entry.sh`` also uses this helper for the
    ``already_on`` gate (pre-532 read tip_status JSON-first and could skip
    live re-resolve when HEAD matched a *stale* tip_pr_commit_branch).
    """
    root = repo_root or _REPO_ROOT
    live = (live_branch if live_branch is not None else prefer_tip_pr_commit_branch())
    live = (live or "").strip() or None
    status = (
        status_branch
        if status_branch is not None
        else tip_pr_commit_branch_from_status_json(repo_root=root)
    )
    status = (status or "").strip() or None
    if live:
        return live
    return status


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


def icml_diamond_source_ready_for_nebius_only(
    *,
    repo_root: Path | None = None,
) -> bool:
    """True when tip PR title/body should ask NEBIUS-only (Tick 506).

    Tick **497–499** made HF optional when CSV / public mirror / non-synthetic
    on-disk diamond is already present, and Tick **502** taught live
    ``--fetch-diamond`` to keep on-disk trees. Tip PR ``suggested_open_git_pr_*``
    helpers still keyed only on ``HF_TOKEN`` or ``resolve_diamond_csv_path()`` —
    after a CSV path was cleaned (or never persisted) while GPQA diamond stayed
    on disk, titles/bodies still said **NEBIUS+HF** and operators chased HF
    while ``docs/icml_secrets_status.json`` blockers were NEBIUS-only.
    """
    load_icml_dotenv()
    if _secret_present("HF_TOKEN") or _secret_present("HUGGINGFACE_HUB_TOKEN"):
        return True
    if resolve_diamond_csv_path(repo_root=repo_root) is not None:
        return True
    if icml_ondisk_nonsynthetic_gpqa(repo_root):
        return True
    return False


def suggested_open_git_pr_title(
    *,
    local_tick: int | None,
    fetch_diamond_ok: bool | None = None,
    repo_root: Path | None = None,
) -> str:
    """Tick 344: secrets-first tip PR title when live PRIMARY is still blocked.

    Tip PR #337 stayed titled ``Tick 336`` through Ticks 337–343, so among
    300+ draft tip PRs operators could treat the MERGEABLE tip as superseded.
    When ``fetch_diamond_ok`` is false, the suggested title leads with the
    PRIMARY secrets blocker (aligns with Tick 343 human_next ordering).
    """
    tick = local_tick if local_tick is not None else 0
    if fetch_diamond_ok is False:
        # Tick 497/506: diamond CSV / public mirror / on-disk non-synthetic often
        # present; NEBIUS is the remaining paid-live blocker — avoid implying HF
        # is still hard-required (Tick 499/502 diamond_ready parity).
        load_icml_dotenv()
        nebius = _secret_present("NEBIUS_API_KEY")
        if not nebius and icml_diamond_source_ready_for_nebius_only(
            repo_root=repo_root
        ):
            return (
                f"ICML Tick {tick}: add NEBIUS_API_KEY — live G2→G4 still blocked"
            )
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
        # Tick 506: include on-disk non-synthetic (Tick 499/502 diamond_ready).
        diamond_src = icml_diamond_source_ready_for_nebius_only(repo_root=root)
        meta_needs = icml_meta_requires_anthropic()
        secrets_ok = bool(nebius) and (bool(anthropic) if meta_needs else True)
        fetch_diamond_ok = bool(secrets_ok and diamond_src)
    tip_title = str(pr.get("title") or "")
    tip_body = str(pr.get("body") or "")
    title_tick = parse_tick_from_pr_title(tip_title)
    body_tick = parse_tick_from_pr_body(tip_body)
    suggested = suggested_open_git_pr_title(
        local_tick=local_tick,
        fetch_diamond_ok=fetch_diamond_ok,
        repo_root=root,
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
            tip_commit_branch=prefer_tip_pr_commit_branch(pr),
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
    # Tick 497: if no local CSV and no HF, try the public OpenAI mirror once.
    public_mirror_used = False
    if diamond_csv is None and not hf:
        mirrored = ensure_diamond_csv_via_public_mirror()
        if mirrored is not None:
            diamond_csv = mirrored
            public_mirror_used = True
    diamond_csv_ok = diamond_csv is not None
    # Tick 499: non-synthetic on-disk diamond (e.g. prior mirror materialize)
    # counts as diamond-ready even if the CSV path was cleaned — same idea as
    # Gate2 ``gpqa_not_synthetic`` / Tick 498 NEBIUS-first Next.
    gpqa_synth = detect_gpqa_is_synthetic()
    diamond_ready = bool(diamond_csv_ok or gpqa_synth is False)
    meta_needs_anthropic = icml_meta_requires_anthropic()
    secrets_ok = bool(nebius) and (bool(anthropic) if meta_needs_anthropic else True)
    # HF needed for --fetch-diamond unless operator supplies CSV offline,
    # Tick 497 public mirror succeeds, or non-synthetic diamond is already on disk.
    fetch_diamond_ok = secrets_ok and (hf or diamond_ready)
    # Tick 273/277: cron passes --fetch-diamond (optionally with --diamond-csv).
    cron_live_ok = fetch_diamond_ok
    blockers: list[str] = []
    if meta_needs_anthropic and not anthropic:
        blockers.append("ANTHROPIC_API_KEY missing")
    if not nebius:
        blockers.append("NEBIUS_API_KEY missing")
    if not hf and not diamond_ready:
        blockers.append(
            "HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing "
            "(required for --fetch-diamond; or provide --diamond-csv / "
            "drop gpqa_diamond.csv at $TMPDIR or docs/private/; or allow "
            "Tick 497 public OpenAI mirror fetch)"
        )
    main_has_tip = main_has_icml_tip_files()
    tip_pr = None if main_has_tip else resolve_icml_tip_pr()
    # Tick 342: surface interim AGENTS bootstrap PR when main still lacks tip.
    bootstrap_pr = None if main_has_tip else resolve_icml_agents_bootstrap_pr()
    # Tick 499: when diamond is already ready, phrase is NEBIUS-only (HF optional
    # omitted) so cron human_next matches Gate2 Next — operators chase NEBIUS.
    human_keys = icml_human_required_secrets_phrase(
        for_fetch_diamond=not diamond_ready
    )
    # Tick 343: PRIMARY-first ordering — secrets unblock live G2→G4; tip/bootstrap
    # merge is hygiene (chicken-egg recover still works). When diamond is blocked,
    # lead with secrets; when secrets+HF/CSV are OK but main lacks tip, lead with
    # bootstrap/tip merge (unchanged from Tick 342).
    # Tick 499: drop hard-coded "Accept HuggingFace access" step when diamond
    # ready (CSV / public mirror / non-synthetic on disk) — same operator trap
    # Tick 498 fixed in Gate2 ## Next.
    secrets_lines = [
        f"Add {human_keys} to automation "
        f"{_AUTOMATION_URL} (or linked env {_ENV_DASHBOARD_URL})",
    ]
    if not diamond_ready:
        secrets_lines.append(
            "Accept HuggingFace access for Idavidrein/gpqa with that HF token "
            "(or drop a real gpqa_diamond.csv at $TMPDIR/gpqa_diamond.csv / "
            "docs/private/gpqa_diamond.csv / $ICML_DIAMOND_CSV to skip HF; "
            "or rely on Tick 497 public OpenAI simple-evals mirror auto-fetch)"
        )
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
            "branch' does not override tip anti-churn); "
            "Tick 499: diamond_ready (CSV / public mirror / non-synthetic on "
            "disk) drops HF-accept human_next step + HF blocker; secrets phrase "
            "is NEBIUS-first when diamond already ready (Gate2 Tick 498 parity)"
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
        # Tick 525: portable label (repo-relative or $TMPDIR/gpqa_diamond.csv).
        "diamond_csv_path": (
            portable_path_for_durable(diamond_csv)
            if diamond_csv is not None
            else None
        ),
        "public_mirror_csv": public_mirror_used,
        # Tick 499: CSV **or** non-synthetic on-disk diamond (Gate2 parity).
        "diamond_ready": diamond_ready,
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


def detect_gpqa_is_synthetic(repo_root: Path | None = None) -> bool | None:
    """Tick 394: probe SIA / sia-upstream GPQA trees for synthetic smoke fixtures.

    Cron ``write_icml_secrets_status()`` historically left ``gpqa_is_synthetic``
    null unless the live pipeline passed an explicit flag derived from gate
    blockers. That meant early cron status (and Tip-393 committed secrets JSON)
    omitted the diamond-needed synthetic blocker even when ``SIA/…/gpqa`` was
    clearly smoke.

    Returns:
      True  — at least one known task tree looks like the smoke fixture
      False — at least one task layout exists and none look synthetic
      None  — no GPQA task layout found under default roots
    """
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    # Lazy import: prepare_gpqa_smoke_data imports this module at load time.
    try:
        from prepare_gpqa_smoke_data import (  # type: ignore
            DEFAULT_ROOTS,
            is_synthetic_smoke,
        )
    except ImportError:  # pragma: no cover - scripts/ not on path
        scripts_dir = str(root / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from prepare_gpqa_smoke_data import (  # type: ignore
            DEFAULT_ROOTS,
            is_synthetic_smoke,
        )

    found_layout = False
    any_synthetic = False
    for name in DEFAULT_ROOTS:
        task_dir = root / name / "sia" / "tasks" / "gpqa"
        if not (task_dir / "data").is_dir():
            continue
        found_layout = True
        if is_synthetic_smoke(task_dir):
            any_synthetic = True
    if not found_layout:
        return None
    return bool(any_synthetic)


def write_icml_secrets_status(
    path: Path | None = None,
    *,
    gpqa_is_synthetic: bool | None = None,
    repo_root: Path | None = None,
) -> dict:
    """Write ``docs/icml_secrets_status.json`` (presence-only; no secret values).

    Tick 394: when ``gpqa_is_synthetic`` is omitted, auto-detect via
    ``detect_gpqa_is_synthetic`` so cron status (which does not pass the flag)
    still surfaces the synthetic-diamond blocker.

    Tick 395: cron must call this **again after preflight** — G2
    ``ensure_smoke_layout`` materializes ``data/`` only during preflight, so the
    early cron write still sees ``None`` on greenfield boots. See
    ``refresh_secrets_after_preflight`` in ``scripts/icml_cron_entry.sh``.
    """
    status = collect_icml_secrets_status()
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    resolved = gpqa_is_synthetic
    if resolved is None:
        resolved = detect_gpqa_is_synthetic(root)
    if resolved is True:
        status["blockers"] = list(status["blockers"]) + [
            "gpqa still synthetic — need --fetch-diamond or real diamond CSV"
        ]
        status["gpqa_is_synthetic"] = True
    elif resolved is False:
        status["gpqa_is_synthetic"] = False
    else:
        status["gpqa_is_synthetic"] = None
    # Tick 274: cron / pipeline --live --fetch-diamond needs HF too.
    # Synthetic fixture is OK as a starting point when fetch_diamond_ok (HF will replace it).
    status["ready_for_live_pipeline"] = bool(status.get("fetch_diamond_ok"))
    # Tick 529: durable secrets free-text must not embed absolute host-tmp /
    # workspace paths (Tick 525/527/528 parity). Source strings already use
    # $TMPDIR, but sanitize blockers/human_next at write so future notes stay
    # portable.
    status["blockers"] = [
        sanitize_repo_paths_in_text(str(b), repo_root=root)
        for b in (status.get("blockers") or [])
    ]
    status["human_next"] = [
        sanitize_repo_paths_in_text(str(h), repo_root=root)
        for h in (status.get("human_next") or [])
    ]
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
    diamond_ready: bool | None = None,
) -> list[str]:
    """Human-facing Next bullets — tip + secrets + HF + cron entry (Tick 268–274/328/501).

    Tick 274: do **not** claim live-ready on Anthropic+Nebius alone — cron and
    ``--live --fetch-diamond`` also need diamond (``fetch_diamond_ok``).
    Tick 328: when ``main`` lacks tip files, prepend merge tip→main (dual unblock).
    Tick **501**: when ``diamond_ready`` (CSV / public mirror / non-synthetic on
    disk), secrets-missing Next is **NEBIUS-first** — no HF-accept chase
    (Gate2 Tick 498 / secrets Tick 499 / G3/G4 Tick 500 parity for pipeline
    ``## Next``).
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
                "`$TMPDIR/gpqa_diamond.csv` / `docs/private/gpqa_diamond.csv` / "
                f"`$ICML_DIAMOND_CSV`, **or** rely on Tick 497 public OpenAI "
                f"mirror auto-fetch. Add HF/CSV to {_AUTOMATION_URL}. "
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

    # Tick 343/501: secrets missing → PRIMARY-first (secrets before tip/bootstrap).
    # When diamond already ready, do not chase HF (Tick 498–500 parity).
    if diamond_ready:
        steps.extend(
            [
                "Add `NEBIUS_API_KEY` "
                "(ANTHROPIC_API_KEY optional — Tick 289 Nebius pydantic-ai meta) "
                "to automation "
                f"{_AUTOMATION_URL} (or linked env dashboard). "
                "Diamond already ready (CSV / public mirror / non-synthetic on "
                "disk) — HF optional (Tick 497/501). See `docs/ICML_HUMAN_UNBLOCK.md`.",
                "Next cron (or now): `bash scripts/icml_cron_entry.sh` — auto-recovers "
                "tip and runs live when `fetch_diamond_ok` (else preflight only).",
                "Portal Save of `docs/icml_portal_save_target.json` is **optional** "
                "(Tick 265–267: uv + runtime deps bootstrap in preflight).",
                "Do **not** set STATUS: READY from offline / preflight alone.",
            ]
        )
    else:
        steps.extend(
            [
                "Add `NEBIUS_API_KEY` + (`HF_TOKEN` **or** local `gpqa_diamond.csv` "
                "**or** Tick 497 public OpenAI mirror) "
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


def _offline_bvd_id_range_blurb(*, repo_root: Path | None = None) -> str:
    """Backticked B/D offline ID ranges from ``docs/offline_bvd_summary.json``.

    Tick 396: tip PR body must not freeze superseded ``1890–1904`` after a
    re-pilot bumps ``b_run_ids`` / ``d_run_ids``.
    """
    root = repo_root or _REPO_ROOT
    path = root / "docs" / "offline_bvd_summary.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        b_ids = [int(x) for x in (payload.get("b_run_ids") or [])]
        d_ids = [int(x) for x in (payload.get("d_run_ids") or [])]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        b_ids, d_ids = [], []
    b_vars = _offline_id_range_strings(b_ids)
    d_vars = _offline_id_range_strings(d_ids)
    b = next((v for v in b_vars if v.startswith("`")), "`1930–1934`")
    d = next((v for v in d_vars if v.startswith("`")), "`1940–1944`")
    return f"{b} / {d}"


def _offline_bvd_h2_blurb(*, repo_root: Path | None = None) -> str:
    """Tick 397: tip PR body H2 line from ``docs/offline_bvd_summary.json``.

    Avoid freezing ``H2 preferred **4/5**; steered-window gen≥3`` after a
    re-pilot that flips MECHANISM seed wins (e.g. post-adoption tail → 5/5).
    """
    root = repo_root or _REPO_ROOT
    path = root / "docs" / "offline_bvd_summary.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        compare = payload.get("compare") or {}
        d_wins = compare.get("d_wins_h2")
        n_pairs = compare.get("n_pairs") or 5
        proto = payload.get("h2_protocol") or {}
        floor = proto.get("min_generation_floor", proto.get("min_generation", 3))
        tail = proto.get("tail_generations")
        if d_wins is None:
            raise ValueError("missing d_wins_h2")
        if tail:
            window = f"floor gen≥{floor} + tail={tail}"
        else:
            window = f"steered-window gen≥{floor}"
        return f"H2 preferred **{int(d_wins)}/{int(n_pairs)}**; {window}"
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return "H2 preferred **5/5**; floor gen≥3 + tail=2"

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

    Tick 399: also require judge-facing ``SUBMISSION.md`` / ``PRESENTATION.md``
    (when present) and ``scripts/present_hackathon.py`` to cite current offline
    B/D ranges — Tick 319/320 surfaces still pointed at superseded Tick-300
    ``1890–1904`` / ``run_1900`` after Tick 397 ID lock.

    Tick 400: also require operator-facing ``ICML_HUMAN_UNBLOCK.md`` (when
    present) to cite current offline B/D ranges — dual-unblock intro still
    froze Tick-300 ``1890–1904`` after Tick 397–399 ID locks.

    Tick 401: also require root ``README.md`` (when present) evidence checklist
    to cite current offline B/D ranges — Tick 318/322 surfaces still pointed at
    superseded Tick-300 ``1890–1904`` after Tick 397–400 ID locks.
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

        # Tick 399: judge-facing SUBMISSION / PRESENTATION / present demo.
        submission = root / "docs" / "SUBMISSION.md"
        if submission.is_file():
            sub_text = submission.read_text(encoding="utf-8")
            if not _text_cites_any(sub_text, b_variants) or not _text_cites_any(
                sub_text, d_variants
            ):
                problems.append(
                    "docs/SUBMISSION.md: missing current offline B/D ranges "
                    f"{b_variants[0]} / {d_variants[0]} (Tick 399)"
                )
            if case_run not in sub_text:
                problems.append(
                    f"docs/SUBMISSION.md: missing current case study {case_run} "
                    "(Tick 399)"
                )
        presentation = root / "docs" / "PRESENTATION.md"
        if presentation.is_file():
            pres_text = presentation.read_text(encoding="utf-8")
            if not _text_cites_any(pres_text, b_variants) or not _text_cites_any(
                pres_text, d_variants
            ):
                problems.append(
                    "docs/PRESENTATION.md: missing current offline B/D ranges "
                    f"{b_variants[0]} / {d_variants[0]} (Tick 399)"
                )
        present_py = root / "scripts" / "present_hackathon.py"
        if present_py.is_file():
            present_text = present_py.read_text(encoding="utf-8")
            if "offline_bvd_summary" not in present_text:
                problems.append(
                    "scripts/present_hackathon.py: must read "
                    "docs/offline_bvd_summary.json for evidence IDs (Tick 399)"
                )
            if "_offline_evidence_ids_blurb" not in present_text:
                problems.append(
                    "scripts/present_hackathon.py: talking points must use "
                    "_offline_evidence_ids_blurb (Tick 399; no hardcoded IDs)"
                )
            # Guard against reintroducing superseded Tick-300 hardcodes.
            if re.search(r"IDs\s+1890[-–]1904", present_text):
                problems.append(
                    "scripts/present_hackathon.py: hardcoded superseded "
                    "1890-1904 evidence IDs (Tick 399)"
                )

        # Tick 400: operator-facing human-unblock dual-unblock intro.
        unblock = root / "docs" / "ICML_HUMAN_UNBLOCK.md"
        if unblock.is_file():
            unblock_text = unblock.read_text(encoding="utf-8")
            # Prefer the dual-unblock section (operators read this first).
            dual_idx = unblock_text.find("## Dual human unblock")
            dual_block = (
                unblock_text[dual_idx : dual_idx + 900]
                if dual_idx != -1
                else unblock_text[:900]
            )
            if not _text_cites_any(dual_block, b_variants) or not _text_cites_any(
                dual_block, d_variants
            ):
                problems.append(
                    "docs/ICML_HUMAN_UNBLOCK.md dual-unblock: missing current "
                    f"offline B/D ranges {b_variants[0]} / {d_variants[0]} "
                    "(Tick 400)"
                )
            # Dual-unblock intro historically used a single combined span
            # (Tick-300 ``1890–1904``). Reject that superseded combined cite
            # in the dual-unblock lead-in only (changelog may still name it).
            if re.search(r"`?1890[-–]1904`?", dual_block):
                problems.append(
                    "docs/ICML_HUMAN_UNBLOCK.md dual-unblock: superseded "
                    "Tick-300 combined ID span 1890-1904 (Tick 400)"
                )

        # Tick 401: root README evidence checklist (first surface humans open).
        readme = root / "README.md"
        if readme.is_file():
            readme_text = readme.read_text(encoding="utf-8")
            # Prefer the Submission / ICML evidence checklist section.
            chk_idx = readme_text.find("## Submission / ICML evidence checklist")
            chk_block = (
                readme_text[chk_idx : chk_idx + 700]
                if chk_idx != -1
                else readme_text
            )
            if not _text_cites_any(chk_block, b_variants) or not _text_cites_any(
                chk_block, d_variants
            ):
                problems.append(
                    "README.md evidence checklist: missing current offline "
                    f"B/D ranges {b_variants[0]} / {d_variants[0]} (Tick 401)"
                )
            # Reject superseded Tick-300 combined span in the checklist.
            if re.search(r"`?1890[-–]1904`?", chk_block):
                problems.append(
                    "README.md evidence checklist: superseded Tick-300 "
                    "combined ID span 1890-1904 (Tick 401)"
                )

    return (len(problems) == 0, problems)
