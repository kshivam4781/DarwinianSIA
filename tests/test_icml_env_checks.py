"""Tests for scripts/icml_env_checks.py (Tick 32 per-run venv probe)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from icml_env_checks import (  # noqa: E402
    DEFAULT_ICML_META_AGENT_PROFILE,
    DEFAULT_ICML_TARGET_AGENT_PROFILE,
    EPHEMERAL_ICML_RELPATHS,
    build_icml_open_git_pr_hint,
    collect_icml_secrets_status,
    collect_icml_tip_status,
    committed_g3g4_recipes_match_live_shape,
    committed_offline_bvd_matches_live_shape,
    default_g2_estimate_usd,
    default_g3_pair_estimate_usd,
    default_g4_pair_estimate_usd,
    discard_ephemeral_icml_dirt,
    ensure_budget_spent_ledger_initialized,
    ensure_icml_runtime_deps,
    ensure_sia_on_pythonpath,
    ensure_uv_on_path,
    extract_sia_shape_flags,
    hydrate_direct_gate_budget_spent,
    persist_direct_gate_stage_spend,
    direct_gate_ledger_skip,
    icml_diamond_n_for_stack,
    icml_fetch_diamond_needs_hf,
    icml_g3g4_live_shape,
    icml_human_required_secrets_phrase,
    icml_meta_profile_cli_flags,
    icml_meta_requires_anthropic,
    icml_ondisk_nonsynthetic_gpqa,
    icml_should_keep_ondisk_diamond,
    icml_python_cli,
    icml_target_profile_cli_flags,
    is_ephemeral_icml_path,
    iter_shape_flag_dicts_from_text,
    live_pipeline_next_steps,
    parse_latest_icml_tick,
    prefer_tip_pr_commit_branch,
    probe_icml_meta_profile,
    probe_icml_target_profile_nebius,
    probe_per_run_venv_capable,
    resolve_icml_meta_agent_profile,
    resolve_icml_target_agent_profile,
    write_icml_secrets_status,
    write_icml_tip_status,
)


def test_probe_passes_when_uv_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "icml_env_checks.shutil.which",
        lambda name: "/tmp/fake-uv" if name == "uv" else None,
    )
    ok, detail = probe_per_run_venv_capable()
    assert ok is True
    assert "uv available" in detail


def test_probe_fails_when_neither_uv_nor_ensurepip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("icml_env_checks.shutil.which", lambda name: None)

    class _Result:
        returncode = 1
        stderr = (
            "The virtual environment was not created successfully because "
            "ensurepip is not available."
        )
        stdout = ""

    monkeypatch.setattr(
        "icml_env_checks.subprocess.run",
        lambda *_a, **_k: _Result(),
    )
    ok, detail = probe_per_run_venv_capable()
    assert ok is False
    assert "ensurepip" in detail or "failed" in detail.lower()


def test_probe_survives_venv_create_systemexit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tick 34: ensurepip path used to sys.exit and kill preflight."""
    monkeypatch.setattr("icml_env_checks.shutil.which", lambda name: None)

    class _Result:
        returncode = 1
        stderr = "venv.create SystemExit:1"
        stdout = ""

    monkeypatch.setattr(
        "icml_env_checks.subprocess.run",
        lambda *_a, **_k: _Result(),
    )
    ok, detail = probe_per_run_venv_capable()
    assert ok is False
    assert "failed" in detail.lower()


def test_ensure_uv_skips_install_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "icml_env_checks.shutil.which",
        lambda name: "/home/ubuntu/.local/bin/uv" if name == "uv" else None,
    )
    calls: list[object] = []

    def _no_run(*_a, **_k):
        calls.append(True)
        raise AssertionError("should not install")

    monkeypatch.setattr("icml_env_checks.subprocess.run", _no_run)
    ok, detail = ensure_uv_on_path(allow_install=True)
    assert ok is True
    assert "uv available" in detail
    assert calls == []


def test_ensure_uv_install_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("icml_env_checks.shutil.which", lambda name: None)
    ok, detail = ensure_uv_on_path(allow_install=False)
    assert ok is False
    assert "install disabled" in detail


def test_probe_bootstrap_uv_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tick 265: bootstrap_uv=True should call ensure_uv and skip stdlib probe."""

    def _ensure(*, allow_install: bool = True):
        assert allow_install is True
        return True, "uv installed at /tmp/uv (Astral bootstrap)"

    monkeypatch.setattr("icml_env_checks.ensure_uv_on_path", _ensure)

    def _boom(*_a, **_k):
        raise AssertionError("stdlib probe should not run when uv bootstrap succeeds")

    monkeypatch.setattr("icml_env_checks.subprocess.run", _boom)
    ok, detail = probe_per_run_venv_capable(bootstrap_uv=True)
    assert ok is True
    assert "Astral bootstrap" in detail


def test_ensure_sia_on_pythonpath(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tick 266: SIA/ prepended so host can ``import sia`` without Portal Save."""
    monkeypatch.delenv("PYTHONPATH", raising=False)
    # Drop any prior sia import residue from earlier tests.
    sys.modules.pop("sia", None)
    ok, detail = ensure_sia_on_pythonpath()
    assert ok is True
    assert "sia importable" in detail
    assert "SIA" in (os.environ.get("PYTHONPATH") or "")


def test_ensure_runtime_deps_install_disabled_reports_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "icml_env_checks.ensure_uv_on_path",
        lambda *, allow_install=True: (True, "uv available at /tmp/uv"),
    )
    monkeypatch.setattr(
        "icml_env_checks.ensure_sia_on_pythonpath",
        lambda: (True, "sia importable via PYTHONPATH=/tmp/SIA"),
    )
    monkeypatch.setattr(
        "icml_env_checks._module_importable",
        lambda name: False,
    )
    ok, detail = ensure_icml_runtime_deps(allow_install=False)
    assert ok is False
    assert "install disabled" in detail
    assert "huggingface_hub" in detail


def test_ensure_runtime_deps_bootstraps_missing_hub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tick 266/289/516: missing hub/pydantic_ai/matplotlib triggers install."""
    monkeypatch.setattr(
        "icml_env_checks.ensure_uv_on_path",
        lambda *, allow_install=True: (True, "uv available at /tmp/uv"),
    )
    monkeypatch.setattr(
        "icml_env_checks.ensure_sia_on_pythonpath",
        lambda: (True, "sia importable via PYTHONPATH=/tmp/SIA"),
    )
    state = {"hub": False, "pydantic_ai": False, "matplotlib": False}

    def _imp(name: str) -> bool:
        if name == "huggingface_hub":
            return state["hub"]
        if name == "pydantic_ai":
            return state["pydantic_ai"]
        if name == "matplotlib":
            return state["matplotlib"]
        return False

    monkeypatch.setattr("icml_env_checks._module_importable", _imp)

    def _pip(*packages: str):
        # Tick 289: also bootstraps pydantic-ai (pip name) for Nebius meta.
        # Tick 516: also bootstraps matplotlib for offline Figs 1–2.
        assert any(
            p in packages
            for p in ("huggingface_hub", "pydantic-ai", "matplotlib")
        )
        if "huggingface_hub" in packages:
            state["hub"] = True
        if "pydantic-ai" in packages or "pydantic_ai" in packages:
            state["pydantic_ai"] = True
        if "matplotlib" in packages:
            state["matplotlib"] = True
        return True, f"pip installed {', '.join(packages)}"

    monkeypatch.setattr("icml_env_checks._pip_install_user", _pip)
    ok, detail = ensure_icml_runtime_deps(allow_install=True)
    assert ok is True
    assert "bootstrapped" in detail
    assert "huggingface_hub" in detail
    assert "matplotlib" in detail
    assert state["hub"] is True
    assert state["pydantic_ai"] is True
    assert state["matplotlib"] is True


def test_runtime_pip_packages_include_matplotlib() -> None:
    """Tick 516: matplotlib is a runtime bootstrap package (cold-boot Figs)."""
    from icml_env_checks import _RUNTIME_PIP_PACKAGES

    assert "matplotlib" in _RUNTIME_PIP_PACKAGES


def test_offline_bvd_figures_call_ensure_runtime_deps() -> None:
    """Tick 517: offline rematerialize path must invoke ensure before Figs."""
    root = Path(__file__).resolve().parents[1]
    offline_cs = (root / "scripts" / "offline_bvd_case_study.py").read_text(
        encoding="utf-8"
    )
    epi = (root / "scripts" / "epistemic_results.py").read_text(encoding="utf-8")
    assert "ensure_icml_runtime_deps" in offline_cs
    assert "Tick 517" in offline_cs
    assert "ensure_icml_runtime_deps" in epi
    assert "Tick 517" in epi
    assert "test_maybe_figures_bootstraps_runtime_deps" in (
        root / "tests" / "test_offline_case_study_steered.py"
    ).read_text(encoding="utf-8")


def test_live_g4_figures_call_ensure_runtime_deps() -> None:
    """Tick 518: live paper-pack Figs must invoke ensure (ledger-skip safe)."""
    root = Path(__file__).resolve().parents[1]
    g4 = (root / "scripts" / "run_g4_multiseed.py").read_text(encoding="utf-8")
    assert "def write_live_bvd_figures" in g4
    assert "Tick 518" in g4
    # Ensure is called inside write_live_bvd_figures, not only in run_preflight.
    fn_idx = g4.find("def write_live_bvd_figures")
    next_def = g4.find("\ndef ", fn_idx + 1)
    body = g4[fn_idx:next_def]
    assert "ensure_icml_runtime_deps" in body
    assert "matplotlib unavailable" in body
    assert "test_write_live_bvd_figures_bootstraps_runtime_deps" in (
        root / "tests" / "test_run_g4_multiseed.py"
    ).read_text(encoding="utf-8")


def test_ensure_deps_before_diamond_fetch_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tick 282: diamond-fetch helper is ensure_icml_runtime_deps (pre-materialize)."""
    from icml_env_checks import ensure_deps_before_diamond_fetch

    called: list[bool] = []

    def _fake(*, allow_install: bool = True) -> tuple[bool, str]:
        called.append(allow_install)
        return True, "bootstrapped for diamond"

    monkeypatch.setattr("icml_env_checks.ensure_icml_runtime_deps", _fake)
    ok, detail = ensure_deps_before_diamond_fetch(allow_install=True)
    assert ok is True
    assert detail == "bootstrapped for diamond"
    assert called == [True]


def test_pip_install_user_prefers_uv_pip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tick 279: uv pip install used before python -m pip (pip-less envs)."""
    from icml_env_checks import _pip_install_user

    monkeypatch.setattr(
        "icml_env_checks._uv_pip_install",
        lambda *packages: (True, f"uv pip installed {', '.join(packages)} into /tmp/py"),
    )

    def _fail_pip(*_a, **_k):  # pragma: no cover - must not be called
        raise AssertionError("python -m pip should not run when uv succeeds")

    monkeypatch.setattr("icml_env_checks.subprocess.run", _fail_pip)
    ok, detail = _pip_install_user("huggingface_hub")
    assert ok is True
    assert "uv pip installed huggingface_hub" in detail


def test_uv_pip_install_targets_user_site(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Tick 280: uv pip uses --target user site (not read-only system dist-packages)."""
    from icml_env_checks import _uv_pip_install

    target = tmp_path / "site-packages"
    monkeypatch.setattr(
        "icml_env_checks._user_site_packages",
        lambda: target,
    )
    monkeypatch.setattr("icml_env_checks.shutil.which", lambda _name: "/tmp/fake-uv")
    monkeypatch.delenv("PYTHONPATH", raising=False)

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    calls: list[list[str]] = []

    def _run(cmd, **_kwargs):
        calls.append(list(cmd))
        return _Proc()

    monkeypatch.setattr("icml_env_checks.subprocess.run", _run)
    ok, detail = _uv_pip_install("huggingface_hub")
    assert ok is True
    assert str(target) in detail
    assert calls, "uv pip should be invoked"
    cmd = calls[0]
    assert cmd[0] == "/tmp/fake-uv"
    assert cmd[1:3] == ["pip", "install"]
    assert "--target" in cmd
    assert str(target) in cmd
    assert "huggingface_hub" in cmd
    # Must not rely on bare system install (Permission denied on /usr/local).
    assert "--system" not in cmd
    assert str(target) in __import__("sys").path
    # Tick 281: also on PYTHONPATH for PYTHONNOUSERSITE / venv children.
    assert str(target) in (os.environ.get("PYTHONPATH") or "")


def test_expose_user_site_on_pythonpath_survives_nousersite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 281: user-site --target packages remain importable under PYTHONNOUSERSITE."""
    import subprocess

    from icml_env_checks import _expose_user_site_on_pythonpath

    site = tmp_path / "site-packages"
    pkg = site / "icml_tick281_probe"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("MARKER = 'tick281'\n", encoding="utf-8")

    monkeypatch.delenv("PYTHONPATH", raising=False)
    exposed = _expose_user_site_on_pythonpath(site)
    assert exposed == str(site)
    assert str(site) in (os.environ.get("PYTHONPATH") or "")

    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    # Drop any prior PYTHONPATH pollution except our exposed site.
    env["PYTHONPATH"] = str(site)
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import icml_tick281_probe; print(icml_tick281_probe.MARKER)",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "tick281"

    # Without PYTHONPATH, PYTHONNOUSERSITE must fail (documents the Tick 280 gap).
    env_fail = os.environ.copy()
    env_fail["PYTHONNOUSERSITE"] = "1"
    env_fail.pop("PYTHONPATH", None)
    fail = subprocess.run(
        [
            sys.executable,
            "-c",
            "import icml_tick281_probe",
        ],
        env=env_fail,
        capture_output=True,
        text=True,
        check=False,
    )
    assert fail.returncode != 0


def test_pip_install_user_falls_back_to_pip_when_uv_misses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tick 279: if uv pip fails, fall back to python -m pip --user."""
    from icml_env_checks import _pip_install_user

    monkeypatch.setattr(
        "icml_env_checks._uv_pip_install",
        lambda *packages: (False, "uv not on PATH for package install"),
    )

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    calls: list[list[str]] = []

    def _run(cmd, **_kwargs):
        calls.append(list(cmd))
        return _Proc()

    monkeypatch.setattr("icml_env_checks.subprocess.run", _run)
    ok, detail = _pip_install_user("huggingface_hub")
    assert ok is True
    assert "pip installed huggingface_hub" in detail
    assert calls and calls[0][:4] == [__import__("sys").executable, "-m", "pip", "install"]
    assert "--user" in calls[0]


def test_collect_secrets_status_presence_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tick 268: status reports PRESENT/ABSENT and never echoes values."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-should-not-leak")
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    monkeypatch.setattr("icml_env_checks.main_has_icml_tip_files", lambda **_k: True)
    status = collect_icml_secrets_status()
    blob = json.dumps(status)
    assert "sk-ant-secret-should-not-leak" not in blob
    assert status["secrets"]["ANTHROPIC_API_KEY"] == "PRESENT"
    assert status["secrets"]["NEBIUS_API_KEY"] == "ABSENT"
    assert status["portal_save_required_for_live"] is False
    assert status["secrets_ok_for_paid_sia"] is False
    assert status["fetch_diamond_ok"] is False
    assert status["cron_live_ok"] is False
    assert any("NEBIUS" in b for b in status["blockers"])
    assert status["main_has_icml_tip"] is True


def test_secrets_status_human_next_merge_tip_when_main_lacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tick 328/330/335/336: dual unblock — tip PR + mergeability + gh copy-paste."""
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.setenv("HF_TOKEN", "hf-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("icml_env_checks.main_has_icml_tip_files", lambda **_k: False)
    fake_pr = {
        "url": "https://github.com/kshivam4781/DarwinianSIA/pull/330",
        "number": 330,
        "title": "ICML Tick 329",
        "is_draft": True,
        "head_ref": "cursor/icml-epistemic-results-45fd",
        "mergeable": "MERGEABLE",
        "merge_state_status": "CLEAN",
    }
    monkeypatch.setattr("icml_env_checks.resolve_icml_tip_pr", lambda **_k: fake_pr)
    # No bootstrap PR → tip merge stays human_next[0] (Tick 342 optional).
    monkeypatch.setattr(
        "icml_env_checks.resolve_icml_agents_bootstrap_pr", lambda **_k: None
    )
    status = collect_icml_secrets_status()
    assert status["main_has_icml_tip"] is False
    assert status["fetch_diamond_ok"] is True  # merge tip does not gate paid live
    assert status["blockers"] == []
    assert "Merge the latest ICML tip PR into `main`" in status["human_next"][0]
    assert "https://github.com/kshivam4781/DarwinianSIA/pull/330" in status["human_next"][0]
    assert "#330" in status["human_next"][0]
    assert "MERGEABLE" in status["human_next"][0]
    assert "undraft" in status["human_next"][0].lower()
    # Tick 336: copy-paste gh ready+merge + tip-PR churn warning.
    assert "gh pr ready 330" in status["human_next"][0]
    assert "gh pr merge 330" in status["human_next"][0]
    # Tick 337: anti-churn note replaces "new tip PR will supersede" wording.
    assert "tip_pr_commit_branch" in status["human_next"][0] or "do NOT open a new tip PR" in status["human_next"][0]
    assert status["tip_pr_url"] == fake_pr["url"]
    assert status["tip_pr_number"] == 330
    assert status["tip_pr_is_draft"] is True
    assert status["tip_pr_mergeable"] == "MERGEABLE"
    assert status["tip_pr_merge_state_status"] == "CLEAN"
    assert status["tip_pr_merge_commands"] == [
        "gh pr ready 330 --repo kshivam4781/DarwinianSIA",
        "gh pr merge 330 --repo kshivam4781/DarwinianSIA --merge",
    ]
    # Tick 337: anti-churn fields on secrets JSON.
    assert status["tip_pr_commit_branch"] == "cursor/icml-epistemic-results-45fd"
    assert status["tip_pr_anti_churn"] is True
    assert status["agents_bootstrap_pr_url"] is None
    assert status["agents_bootstrap_merge_commands"] == []
    steps = live_pipeline_next_steps(
        secrets_ok=True,
        tip_ok=True,
        fetch_diamond_ok=True,
        main_has_icml_tip=False,
    )
    assert "Merge the latest ICML tip PR into `main`" in steps[0]
    assert "pull/330" in steps[0]
    assert "gh pr merge 330" in steps[0]
    assert "do NOT open a new tip PR" in steps[0]


def test_secrets_status_human_next_agents_bootstrap_before_tip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tick 342: interim AGENTS bootstrap PR leads human_next when open."""
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.setenv("HF_TOKEN", "hf-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("icml_env_checks.main_has_icml_tip_files", lambda **_k: False)
    tip_pr = {
        "url": "https://github.com/kshivam4781/DarwinianSIA/pull/337",
        "number": 337,
        "title": "ICML tip",
        "is_draft": True,
        "head_ref": "cursor/icml-epistemic-results-f49c",
        "mergeable": "MERGEABLE",
        "merge_state_status": "CLEAN",
    }
    boot_pr = {
        "url": "https://github.com/kshivam4781/DarwinianSIA/pull/338",
        "number": 338,
        "title": "ICML AGENTS bootstrap",
        "is_draft": True,
        "head_ref": "cursor/icml-main-agents-bootstrap",
        "mergeable": "MERGEABLE",
        "merge_state_status": "CLEAN",
    }
    monkeypatch.setattr("icml_env_checks.resolve_icml_tip_pr", lambda **_k: tip_pr)
    monkeypatch.setattr(
        "icml_env_checks.resolve_icml_agents_bootstrap_pr", lambda **_k: boot_pr
    )
    status = collect_icml_secrets_status()
    assert "Optional interim" in status["human_next"][0]
    assert "pull/338" in status["human_next"][0]
    assert "gh pr ready 338" in status["human_next"][0]
    assert "gh pr merge 338" in status["human_next"][0]
    assert "not a tip PR" in status["human_next"][0].lower() or "not** a tip PR" in status["human_next"][0]
    assert "Merge the latest ICML tip PR into `main`" in status["human_next"][1]
    assert "#337" in status["human_next"][1]
    assert status["agents_bootstrap_pr_number"] == 338
    assert status["agents_bootstrap_pr_url"] == boot_pr["url"]
    assert status["agents_bootstrap_pr_mergeable"] == "MERGEABLE"
    assert status["agents_bootstrap_merge_commands"] == [
        "gh pr ready 338 --repo kshivam4781/DarwinianSIA",
        "gh pr merge 338 --repo kshivam4781/DarwinianSIA --merge",
    ]
    steps = live_pipeline_next_steps(
        secrets_ok=True,
        tip_ok=True,
        fetch_diamond_ok=True,
        main_has_icml_tip=False,
    )
    assert "Optional interim" in steps[0]
    assert "pull/338" in steps[0]
    assert "Merge the latest ICML tip PR into `main`" in steps[1]


def test_secrets_status_human_next_primary_first_when_diamond_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tick 343: secrets lead human_next when fetch_diamond_ok is false."""
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("icml_env_checks.load_icml_dotenv", lambda: [])
    monkeypatch.setattr("icml_env_checks.main_has_icml_tip_files", lambda **_k: False)
    monkeypatch.setattr(
        "icml_env_checks.resolve_diamond_csv_path", lambda *_a, **_k: None
    )
    monkeypatch.setattr(
        "icml_env_checks.ensure_diamond_csv_via_public_mirror",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "icml_env_checks.detect_gpqa_is_synthetic", lambda *_a, **_k: None
    )
    tip_pr = {
        "url": "https://github.com/kshivam4781/DarwinianSIA/pull/337",
        "number": 337,
        "title": "ICML tip",
        "is_draft": True,
        "head_ref": "cursor/icml-epistemic-results-f49c",
        "mergeable": "MERGEABLE",
        "merge_state_status": "CLEAN",
    }
    boot_pr = {
        "url": "https://github.com/kshivam4781/DarwinianSIA/pull/338",
        "number": 338,
        "title": "ICML AGENTS bootstrap",
        "is_draft": True,
        "head_ref": "cursor/icml-main-agents-bootstrap",
        "mergeable": "MERGEABLE",
        "merge_state_status": "CLEAN",
    }
    monkeypatch.setattr("icml_env_checks.resolve_icml_tip_pr", lambda **_k: tip_pr)
    monkeypatch.setattr(
        "icml_env_checks.resolve_icml_agents_bootstrap_pr", lambda **_k: boot_pr
    )
    status = collect_icml_secrets_status()
    assert status["fetch_diamond_ok"] is False
    assert status["diamond_ready"] is False
    assert status["main_has_icml_tip"] is False
    assert "NEBIUS" in status["human_next"][0]
    assert "automation" in status["human_next"][0].lower() or "Add" in status["human_next"][0]
    # Diamond absent → HF-accept step still present (Tick 499 keeps it when not ready).
    assert any("Accept HuggingFace access" in line for line in status["human_next"])
    # Tip/bootstrap still present, but after secrets (+ HF accept line).
    assert any("pull/338" in line for line in status["human_next"])
    assert any("#337" in line for line in status["human_next"])
    boot_idx = next(
        i for i, line in enumerate(status["human_next"]) if "pull/338" in line
    )
    assert boot_idx > 0
    steps = live_pipeline_next_steps(
        secrets_ok=False,
        tip_ok=True,
        fetch_diamond_ok=False,
        main_has_icml_tip=False,
    )
    assert "NEBIUS_API_KEY" in steps[0]
    assert any("pull/338" in s for s in steps)
    assert any("pull/337" in s or "#337" in s for s in steps)
    merge_idx = next(i for i, s in enumerate(steps) if "Optional interim" in s or "pull/338" in s)
    assert merge_idx > 0


def test_icml_preflight_diamond_ready_shared_helper() -> None:
    """Tick 500: shared diamond-ready helper used by Gate2/G3/G4 Next."""
    from icml_env_checks import icml_preflight_diamond_ready

    assert icml_preflight_diamond_ready(gpqa_not_synthetic_ok=True) is True
    assert (
        icml_preflight_diamond_ready(
            notes=["Tick 278: auto-wired --diamond-csv from /tmp/gpqa_diamond.csv"]
        )
        is True
    )
    assert (
        icml_preflight_diamond_ready(
            notes=["materialized diamond from CSV → ['/tmp/x']"]
        )
        is True
    )
    assert (
        icml_preflight_diamond_ready(
            notes=["fetched via public OpenAI simple-evals mirror"]
        )
        is True
    )
    assert icml_preflight_diamond_ready(notes=["unrelated note"]) is False
    assert icml_preflight_diamond_ready() is False


def test_icml_fetch_diamond_needs_hf_skips_ondisk_nonsynthetic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 502: on-disk non-synthetic diamond ⇒ HF not required for --fetch-diamond."""
    # No layout → needs HF when fetch + no CSV.
    assert (
        icml_fetch_diamond_needs_hf(
            fetch_diamond=True, diamond_csv=None, repo_root=tmp_path
        )
        is True
    )
    assert (
        icml_fetch_diamond_needs_hf(
            fetch_diamond=True,
            diamond_csv=tmp_path / "gpqa_diamond.csv",
            repo_root=tmp_path,
        )
        is False
    )
    assert (
        icml_fetch_diamond_needs_hf(
            fetch_diamond=False, diamond_csv=None, repo_root=tmp_path
        )
        is False
    )

    # Build a non-synthetic GPQA layout under SIA/.
    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa" / "data"
    (task / "private").mkdir(parents=True)
    rows = [
        {
            "domain": "physics",
            "Question": "Real diamond Q1?",
            "correct_answer_letter": "A",
        }
    ]
    (task / "private" / "diamond_questions.json").write_text(
        json.dumps(rows), encoding="utf-8"
    )
    assert icml_ondisk_nonsynthetic_gpqa(tmp_path) is True
    assert (
        icml_fetch_diamond_needs_hf(
            fetch_diamond=True, diamond_csv=None, repo_root=tmp_path
        )
        is False
    )


def test_icml_should_keep_ondisk_diamond_csv_auto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 504: keep ondisk when CSV is auto-wired; rematerialize if explicit."""
    assert (
        icml_should_keep_ondisk_diamond(
            diamond_csv=None, csv_auto=False, repo_root=tmp_path
        )
        is False
    )
    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa" / "data"
    (task / "private").mkdir(parents=True)
    rows = [
        {
            "domain": "physics",
            "Question": "Real diamond Q1?",
            "correct_answer_letter": "A",
        }
    ]
    (task / "private" / "diamond_questions.json").write_text(
        json.dumps(rows), encoding="utf-8"
    )
    csv_path = tmp_path / "gpqa_diamond.csv"
    assert (
        icml_should_keep_ondisk_diamond(
            diamond_csv=None, csv_auto=False, repo_root=tmp_path
        )
        is True
    )
    assert (
        icml_should_keep_ondisk_diamond(
            diamond_csv=csv_path, csv_auto=True, repo_root=tmp_path
        )
        is True
    )
    assert (
        icml_should_keep_ondisk_diamond(
            diamond_csv=csv_path, csv_auto=False, repo_root=tmp_path
        )
        is False
    )


def test_secrets_status_human_next_nebius_first_when_diamond_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 499: drop HF-accept human_next when diamond CSV / non-synthetic ready."""
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("icml_env_checks.load_icml_dotenv", lambda: [])
    monkeypatch.setattr("icml_env_checks.main_has_icml_tip_files", lambda **_k: False)
    csv_path = tmp_path / "gpqa_diamond.csv"
    csv_path.write_text("Question,Correct Answer\nQ?,A\n", encoding="utf-8")
    monkeypatch.setattr(
        "icml_env_checks.resolve_diamond_csv_path", lambda **_k: csv_path
    )
    monkeypatch.setattr(
        "icml_env_checks.ensure_diamond_csv_via_public_mirror", lambda **_k: None
    )
    monkeypatch.setattr(
        "icml_env_checks.detect_gpqa_is_synthetic", lambda *_a, **_k: False
    )
    tip_pr = {
        "url": "https://github.com/kshivam4781/DarwinianSIA/pull/337",
        "number": 337,
        "title": "ICML tip",
        "is_draft": True,
        "head_ref": "cursor/icml-epistemic-results-f49c",
        "mergeable": "MERGEABLE",
        "merge_state_status": "CLEAN",
    }
    monkeypatch.setattr("icml_env_checks.resolve_icml_tip_pr", lambda **_k: tip_pr)
    monkeypatch.setattr(
        "icml_env_checks.resolve_icml_agents_bootstrap_pr", lambda **_k: None
    )
    status = collect_icml_secrets_status()
    assert status["diamond_ready"] is True
    assert status["diamond_csv_present"] is True
    assert status["fetch_diamond_ok"] is False  # NEBIUS still missing
    assert "NEBIUS" in status["human_next"][0]
    assert "HF_TOKEN" not in status["human_next"][0]
    assert not any(
        "Accept HuggingFace access" in line for line in status["human_next"]
    )
    assert "HF_TOKEN / HUGGINGFACE_HUB_TOKEN missing" not in status["blockers"]
    assert status["blockers"] == ["NEBIUS_API_KEY missing"]

    # Non-synthetic on disk without CSV also counts as diamond_ready.
    monkeypatch.setattr(
        "icml_env_checks.resolve_diamond_csv_path", lambda **_k: None
    )
    status2 = collect_icml_secrets_status()
    assert status2["diamond_csv_present"] is False
    assert status2["diamond_ready"] is True
    assert not any(
        "Accept HuggingFace access" in line for line in status2["human_next"]
    )
    assert status2["blockers"] == ["NEBIUS_API_KEY missing"]


def test_suggested_open_git_pr_body_secrets_first_generic() -> None:
    """Tick 393: tip PR body stays secrets-first; no frozen infra changelog."""
    from icml_env_checks import suggested_open_git_pr_body

    body = suggested_open_git_pr_body(
        local_tick=393, fetch_diamond_ok=False, tip_pr_number=337
    )
    assert "Tick 393" in body
    assert "PRIMARY" in body
    assert "NEBIUS_API_KEY" in body
    # Must NOT claim Tick 393 *is* the Tick 392 chicken-egg fix.
    assert "chicken-egg tip-apply without tip module" not in body
    # Tick 394: durable recover note must not freeze a single tip-apply Tick.
    assert "through Tick 392" not in body
    assert "ICML_PROGRESS.md" in body
    ready = suggested_open_git_pr_body(
        local_tick=393, fetch_diamond_ok=True, tip_pr_number=337
    )
    assert "Secrets OK" in ready or "secrets present" in ready.lower()
    assert "icml_cron_entry.sh" in ready


def test_detect_gpqa_is_synthetic_and_secrets_auto_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 394: secrets status auto-detects synthetic smoke without an explicit flag."""
    from icml_env_checks import detect_gpqa_is_synthetic, write_icml_secrets_status
    from prepare_gpqa_smoke_data import prepare_task_tree

    # Empty repo → None
    assert detect_gpqa_is_synthetic(tmp_path) is None

    task = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    prepare_task_tree(task, n=3)
    assert detect_gpqa_is_synthetic(tmp_path) is True

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    monkeypatch.setattr(
        "icml_env_checks.resolve_diamond_csv_path",
        lambda repo_root=None: None,
    )
    out = tmp_path / "docs" / "icml_secrets_status.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    status = write_icml_secrets_status(out, repo_root=tmp_path)
    assert status["gpqa_is_synthetic"] is True
    assert any("synthetic" in b.lower() for b in status["blockers"])


def test_cron_refreshes_secrets_after_preflight() -> None:
    """Tick 395: cron rewrites secrets after preflight (smoke may appear mid-run)."""
    root = Path(__file__).resolve().parents[1]
    cron = (root / "scripts" / "icml_cron_entry.sh").read_text(encoding="utf-8")
    assert "refresh_secrets_after_preflight" in cron
    assert "Tick 395" in cron
    # Blocked paths: preflight → refresh → human_next (not human_next first).
    assert "run_preflight\n    refresh_secrets_after_preflight\n    print_human_next" in cron
    env_checks = (root / "scripts" / "icml_env_checks.py").read_text(encoding="utf-8")
    assert "Tick 395" in env_checks
    assert "refresh_secrets_after_preflight" in env_checks
    assert "test_cron_refreshes_secrets_after_preflight" in env_checks


def test_suggested_open_git_pr_title_secrets_first_when_stale() -> None:
    """Tick 344–347: secrets-first title + body-file + tip_pr_title_stale + gh edit."""
    from icml_env_checks import (
        ICML_TIP_PR_BODY_RELPATH,
        _tip_pr_title_edit_commands,
        _tip_pr_title_edit_human_next,
        build_icml_open_git_pr_hint,
        parse_tick_from_pr_body,
        parse_tick_from_pr_title,
        suggested_open_git_pr_body,
        suggested_open_git_pr_title,
    )

    assert parse_tick_from_pr_title("ICML Tick 336: tip PR gh copy-paste") == 336
    assert parse_tick_from_pr_title("no tick here") is None
    assert parse_tick_from_pr_body("## Summary\n- Tick 336: frozen body") == 336
    assert parse_tick_from_pr_body("") is None
    blocked = suggested_open_git_pr_title(local_tick=347, fetch_diamond_ok=False)
    assert "347" in blocked
    assert "NEBIUS" in blocked or "secrets" in blocked.lower()
    ready = suggested_open_git_pr_title(local_tick=347, fetch_diamond_ok=True)
    assert "347" in ready
    assert "NEBIUS" not in ready
    body = suggested_open_git_pr_body(
        local_tick=347, fetch_diamond_ok=False, tip_pr_number=337
    )
    assert "PRIMARY blocker" in body
    assert "NEBIUS_API_KEY" in body
    assert ICML_TIP_PR_BODY_RELPATH in body or "body-file" in body
    assert "tip_pr_body_stale" in body or "347" in body
    # Tick 393: even older local_tick bodies must not claim chicken-egg as Tick N.
    assert "chicken-egg tip-apply without tip module" not in body
    pr = {
        "number": 337,
        "url": "https://github.com/kshivam4781/DarwinianSIA/pull/337",
        "title": "ICML Tick 336: tip PR gh copy-paste merge commands",
        "body": "## Summary\n- Tick 336: tip PR human_next / tip+secrets JSON\n",
        "head_ref": "cursor/icml-epistemic-results-f49c",
        "mergeable": "MERGEABLE",
        "merge_state_status": "CLEAN",
        "is_draft": True,
    }
    hint = build_icml_open_git_pr_hint(
        pr,
        local_tick=347,
        fetch_diamond_ok=False,
    )
    assert hint is not None
    assert hint["tip_pr_title_tick"] == 336
    assert hint["tip_pr_body_tick"] == 336
    assert hint["tip_pr_title_stale"] is True
    assert hint["tip_pr_body_stale"] is True
    assert hint["suggested_open_git_pr_title"] == blocked
    assert "NEBIUS" in hint["suggested_open_git_pr_title"] or "secrets" in hint[
        "suggested_open_git_pr_title"
    ].lower()
    # Tick 345–347: gh pr edit --title --body-file when MCP won't rewrite.
    cmds = hint.get("tip_pr_title_edit_commands") or []
    assert cmds, "expected tip_pr_title_edit_commands when title/body stale"
    assert "gh pr edit 337" in cmds[0]
    assert "--title" in cmds[0]
    assert "--body-file" in cmds[0]
    assert ICML_TIP_PR_BODY_RELPATH in cmds[0]
    assert "347" in cmds[0]
    assert hint.get("tip_pr_body_file") == ICML_TIP_PR_BODY_RELPATH
    assert _tip_pr_title_edit_commands(
        pr, blocked, body_file=ICML_TIP_PR_BODY_RELPATH, include_title=True
    ) == cmds
    line = _tip_pr_title_edit_human_next(
        pr,
        suggested_title=blocked,
        title_stale=True,
        body_file=ICML_TIP_PR_BODY_RELPATH,
        body_stale=True,
    )
    assert line is not None
    assert "gh pr edit 337" in line
    assert "body" in line.lower()
    assert "does **not** rewrite" in line or "does not rewrite" in line.lower()
    # Fresh title+body → no edit commands.
    fresh = build_icml_open_git_pr_hint(
        {
            "number": 337,
            "url": "https://github.com/kshivam4781/DarwinianSIA/pull/337",
            "title": blocked,
            "body": suggested_open_git_pr_body(
                local_tick=347, fetch_diamond_ok=False, tip_pr_number=337
            ),
            "head_ref": "cursor/icml-epistemic-results-f49c",
            "mergeable": "MERGEABLE",
            "merge_state_status": "CLEAN",
            "is_draft": True,
        },
        local_tick=347,
        fetch_diamond_ok=False,
    )
    assert fresh is not None
    assert fresh["tip_pr_title_stale"] is False
    assert fresh["tip_pr_body_stale"] is False
    assert fresh.get("tip_pr_title_edit_commands") == []
    assert fresh.get("tip_pr_body_file") is None
    assert (
        _tip_pr_title_edit_human_next(
            pr, suggested_title=blocked, title_stale=False, body_stale=False
        )
        is None
    )


def test_suggested_open_git_pr_title_nebius_only_when_ondisk_diamond(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tick 506: on-disk non-synthetic diamond → NEBIUS-only tip PR title/body.

    Tick 497–499 already treated CSV / mirror / on-disk as diamond_ready for
    secrets human_next, and Tick 502 kept on-disk trees on live fetch. Tip PR
    title/body helpers still required HF or a CSV path — after CSV cleanup with
    diamond remaining on disk they said NEBIUS+HF while blockers were NEBIUS-only.
    """
    from icml_env_checks import (
        icml_diamond_source_ready_for_nebius_only,
        suggested_open_git_pr_body,
        suggested_open_git_pr_title,
    )

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    monkeypatch.setattr(
        "icml_env_checks.resolve_diamond_csv_path",
        lambda repo_root=None: None,
    )
    monkeypatch.setattr(
        "icml_env_checks.icml_ondisk_nonsynthetic_gpqa",
        lambda repo_root=None: True,
    )
    assert icml_diamond_source_ready_for_nebius_only() is True
    title = suggested_open_git_pr_title(local_tick=506, fetch_diamond_ok=False)
    assert title == (
        "ICML Tick 506: add NEBIUS_API_KEY — live G2→G4 still blocked"
    )
    assert "NEBIUS+HF" not in title
    body = suggested_open_git_pr_body(
        local_tick=506, fetch_diamond_ok=False, tip_pr_number=337
    )
    assert "NEBIUS_API_KEY" in body
    assert "HF optional" in body or "on-disk" in body.lower()
    assert "NEBIUS + (HF_TOKEN" not in body

    monkeypatch.setattr(
        "icml_env_checks.icml_ondisk_nonsynthetic_gpqa",
        lambda repo_root=None: False,
    )
    assert icml_diamond_source_ready_for_nebius_only() is False
    cold = suggested_open_git_pr_title(local_tick=506, fetch_diamond_ok=False)
    assert "NEBIUS+HF" in cold



def test_tip_pr_body_stale_independent_of_title() -> None:
    """Tick 347: title-fresh + body-stale still emits --body-file paste."""
    from icml_env_checks import (
        ICML_TIP_PR_BODY_RELPATH,
        _tip_pr_title_edit_commands,
        _tip_pr_title_edit_human_next,
        build_icml_open_git_pr_hint,
        suggested_open_git_pr_title,
    )

    title = suggested_open_git_pr_title(local_tick=347, fetch_diamond_ok=False)
    pr = {
        "number": 337,
        "url": "https://github.com/kshivam4781/DarwinianSIA/pull/337",
        "title": title,  # title already refreshed to local tick
        "body": "## Summary\n- Tick 336: still frozen body\n",
        "head_ref": "cursor/icml-epistemic-results-f49c",
        "mergeable": "MERGEABLE",
        "merge_state_status": "CLEAN",
        "is_draft": True,
    }
    hint = build_icml_open_git_pr_hint(
        pr, local_tick=347, fetch_diamond_ok=False
    )
    assert hint is not None
    assert hint["tip_pr_title_stale"] is False
    assert hint["tip_pr_body_stale"] is True
    assert hint["tip_pr_body_tick"] == 336
    assert hint.get("tip_pr_body_file") == ICML_TIP_PR_BODY_RELPATH
    cmds = hint.get("tip_pr_title_edit_commands") or []
    assert cmds
    assert "--body-file" in cmds[0]
    assert ICML_TIP_PR_BODY_RELPATH in cmds[0]
    # Body-only: no --title (title already current).
    assert "--title" not in cmds[0]
    assert cmds == _tip_pr_title_edit_commands(
        pr,
        title,
        body_file=ICML_TIP_PR_BODY_RELPATH,
        include_title=False,
    )
    line = _tip_pr_title_edit_human_next(
        pr,
        suggested_title=title,
        title_stale=False,
        body_file=ICML_TIP_PR_BODY_RELPATH,
        body_stale=True,
    )
    assert line is not None
    assert "body" in line.lower()
    assert "title **and** body" not in line
    assert "gh pr edit 337" in line


def test_open_git_pr_pass_description_when_body_stale() -> None:
    """Tick 348: tip_pr_body_stale → open_git_pr_pass_description + description file."""
    from icml_env_checks import (
        ICML_TIP_PR_BODY_RELPATH,
        build_icml_open_git_pr_hint,
        suggested_open_git_pr_title,
    )

    title = suggested_open_git_pr_title(local_tick=348, fetch_diamond_ok=False)
    stale_body = {
        "number": 337,
        "url": "https://github.com/kshivam4781/DarwinianSIA/pull/337",
        "title": "ICML Tick 336: tip PR gh copy-paste merge commands",
        "body": "## Summary\n- Tick 336: frozen body\n",
        "head_ref": "cursor/icml-epistemic-results-f49c",
        "mergeable": "MERGEABLE",
        "merge_state_status": "CLEAN",
        "is_draft": True,
    }
    hint = build_icml_open_git_pr_hint(
        stale_body, local_tick=348, fetch_diamond_ok=False
    )
    assert hint is not None
    assert hint["tip_pr_body_stale"] is True
    assert hint["open_git_pr_pass_description"] is True
    assert hint["open_git_pr_description_file"] == ICML_TIP_PR_BODY_RELPATH
    assert "description=" in hint["warning"]
    assert ICML_TIP_PR_BODY_RELPATH in hint["warning"]
    assert "Tick 348" in hint["tick_note"]
    # Fresh body → do not require description= pass flag.
    fresh = build_icml_open_git_pr_hint(
        {
            **stale_body,
            "title": title,
            "body": (
                f"## Summary\n- Tick 348: secrets-first body\n"
                f"- PRIMARY blocker: NEBIUS\n"
            ),
        },
        local_tick=348,
        fetch_diamond_ok=False,
    )
    assert fresh is not None
    assert fresh["tip_pr_body_stale"] is False
    assert fresh["open_git_pr_pass_description"] is False
    assert fresh.get("open_git_pr_description_file") is None


def test_open_git_pr_description_inline_in_json(tmp_path) -> None:
    """Tick 349: write_icml_open_git_pr_hint keeps open_git_pr_description inline."""
    import json
    from pathlib import Path

    from icml_env_checks import (
        ICML_TIP_PR_BODY_RELPATH,
        write_icml_open_git_pr_hint,
    )

    stale = {
        "number": 337,
        "url": "https://github.com/kshivam4781/DarwinianSIA/pull/337",
        "title": "ICML Tick 336: tip PR gh copy-paste merge commands",
        "body": "## Summary\n- Tick 336: frozen body\n",
        "head_ref": "cursor/icml-epistemic-results-f49c",
        "mergeable": "MERGEABLE",
        "merge_state_status": "CLEAN",
        "is_draft": True,
    }
    docs = tmp_path / "docs"
    docs.mkdir()
    # write_icml_open_git_pr_hint uses repo_root for body path relative to root
    out = docs / "icml_open_git_pr.json"
    written = write_icml_open_git_pr_hint(
        path=out,
        pr=stale,
        repo_root=tmp_path,
        local_tick=349,
        fetch_diamond_ok=False,
    )
    assert written is not None
    assert written["tip_pr_body_stale"] is True
    assert written["open_git_pr_pass_description"] is True
    desc = written.get("open_git_pr_description")
    assert isinstance(desc, str) and "Tick 349" in desc
    assert "PRIMARY blocker" in desc or "NEBIUS" in desc
    # Internal duplicate key must not appear in persisted JSON.
    assert "suggested_open_git_pr_body" not in written
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk.get("open_git_pr_description") == desc
    assert "suggested_open_git_pr_body" not in on_disk
    body_md = tmp_path / ICML_TIP_PR_BODY_RELPATH
    assert body_md.is_file()
    assert body_md.read_text(encoding="utf-8") == desc
    # Fresh GitHub body → no inline description required.
    fresh_written = write_icml_open_git_pr_hint(
        path=out,
        pr={
            **stale,
            "title": "ICML Tick 349: add NEBIUS+HF secrets — live G2→G4 still blocked",
            "body": "## Summary\n- Tick 349: secrets-first body\n",
        },
        repo_root=tmp_path,
        local_tick=349,
        fetch_diamond_ok=False,
    )
    assert fresh_written is not None
    assert fresh_written["tip_pr_body_stale"] is False
    assert fresh_written.get("open_git_pr_description") is None
    assert fresh_written["open_git_pr_pass_description"] is False


def test_prefer_tip_pr_commit_branch_unknown_mergeable() -> None:
    """Tick 351: UNKNOWN/null/empty mergeable still returns tip head_ref."""
    from icml_env_checks import prefer_tip_pr_commit_branch

    head = "cursor/icml-epistemic-results-f49c"
    assert prefer_tip_pr_commit_branch(
        {"head_ref": head, "mergeable": "UNKNOWN", "merge_state_status": "UNSTABLE"}
    ) == head
    assert prefer_tip_pr_commit_branch(
        {"head_ref": head, "mergeable": None, "merge_state_status": None}
    ) == head
    assert prefer_tip_pr_commit_branch(
        {"head_ref": head, "mergeable": "", "merge_state_status": ""}
    ) == head
    assert prefer_tip_pr_commit_branch(
        {
            "head_ref": head,
            "mergeable": "MERGEABLE",
            "merge_state_status": "CLEAN",
        }
    ) == head
    assert prefer_tip_pr_commit_branch(
        {
            "head_ref": head,
            "mergeable": "CONFLICTING",
            "merge_state_status": "DIRTY",
        }
    ) is None


def test_detect_cloud_boot_branch_env_and_mismatch(monkeypatch, tmp_path) -> None:
    """Tick 352–354: ICML_CLOUD_BOOT_BRANCH env + call JSON boot fields."""
    import json

    from icml_env_checks import (
        ICML_CLOUD_BOOT_BRANCH_RELPATH,
        ICML_OPEN_GIT_PR_CALL_RELPATH,
        detect_cloud_boot_branch,
        write_icml_open_git_pr_hint,
    )

    tip = "cursor/icml-epistemic-results-f49c"
    boot = "cursor/icml-epistemic-results-6a00"
    monkeypatch.setenv("ICML_CLOUD_BOOT_BRANCH", boot)
    assert detect_cloud_boot_branch(tip_commit_branch=tip, repo_root=tmp_path) == boot
    # Tick 354: non-tip env also persists ephemeral boot file.
    assert (tmp_path / ICML_CLOUD_BOOT_BRANCH_RELPATH).read_text(encoding="utf-8").strip() == boot
    monkeypatch.delenv("ICML_CLOUD_BOOT_BRANCH", raising=False)

    (tmp_path / "docs").mkdir(exist_ok=True)
    out = tmp_path / "docs" / "icml_open_git_pr.json"
    monkeypatch.setenv("ICML_CLOUD_BOOT_BRANCH", boot)
    written = write_icml_open_git_pr_hint(
        path=out,
        pr={
            "number": 337,
            "url": "https://github.com/kshivam4781/DarwinianSIA/pull/337",
            "title": "ICML Tick 336: tip PR gh copy-paste merge commands",
            "body": "## Summary\n- Tick 336: frozen body\n",
            "head_ref": tip,
            "mergeable": "MERGEABLE",
            "merge_state_status": "CLEAN",
            "is_draft": True,
        },
        repo_root=tmp_path,
        local_tick=354,
        fetch_diamond_ok=False,
    )
    assert written is not None
    assert written.get("cloud_boot_branch") == boot
    assert written.get("omit_branch_opens_pr_on") == boot
    call = json.loads((tmp_path / ICML_OPEN_GIT_PR_CALL_RELPATH).read_text(encoding="utf-8"))
    assert call["branch"] == tip
    assert call["cloud_boot_branch"] == boot
    assert call["omit_branch_opens_pr_on"] == boot
    assert boot in call["note"]
    assert "correct working branch" in call["note"]
    assert "Tick 354" in call["note"]
    assert "Tick 355" in call["note"]
    assert "ICML_CLOUD_BOOT_BRANCH" in call["note"]
    monkeypatch.delenv("ICML_CLOUD_BOOT_BRANCH", raising=False)


def test_detect_cloud_boot_branch_ignores_env_eq_tip(monkeypatch, tmp_path) -> None:
    """Tick 354: env==tip is a false capture; prefer persisted boot / reflog."""
    from icml_env_checks import (
        ICML_CLOUD_BOOT_BRANCH_RELPATH,
        detect_cloud_boot_branch,
        persist_cloud_boot_branch,
    )

    tip = "cursor/icml-epistemic-results-f49c"
    boot = "cursor/icml-epistemic-results-6a00"
    (tmp_path / "docs").mkdir()
    # False capture: agent checked out tip before cron exported current as boot.
    monkeypatch.setenv("ICML_CLOUD_BOOT_BRANCH", tip)
    assert (
        detect_cloud_boot_branch(tip_commit_branch=tip, repo_root=tmp_path) is None
    )
    # Persisted true boot wins over false env==tip.
    persist_cloud_boot_branch(boot, tip_commit_branch=tip, repo_root=tmp_path)
    assert (
        detect_cloud_boot_branch(tip_commit_branch=tip, repo_root=tmp_path) == boot
    )
    assert (tmp_path / ICML_CLOUD_BOOT_BRANCH_RELPATH).read_text(encoding="utf-8").strip() == boot
    # persist refuses to overwrite with tip.
    assert persist_cloud_boot_branch(tip, tip_commit_branch=tip, repo_root=tmp_path) is None
    assert (
        detect_cloud_boot_branch(tip_commit_branch=tip, repo_root=tmp_path) == boot
    )
    monkeypatch.delenv("ICML_CLOUD_BOOT_BRANCH", raising=False)


def test_cron_entry_captures_boot_branch_before_tip_recover() -> None:
    """Tick 353–355: icml_cron_entry.sh exports ICML_CLOUD_BOOT_BRANCH before tip recover."""
    from pathlib import Path

    text = Path("scripts/icml_cron_entry.sh").read_text(encoding="utf-8")
    assert "Tick 353" in text
    assert "Tick 354" in text
    assert "Tick 355" in text
    assert "ICML_CLOUD_BOOT_BRANCH" in text
    assert "capture before tip recover" in text
    assert "icml_cloud_boot_branch.txt" in text
    assert "already on tip" in text
    # Tick 355: preserved-env path must not clobber boot file when env==tip.
    assert "equals tip (Tick 355 false capture)" in text
    assert "do NOT clobber" in text or "does not clobber" in text or "keep boot file" in text
    # Capture block must appear before tip recover section.
    idx_capture = text.index("ICML_CLOUD_BOOT_BRANCH")
    idx_recover = text.index("# --- Tip recover (chicken-egg)")
    assert idx_capture < idx_recover
    # Must preserve across re-exec (only set when unset).
    assert '[[ -z "${ICML_CLOUD_BOOT_BRANCH:-}" ]]' in text


def test_cron_entry_unsets_env_eq_tip_no_boot_clobber() -> None:
    """Tick 355: pre-set ICML_CLOUD_BOOT_BRANCH==tip must not overwrite boot file."""
    from pathlib import Path

    text = Path("scripts/icml_cron_entry.sh").read_text(encoding="utf-8")
    # Preserved-env branch must detect tip equality and unset rather than printf tip.
    assert "Tick 355" in text
    assert "equals tip (Tick 355 false capture)" in text
    assert "unset ICML_CLOUD_BOOT_BRANCH" in text
    # The false-capture branch must appear in the elif preserved-env path.
    idx_elif = text.index('elif [[ -n "${ICML_CLOUD_BOOT_BRANCH:-}" ]]')
    idx_355 = text.index("Tick 355 false capture", idx_elif)
    idx_recover = text.index("# --- Tip recover (chicken-egg)")
    assert idx_elif < idx_355 < idx_recover


def test_boot_file_gitignored_survives_ephemeral_discard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 356: boot file must survive discard_ephemeral_icml_dirt (gitignored)."""
    import subprocess

    from icml_env_checks import (
        ICML_CLOUD_BOOT_BRANCH_RELPATH,
        detect_cloud_boot_branch,
        persist_cloud_boot_branch,
        porcelain_dirty_paths,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    docs.mkdir()
    (docs / "gate2_report.md").write_text("clean\n", encoding="utf-8")
    (docs / "ICML_PROGRESS.md").write_text("## Tick 356\n", encoding="utf-8")
    (repo / ".gitignore").write_text(
        "docs/icml_cloud_boot_branch.txt\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    # Dirty an ephemeral report + write the gitignored boot file.
    (docs / "gate2_report.md").write_text("dirty\n", encoding="utf-8")
    boot = "cursor/icml-epistemic-results-5fe4"
    tip = "cursor/icml-epistemic-results-f49c"
    persist_cloud_boot_branch(boot, tip_commit_branch=tip, repo_root=repo)
    boot_path = repo / ICML_CLOUD_BOOT_BRANCH_RELPATH
    assert boot_path.is_file()
    assert boot_path.read_text(encoding="utf-8").strip() == boot
    # Boot file must NOT be in ephemeral set (or discard would unlink it).
    assert ICML_CLOUD_BOOT_BRANCH_RELPATH not in EPHEMERAL_ICML_RELPATHS
    assert is_ephemeral_icml_path(ICML_CLOUD_BOOT_BRANCH_RELPATH) is False
    # Gitignored → invisible to porcelain; discard clears report only.
    dirty = porcelain_dirty_paths(repo)
    assert ICML_CLOUD_BOOT_BRANCH_RELPATH not in dirty
    assert "docs/gate2_report.md" in dirty
    ok, detail = discard_ephemeral_icml_dirt(repo)
    assert ok, detail
    assert boot_path.is_file(), "Tick 356: boot file must survive ephemeral discard"
    assert boot_path.read_text(encoding="utf-8").strip() == boot
    monkeypatch.delenv("ICML_CLOUD_BOOT_BRANCH", raising=False)
    assert detect_cloud_boot_branch(tip_commit_branch=tip, repo_root=repo) == boot
    # Root .gitignore must list the boot file (tip poison / discard survival).
    root_gi = Path(".gitignore").read_text(encoding="utf-8")
    assert "docs/icml_cloud_boot_branch.txt" in root_gi
    assert "Tick 356" in root_gi


def test_call_json_gitignored_survives_ephemeral_discard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 359: call JSON must survive discard (gitignored; not ephemeral).

    Tip HEAD previously committed ``docs/icml_open_git_pr_call.json`` with a
    prior-tick ``cloud_boot_branch`` (e.g. …-48b0). ``discard_ephemeral`` then
    ``git restore``'d that stale boot onto fresh VMs after tip --apply.
    """
    import json
    import subprocess

    from icml_env_checks import (
        EPHEMERAL_ICML_RELPATHS,
        ICML_OPEN_GIT_PR_CALL_RELPATH,
        discard_ephemeral_icml_dirt,
        is_ephemeral_icml_path,
        porcelain_dirty_paths,
        write_icml_open_git_pr_hint,
    )

    tip = "cursor/icml-epistemic-results-f49c"
    fresh_boot = "cursor/icml-epistemic-results-1624"
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    docs.mkdir()
    (docs / "gate2_report.md").write_text("clean\n", encoding="utf-8")
    (docs / "ICML_PROGRESS.md").write_text("## Tick 359\n", encoding="utf-8")
    (repo / ".gitignore").write_text(
        "docs/icml_cloud_boot_branch.txt\n"
        "docs/icml_open_git_pr_call.json\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "docs", ".gitignore"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    # Dirty an ephemeral report + write fresh call JSON (as cron does).
    (docs / "gate2_report.md").write_text("dirty preflight\n", encoding="utf-8")
    monkeypatch.setenv("ICML_CLOUD_BOOT_BRANCH", fresh_boot)
    pr = {
        "number": 337,
        "url": "https://github.com/kshivam4781/DarwinianSIA/pull/337",
        "title": "ICML Tick 336: tip PR gh copy-paste merge commands",
        "body": "## Summary\n- Tick 336: frozen body\n",
        "head_ref": tip,
        "mergeable": "MERGEABLE",
        "merge_state_status": "CLEAN",
        "is_draft": True,
    }
    written = write_icml_open_git_pr_hint(
        path=docs / "icml_open_git_pr.json",
        pr=pr,
        repo_root=repo,
        local_tick=359,
        fetch_diamond_ok=False,
    )
    assert written is not None
    call_path = repo / ICML_OPEN_GIT_PR_CALL_RELPATH
    assert call_path.is_file()
    assert json.loads(call_path.read_text(encoding="utf-8"))["cloud_boot_branch"] == fresh_boot
    assert ICML_OPEN_GIT_PR_CALL_RELPATH not in EPHEMERAL_ICML_RELPATHS
    assert is_ephemeral_icml_path(ICML_OPEN_GIT_PR_CALL_RELPATH) is False
    dirty = porcelain_dirty_paths(repo)
    assert ICML_OPEN_GIT_PR_CALL_RELPATH not in dirty
    assert "docs/gate2_report.md" in dirty
    ok, detail = discard_ephemeral_icml_dirt(repo)
    assert ok, detail
    assert call_path.is_file(), "Tick 359: call JSON must survive ephemeral discard"
    assert (
        json.loads(call_path.read_text(encoding="utf-8"))["cloud_boot_branch"]
        == fresh_boot
    )
    # Root .gitignore + cron already_on refresh markers.
    root_gi = Path(".gitignore").read_text(encoding="utf-8")
    assert "docs/icml_open_git_pr_call.json" in root_gi
    assert "Tick 359" in root_gi
    cron = Path("scripts/icml_cron_entry.sh").read_text(encoding="utf-8")
    assert "Tick 359" in cron
    assert "refreshed_open_git_pr_call_already_on" in cron


def test_reject_short_boot_poison_and_checkout_persists(tmp_path, monkeypatch) -> None:
    """Tick 357/358: short boot names rejected; checkout persists + refreshes call JSON."""
    from icml_env_checks import (
        ICML_CLOUD_BOOT_BRANCH_RELPATH,
        _is_valid_cloud_boot_branch_name,
        detect_cloud_boot_branch,
        persist_cloud_boot_branch,
    )

    tip = "cursor/icml-epistemic-results-f49c"
    boot = "cursor/icml-epistemic-results-48b0"
    assert _is_valid_cloud_boot_branch_name(boot, tip_commit_branch=tip)
    assert not _is_valid_cloud_boot_branch_name("48b0", tip_commit_branch=tip)
    assert not _is_valid_cloud_boot_branch_name(tip, tip_commit_branch=tip)
    assert persist_cloud_boot_branch("48b0", tip_commit_branch=tip, repo_root=tmp_path) is None

    (tmp_path / "docs").mkdir()
    poison = tmp_path / ICML_CLOUD_BOOT_BRANCH_RELPATH
    poison.write_text("48b0\n", encoding="utf-8")
    # Poisoned short name must be unlinked; without reflog/env → None here.
    monkeypatch.delenv("ICML_CLOUD_BOOT_BRANCH", raising=False)
    assert detect_cloud_boot_branch(tip_commit_branch=tip, repo_root=tmp_path) is None
    assert not poison.is_file()

    # Checkout script must mention Tick 357 persist-before-tip + Tick 358 refresh.
    checkout = Path("scripts/icml_checkout_tip_pr_branch.sh").read_text(encoding="utf-8")
    assert "Tick 357" in checkout
    assert "persist_cloud_boot_branch" in checkout
    assert "persisted_cloud_boot_branch" in checkout
    assert "Tick 358" in checkout
    assert "refresh_open_git_pr_after_tip_checkout" in checkout
    assert "refreshed_open_git_pr_call" in checkout
    # Live tree: poisoned short name must not stick after detect.
    # Tick 358: do not hardcode a prior-tick boot (…-48b0); any valid cursor/*
    # ≠ tip heal is OK (this workspace may be …-05af).
    root = Path(".").resolve()
    live_poison = root / ICML_CLOUD_BOOT_BRANCH_RELPATH
    live_poison.parent.mkdir(parents=True, exist_ok=True)
    live_poison.write_text("48b0\n", encoding="utf-8")
    monkeypatch.delenv("ICML_CLOUD_BOOT_BRANCH", raising=False)
    healed = detect_cloud_boot_branch(tip_commit_branch=tip, repo_root=root)
    assert healed is None or (
        _is_valid_cloud_boot_branch_name(healed, tip_commit_branch=tip)
        and healed != tip
        and healed != "48b0"
    )
    if healed is not None:
        assert live_poison.read_text(encoding="utf-8").strip() == healed
    else:
        assert not live_poison.is_file() or live_poison.read_text(
            encoding="utf-8"
        ).strip() != "48b0"


def test_refresh_open_git_pr_after_tip_checkout_updates_boot(tmp_path, monkeypatch) -> None:
    """Tick 358: checkout refresh rewrites stale cloud_boot_branch in call JSON."""
    import json

    from icml_env_checks import (
        ICML_CLOUD_BOOT_BRANCH_RELPATH,
        ICML_OPEN_GIT_PR_CALL_RELPATH,
        persist_cloud_boot_branch,
        refresh_open_git_pr_after_tip_checkout,
        write_icml_open_git_pr_hint,
    )

    tip = "cursor/icml-epistemic-results-f49c"
    stale_boot = "cursor/icml-epistemic-results-48b0"
    fresh_boot = "cursor/icml-epistemic-results-05af"
    docs = tmp_path / "docs"
    docs.mkdir()
    # Prior-tick call JSON still has stale boot.
    stale_pr = {
        "number": 337,
        "url": "https://github.com/kshivam4781/DarwinianSIA/pull/337",
        "title": "ICML Tick 336: tip PR gh copy-paste merge commands",
        "body": "## Summary\n- Tick 336: frozen body\n",
        "head_ref": tip,
        "mergeable": "MERGEABLE",
        "merge_state_status": "CLEAN",
        "is_draft": True,
    }
    monkeypatch.setenv("ICML_CLOUD_BOOT_BRANCH", stale_boot)
    written = write_icml_open_git_pr_hint(
        path=docs / "icml_open_git_pr.json",
        pr=stale_pr,
        repo_root=tmp_path,
        local_tick=357,
        fetch_diamond_ok=False,
    )
    assert written is not None
    call_path = tmp_path / ICML_OPEN_GIT_PR_CALL_RELPATH
    assert json.loads(call_path.read_text(encoding="utf-8"))["cloud_boot_branch"] == stale_boot

    # Tip status present (as after cron) + persist fresh boot (as checkout does).
    (docs / "icml_tip_status.json").write_text(
        json.dumps(
            {
                "tip_pr_number": 337,
                "tip_pr_url": stale_pr["url"],
                "tip_pr_title": stale_pr["title"],
                "tip_pr_body": stale_pr["body"],
                "tip_pr_head_ref": tip,
                "tip_pr_commit_branch": tip,
                "tip_pr_mergeable": "MERGEABLE",
                "tip_pr_merge_state_status": "CLEAN",
                "tip_pr_is_draft": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ICML_CLOUD_BOOT_BRANCH", fresh_boot)
    assert persist_cloud_boot_branch(fresh_boot, tip_commit_branch=tip, repo_root=tmp_path) == fresh_boot
    assert (tmp_path / ICML_CLOUD_BOOT_BRANCH_RELPATH).read_text(encoding="utf-8").strip() == fresh_boot

    hint = refresh_open_git_pr_after_tip_checkout(
        tip_commit_branch=tip, repo_root=tmp_path
    )
    assert hint is not None
    assert hint.get("cloud_boot_branch") == fresh_boot
    call = json.loads(call_path.read_text(encoding="utf-8"))
    assert call["branch"] == tip
    assert call["cloud_boot_branch"] == fresh_boot
    assert call["omit_branch_opens_pr_on"] == fresh_boot
    assert "Tick 358" in (call.get("note") or "")


def test_open_git_pr_call_json_atomic_mcp_args(tmp_path) -> None:
    """Tick 350: write_icml_open_git_pr_hint also writes atomic MCP call JSON."""
    import json

    from icml_env_checks import (
        ICML_OPEN_GIT_PR_CALL_RELPATH,
        write_icml_open_git_pr_hint,
    )

    stale = {
        "number": 337,
        "url": "https://github.com/kshivam4781/DarwinianSIA/pull/337",
        "title": "ICML Tick 336: tip PR gh copy-paste merge commands",
        "body": "## Summary\n- Tick 336: frozen body\n",
        "head_ref": "cursor/icml-epistemic-results-f49c",
        "mergeable": "MERGEABLE",
        "merge_state_status": "CLEAN",
        "is_draft": True,
    }
    (tmp_path / "docs").mkdir()
    out = tmp_path / "docs" / "icml_open_git_pr.json"
    written = write_icml_open_git_pr_hint(
        path=out,
        pr=stale,
        repo_root=tmp_path,
        local_tick=350,
        fetch_diamond_ok=False,
    )
    assert written is not None
    assert written.get("open_git_pr_call_file") == ICML_OPEN_GIT_PR_CALL_RELPATH
    call_path = tmp_path / ICML_OPEN_GIT_PR_CALL_RELPATH
    assert call_path.is_file()
    call = json.loads(call_path.read_text(encoding="utf-8"))
    assert call["branch"] == "cursor/icml-epistemic-results-f49c"
    assert "Tick 350" in call["title"]
    assert "NEBIUS" in call["title"]
    assert isinstance(call["description"], str) and "Tick 350" in call["description"]
    assert "PRIMARY blocker" in call["description"] or "NEBIUS" in call["description"]
    # Tick 352: call JSON records cloud_boot_branch / omit_branch_opens_pr_on.
    assert "cloud_boot_branch" in call
    assert "omit_branch_opens_pr_on" in call
    assert written.get("cloud_boot_branch") == call.get("cloud_boot_branch")
    assert written.get("omit_branch_opens_pr_on") == call.get("omit_branch_opens_pr_on")
    # Fresh metadata still gets a call JSON (MCP always needs all three args).
    fresh = write_icml_open_git_pr_hint(
        path=out,
        pr={
            **stale,
            "title": "ICML Tick 350: add NEBIUS+HF secrets — live G2→G4 still blocked",
            "body": "## Summary\n- Tick 350: secrets-first body\n",
        },
        repo_root=tmp_path,
        local_tick=350,
        fetch_diamond_ok=False,
    )
    assert fresh is not None
    assert fresh["tip_pr_title_stale"] is False
    assert fresh["tip_pr_body_stale"] is False
    call2 = json.loads(call_path.read_text(encoding="utf-8"))
    assert call2["branch"] == "cursor/icml-epistemic-results-f49c"
    assert call2["title"]
    assert call2["description"]
    # No tip PR → call file removed.
    assert (
        write_icml_open_git_pr_hint(
            path=out, pr=None, repo_root=tmp_path, local_tick=350
        )
        is None
    )
    assert not call_path.exists()
    assert not out.exists()


def test_refresh_pr_mergeability_unknown_via_gh_pr_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tick 505: UNKNOWN/null mergeable refreshes via gh pr view; MERGEABLE untouched."""
    from icml_env_checks import (
        _mergeability_needs_refresh,
        refresh_pr_mergeability,
    )

    assert _mergeability_needs_refresh(None)
    assert _mergeability_needs_refresh("")
    assert _mergeability_needs_refresh("UNKNOWN")
    assert not _mergeability_needs_refresh("MERGEABLE")
    assert not _mergeability_needs_refresh("CONFLICTING")

    calls: list[list[str]] = []

    def fake_run(cmd, **_k):
        calls.append(list(cmd))
        class R:
            returncode = 0
            stdout = json.dumps(
                {"mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"}
            )
            stderr = ""

        return R()

    monkeypatch.setattr("icml_env_checks.subprocess.run", fake_run)

    unknown = {
        "number": 337,
        "url": "https://github.com/kshivam4781/DarwinianSIA/pull/337",
        "mergeable": "UNKNOWN",
        "merge_state_status": "UNKNOWN",
    }
    out = refresh_pr_mergeability(unknown)
    assert out is unknown
    assert unknown["mergeable"] == "MERGEABLE"
    assert unknown["merge_state_status"] == "CLEAN"
    assert calls and "view" in calls[0] and "337" in calls[0]

    calls.clear()
    already = {
        "number": 337,
        "mergeable": "MERGEABLE",
        "merge_state_status": "CLEAN",
    }
    refresh_pr_mergeability(already)
    assert calls == []  # no gh call when already known

    null_pr = {"number": 338, "mergeable": None, "merge_state_status": None}
    refresh_pr_mergeability(null_pr)
    assert null_pr["mergeable"] == "MERGEABLE"
    assert null_pr["merge_state_status"] == "CLEAN"


def test_tip_pr_mergeability_note_and_merge_next() -> None:
    """Tick 335–337/351: MERGEABLE/CLEAN + gh copy-paste + anti-churn in human_next."""
    from icml_env_checks import (
        _merge_tip_to_main_human_next,
        _tip_pr_merge_commands,
        prefer_tip_pr_commit_branch,
        _tip_pr_mergeability_note,
    )

    assert _tip_pr_mergeability_note({}) == ""
    clean = _tip_pr_mergeability_note(
        {"mergeable": "MERGEABLE", "merge_state_status": "CLEAN"}
    )
    assert "MERGEABLE" in clean
    assert "undraft & merge now" in clean.lower()
    conflict = _tip_pr_mergeability_note(
        {"mergeable": "CONFLICTING", "merge_state_status": "DIRTY"}
    )
    assert "CONFLICTING" in conflict
    assert "rebase" in conflict.lower()
    msg = _merge_tip_to_main_human_next(
        {
            "url": "https://github.com/kshivam4781/DarwinianSIA/pull/335",
            "number": 335,
            "title": "ICML Tick 334",
            "is_draft": True,
            "head_ref": "cursor/icml-epistemic-results-4bb3",
            "mergeable": "MERGEABLE",
            "merge_state_status": "CLEAN",
        }
    )
    assert "#335" in msg
    assert "MERGEABLE" in msg
    assert "undraft" in msg.lower()
    assert "no conflicts" in msg.lower()
    assert "gh pr ready 335" in msg
    assert "gh pr merge 335" in msg
    assert "do NOT open a new tip PR" in msg
    assert "cursor/icml-epistemic-results-4bb3" in msg
    assert prefer_tip_pr_commit_branch(
        {
            "number": 335,
            "head_ref": "cursor/icml-epistemic-results-4bb3",
            "mergeable": "MERGEABLE",
            "merge_state_status": "CLEAN",
        }
    ) == "cursor/icml-epistemic-results-4bb3"
    assert prefer_tip_pr_commit_branch(
        {
            "number": 1,
            "head_ref": "cursor/icml-epistemic-results-x",
            "mergeable": "CONFLICTING",
            "merge_state_status": "DIRTY",
        }
    ) is None
    # Tick 351: UNKNOWN/null/empty mergeable still returns head (anti-churn).
    assert prefer_tip_pr_commit_branch(
        {
            "number": 337,
            "head_ref": "cursor/icml-epistemic-results-f49c",
            "mergeable": "UNKNOWN",
            "merge_state_status": "UNSTABLE",
        }
    ) == "cursor/icml-epistemic-results-f49c"
    assert prefer_tip_pr_commit_branch(
        {
            "number": 337,
            "head_ref": "cursor/icml-epistemic-results-f49c",
            "mergeable": None,
            "merge_state_status": None,
        }
    ) == "cursor/icml-epistemic-results-f49c"
    assert prefer_tip_pr_commit_branch(
        {
            "number": 337,
            "head_ref": "cursor/icml-epistemic-results-f49c",
            "mergeable": "",
            "merge_state_status": "",
        }
    ) == "cursor/icml-epistemic-results-f49c"
    assert _tip_pr_merge_commands(
        {
            "number": 335,
            "is_draft": True,
        }
    ) == [
        "gh pr ready 335 --repo kshivam4781/DarwinianSIA",
        "gh pr merge 335 --repo kshivam4781/DarwinianSIA --merge",
    ]
    # Non-draft MERGEABLE: ready step omitted.
    assert _tip_pr_merge_commands(
        {"number": 335, "is_draft": False}
    ) == ["gh pr merge 335 --repo kshivam4781/DarwinianSIA --merge"]
    # CONFLICTING: still expose commands but after-rebase wording.
    conflict_msg = _merge_tip_to_main_human_next(
        {
            "url": "https://github.com/kshivam4781/DarwinianSIA/pull/335",
            "number": 335,
            "title": "ICML Tick 334",
            "is_draft": True,
            "head_ref": "cursor/icml-epistemic-results-4bb3",
            "mergeable": "CONFLICTING",
            "merge_state_status": "DIRTY",
        }
    )
    assert "After rebase" in conflict_msg
    assert "gh pr merge 335" in conflict_msg
    assert "next cron" not in conflict_msg.lower()
    assert "Copy-paste:" not in conflict_msg

def test_branch_from_tip_ref_and_merge_next_without_pr() -> None:
    """Tick 330/331: tip-ref → branch; merge Next still works if gh unavailable."""
    from icml_env_checks import _branch_from_tip_ref, _merge_tip_to_main_human_next

    assert (
        _branch_from_tip_ref("refs/remotes/origin/cursor/icml-epistemic-results-45fd")
        == "cursor/icml-epistemic-results-45fd"
    )
    assert (
        _branch_from_tip_ref("origin/cursor/icml-epistemic-results-45fd")
        == "cursor/icml-epistemic-results-45fd"
    )
    # Tick 331: cloud cron bc-* tip refs also resolve to a branch name.
    assert (
        _branch_from_tip_ref(
            "refs/remotes/origin/cursor/bc-5113ca94-4af3-4c06-a183-b4a9a84052b6-ecba"
        )
        == "cursor/bc-5113ca94-4af3-4c06-a183-b4a9a84052b6-ecba"
    )
    # Explicit empty pr dict path: pass a non-draft resolved PR.
    msg = _merge_tip_to_main_human_next(
        {
            "url": "https://github.com/kshivam4781/DarwinianSIA/pull/999",
            "number": 999,
            "title": "ICML Tick 331",
            "is_draft": False,
            "head_ref": "cursor/bc-5113ca94-4af3-4c06-a183-b4a9a84052b6-ecba",
        }
    )
    assert "#999" in msg
    assert "pull/999" in msg
    assert "undraft" not in msg.lower()


def test_resolve_icml_tip_pr_no_stale_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tick 331: missing tip-head PR must not fall back to an unrelated ICML PR."""
    from icml_env_checks import resolve_icml_tip_pr
    import subprocess

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        # First call: gh pr list --head <branch> → empty
        class R:
            returncode = 0
            stdout = "[]"
            stderr = ""

        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "icml_env_checks.list_remote_icml_tip_candidates",
        lambda **_k: [
            {
                "ref": "refs/remotes/origin/cursor/bc-deadbeef-ecba",
                "tick": 331,
                "sha": "abc1234",
                "lineage_score": 6,
            }
        ],
    )
    assert resolve_icml_tip_pr(tip_ref="refs/remotes/origin/cursor/bc-deadbeef-ecba") is None
    # Must not issue a broad "ICML Tick in:title" search (stale-PR hazard).
    joined = [" ".join(c) for c in calls]
    assert any("pr" in j and "--head" in j for j in joined)
    assert not any("ICML Tick in:title" in j for j in joined)


def test_resolve_icml_tip_pr_same_sha_sibling_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tick 333: tip head without PR may reuse same-SHA sibling tip PR."""
    from icml_env_checks import resolve_icml_tip_pr
    import subprocess

    def fake_run(cmd, **kwargs):
        class R:
            returncode = 0
            stdout = "[]"
            stderr = ""

        # gh pr list --head <branch>
        if "pr" in cmd and "--head" in cmd:
            head = cmd[cmd.index("--head") + 1]
            if head == "cursor/icml-epistemic-results-cd84":
                R.stdout = "[]"
            elif head == "cursor/icml-epistemic-results-0f03":
                R.stdout = json.dumps(
                    [
                        {
                            "number": 333,
                            "url": "https://github.com/kshivam4781/DarwinianSIA/pull/333",
                            "title": "ICML Tick 332",
                            "isDraft": True,
                            "headRefName": "cursor/icml-epistemic-results-0f03",
                        }
                    ]
                )
            else:
                R.stdout = "[]"
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "icml_env_checks.list_remote_icml_tip_candidates",
        lambda **_k: [
            {
                "ref": "refs/remotes/origin/cursor/icml-epistemic-results-cd84",
                "tick": 332,
                "sha": "ed1e54d",
                "lineage_score": 6,
            },
            {
                "ref": "refs/remotes/origin/cursor/icml-epistemic-results-0f03",
                "tick": 332,
                "sha": "ed1e54d",
                "lineage_score": 6,
            },
        ],
    )
    pr = resolve_icml_tip_pr(
        tip_ref="refs/remotes/origin/cursor/icml-epistemic-results-cd84"
    )
    assert pr is not None
    assert pr["number"] == 333
    assert pr["head_ref"] == "cursor/icml-epistemic-results-0f03"
    assert pr["is_draft"] is True


def test_resolve_icml_tip_pr_same_sha_ignores_different_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tick 333: sibling with different SHA must not supply tip_pr_url."""
    from icml_env_checks import resolve_icml_tip_pr
    import subprocess

    def fake_run(cmd, **kwargs):
        class R:
            returncode = 0
            stdout = "[]"
            stderr = ""

        if "pr" in cmd and "--head" in cmd:
            head = cmd[cmd.index("--head") + 1]
            if head == "cursor/icml-epistemic-results-0f03":
                R.stdout = json.dumps(
                    [
                        {
                            "number": 333,
                            "url": "https://github.com/kshivam4781/DarwinianSIA/pull/333",
                            "title": "ICML Tick 332",
                            "isDraft": True,
                            "headRefName": "cursor/icml-epistemic-results-0f03",
                        }
                    ]
                )
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "icml_env_checks.list_remote_icml_tip_candidates",
        lambda **_k: [
            {
                "ref": "refs/remotes/origin/cursor/icml-epistemic-results-cd84",
                "tick": 333,
                "sha": "aaaaaaa",
                "lineage_score": 6,
            },
            {
                "ref": "refs/remotes/origin/cursor/icml-epistemic-results-0f03",
                "tick": 332,
                "sha": "ed1e54d",
                "lineage_score": 6,
            },
        ],
    )
    assert (
        resolve_icml_tip_pr(
            tip_ref="refs/remotes/origin/cursor/icml-epistemic-results-cd84"
        )
        is None
    )


def test_resolve_icml_tip_pr_unpushed_remote_uses_head_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tick 334: unpushed greenfield remote tip_ref still same-SHA via HEAD."""
    from icml_env_checks import resolve_icml_tip_pr
    import subprocess

    def fake_run(cmd, **kwargs):
        class R:
            returncode = 1
            stdout = ""
            stderr = ""

        if "pr" in cmd and "--head" in cmd:
            R.returncode = 0
            head = cmd[cmd.index("--head") + 1]
            if head == "cursor/icml-epistemic-results-cd84":
                R.stdout = json.dumps(
                    [
                        {
                            "number": 334,
                            "url": "https://github.com/kshivam4781/DarwinianSIA/pull/334",
                            "title": "ICML Tick 333",
                            "isDraft": True,
                            "headRefName": "cursor/icml-epistemic-results-cd84",
                        }
                    ]
                )
            else:
                R.stdout = "[]"
            return R()
        # tip_ref remote missing; HEAD / local branch has tip SHA
        if "rev-parse" in cmd:
            ref = cmd[-1]
            if ref.startswith("refs/remotes/origin/"):
                R.returncode = 1
                R.stdout = ""
            else:
                R.returncode = 0
                R.stdout = "dab2c77abcde\n"
            return R()
        return R()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "icml_env_checks.list_remote_icml_tip_candidates",
        lambda **_k: [
            {
                "ref": "refs/remotes/origin/cursor/icml-epistemic-results-cd84",
                "tick": 333,
                "sha": "dab2c77",
                "lineage_score": 6,
            },
        ],
    )
    pr = resolve_icml_tip_pr(
        tip_ref="refs/remotes/origin/cursor/icml-epistemic-results-4bb3"
    )
    assert pr is not None
    assert pr["number"] == 334
    assert pr["head_ref"] == "cursor/icml-epistemic-results-cd84"


def test_tip_ref_prefixes_include_cloud_bc_branches() -> None:
    """Tick 331: tip lineage must scan cursor/bc-* cloud cron boots."""
    from icml_env_checks import (
        _TIP_FETCH_REFSPECS,
        _TIP_FOR_EACH_REF_PATTERNS,
        _TIP_REF_PREFIXES,
    )

    assert any(p.endswith("cursor/bc-") for p in _TIP_REF_PREFIXES)
    assert any("cursor/bc-*" in s for s in _TIP_FETCH_REFSPECS)
    assert any(p.endswith("cursor/bc-*") for p in _TIP_FOR_EACH_REF_PATTERNS)
    # Shell pickers / recover / cron must mirror the Python patterns.
    for rel in (
        "scripts/icml_pick_remote_tip.sh",
        "scripts/icml_boot_recover.sh",
        "scripts/icml_cron_entry.sh",
    ):
        text = (REPO / rel).read_text(encoding="utf-8")
        assert "cursor/bc-*" in text, f"{rel} must scan cursor/bc-*"
        assert "Tick 331" in text or "bc-*" in text



def test_fetch_diamond_ok_requires_hf(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tick 273: anthropic+nebius alone must not mark cron --fetch-diamond live OK."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    monkeypatch.delenv("ICML_DIAMOND_CSV", raising=False)
    monkeypatch.delenv("SIA_DIAMOND_CSV", raising=False)
    # Ensure no accidental /tmp CSV from other tests.
    monkeypatch.setattr(
        "icml_env_checks.resolve_diamond_csv_path",
        lambda repo_root=None: None,
    )
    status = collect_icml_secrets_status()
    assert status["secrets_ok_for_paid_sia"] is True
    assert status["fetch_diamond_ok"] is False
    assert status["cron_live_ok"] is False
    assert any("HF_TOKEN" in b for b in status["blockers"])

    monkeypatch.setenv("HF_TOKEN", "hf-test")
    status2 = collect_icml_secrets_status()
    assert status2["fetch_diamond_ok"] is True
    assert status2["cron_live_ok"] is True
    assert status2["blockers"] == []


def test_autowire_diamond_csv_under_fetch_diamond(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 278: --fetch-diamond auto-wires local CSV; no fetch ⇒ no invent."""
    from icml_env_checks import autowire_diamond_csv

    csv_path = tmp_path / "gpqa_diamond.csv"
    csv_path.write_text(
        "Question,Correct Answer,Incorrect Answer 1,Incorrect Answer 2,"
        "Incorrect Answer 3\n" + ("Q?,A,B,C,D\n" * 3),
        encoding="utf-8",
    )
    monkeypatch.setenv("ICML_DIAMOND_CSV", str(csv_path))

    path, auto = autowire_diamond_csv(None, fetch_diamond=True)
    assert auto is True
    assert path == csv_path.resolve()

    # Explicit path wins; not auto.
    explicit = tmp_path / "explicit.csv"
    explicit.write_text(csv_path.read_text(encoding="utf-8"), encoding="utf-8")
    path2, auto2 = autowire_diamond_csv(explicit, fetch_diamond=True)
    assert auto2 is False
    assert path2 == explicit

    # Without --fetch-diamond, do not invent a CSV (avoid surprise materialize).
    path3, auto3 = autowire_diamond_csv(None, fetch_diamond=False)
    assert path3 is None and auto3 is False


def test_autowire_diamond_csv_public_mirror_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 497: --fetch-diamond downloads public mirror when no local CSV/HF."""
    from icml_env_checks import autowire_diamond_csv

    monkeypatch.delenv("ICML_DIAMOND_CSV", raising=False)
    monkeypatch.delenv("SIA_DIAMOND_CSV", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    # Hide any real /tmp CSV so ensure path runs.
    monkeypatch.setattr(
        "icml_env_checks.resolve_diamond_csv_path",
        lambda repo_root=None: None,
    )
    dest = tmp_path / "gpqa_diamond.csv"

    def _fake_ensure(repo_root=None, *, allow_network=None):
        dest.write_text(
            "Question,Correct Answer,Incorrect Answer 1,Incorrect Answer 2,"
            "Incorrect Answer 3\n" + ("Q?,A,B,C,D\n" * 3),
            encoding="utf-8",
        )
        return dest.resolve()

    monkeypatch.setattr(
        "icml_env_checks.ensure_diamond_csv_via_public_mirror", _fake_ensure
    )
    path, auto = autowire_diamond_csv(None, fetch_diamond=True, repo_root=tmp_path)
    assert auto is True
    assert path == dest.resolve()


def test_secrets_status_public_mirror_unblocks_hf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 497: NEBIUS + public-mirror CSV ⇒ fetch_diamond_ok without HF."""
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    monkeypatch.delenv("ICML_DIAMOND_CSV", raising=False)
    monkeypatch.setattr(
        "icml_env_checks.resolve_diamond_csv_path",
        lambda repo_root=None: None,
    )
    dest = tmp_path / "gpqa_diamond.csv"

    def _fake_ensure(repo_root=None, *, allow_network=None):
        dest.write_text(
            "Question,Correct Answer,Incorrect Answer 1,Incorrect Answer 2,"
            "Incorrect Answer 3\n" + ("Q?,A,B,C,D\n" * 3),
            encoding="utf-8",
        )
        return dest.resolve()

    monkeypatch.setattr(
        "icml_env_checks.ensure_diamond_csv_via_public_mirror", _fake_ensure
    )
    status = collect_icml_secrets_status()
    assert status["public_mirror_csv"] is True
    assert status["diamond_csv_present"] is True
    assert status["hf_token_present"] is False
    assert status["fetch_diamond_ok"] is True
    assert status["blockers"] == []


def test_fetch_diamond_ok_with_local_csv_skips_hf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 277: local diamond CSV + API keys ⇒ fetch_diamond_ok without HF."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    csv_path = tmp_path / "gpqa_diamond.csv"
    csv_path.write_text(
        "Question,Correct Answer,Incorrect Answer 1,Incorrect Answer 2,"
        "Incorrect Answer 3\n" + ("Q?,A,B,C,D\n" * 3),
        encoding="utf-8",
    )
    monkeypatch.setenv("ICML_DIAMOND_CSV", str(csv_path))
    status = collect_icml_secrets_status()
    assert status["diamond_csv_present"] is True
    assert status["diamond_csv_path"] == str(csv_path.resolve())
    assert status["hf_token_present"] is False
    assert status["fetch_diamond_ok"] is True
    assert status["cron_live_ok"] is True
    assert status["blockers"] == []
    # Existing local CSV ⇒ public_mirror_csv stays false.
    assert status.get("public_mirror_csv") is False

def test_load_icml_dotenv_fills_missing_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 277: gitignored .env supplies missing keys; never overwrites env."""
    from icml_env_checks import load_icml_dotenv

    env_file = tmp_path / ".env"
    env_file.write_text(
        "ANTHROPIC_API_KEY=sk-from-dotenv\n"
        "NEBIUS_API_KEY=nb-from-dotenv\n"
        "HF_TOKEN=hf-from-dotenv\n"
        "UNRELATED=ignore-me\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-already-set")
    loaded = load_icml_dotenv(env_file)
    assert "ANTHROPIC_API_KEY" in loaded
    assert "HF_TOKEN" in loaded
    assert "NEBIUS_API_KEY" not in loaded  # already set
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-from-dotenv"
    assert os.environ["NEBIUS_API_KEY"] == "nb-already-set"
    assert os.environ["HF_TOKEN"] == "hf-from-dotenv"
    assert "UNRELATED" not in os.environ or os.environ.get("UNRELATED") != "ignore-me"


def test_live_pipeline_next_steps_requires_fetch_diamond_ok() -> None:
    """Tick 274: Anthropic+Nebius alone must not claim cron live OK."""
    partial = live_pipeline_next_steps(
        secrets_ok=True, fetch_diamond_ok=False, main_has_icml_tip=True
    )
    assert "HF_TOKEN" in partial[0] or "gpqa_diamond.csv" in partial[0]
    assert "fetch_diamond_ok" in partial[0]
    assert "preflight-only" in partial[1]
    full = live_pipeline_next_steps(
        secrets_ok=True, fetch_diamond_ok=True, main_has_icml_tip=True
    )
    assert "fetch_diamond_ok" in full[0]
    assert "icml_cron_entry.sh" in full[1]


def test_live_pipeline_next_steps_nebius_first_when_diamond_ready() -> None:
    """Tick 501: pipeline ## Next is NEBIUS-only when diamond already ready."""
    ready = live_pipeline_next_steps(
        secrets_ok=False,
        fetch_diamond_ok=False,
        main_has_icml_tip=True,
        diamond_ready=True,
    )
    assert "NEBIUS_API_KEY" in ready[0]
    assert "HF_TOKEN" not in ready[0]
    assert "Accept HF" not in ready[0]
    assert "Diamond already ready" in ready[0]
    assert "icml_cron_entry.sh" in ready[1]

    not_ready = live_pipeline_next_steps(
        secrets_ok=False,
        fetch_diamond_ok=False,
        main_has_icml_tip=True,
        diamond_ready=False,
    )
    assert "NEBIUS_API_KEY" in not_ready[0]
    assert "HF_TOKEN" in not_ready[0] or "gpqa_diamond.csv" in not_ready[0]


def test_write_icml_secrets_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    monkeypatch.setattr(
        "icml_env_checks.resolve_diamond_csv_path",
        lambda repo_root=None: None,
    )
    out = tmp_path / "icml_secrets_status.json"
    status = write_icml_secrets_status(out, gpqa_is_synthetic=True)
    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["secrets"]["ANTHROPIC_API_KEY"] == "ABSENT"
    assert loaded["anthropic_key_present"] is False
    assert loaded["nebius_key_present"] is False
    assert loaded["hf_token_present"] is False
    assert loaded["gpqa_is_synthetic"] is True
    assert loaded["ready_for_live_pipeline"] is False
    assert status["portal_save_required_for_live"] is False
    # Tick 272: human_next prefers cron entry (not bare live_pipeline).
    assert any("icml_cron_entry.sh" in s for s in loaded["human_next"])


def test_ready_for_live_pipeline_requires_fetch_diamond_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 274: ready_for_live_pipeline tracks fetch_diamond_ok (not keys alone)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    monkeypatch.setattr(
        "icml_env_checks.resolve_diamond_csv_path",
        lambda repo_root=None: None,
    )
    out = tmp_path / "icml_secrets_status.json"
    status = write_icml_secrets_status(out, gpqa_is_synthetic=True)
    assert status["secrets_ok_for_paid_sia"] is True
    assert status["fetch_diamond_ok"] is False
    assert status["ready_for_live_pipeline"] is False

    monkeypatch.setenv("HF_TOKEN", "hf-test")
    status2 = write_icml_secrets_status(out, gpqa_is_synthetic=True)
    assert status2["fetch_diamond_ok"] is True
    # Synthetic OK as start state when HF can --fetch-diamond.
    assert status2["ready_for_live_pipeline"] is True


def test_live_pipeline_next_steps_secrets_first() -> None:
    blocked = live_pipeline_next_steps(secrets_ok=False, main_has_icml_tip=True)
    assert "NEBIUS_API_KEY" in blocked[0]
    assert "icml_cron_entry.sh" in blocked[1]
    assert "optional" in blocked[2].lower()
    # Legacy caller (no fetch_diamond_ok): secrets_ok still means "go".
    ready = live_pipeline_next_steps(secrets_ok=True, main_has_icml_tip=True)
    assert "Secrets present" in ready[0]
    assert "icml_cron_entry.sh" in ready[1]


def test_live_pipeline_next_steps_tip_before_secrets() -> None:
    """Tick 343: secrets lead when fetch/secrets blocked — tip recover is secondary.

    Historical name kept; pre-343 expected tip recover first. PRIMARY-first
    (Tick 343) puts NEBIUS/HF ahead of tip recover even when tip_ok is False.
    """
    steps = live_pipeline_next_steps(
        secrets_ok=False,
        tip_ok=False,
        tip_ref="origin/cursor/icml-epistemic-results-de52",
        main_has_icml_tip=True,
    )
    assert "NEBIUS_API_KEY" in steps[0]
    assert any("icml_cron_entry.sh" in s for s in steps)


def test_icml_boot_recover_script_exists_and_help() -> None:
    """Tick 270: pure-bash tip recover for main-only cron boots."""
    script = REPO / "scripts" / "icml_boot_recover.sh"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "Tick 270" in text
    assert "--apply" in text
    # Help exits 0 without needing remotes.
    import subprocess

    proc = subprocess.run(
        ["bash", str(script), "--help"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "icml_boot_recover" in (proc.stdout + proc.stderr)


def test_icml_cron_entry_script_exists_and_help() -> None:
    """Tick 271–278/329: recover→live/preflight; lineage tip pick; HF/CSV; full human_next."""
    script = REPO / "scripts" / "icml_cron_entry.sh"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "Tick 271" in text
    assert "icml_boot_recover" in text
    assert "run_icml_live_pipeline" in text
    assert "icml_pick_remote_tip" in text or "_pick_tip_ref" in text
    assert "committerdate-only" in text or "lineage" in text.lower()
    # Tick 273: auto-live requires fetch_diamond_ok (HF), not API keys alone.
    assert "fetch_diamond_ok" in text
    assert "CRON_LIVE_OK" in text
    # Tick 276: preflight also passes --fetch-diamond (match live intent).
    assert "--preflight-only" in text and "--fetch-diamond" in text
    # Tick 277: optional local CSV path into pipeline.
    assert "diamond-csv" in text or "DIAMOND_CSV" in text
    assert "Tick 277" in text
    # Tick 278: runners also autowire CSV (helper lives in env_checks; cron still passes).
    assert "autowire_diamond_csv" in (
        (REPO / "scripts" / "icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 329: full human_next on blocked paths (--preflight-only / auto / live-refuse).
    assert "print_human_next" in text
    assert "Tick 329" in text
    assert "Human next (dual unblock)" in text
    import subprocess

    proc = subprocess.run(
        ["bash", str(script), "--help"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "icml_cron_entry" in (proc.stdout + proc.stderr)


def test_icml_pick_remote_tip_script_picks_lineage() -> None:
    """Tick 272: tip picker skips refs lacking cron_entry; prefers highest Tick."""
    script = REPO / "scripts" / "icml_pick_remote_tip.sh"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "Tick 272" in text or "lineage-aware" in text
    assert "--require" in text
    import subprocess

    proc = subprocess.run(
        ["bash", str(script), "--help"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    # Against real remotes (fetched by prior ticks / this env): expect a tip.
    pick = subprocess.run(
        ["bash", str(script)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    if pick.returncode == 0:
        ref = pick.stdout.strip()
        # Tick 331: tip may be icml-epistemic-results-* OR cursor/bc-*.
        assert ("icml-epistemic" in ref) or ("/cursor/bc-" in ref) or ref.startswith(
            "refs/remotes/origin/cursor/bc-"
        )
        # Winning tip must contain cron_entry.
        probe = subprocess.run(
            ["git", "cat-file", "-e", f"{ref}:scripts/icml_cron_entry.sh"],
            cwd=str(REPO),
            check=False,
        )
        assert probe.returncode == 0


def test_parse_latest_icml_tick_prefers_top_heading() -> None:
    text = (
        "# ICML Thesis 1 — Progress log\n\n"
        "## 2026-08-29T20:14Z — Tick 268 (automation cron)\n\n"
        "### Status\n\n"
        "## 2026-08-29T18:09Z — Tick 267 (automation cron)\n"
    )
    assert parse_latest_icml_tick(text) == 268
    assert parse_latest_icml_tick("no ticks here") is None


def test_collect_icml_tip_status_missing_progress(tmp_path: Path) -> None:
    status = collect_icml_tip_status(repo_root=tmp_path, fetch=False)
    assert status["local_tick"] is None
    assert status["tip_ok_for_live"] is False
    assert any("ICML_PROGRESS" in b for b in status["blockers"])


def test_write_icml_tip_status_local_ok(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "ICML_PROGRESS.md").write_text(
        "## 2026-08-29T22:00Z — Tick 269 (automation cron)\n\nsecrets-first\n",
        encoding="utf-8",
    )
    # No remote candidates in empty git-less tmp → local-only OK path.
    out = docs / "icml_tip_status.json"
    status = write_icml_tip_status(out, fetch=False, repo_root=tmp_path)
    assert out.is_file()
    assert status["local_tick"] == 269
    assert status["tip_ok_for_live"] is True
    assert status["blockers"] == []


def test_is_ephemeral_icml_path() -> None:
    assert is_ephemeral_icml_path("docs/gate2_report.md") is True
    assert is_ephemeral_icml_path("./docs/icml_tip_status.json") is True
    assert is_ephemeral_icml_path("scripts/icml_env_checks.py") is False
    assert is_ephemeral_icml_path("docs/ICML_PROGRESS.md") is False


def test_ensure_budget_spent_ledger_initialized(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    path, created = ensure_budget_spent_ledger_initialized(tmp_path)
    assert created is True
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["spent_usd"] == 0.0
    assert data["stages_complete"] == []
    path2, created2 = ensure_budget_spent_ledger_initialized(tmp_path)
    assert created2 is False
    assert path2 == path
    # Must not wipe a non-zero ledger
    path.write_text(
        json.dumps({"spent_usd": 3.5, "stages_complete": ["G2"], "run_ids": [1300]}),
        encoding="utf-8",
    )
    _, created3 = ensure_budget_spent_ledger_initialized(tmp_path)
    assert created3 is False
    assert json.loads(path.read_text(encoding="utf-8"))["spent_usd"] == 3.5


def test_discard_ephemeral_icml_dirt_clears_reports_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 286: only ephemeral report dirt is discarded."""
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    docs.mkdir()
    (docs / "gate2_report.md").write_text("clean\n", encoding="utf-8")
    (docs / "ICML_PROGRESS.md").write_text("## Tick 286\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (docs / "gate2_report.md").write_text("dirty preflight\n", encoding="utf-8")
    ok, detail = discard_ephemeral_icml_dirt(repo)
    assert ok is True
    assert "gate2_report" in detail
    assert (docs / "gate2_report.md").read_text(encoding="utf-8") == "clean\n"

    (docs / "gate2_report.md").write_text("dirty again\n", encoding="utf-8")
    (docs / "ICML_PROGRESS.md").write_text("## Tick 286 EDITED\n", encoding="utf-8")
    ok2, detail2 = discard_ephemeral_icml_dirt(repo)
    assert ok2 is False
    assert "non-ephemeral" in detail2
    assert "dirty again" in (docs / "gate2_report.md").read_text(encoding="utf-8")


def test_discard_ephemeral_preserves_prior_live_via_stash(
    tmp_path: Path,
) -> None:
    """Tick 387: discard stashes prior_live_metrics; reinject after restore."""
    import json
    import subprocess

    from icml_env_checks import (
        ICML_PRIOR_LIVE_STASH_RELPATH,
        discard_ephemeral_icml_dirt,
        reinject_prior_live_stash,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    docs.mkdir()
    clean_g4 = {
        "mode": "preflight",
        "executed": False,
        "comparison": None,
        "paper_refreshed": False,
    }
    (docs / "gate4_report.json").write_text(
        json.dumps(clean_g4, indent=2) + "\n", encoding="utf-8"
    )
    (docs / "gate4_report.md").write_text("# gate4\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    dirty_g4 = {
        "mode": "preflight",
        "executed": False,
        "comparison": None,
        "paper_refreshed": False,
        "prior_live_metrics": {
            "comparison": {"d_wins_gens30": 4, "n_pairs": 5},
            "h5_by_d_run": {"run_1311": {"spearman_rho": 0.8}},
            "h2_by_d_run": {"run_1311": {"preferred_share": 0.7}},
            "executed": True,
            "paper_refreshed": True,
            "primary_pass": True,
            "h2_pass": True,
            "h5_pass": True,
            "ready_status": "READY",
            "figures_written": [],
        },
    }
    (docs / "gate4_report.json").write_text(
        json.dumps(dirty_g4, indent=2) + "\n", encoding="utf-8"
    )
    ok, detail = discard_ephemeral_icml_dirt(repo)
    assert ok is True
    assert "prior_live stashed" in detail
    assert "gate4_report.json" in detail
    # Restored committed preflight has no prior_live yet.
    restored = json.loads((docs / "gate4_report.json").read_text(encoding="utf-8"))
    assert restored.get("prior_live_metrics") is None
    stash_path = repo / ICML_PRIOR_LIVE_STASH_RELPATH
    assert stash_path.is_file()
    stash = json.loads(stash_path.read_text(encoding="utf-8"))
    assert stash["gates"]["docs/gate4_report.json"]["prior_live_metrics"][
        "comparison"
    ]["d_wins_gens30"] == 4

    # Simulate tip --apply wiping working tree to committed preflight again,
    # then reinject from durable stash.
    (docs / "gate4_report.json").write_text(
        json.dumps(clean_g4, indent=2) + "\n", encoding="utf-8"
    )
    ok2, detail2 = reinject_prior_live_stash(repo)
    assert ok2 is True
    assert "reinjected" in detail2
    after = json.loads((docs / "gate4_report.json").read_text(encoding="utf-8"))
    assert after["prior_live_metrics"]["ready_status"] == "READY"
    assert after["prior_live_metrics"]["comparison"]["d_wins_gens30"] == 4


def test_discard_ephemeral_ok_when_persist_writes_evidence(
    tmp_path: Path,
) -> None:
    """Tick 419: evidence written by persist must not fail discard (387 path).

    Tick 390 still blocks tip --apply on dirty evidence via
    ``tip_apply_blocking_dirty_paths``; discard itself must return ok so cron
    can stash prior_live and ask the operator to commit evidence.
    """
    import json
    import subprocess

    from icml_env_checks import (
        ICML_PRIOR_LIVE_EVIDENCE_RELPATH,
        discard_ephemeral_icml_dirt,
        tip_apply_blocking_dirty_paths,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    docs.mkdir()
    clean_g4 = {
        "mode": "preflight",
        "executed": False,
        "comparison": None,
        "paper_refreshed": False,
    }
    (docs / "gate4_report.json").write_text(
        json.dumps(clean_g4, indent=2) + "\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    dirty_g4 = {
        **clean_g4,
        "prior_live_metrics": {
            "comparison": {"d_wins_gens30": 3, "n_pairs": 5},
            "executed": True,
            "primary_pass": True,
            "h2_pass": True,
            "h5_pass": True,
            "ready_status": "IN_PROGRESS",
            "paper_refreshed": True,
            "h5_by_d_run": {},
            "h2_by_d_run": {},
            "figures_written": [],
        },
    }
    (docs / "gate4_report.json").write_text(
        json.dumps(dirty_g4, indent=2) + "\n", encoding="utf-8"
    )
    ok, detail = discard_ephemeral_icml_dirt(repo)
    assert ok is True, detail
    assert "prior_live stashed" in detail
    assert "Tick 390/419" in detail or "commit" in detail
    evidence = repo / ICML_PRIOR_LIVE_EVIDENCE_RELPATH
    assert evidence.is_file()
    blocking = tip_apply_blocking_dirty_paths(repo)
    assert any(
        p.replace("\\", "/").endswith("icml_prior_live_evidence.json")
        for p in blocking
    ), blocking


def test_commit_durable_ledgers_after_live_with_ephemeral_dirt(
    tmp_path: Path, monkeypatch
) -> None:
    """Tick 422/423: post-live dirt commits + pushes tip; ephemeral gate dirt OK."""
    import json
    import subprocess

    from icml_env_checks import (
        ICML_BUDGET_SPENT_RELPATH,
        ICML_PRIOR_LIVE_EVIDENCE_RELPATH,
        commit_durable_ledgers_after_live,
        is_ephemeral_icml_path,
        porcelain_dirty_paths,
    )
    import icml_env_checks as m

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"], cwd=repo, check=True, capture_output=True
    )
    tip_branch = "cursor/icml-epistemic-results-test423"
    monkeypatch.setattr(m, "prefer_tip_pr_commit_branch", lambda pr=None: tip_branch)
    subprocess.run(
        ["git", "checkout", "-b", tip_branch],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    docs.mkdir()
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 389, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "gate2_report.md").write_text("# pre\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "push", "-u", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Simulate post-live: durable spend + prior_live dirty; ephemeral gate dirty too.
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 3.5,
                "stages_complete": ["G2"],
                "run_ids": [1300],
                "detail": "Tick 423 post-live",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps(
            {
                "tick": 423,
                "gates": {
                    "docs/gate2_report.json": {
                        "prior_live_post": [{"name": "cabs_inline", "ok": True}]
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "gate2_report.md").write_text("# live post\n", encoding="utf-8")
    (docs / "gate2_report.json").write_text(
        json.dumps({"mode": "live", "executed": True}) + "\n", encoding="utf-8"
    )

    dirty_before = porcelain_dirty_paths(repo)
    assert ICML_BUDGET_SPENT_RELPATH in [
        p.replace("\\", "/") for p in dirty_before
    ]
    assert any(is_ephemeral_icml_path(p) for p in dirty_before)

    ok, detail = commit_durable_ledgers_after_live(repo)
    assert ok is True, detail
    assert "committed" in detail.lower()
    assert "423" in detail and "pushed" in detail.lower()

    committed_budget = json.loads(
        subprocess.check_output(
            ["git", "show", f"HEAD:{ICML_BUDGET_SPENT_RELPATH}"],
            cwd=repo,
            text=True,
        )
    )
    assert committed_budget["spent_usd"] == 3.5
    assert "G2" in committed_budget["stages_complete"]
    committed_ev = json.loads(
        subprocess.check_output(
            ["git", "show", f"HEAD:{ICML_PRIOR_LIVE_EVIDENCE_RELPATH}"],
            cwd=repo,
            text=True,
        )
    )
    assert "docs/gate2_report.json" in committed_ev["gates"]

    # Ephemeral gate dirt must remain (not part of durable commit).
    dirty_after = [p.replace("\\", "/") for p in porcelain_dirty_paths(repo)]
    assert "docs/gate2_report.md" in dirty_after or "docs/gate2_report.json" in dirty_after
    assert ICML_BUDGET_SPENT_RELPATH not in dirty_after
    assert ICML_PRIOR_LIVE_EVIDENCE_RELPATH not in dirty_after

    # Tick 423: remote tip must see the durable ledger spend (cross-VM).
    remote_budget = json.loads(
        subprocess.check_output(
            ["git", "show", f"refs/heads/{tip_branch}:{ICML_BUDGET_SPENT_RELPATH}"],
            cwd=bare,
            text=True,
        )
    )
    assert remote_budget["spent_usd"] == 3.5


def test_commit_durable_ledgers_after_live_surfaces_push_failure(
    tmp_path: Path,
) -> None:
    """Tick 423: commit without origin must not pretend cross-VM safety."""
    import json
    import subprocess

    from icml_env_checks import (
        commit_durable_ledgers_after_live,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "checkout", "-b", "cursor/icml-epistemic-results-nopush"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps({"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 389, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True
    )
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {"spent_usd": 1.0, "stages_complete": ["G2"], "run_ids": [1]},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ok, detail = commit_durable_ledgers_after_live(repo)
    assert ok is False, detail
    assert "committed" in detail.lower()
    assert "push" in detail.lower()


def test_commit_durable_ledgers_after_live_pushes_when_ahead_on_noop(
    tmp_path: Path, monkeypatch
) -> None:
    """Tick 424: commit-noop still pushes when tip HEAD is ahead of origin.

    Simulates Tick 423 mid-tick push failure: durable ledgers already committed
    locally (clean tree) but never reached origin — next call must not skip push.
    """
    import json
    import subprocess

    from icml_env_checks import (
        ICML_BUDGET_SPENT_RELPATH,
        commit_durable_ledgers_after_live,
        tip_commits_ahead_of_origin,
    )
    import icml_env_checks as m

    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    tip_branch = "cursor/icml-epistemic-results-ahead"
    monkeypatch.setattr(m, "prefer_tip_pr_commit_branch", lambda pr=None: tip_branch)
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "checkout", "-b", tip_branch],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {"spent_usd": 0.0, "stages_complete": [], "run_ids": [], "detail": "init"},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 424, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True
    )
    # Publish baseline to origin so ahead-count is meaningful.
    subprocess.run(
        ["git", "push", "-u", "origin", f"HEAD:{tip_branch}"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Local-only durable ledger commit (simulates Tick 423 push failure).
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 4.25,
                "stages_complete": ["G2", "G3"],
                "run_ids": [1300, 1301],
                "detail": "Tick 424 unpushed",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "--", ICML_BUDGET_SPENT_RELPATH],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "local durable only"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    assert tip_commits_ahead_of_origin(repo) == 1

    ok, detail = commit_durable_ledgers_after_live(repo)
    assert ok is True, detail
    assert "noop" in detail.lower() or "not dirty" in detail.lower()
    assert "424" in detail and "pushed" in detail.lower()
    assert tip_commits_ahead_of_origin(repo) == 0

    remote_budget = json.loads(
        subprocess.check_output(
            ["git", "show", f"refs/heads/{tip_branch}:{ICML_BUDGET_SPENT_RELPATH}"],
            cwd=bare,
            text=True,
        )
    )
    assert remote_budget["spent_usd"] == 4.25
    assert "G3" in remote_budget["stages_complete"]


def test_cron_entry_commits_durable_ledgers_after_live() -> None:
    """Tick 422/423/424/425: cron run_live + tip-recover must push durable ledgers."""
    text = (Path(__file__).resolve().parents[1] / "scripts" / "icml_cron_entry.sh").read_text(
        encoding="utf-8"
    )
    assert "commit_durable_ledgers_after_live" in text
    assert "durable_ledgers_after_live" in text
    # Must run after the live pipeline, not only at tip-recover start.
    live_idx = text.find("run_icml_live_pipeline.py --live")
    commit_idx = text.find("commit_durable_ledgers_after_live", live_idx)
    assert live_idx != -1
    assert commit_idx != -1
    assert commit_idx > live_idx
    # Tick 425: tip-recover path also commit+pushes (before live).
    tip_recover_idx = text.find("commit_durable_ledgers_on_tip_recover")
    assert tip_recover_idx != -1
    assert tip_recover_idx < live_idx


def test_tip_recover_paths_push_durable_ledgers() -> None:
    """Tick 425: tip-recover scripts must call commit_durable_ledgers_on_tip_recover."""
    root = Path(__file__).resolve().parents[1]
    cron = (root / "scripts" / "icml_cron_entry.sh").read_text(encoding="utf-8")
    boot = (root / "scripts" / "icml_boot_recover.sh").read_text(encoding="utf-8")
    recover = (root / "scripts" / "icml_recover_tip.py").read_text(encoding="utf-8")
    for name, text in (
        ("icml_cron_entry.sh", cron),
        ("icml_boot_recover.sh", boot),
        ("icml_recover_tip.py", recover),
    ):
        assert "commit_durable_ledgers_on_tip_recover" in text, name
        # Tip-recover must not call the commit-only helper alone.
        assert "commit_prior_live_evidence_if_dirty()" not in text, name
    from icml_env_checks import (
        commit_durable_ledgers_after_live,
        commit_durable_ledgers_on_tip_recover,
    )

    assert commit_durable_ledgers_on_tip_recover is commit_durable_ledgers_after_live


def test_commit_durable_ledgers_co_commits_paper_pack_companions(
    tmp_path: Path, monkeypatch) -> None:
    """Tick 426: post-G4 paper-pack dirt must not refuse durable commit+push.

    Pre-426: apply_paper_pack dirtied paper_artifacts / ICML_READY / Figs 1–2
    → commit_durable_ledgers_after_live refused (non-ephemeral besides durable)
    → spend + READY + Live Tables never reached origin after paid G4.
    """
    import json
    import subprocess

    from icml_env_checks import (
        ICML_BUDGET_SPENT_RELPATH,
        ICML_PRIOR_LIVE_EVIDENCE_RELPATH,
        commit_durable_ledgers_after_live,
        is_ephemeral_icml_path,
        porcelain_dirty_paths,
    )
    import icml_env_checks as m

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"], cwd=repo, check=True, capture_output=True
    )
    tip_branch = "cursor/icml-epistemic-results-test426"
    monkeypatch.setattr(m, "prefer_tip_pr_commit_branch", lambda pr=None: tip_branch)
    subprocess.run(
        ["git", "checkout", "-b", tip_branch],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    figs = docs / "figures"
    figs.mkdir(parents=True)
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 389, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "paper_artifacts.md").write_text("# offline stub\n", encoding="utf-8")
    (docs / "ICML_READY.md").write_text("**STATUS: IN_PROGRESS**\n", encoding="utf-8")
    (figs / "fig1_learning_curves.png").write_bytes(b"PNG1")
    (figs / "fig2_mechanism.png").write_bytes(b"PNG2")
    (docs / "gate4_report.md").write_text("# pre\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "push", "-u", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Simulate post-G4 live: durable spend + paper pack + ephemeral gate dirt.
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 18.0,
                "stages_complete": ["G2", "G3", "G4"],
                "run_ids": [1300, 1201, 1301, 1211, 1311],
                "detail": "Tick 426 post-G4",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps(
            {
                "tick": 426,
                "gates": {
                    "docs/gate4_report.json": {
                        "prior_live_metrics": {
                            "executed": True,
                            "primary_pass": True,
                            "paper_refreshed": True,
                        }
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "paper_artifacts.md").write_text(
        "# Live Table 1\n| Seed | Winner |\n| 1 | D |\n", encoding="utf-8"
    )
    (docs / "ICML_READY.md").write_text("**STATUS: READY**\n", encoding="utf-8")
    (figs / "fig1_learning_curves.png").write_bytes(b"PNG1-LIVE")
    (figs / "fig2_mechanism.png").write_bytes(b"PNG2-LIVE")
    (docs / "gate4_report.md").write_text("# live post\n", encoding="utf-8")

    dirty_before = [p.replace("\\", "/") for p in porcelain_dirty_paths(repo)]
    assert ICML_BUDGET_SPENT_RELPATH in dirty_before
    assert "docs/paper_artifacts.md" in dirty_before
    assert "docs/ICML_READY.md" in dirty_before
    assert any(is_ephemeral_icml_path(p) for p in dirty_before)

    ok, detail = commit_durable_ledgers_after_live(repo)
    assert ok is True, detail
    assert "committed" in detail.lower()
    assert "426" in detail or "companion" in detail.lower()
    assert "pushed" in detail.lower()

    committed_ready = subprocess.check_output(
        ["git", "show", "HEAD:docs/ICML_READY.md"],
        cwd=repo,
        text=True,
    )
    assert "STATUS: READY" in committed_ready
    committed_paper = subprocess.check_output(
        ["git", "show", "HEAD:docs/paper_artifacts.md"],
        cwd=repo,
        text=True,
    )
    assert "Live Table 1" in committed_paper
    committed_budget = json.loads(
        subprocess.check_output(
            ["git", "show", f"HEAD:{ICML_BUDGET_SPENT_RELPATH}"],
            cwd=repo,
            text=True,
        )
    )
    assert committed_budget["spent_usd"] == 18.0
    assert "G4" in committed_budget["stages_complete"]

    dirty_after = [p.replace("\\", "/") for p in porcelain_dirty_paths(repo)]
    assert "docs/gate4_report.md" in dirty_after
    assert ICML_BUDGET_SPENT_RELPATH not in dirty_after
    assert "docs/paper_artifacts.md" not in dirty_after
    assert "docs/ICML_READY.md" not in dirty_after

    remote_ready = subprocess.check_output(
        ["git", "show", f"refs/heads/{tip_branch}:docs/ICML_READY.md"],
        cwd=bare,
        text=True,
    )
    assert "STATUS: READY" in remote_ready
    remote_budget = json.loads(
        subprocess.check_output(
            ["git", "show", f"refs/heads/{tip_branch}:{ICML_BUDGET_SPENT_RELPATH}"],
            cwd=bare,
            text=True,
        )
    )
    assert remote_budget["spent_usd"] == 18.0


def test_commit_durable_ledgers_still_refuses_unrelated_code_dirt(
    tmp_path: Path,
) -> None:
    """Tick 426: paper-pack companions do not open the door to code dirt."""
    import json
    import subprocess

    from icml_env_checks import commit_durable_ledgers_after_live

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "checkout", "-b", "cursor/icml-epistemic-results-test426b"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps({"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (docs / "paper_artifacts.md").write_text("# paper\n", encoding="utf-8")
    (repo / "scripts").mkdir()
    (repo / "scripts" / "icml_env_checks.py").write_text("# stub\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True
    )

    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {"spent_usd": 1.0, "stages_complete": ["G2"], "run_ids": [1300]}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "paper_artifacts.md").write_text("# live paper\n", encoding="utf-8")
    (repo / "scripts" / "icml_env_checks.py").write_text("# edited\n", encoding="utf-8")

    ok, detail = commit_durable_ledgers_after_live(repo)
    assert ok is False
    assert "refused" in detail.lower()
    assert "icml_env_checks.py" in detail


def test_prepare_parks_paper_pack_companions_for_tip_apply(
    tmp_path: Path, monkeypatch) -> None:
    """Tick 427: dirty paper-pack companions must park across tip --apply.

    Pre-427: Tick 426 co-commit accepted companions on the post-live path, but
    prepare_prior_live_evidence_for_tip_apply still refused them as other
    non-ephemeral dirt → tip recover blocked after mid-tick apply_paper_pack
    crash (READY/Live Tables wiped on hard-reset).
    """
    import json
    import subprocess

    from icml_env_checks import (
        ICML_BUDGET_SPENT_RELPATH,
        ICML_PAPER_PACK_STASH_RELPATH,
        ICML_PRIOR_LIVE_EVIDENCE_RELPATH,
        commit_durable_ledgers_after_live,
        porcelain_dirty_paths,
        prepare_prior_live_evidence_for_tip_apply,
        reinject_paper_pack_stash,
        tip_apply_blocking_dirty_paths,
    )
    import icml_env_checks as m

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"], cwd=repo, check=True, capture_output=True
    )
    tip_branch = "cursor/icml-epistemic-results-test427"
    monkeypatch.setattr(m, "prefer_tip_pr_commit_branch", lambda pr=None: tip_branch)
    subprocess.run(
        ["git", "checkout", "-b", tip_branch],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    figs = docs / "figures"
    figs.mkdir(parents=True)
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 389, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "paper_artifacts.md").write_text("# offline stub\n", encoding="utf-8")
    (docs / "ICML_READY.md").write_text("**STATUS: IN_PROGRESS**\n", encoding="utf-8")
    (figs / "fig1_learning_curves.png").write_bytes(b"PNG1")
    (figs / "fig2_mechanism.png").write_bytes(b"PNG2")
    (docs / "gate4_report.md").write_text("# pre\n", encoding="utf-8")
    (repo / ".gitignore").write_text(
        "docs/icml_prior_live_stash.json\n"
        "docs/icml_budget_spent_stash.json\n"
        "docs/icml_paper_pack_stash.json\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "push", "-u", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Mid-tick crash simulation: post-G4 dirt without durable commit yet.
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 17.5,
                "stages_complete": ["G2", "G3", "G4"],
                "run_ids": [1300, 1201, 1301],
                "detail": "Tick 427 mid-tick",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps(
            {
                "tick": 427,
                "gates": {
                    "docs/gate4_report.json": {
                        "prior_live_metrics": {
                            "executed": True,
                            "primary_pass": True,
                            "paper_refreshed": True,
                        }
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "paper_artifacts.md").write_text(
        "# Live Table 1\n| Seed | Winner |\n| 1 | D |\n", encoding="utf-8"
    )
    (docs / "ICML_READY.md").write_text("**STATUS: READY**\n", encoding="utf-8")
    (figs / "fig1_learning_curves.png").write_bytes(b"PNG1-LIVE")
    (figs / "fig2_mechanism.png").write_bytes(b"PNG2-LIVE")
    (docs / "gate4_report.md").write_text("# live post\n", encoding="utf-8")

    dirty_before = [p.replace("\\", "/") for p in porcelain_dirty_paths(repo)]
    assert "docs/paper_artifacts.md" in dirty_before
    assert "docs/ICML_READY.md" in dirty_before
    assert ICML_BUDGET_SPENT_RELPATH in dirty_before

    ok_prep, prep_detail = prepare_prior_live_evidence_for_tip_apply(repo)
    assert ok_prep is True, prep_detail
    assert "427" in prep_detail or "paper-pack" in prep_detail.lower()
    assert (repo / ICML_PAPER_PACK_STASH_RELPATH).is_file()

    dirty_after_prep = [p.replace("\\", "/") for p in porcelain_dirty_paths(repo)]
    assert "docs/paper_artifacts.md" not in dirty_after_prep
    assert "docs/ICML_READY.md" not in dirty_after_prep
    assert ICML_BUDGET_SPENT_RELPATH not in dirty_after_prep
    assert ICML_PRIOR_LIVE_EVIDENCE_RELPATH not in dirty_after_prep
    # Ephemeral gate dirt may remain; must not block tip apply after prepare.
    blocking = tip_apply_blocking_dirty_paths(repo)
    assert not any(
        p.replace("\\", "/").endswith(x)
        for p in blocking
        for x in (
            "paper_artifacts.md",
            "ICML_READY.md",
            "icml_budget_spent.json",
            "icml_prior_live_evidence.json",
        )
    ), blocking

    # Hard-reset to tip HEAD (wipes uncommitted READY) then reinject stash.
    subprocess.run(
        ["git", "reset", "--hard", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    assert "STATUS: IN_PROGRESS" in (docs / "ICML_READY.md").read_text(encoding="utf-8")
    ok_pp, detail_pp = reinject_paper_pack_stash(repo)
    assert ok_pp is True, detail_pp
    assert "STATUS: READY" in (docs / "ICML_READY.md").read_text(encoding="utf-8")
    assert "Live Table 1" in (docs / "paper_artifacts.md").read_text(encoding="utf-8")
    assert (figs / "fig1_learning_curves.png").read_bytes() == b"PNG1-LIVE"

    # Reinject budget via durable path helper used by tip recover, then commit.
    from icml_env_checks import reinject_budget_spent_stash, reinject_prior_live_stash

    ok_b, _ = reinject_budget_spent_stash(repo)
    assert ok_b is True
    ok_pl, _ = reinject_prior_live_stash(repo)
    assert ok_pl is True

    ok, detail = commit_durable_ledgers_after_live(repo)
    assert ok is True, detail
    assert "pushed" in detail.lower()
    committed_ready = subprocess.check_output(
        ["git", "show", "HEAD:docs/ICML_READY.md"],
        cwd=repo,
        text=True,
    )
    assert "STATUS: READY" in committed_ready
    remote_ready = subprocess.check_output(
        ["git", "show", f"refs/heads/{tip_branch}:docs/ICML_READY.md"],
        cwd=bare,
        text=True,
    )
    assert "STATUS: READY" in remote_ready
    # Tick 428: stashes must be consumed after successful durable commit.
    assert not (repo / ICML_PAPER_PACK_STASH_RELPATH).is_file()
    assert "428" in detail or "consumed" in detail.lower()


def test_durable_commit_consumes_stashes_prevents_stale_reinject(
    tmp_path: Path, monkeypatch) -> None:
    """Tick 428: leftover stashes must not reinject stale READY over tip HEAD.

    Pre-428: after reinject+commit, paper-pack stash survived. A later tip
    ``--apply`` reinjected mid-tick READY over a newer demoted IN_PROGRESS tip.
    """
    import json
    import subprocess

    from icml_env_checks import (
        ICML_BUDGET_SPENT_RELPATH,
        ICML_BUDGET_SPENT_STASH_RELPATH,
        ICML_PAPER_PACK_STASH_RELPATH,
        ICML_PRIOR_LIVE_EVIDENCE_RELPATH,
        ICML_PRIOR_LIVE_STASH_RELPATH,
        commit_durable_ledgers_after_live,
        prepare_prior_live_evidence_for_tip_apply,
        reinject_budget_spent_stash,
        reinject_paper_pack_stash,
        reinject_prior_live_stash,
    )
    import icml_env_checks as m

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"], cwd=repo, check=True, capture_output=True
    )
    tip_branch = "cursor/icml-epistemic-results-test428"
    monkeypatch.setattr(m, "prefer_tip_pr_commit_branch", lambda pr=None: tip_branch)
    subprocess.run(
        ["git", "checkout", "-b", tip_branch],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    figs = docs / "figures"
    figs.mkdir(parents=True)
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 389, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "paper_artifacts.md").write_text("# offline stub\n", encoding="utf-8")
    (docs / "ICML_READY.md").write_text("**STATUS: IN_PROGRESS**\n", encoding="utf-8")
    (figs / "fig1_learning_curves.png").write_bytes(b"PNG1")
    (figs / "fig2_mechanism.png").write_bytes(b"PNG2")
    (repo / ".gitignore").write_text(
        "docs/icml_prior_live_stash.json\n"
        "docs/icml_budget_spent_stash.json\n"
        "docs/icml_paper_pack_stash.json\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "push", "-u", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Mid-tick READY + spend dirt → park → reinject → durable commit.
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 12.0,
                "stages_complete": ["G2", "G3", "G4"],
                "run_ids": [1211, 1311],
                "detail": "Tick 428 mid-tick",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps(
            {
                "tick": 428,
                "gates": {
                    "docs/gate4_report.json": {
                        "prior_live_metrics": {
                            "executed": True,
                            "primary_pass": True,
                            "paper_refreshed": True,
                        }
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "paper_artifacts.md").write_text("# Live Table 1\n", encoding="utf-8")
    (docs / "ICML_READY.md").write_text("**STATUS: READY**\n", encoding="utf-8")
    (figs / "fig1_learning_curves.png").write_bytes(b"PNG1-LIVE")
    (figs / "fig2_mechanism.png").write_bytes(b"PNG2-LIVE")

    ok_prep, prep_detail = prepare_prior_live_evidence_for_tip_apply(repo)
    assert ok_prep is True, prep_detail
    assert (repo / ICML_PAPER_PACK_STASH_RELPATH).is_file()
    assert (repo / ICML_BUDGET_SPENT_STASH_RELPATH).is_file()

    subprocess.run(
        ["git", "reset", "--hard", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    assert reinject_paper_pack_stash(repo)[0] is True
    assert reinject_budget_spent_stash(repo)[0] is True
    assert reinject_prior_live_stash(repo)[0] is True

    ok, detail = commit_durable_ledgers_after_live(repo)
    assert ok is True, detail
    assert "consumed" in detail.lower() or "428" in detail
    assert not (repo / ICML_PAPER_PACK_STASH_RELPATH).is_file()
    assert not (repo / ICML_BUDGET_SPENT_STASH_RELPATH).is_file()
    assert not (repo / ICML_PRIOR_LIVE_STASH_RELPATH).is_file()

    # Honest demotion on tip after durable commit (criteria revalidation fail).
    (docs / "ICML_READY.md").write_text("**STATUS: IN_PROGRESS**\n", encoding="utf-8")
    (docs / "paper_artifacts.md").write_text("# demoted offline stub\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "docs/ICML_READY.md", "docs/paper_artifacts.md"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "demote READY"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Later tip --apply reinject must be a noop (stashes consumed) — keep demotion.
    subprocess.run(
        ["git", "reset", "--hard", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    ok_pp, detail_pp = reinject_paper_pack_stash(repo)
    assert ok_pp is True, detail_pp
    assert "empty" in detail_pp.lower() or "noop" in detail_pp.lower()
    assert "STATUS: IN_PROGRESS" in (docs / "ICML_READY.md").read_text(encoding="utf-8")
    assert "demoted" in (docs / "paper_artifacts.md").read_text(encoding="utf-8")
    # Evidence still available via committed file (Tick 389 fallback).
    assert (repo / ICML_PRIOR_LIVE_EVIDENCE_RELPATH).is_file()
    assert (repo / ICML_BUDGET_SPENT_RELPATH).is_file()


def test_consume_keeps_non_redundant_stash_after_failed_reinject(
    tmp_path: Path, monkeypatch) -> None:
    """Tick 429: commit-noop must not wipe unique mid-tick paper-pack stash.

    Pre-429 Tick 428 consumed on tip-synced commit-noop even when reinject
    failed — mid-tick READY/Figs parked in stash were lost forever.
    """
    import json
    import subprocess

    from icml_env_checks import (
        ICML_PAPER_PACK_STASH_RELPATH,
        commit_durable_ledgers_after_live,
        prepare_prior_live_evidence_for_tip_apply,
        reinject_paper_pack_stash,
    )
    import icml_env_checks as m

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"], cwd=repo, check=True, capture_output=True
    )
    tip_branch = "cursor/icml-epistemic-results-test429"
    monkeypatch.setattr(m, "prefer_tip_pr_commit_branch", lambda pr=None: tip_branch)
    subprocess.run(
        ["git", "checkout", "-b", tip_branch],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    figs = docs / "figures"
    figs.mkdir(parents=True)
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 389, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "paper_artifacts.md").write_text("# offline stub\n", encoding="utf-8")
    (docs / "ICML_READY.md").write_text("**STATUS: IN_PROGRESS**\n", encoding="utf-8")
    (figs / "fig1_learning_curves.png").write_bytes(b"PNG1")
    (figs / "fig2_mechanism.png").write_bytes(b"PNG2")
    (repo / ".gitignore").write_text(
        "docs/icml_prior_live_stash.json\n"
        "docs/icml_budget_spent_stash.json\n"
        "docs/icml_paper_pack_stash.json\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "push", "-u", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Mid-tick READY → park → hard-reset (tip --apply).
    (docs / "ICML_READY.md").write_text("**STATUS: READY**\n", encoding="utf-8")
    (docs / "paper_artifacts.md").write_text("# Live Table 1\n", encoding="utf-8")
    (figs / "fig1_learning_curves.png").write_bytes(b"PNG1-LIVE")
    ok_prep, prep_detail = prepare_prior_live_evidence_for_tip_apply(repo)
    assert ok_prep is True, prep_detail
    stash_path = repo / ICML_PAPER_PACK_STASH_RELPATH
    assert stash_path.is_file()
    # Preserve unique mid-tick payload, then break reinject (empty files).
    good_stash = json.loads(stash_path.read_text(encoding="utf-8"))
    assert good_stash.get("files")
    subprocess.run(
        ["git", "reset", "--hard", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    assert "IN_PROGRESS" in (docs / "ICML_READY.md").read_text(encoding="utf-8")
    # Restore good payload then corrupt only the reinject path: write empty files
    # into a *copy* used by reinject fail — actually corrupt in place then restore
    # unique payload after proving reinject refuse, so commit-noop sees unique stash.
    stash_path.write_text(
        json.dumps({**good_stash, "files": {}}, indent=2) + "\n", encoding="utf-8"
    )
    ok_r, detail_r = reinject_paper_pack_stash(repo)
    assert ok_r is False, detail_r
    # Put the unique mid-tick stash back (simulates reinject failure that left
    # the original parked payload intact — e.g. write error mid-loop).
    stash_path.write_text(json.dumps(good_stash, indent=2) + "\n", encoding="utf-8")

    ok, detail = commit_durable_ledgers_after_live(repo)
    assert ok is True, detail
    assert stash_path.is_file(), f"Tick 429 must keep unique stash; detail={detail}"
    assert "429" in detail or "non-redundant" in detail.lower() or "kept" in detail.lower()
    # HEAD still demoted / offline — stash still has READY for retry.
    assert "IN_PROGRESS" in (docs / "ICML_READY.md").read_text(encoding="utf-8")
    kept = json.loads(stash_path.read_text(encoding="utf-8"))
    assert "READY" in kept["files"]["docs/ICML_READY.md"]["content"]




def test_consume_keeps_stash_when_wt_matches_but_head_differs(
    tmp_path: Path, monkeypatch) -> None:
    """Tick 430: reinject WT==stash must not wipe unique stash vs committed HEAD.

    Pre-430 redundancy compared stash to the working tree. After a successful
    reinject (WT matches stash) with commit-noop / staged-only (HEAD still
    demoted), consume wiped the unique mid-tick READY/Figs forever.
    """
    import json
    import subprocess

    from icml_env_checks import (
        ICML_PAPER_PACK_STASH_RELPATH,
        commit_durable_ledgers_after_live,
        consume_durable_stashes_after_commit,
        prepare_prior_live_evidence_for_tip_apply,
        reinject_paper_pack_stash,
    )
    import icml_env_checks as m

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"], cwd=repo, check=True, capture_output=True
    )
    tip_branch = "cursor/icml-epistemic-results-test430"
    monkeypatch.setattr(m, "prefer_tip_pr_commit_branch", lambda pr=None: tip_branch)
    subprocess.run(
        ["git", "checkout", "-b", tip_branch],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    figs = docs / "figures"
    figs.mkdir(parents=True)
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 389, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "paper_artifacts.md").write_text("# offline stub\n", encoding="utf-8")
    (docs / "ICML_READY.md").write_text("**STATUS: IN_PROGRESS**\n", encoding="utf-8")
    (figs / "fig1_learning_curves.png").write_bytes(b"PNG1")
    (figs / "fig2_mechanism.png").write_bytes(b"PNG2")
    (repo / ".gitignore").write_text(
        "docs/icml_prior_live_stash.json\n"
        "docs/icml_budget_spent_stash.json\n"
        "docs/icml_paper_pack_stash.json\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "push", "-u", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Mid-tick READY → park → hard-reset (tip --apply).
    (docs / "ICML_READY.md").write_text("**STATUS: READY**\n", encoding="utf-8")
    (docs / "paper_artifacts.md").write_text("# Live Table 1\n", encoding="utf-8")
    (figs / "fig1_learning_curves.png").write_bytes(b"PNG1-LIVE")
    ok_prep, prep_detail = prepare_prior_live_evidence_for_tip_apply(repo)
    assert ok_prep is True, prep_detail
    stash_path = repo / ICML_PAPER_PACK_STASH_RELPATH
    assert stash_path.is_file()
    subprocess.run(
        ["git", "reset", "--hard", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    assert "IN_PROGRESS" in (docs / "ICML_READY.md").read_text(encoding="utf-8")

    # Successful reinject: WT matches unique stash; committed HEAD still demoted.
    ok_r, detail_r = reinject_paper_pack_stash(repo)
    assert ok_r is True, detail_r
    assert "READY" in (docs / "ICML_READY.md").read_text(encoding="utf-8")
    assert stash_path.is_file()

    # Direct consume (pre-430 WT compare would wipe here).
    ok_c, detail_c = consume_durable_stashes_after_commit(repo)
    assert ok_c is True, detail_c
    assert stash_path.is_file(), f"Tick 430 must keep unique stash; detail={detail_c}"
    assert "430" in detail_c or "429" in detail_c or "kept" in detail_c.lower()

    # Integration: commit-noop while WT still matches stash.
    def _noop_commit(repo_root=None, *, commit_message=None):
        return True, "durable ledgers not dirty (Tick 422 commit noop)"

    orig = m.commit_prior_live_evidence_if_dirty
    m.commit_prior_live_evidence_if_dirty = _noop_commit
    try:
        ok, detail = commit_durable_ledgers_after_live(repo)
    finally:
        m.commit_prior_live_evidence_if_dirty = orig
    assert ok is True, detail
    assert stash_path.is_file(), f"Tick 430 commit-noop must keep stash; detail={detail}"
    kept = json.loads(stash_path.read_text(encoding="utf-8"))
    assert "READY" in kept["files"]["docs/ICML_READY.md"]["content"]
    head_ready = subprocess.run(
        ["git", "show", "HEAD:docs/ICML_READY.md"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "IN_PROGRESS" in head_ready


def test_resolve_push_branch_redirects_greenfield_boot_to_tip_pr(
    tmp_path: Path, monkeypatch
) -> None:
    """Tick 431: durable push must target tip PR head, not unpushed boot branch.

    Pre-431 ``resolve_push_branch_for_durable_ledgers`` returned any ``cursor/*``
    HEAD name. Greenfield cron boots never exist on origin, so post-live
    ``git push origin HEAD:refs/heads/<boot>`` parked spend/READY off the tip
    PR head — next tip ``--apply`` recovered an empty ledger.
    """
    import json
    import subprocess

    from icml_env_checks import (
        commit_durable_ledgers_after_live,
        resolve_push_branch_for_durable_ledgers,
        tip_commits_ahead_of_origin,
    )
    import icml_env_checks as m

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    tip_branch = "cursor/icml-epistemic-results-tip431"
    boot_branch = "cursor/icml-epistemic-results-boot431"

    tip_repo = tmp_path / "tip"
    tip_repo.mkdir()
    subprocess.run(["git", "init"], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", tip_branch],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    docs = tip_repo / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps({"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 389, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "tip init"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "-u", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )

    # Greenfield boot: same SHA as tip, branch name never on origin.
    boot = tmp_path / "boot"
    subprocess.run(
        ["git", "clone", str(bare), str(boot)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-B", tip_branch, f"origin/{tip_branch}"],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", boot_branch],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    # Ensure tip remote-tracking ref is present; boot ref must stay absent.
    subprocess.run(
        ["git", "fetch", "origin", f"+refs/heads/{tip_branch}:refs/remotes/origin/{tip_branch}"],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    assert m._origin_branch_exists(boot, tip_branch)
    assert not m._origin_branch_exists(boot, boot_branch)

    monkeypatch.setattr(m, "prefer_tip_pr_commit_branch", lambda pr=None: tip_branch)
    monkeypatch.delenv("ICML_CLOUD_BOOT_BRANCH", raising=False)

    assert resolve_push_branch_for_durable_ledgers(boot) == tip_branch

    # Dirty ledger on boot → commit + push must land on origin/<tip>, not boot.
    (boot / "docs" / "icml_budget_spent.json").write_text(
        json.dumps(
            {"spent_usd": 2.5, "stages_complete": ["G2"], "run_ids": [1300]},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    assert tip_commits_ahead_of_origin(boot) >= 0  # resolves against tip
    ok, detail = commit_durable_ledgers_after_live(boot)
    assert ok is True, detail
    assert "pushed" in detail.lower() or "Tick 423" in detail

    # Tip remote has the spend; boot ref still absent on origin.
    tip_spent = subprocess.run(
        ["git", "show", f"origin/{tip_branch}:docs/icml_budget_spent.json"],
        cwd=boot,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "2.5" in tip_spent
    assert not m._origin_branch_exists(boot, boot_branch)

    # Env-captured boot with origin/<boot> still redirects (anti-churn).
    subprocess.run(
        ["git", "push", "origin", f"HEAD:refs/heads/{boot_branch}"],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "fetch", "origin", f"+refs/heads/{boot_branch}:refs/remotes/origin/{boot_branch}"],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    monkeypatch.setenv("ICML_CLOUD_BOOT_BRANCH", boot_branch)
    assert resolve_push_branch_for_durable_ledgers(boot) == tip_branch


def test_resolve_push_branch_redirects_even_when_origin_boot_exists_without_capture(
    tmp_path: Path, monkeypatch
) -> None:
    """Tick 432: origin/<boot> alone must not keep durable push on boot.

    Pre-432 kept any ``cursor/*`` with an origin ref as an "alternate tip-like"
    branch when cloud-boot env/persisted capture was missing. After
    ``open_git_pr`` omitted ``branch=`` (MCP default → boot), a later live
    durable push re-parked spend/READY on ``origin/<boot>`` off tip PR head.
    """
    import json
    import subprocess

    from icml_env_checks import resolve_push_branch_for_durable_ledgers
    import icml_env_checks as m

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    tip_branch = "cursor/icml-epistemic-results-tip432"
    boot_branch = "cursor/icml-epistemic-results-boot432"

    tip_repo = tmp_path / "tip"
    tip_repo.mkdir()
    subprocess.run(["git", "init"], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", tip_branch],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    docs = tip_repo / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps({"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "tip init"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "-u", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )

    boot = tmp_path / "boot"
    subprocess.run(
        ["git", "clone", str(bare), str(boot)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-B", tip_branch, f"origin/{tip_branch}"],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", boot_branch],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    # Accidental boot push (open_git_pr omitted branch=).
    subprocess.run(
        ["git", "push", "origin", f"HEAD:refs/heads/{boot_branch}"],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "fetch", "origin", f"+refs/heads/{boot_branch}:refs/remotes/origin/{boot_branch}"],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    assert m._origin_branch_exists(boot, tip_branch)
    assert m._origin_branch_exists(boot, boot_branch)

    monkeypatch.setattr(m, "prefer_tip_pr_commit_branch", lambda pr=None: tip_branch)
    # No env / persisted capture — Pre-432 would have kept boot.
    monkeypatch.delenv("ICML_CLOUD_BOOT_BRANCH", raising=False)
    boot_file = boot / "docs" / "icml_cloud_boot_branch.txt"
    if boot_file.exists():
        boot_file.unlink()

    assert resolve_push_branch_for_durable_ledgers(boot) == tip_branch


def test_ensure_local_tip_branch_syncs_boot_commit_onto_tip_ref(
    tmp_path: Path, monkeypatch
) -> None:
    """Tick 433: durable commit on boot must advance local tip ref + checkout tip.

    Pre-433 pushed ``HEAD:refs/heads/<tip>`` but left local ``<tip>`` at the
    pre-commit tip SHA when HEAD was still the greenfield boot branch. A later
    ``git checkout <tip>`` dropped the unpushed spend commit; ahead from that
    old tip HEAD was 0 → Tick 428/429 consume wiped reinject stashes.
    """
    import json
    import subprocess

    from icml_env_checks import (
        commit_durable_ledgers_after_live,
        ensure_local_tip_branch_for_durable_ledgers,
        tip_commits_ahead_of_origin,
    )
    import icml_env_checks as m

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    tip_branch = "cursor/icml-epistemic-results-tip433"
    boot_branch = "cursor/icml-epistemic-results-boot433"

    tip_repo = tmp_path / "tip"
    tip_repo.mkdir()
    subprocess.run(["git", "init"], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", tip_branch],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    docs = tip_repo / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps({"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 433, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "tip init"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "-u", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )

    boot = tmp_path / "boot"
    subprocess.run(
        ["git", "clone", str(bare), str(boot)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-B", tip_branch, f"origin/{tip_branch}"],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    tip_sha_before = subprocess.run(
        ["git", "rev-parse", tip_branch],
        cwd=boot,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ["git", "checkout", "-b", boot_branch],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    monkeypatch.setattr(m, "prefer_tip_pr_commit_branch", lambda pr=None: tip_branch)
    monkeypatch.delenv("ICML_CLOUD_BOOT_BRANCH", raising=False)

    # Dirty spend while still on boot branch name.
    (boot / "docs" / "icml_budget_spent.json").write_text(
        json.dumps(
            {"spent_usd": 4.33, "stages_complete": ["G2"], "run_ids": [1300]},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ok, detail = commit_durable_ledgers_after_live(boot)
    assert ok is True, detail
    assert "synced local tip" in detail or "already on tip" in detail

    head_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=boot,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head_branch == tip_branch

    tip_sha_after = subprocess.run(
        ["git", "rev-parse", tip_branch],
        cwd=boot,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert tip_sha_after != tip_sha_before

    tip_spent = subprocess.run(
        ["git", "show", f"{tip_branch}:docs/icml_budget_spent.json"],
        cwd=boot,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "4.33" in tip_spent

    origin_spent = subprocess.run(
        ["git", "show", f"origin/{tip_branch}:docs/icml_budget_spent.json"],
        cwd=boot,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "4.33" in origin_spent
    assert tip_commits_ahead_of_origin(boot) == 0
    assert not m._origin_branch_exists(boot, boot_branch)

    # Ensure alone: boot name with tip-descendant HEAD → tip checkout.
    subprocess.run(
        ["git", "checkout", "-B", boot_branch],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    ok_e, detail_e = ensure_local_tip_branch_for_durable_ledgers(boot)
    assert ok_e is True, detail_e
    assert "synced local tip" in detail_e
    head2 = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=boot,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head2 == tip_branch


def test_ensure_local_tip_checkouts_tip_when_boot_behind(
    tmp_path: Path, monkeypatch
) -> None:
    """Tick 434: behind-tip boot must checkout tip (not commit-on-boot + NF push).

    Pre-434 skipped tip sync when HEAD was not a tip descendant, committed
    durable ledgers onto the greenfield boot SHA, then ``git push HEAD:tip``
    was non-fast-forward rejected — spend stayed only on an invisible boot ref.
    """
    import json
    import subprocess

    from icml_env_checks import (
        commit_durable_ledgers_after_live,
        tip_commits_ahead_of_origin,
    )
    import icml_env_checks as m

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    tip_branch = "cursor/icml-epistemic-results-tip434"
    boot_branch = "cursor/icml-epistemic-results-boot434"

    tip_repo = tmp_path / "tip"
    tip_repo.mkdir()
    subprocess.run(["git", "init"], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", tip_branch],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    docs = tip_repo / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps({"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 0, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "-u", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    # Tip advances ahead of the base SHA greenfield boots still sit on.
    (docs / "ICML_READY.md").write_text("STATUS: IN_PROGRESS\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "tip ahead"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD~1"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    tip_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    boot = tmp_path / "boot"
    subprocess.run(
        ["git", "clone", str(bare), str(boot)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-B", boot_branch, base_sha],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "branch", "-f", tip_branch, f"origin/{tip_branch}"],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=boot,
        check=True,
        capture_output=True,
    )
    monkeypatch.setattr(m, "prefer_tip_pr_commit_branch", lambda pr=None: tip_branch)
    monkeypatch.delenv("ICML_CLOUD_BOOT_BRANCH", raising=False)

    (boot / "docs" / "icml_budget_spent.json").write_text(
        json.dumps(
            {"spent_usd": 4.34, "stages_complete": ["G2"], "run_ids": [1300]},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ok, detail = commit_durable_ledgers_after_live(boot)
    assert ok is True, detail
    assert "checked out tip" in detail
    assert "4.34" in detail or "committed durable" in detail

    head_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=boot,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head_branch == tip_branch

    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=boot,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    # Durable commit is a child of tip tipish (not the behind-tip base).
    assert head_sha != base_sha
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", tip_sha, "HEAD"],
            cwd=boot,
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )

    origin_spent = subprocess.run(
        ["git", "show", f"origin/{tip_branch}:docs/icml_budget_spent.json"],
        cwd=boot,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "4.34" in origin_spent
    assert tip_commits_ahead_of_origin(boot) == 0
    # Tip READY companion from tip-ahead commit must still be present.
    ready = subprocess.run(
        ["git", "show", f"origin/{tip_branch}:docs/ICML_READY.md"],
        cwd=boot,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "IN_PROGRESS" in ready


def test_ensure_local_tip_ffs_when_already_on_tip_behind_origin(
    tmp_path: Path, monkeypatch
) -> None:
    """Tick 435: already-on-tip behind origin/tip must FF (preserve durable dirt).

    Pre-435 early-returned ``already on tip branch`` when HEAD name matched tip
    even if ``origin/<tip>`` had advanced (concurrent cron / stale tip SHA).
    Durable commit then landed on the stale tip base and ``git push`` tip was
    non-fast-forward rejected — spend stayed only local / invisible.
    """
    import json
    import subprocess

    from icml_env_checks import (
        commit_durable_ledgers_after_live,
        tip_commits_ahead_of_origin,
    )
    import icml_env_checks as m

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    tip_branch = "cursor/icml-epistemic-results-tip435"

    tip_repo = tmp_path / "tip"
    tip_repo.mkdir()
    subprocess.run(["git", "init"], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", tip_branch],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    docs = tip_repo / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps({"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 0, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "-u", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    # Tip advances ahead of the SHA the stale local tip still sits on.
    (docs / "ICML_READY.md").write_text("STATUS: IN_PROGRESS\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "tip ahead"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD~1"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    tip_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    stale = tmp_path / "stale"
    subprocess.run(
        ["git", "clone", str(bare), str(stale)],
        check=True,
        capture_output=True,
    )
    # Already on tip *name*, but reset to the behind-origin base SHA.
    subprocess.run(
        ["git", "checkout", "-B", tip_branch, base_sha],
        cwd=stale,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "fetch", "origin"],
        cwd=stale,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=stale,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=stale,
        check=True,
        capture_output=True,
    )
    monkeypatch.setattr(m, "prefer_tip_pr_commit_branch", lambda pr=None: tip_branch)
    monkeypatch.delenv("ICML_CLOUD_BOOT_BRANCH", raising=False)

    (stale / "docs" / "icml_budget_spent.json").write_text(
        json.dumps(
            {"spent_usd": 4.35, "stages_complete": ["G2"], "run_ids": [1300]},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ok, detail = commit_durable_ledgers_after_live(stale)
    assert ok is True, detail
    assert "Tick 435" in detail or "checked out tip" in detail
    assert "behind" in detail or "4.35" in detail or "committed durable" in detail

    head_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=stale,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head_branch == tip_branch

    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=stale,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head_sha != base_sha
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", tip_sha, "HEAD"],
            cwd=stale,
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )

    origin_spent = subprocess.run(
        ["git", "show", f"origin/{tip_branch}:docs/icml_budget_spent.json"],
        cwd=stale,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "4.35" in origin_spent
    assert tip_commits_ahead_of_origin(stale) == 0
    ready = subprocess.run(
        ["git", "show", f"origin/{tip_branch}:docs/ICML_READY.md"],
        cwd=stale,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "IN_PROGRESS" in ready


def test_ensure_local_tip_fetches_before_ff_when_origin_tracking_stale(
    tmp_path: Path, monkeypatch
) -> None:
    """Tick 436: stale origin/<tip> tracking must be fetched before Tick 435 FF.

    Pre-436 inspected the local remote-tracking ref only. After a long live
    gate (or durable commit without a fresh cron fetch), origin/<tip> can lag
    the real tip — Tick 435 skips FF, durable commit lands on a stale base,
    and tip push is non-fast-forward rejected.
    """
    import json
    import subprocess

    from icml_env_checks import (
        commit_durable_ledgers_after_live,
        tip_commits_ahead_of_origin,
    )
    import icml_env_checks as m

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    tip_branch = "cursor/icml-epistemic-results-tip436"

    tip_repo = tmp_path / "tip"
    tip_repo.mkdir()
    subprocess.run(["git", "init"], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", tip_branch],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    docs = tip_repo / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps({"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 0, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "-u", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )

    # Stale clone at base SHA (tracking matches HEAD). Bare HEAD may not
    # point at tip, so clone leaves an empty master — checkout origin/<tip>.
    stale = tmp_path / "stale"
    subprocess.run(
        ["git", "clone", str(bare), str(stale)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-B", tip_branch, f"origin/{tip_branch}"],
        cwd=stale,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=stale,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=stale,
        check=True,
        capture_output=True,
    )
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=stale,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    # Concurrent tip advance on bare — stale clone does NOT fetch yet.
    (docs / "ICML_READY.md").write_text("STATUS: IN_PROGRESS\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "tip ahead concurrent"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    tip_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    # Confirm tracking is still stale (= base) before durable commit.
    tracking_sha = subprocess.run(
        ["git", "rev-parse", f"origin/{tip_branch}"],
        cwd=stale,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert tracking_sha == base_sha
    assert tip_sha != base_sha

    monkeypatch.setattr(m, "prefer_tip_pr_commit_branch", lambda pr=None: tip_branch)
    monkeypatch.delenv("ICML_CLOUD_BOOT_BRANCH", raising=False)

    (stale / "docs" / "icml_budget_spent.json").write_text(
        json.dumps(
            {"spent_usd": 5.15, "stages_complete": ["G2"], "run_ids": [1300]},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ok, detail = commit_durable_ledgers_after_live(stale)
    assert ok is True, detail
    assert "Tick 436" in detail or "fetched origin" in detail
    assert "Tick 435" in detail or "checked out tip" in detail or "behind" in detail

    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=stale,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head_sha != base_sha
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", tip_sha, "HEAD"],
            cwd=stale,
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )

    origin_spent = subprocess.run(
        ["git", "show", f"origin/{tip_branch}:docs/icml_budget_spent.json"],
        cwd=stale,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "5.15" in origin_spent
    assert tip_commits_ahead_of_origin(stale) == 0
    ready = subprocess.run(
        ["git", "show", f"origin/{tip_branch}:docs/ICML_READY.md"],
        cwd=stale,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "IN_PROGRESS" in ready


def test_push_tip_rebases_after_nf_when_diverged_from_origin(
    tmp_path: Path, monkeypatch
) -> None:
    """Tick 437: NF tip push with unique local durable commit must rebase+retry.

    Pre-437 Tick 435/436 only FF when origin is a strict descendant of HEAD.
    When durable spend is already committed on a stale tip base and origin tip
    advanced concurrently, push is non-fast-forward rejected and spend stayed
    local-only. Tick 437 fetches, rebases onto origin/<tip>, retries once.
    """
    import json
    import subprocess

    from icml_env_checks import (
        commit_durable_ledgers_after_live,
        tip_commits_ahead_of_origin,
    )
    import icml_env_checks as m

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    tip_branch = "cursor/icml-epistemic-results-tip437"

    tip_repo = tmp_path / "tip"
    tip_repo.mkdir()
    subprocess.run(["git", "init"], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", tip_branch],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    docs = tip_repo / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps({"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 0, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "-u", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )

    stale = tmp_path / "stale"
    subprocess.run(
        ["git", "clone", str(bare), str(stale)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-B", tip_branch, f"origin/{tip_branch}"],
        cwd=stale,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=stale,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=stale,
        check=True,
        capture_output=True,
    )

    # Local durable spend commit first (unique on stale tip base).
    (stale / "docs" / "icml_budget_spent.json").write_text(
        json.dumps(
            {"spent_usd": 7.37, "stages_complete": ["G2", "G3"], "run_ids": [1300, 1201]},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "docs/icml_budget_spent.json"],
        cwd=stale,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "local durable spend"],
        cwd=stale,
        check=True,
        capture_output=True,
    )

    # Concurrent tip advance on bare — diverges from local durable commit.
    (docs / "ICML_READY.md").write_text("STATUS: IN_PROGRESS\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "tip ahead concurrent"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    tip_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    # Refresh stale tracking so push sees the concurrent tip (matches live:
    # Tick 436 fetch already ran before commit; race is between commit and push).
    subprocess.run(
        ["git", "fetch", "origin", f"+refs/heads/{tip_branch}:refs/remotes/origin/{tip_branch}"],
        cwd=stale,
        check=True,
        capture_output=True,
    )

    monkeypatch.setattr(m, "prefer_tip_pr_commit_branch", lambda pr=None: tip_branch)
    monkeypatch.delenv("ICML_CLOUD_BOOT_BRANCH", raising=False)

    # Commit-noop path: durable already committed; ahead>0 → Tick 424 push retry
    # which must Tick 437 rebase after NF.
    ok, detail = commit_durable_ledgers_after_live(stale)
    assert ok is True, detail
    assert "437" in detail or "rebased" in detail.lower() or "NF" in detail

    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=stale,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", tip_sha, "HEAD"],
            cwd=stale,
            check=False,
            capture_output=True,
        ).returncode
        == 0
    ), f"HEAD {head_sha} must contain concurrent tip {tip_sha}; detail={detail}"

    origin_spent = subprocess.run(
        ["git", "show", f"origin/{tip_branch}:docs/icml_budget_spent.json"],
        cwd=stale,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "7.37" in origin_spent
    ready = subprocess.run(
        ["git", "show", f"origin/{tip_branch}:docs/ICML_READY.md"],
        cwd=stale,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "IN_PROGRESS" in ready
    assert tip_commits_ahead_of_origin(stale) == 0


def test_merge_budget_spent_dict_unions_stages_and_max_spend() -> None:
    """Tick 438: concurrent budget ledgers keep max spend + union stages/ids."""
    from icml_env_checks import merge_budget_spent_dict

    merged = merge_budget_spent_dict(
        {
            "spent_usd": 2.1,
            "stages_complete": ["G2"],
            "run_ids": [1300],
            "updated_at": "2026-09-26T10:00:00Z",
            "detail": "g2 only",
        },
        {
            "spent_usd": 7.37,
            "stages_complete": ["G2", "G3"],
            "run_ids": [1300, 1201],
            "updated_at": "2026-09-26T12:00:00Z",
            "detail": "g2+g3",
        },
    )
    assert merged["spent_usd"] == 7.37
    assert merged["stages_complete"] == ["G2", "G3"]
    assert merged["run_ids"] == [1300, 1201]
    assert merged["updated_at"] == "2026-09-26T12:00:00Z"


def test_merge_prior_live_prefers_richer_onto_g4_over_thin_local() -> None:
    """Tick 439: thinner replayed local must not wipe onto executed G4 metrics.

    Pre-439 always preferred theirs (replayed local) when both sides set the
    same gate key — a partial/preflight local capture could drop onto's
    executed G4 ``prior_live_metrics`` during durable rebase conflict merge.
    """
    from icml_env_checks import merge_prior_live_evidence_dict

    rich_g4 = {
        "prior_live_metrics": {
            "comparison": {"d_wins_gens30": 4, "n_pairs": 5},
            "executed": True,
            "primary_pass": True,
            "h2_pass": True,
            "h5_pass": True,
            "paper_refreshed": True,
        }
    }
    thin_g4 = {
        "prior_live_metrics": {
            "comparison": {"n_pairs": 1},
            "executed": False,
            "primary_pass": False,
        }
    }
    # onto (ours) = rich G4; replayed local (theirs) = thin G4
    merged = merge_prior_live_evidence_dict(
        {
            "tick": 438,
            "updated_at": "2026-09-26T12:00:00Z",
            "gates": {
                "docs/gate4_report.json": rich_g4,
                "docs/gate3_report.json": {
                    "prior_live_metrics": {"executed": True, "comparison": {"n_pairs": 1}}
                },
            },
        },
        {
            "tick": 439,
            "updated_at": "2026-09-26T13:00:00Z",
            "gates": {
                "docs/gate4_report.json": thin_g4,
                "docs/gate2_report.json": {"prior_live_post": [{"name": "ok"}]},
            },
        },
    )
    assert merged["tick"] == 439
    g4 = merged["gates"]["docs/gate4_report.json"]["prior_live_metrics"]
    assert g4["executed"] is True
    assert g4["comparison"]["n_pairs"] == 5
    assert g4["primary_pass"] is True
    assert g4["paper_refreshed"] is True
    # Union preserves unique keys from both sides.
    assert "docs/gate3_report.json" in merged["gates"]
    assert "docs/gate2_report.json" in merged["gates"]

    # Symmetric: rich local beats thin onto.
    merged2 = merge_prior_live_evidence_dict(
        {"gates": {"docs/gate4_report.json": thin_g4}},
        {"gates": {"docs/gate4_report.json": rich_g4}},
    )
    g4b = merged2["gates"]["docs/gate4_report.json"]["prior_live_metrics"]
    assert g4b["executed"] is True
    assert g4b["comparison"]["n_pairs"] == 5


def test_merge_icml_ready_prefers_richer_live_checklist_over_long_thin() -> None:
    """Tick 441: length-padded thin IN_PROGRESS must not wipe live [x] criteria.

    Pre-441 ``merge_icml_ready_text`` chose the longer body when either side was
    IN_PROGRESS. A concurrent docs tick with a long note could overwrite onto's
    post-G4 checklist (PRIMARY / H2 / H5 / Tables checked) while demoting
    STATUS — paid READY evidence lost even though Tick 438 "merged".
    """
    from icml_env_checks import (
        _merge_durable_conflict_bytes,
        merge_icml_ready_text,
        prefer_richer_icml_ready,
    )

    rich_live = (
        "# ICML Thesis 1 — Ready checklist\n\n"
        "**STATUS: READY**\n\n"
        "## Criteria\n\n"
        "### 1. PRIMARY — Condition D beats B\n"
        "- [x] D beats B on ≥3/5 seeds for gens-to-threshold (25% or 30%), **or**\n"
        "- [x] D beats B on ≥3/5 seeds for cost-to-threshold (≥15% fewer tokens/calls), **or**\n"
        "- [x] Non-trivial mean final accuracy gap (not ~1pp noise)\n"
        "### 2. MECHANISM — H2 or case study\n"
        "- [x] Live API-run H2 DNA trait skew under contradiction bias\n"
        "### 3. VALIDITY — H5\n"
        "- [x] Spearman ρ (`epistemic_value_t` vs `Δfitness_t+1`) > 0.3 on live\n"
        "### 4. PAPER\n"
        "- [x] Table 1 (primary metrics by seed) — live filled\n"
        "- [x] Table 2 (H2/H5 / cost) — live filled\n"
        "- [x] Reproducible **live** run IDs listed in `docs/paper_artifacts.md`\n"
    )
    # Longer than rich_live but zero live end-goal checks (pre-441 length trap).
    thin_long = (
        "# ICML Thesis 1 — Ready checklist\n\n"
        "**STATUS: IN_PROGRESS**\n\n"
        "_Tick 440 note: " + ("x" * 400) + "_\n\n"
        "## Criteria\n\n"
        "### 1. PRIMARY — Condition D beats B\n"
        "- [ ] D beats B on ≥3/5 seeds for gens-to-threshold (25% or 30%), **or**\n"
        "- [ ] D beats B on ≥3/5 seeds for cost-to-threshold (≥15% fewer tokens/calls), **or**\n"
        "- [ ] Non-trivial mean final accuracy gap (not ~1pp noise)\n"
        "### 2. MECHANISM — H2 or case study\n"
        "- [ ] Live API-run H2 DNA trait skew under contradiction bias\n"
        "### 3. VALIDITY — H5\n"
        "- [ ] Spearman ρ (`epistemic_value_t` vs `Δfitness_t+1`) > 0.3 on live\n"
        "### 4. PAPER\n"
        "- [ ] Table 1 (primary metrics by seed) — live empty\n"
        "- [ ] Table 2 (H2/H5 / cost) — live empty\n"
        "- [ ] Reproducible **live** run IDs listed in `docs/paper_artifacts.md`\n"
    )
    assert len(thin_long) > len(rich_live)

    # Prefer richer body even when thin is longer.
    preferred = prefer_richer_icml_ready(rich_live, thin_long)
    assert "- [x] D beats B on ≥3/5 seeds for gens-to-threshold" in preferred
    assert "- [x] Live API-run H2" in preferred

    # Conflict merge: demote STATUS but keep live checkmarks (onto=rich, local=thin).
    merged = merge_icml_ready_text(rich_live, thin_long)
    from icml_env_checks import _icml_ready_status_header

    assert _icml_ready_status_header(merged) == "IN_PROGRESS"
    assert not any(
        ln.strip().startswith("**STATUS: READY") for ln in merged.splitlines()
    )
    assert "- [x] D beats B on ≥3/5 seeds for gens-to-threshold" in merged
    assert "- [x] Spearman ρ" in merged
    assert "- [x] Reproducible **live** run IDs" in merged
    # Must not keep the thin unchecked PRIMARY line as the winner.
    assert "- [ ] D beats B on ≥3/5 seeds for gens-to-threshold" not in merged

    # Symmetric: rich local beats thin onto.
    merged2 = merge_icml_ready_text(thin_long, rich_live)
    assert _icml_ready_status_header(merged2) == "IN_PROGRESS"
    assert "- [x] Live API-run H2" in merged2

    out = _merge_durable_conflict_bytes(
        "docs/ICML_READY.md",
        rich_live.encode("utf-8"),
        thin_long.encode("utf-8"),
    )
    assert out is not None
    text = out.decode("utf-8")
    assert _icml_ready_status_header(text) == "IN_PROGRESS"
    assert "- [x] Table 1 (primary metrics by seed)" in text


def test_merge_icml_ready_demotes_header_despite_prose_status_mention() -> None:
    """Tick 442: Tick-note prose ``STATUS: IN_PROGRESS`` must not poison demote.

    Pre-442 whole-body substring checks made ``_demote_icml_ready_status`` no-op
    when audit/Tick prose mentioned ``STATUS: IN_PROGRESS``, leaving a poisoned
    ``**STATUS: READY**`` header after durable conflict merge with a thin
    IN_PROGRESS side. Richness also zeroed ``status_ready`` on true READY.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _merge_durable_conflict_bytes,
        merge_icml_ready_text,
    )

    rich_ready = (
        "# ICML Thesis 1 — Ready checklist\n\n"
        "**STATUS: READY**\n\n"
        "_Last G4 pack refresh: 2026-09-27; PRIMARY=True; allow_ready=True_\n"
        "_Note: do not leave STATUS: IN_PROGRESS after live criteria pass._\n\n"
        "## Criteria\n\n"
        "- [x] D beats B on ≥3/5 seeds for gens-to-threshold (25% or 30%), **or**\n"
        "- [x] D beats B on ≥3/5 seeds for cost-to-threshold (≥15% fewer tokens/calls), **or**\n"
        "- [x] Non-trivial mean final accuracy gap (not ~1pp noise)\n"
        "- [x] Live API-run H2 DNA trait skew under contradiction bias\n"
        "- [x] Spearman ρ (`epistemic_value_t` vs `Δfitness_t+1`) > 0.3 on live\n"
        "- [x] Table 1 (primary metrics by seed) — live filled\n"
        "- [x] Table 2 (H2/H5 / cost) — live filled\n"
        "- [x] Reproducible **live** run IDs listed in `docs/paper_artifacts.md`\n"
    )
    thin = (
        "# ICML Thesis 1 — Ready checklist\n\n"
        "**STATUS: IN_PROGRESS**\n\n"
        "_Tick pad: " + ("y" * 200) + "_\n\n"
        "- [ ] D beats B on ≥3/5 seeds for gens-to-threshold (25% or 30%), **or**\n"
    )

    assert "STATUS: IN_PROGRESS" in rich_ready  # prose only
    assert _icml_ready_status_header(rich_ready) == "READY"
    assert _icml_ready_richness(rich_ready)[2] == 1  # status_ready bit

    demoted = _demote_icml_ready_status(rich_ready)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert not any(
        ln.strip().startswith("**STATUS: READY") for ln in demoted.splitlines()
    )
    assert "- [x] Live API-run H2" in demoted
    assert "do not leave STATUS: IN_PROGRESS" in demoted  # prose preserved

    merged = merge_icml_ready_text(rich_ready, thin)
    assert _icml_ready_status_header(merged) == "IN_PROGRESS"
    assert not any(
        ln.strip().startswith("**STATUS: READY") for ln in merged.splitlines()
    )
    assert "- [x] D beats B on ≥3/5 seeds for gens-to-threshold" in merged
    assert "- [x] Reproducible **live** run IDs" in merged

    out = _merge_durable_conflict_bytes(
        "docs/ICML_READY.md",
        rich_ready.encode("utf-8"),
        thin.encode("utf-8"),
    )
    assert out is not None
    text = out.decode("utf-8")
    assert _icml_ready_status_header(text) == "IN_PROGRESS"
    assert "- [x] Table 1 (primary metrics by seed)" in text


def test_icml_ready_status_header_parses_token_not_trailing_substring() -> None:
    """Tick 446: READY header with trailing IN_PROGRESS note must still read READY.

    Pre-446 preferred ``IN_PROGRESS`` anywhere on the ``**STATUS:`` line, so
    ``**STATUS: READY** — was IN_PROGRESS`` was misread as IN_PROGRESS —
    ``demote_icml_ready_file`` then no-op'd (gate ``!= READY``) and left
    poisoned READY on disk after trust refuse; richness zeroed ``status_ready``.
    """
    from icml_env_checks import _icml_ready_richness, _icml_ready_status_header

    ready_trail = "**STATUS: READY** — was IN_PROGRESS; demote must still see READY\n"
    assert _icml_ready_status_header(ready_trail) == "READY"
    assert _icml_ready_status_header("**STATUS: READY** (not IN_PROGRESS yet)") == "READY"
    assert _icml_ready_status_header("**STATUS: IN_PROGRESS** (not READY)") == (
        "IN_PROGRESS"
    )
    assert _icml_ready_status_header("  **STATUS: READY**  ") == "READY"
    # Mid-line prose must still be ignored (Tick 442/445).
    prose = (
        "_Note: never set **STATUS: READY** from offline._\n\n"
        "**STATUS: IN_PROGRESS**\n"
    )
    assert _icml_ready_status_header(prose) == "IN_PROGRESS"
    # Richness status_ready bit must stay 1 for true READY + trailing note.
    rich = (
        "# ICML Thesis 1 — Ready checklist\n\n"
        "**STATUS: READY** — was IN_PROGRESS before G4 pack\n\n"
        "- [x] Table 1 (primary metrics by seed)\n"
    )
    assert _icml_ready_status_header(rich) == "READY"
    assert _icml_ready_richness(rich)[2] == 1


def test_icml_ready_status_header_accepts_plain_status() -> None:
    """Tick 447: bare ``STATUS:`` headers (no ``**``) must parse like bold ones.

    Pre-447 required ``**STATUS:`` only, so plain ``STATUS: READY`` stubs made
    demote/pipeline/richness miss READY, and G4 pack failed to rewrite plain
    IN_PROGRESS up to READY. Mid-line prose must still be ignored.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
    )

    assert _icml_ready_status_header("STATUS: READY\n") == "READY"
    assert _icml_ready_status_header("STATUS: IN_PROGRESS\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(
        "STATUS: READY — was IN_PROGRESS before pack\n"
    ) == "READY"
    assert _icml_ready_status_header("  STATUS: READY  \n") == "READY"
    # Mid-line prose must not count as the header.
    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS: IN_PROGRESS\n"
    )
    assert _icml_ready_status_header(prose) == "IN_PROGRESS"
    # Demote must rewrite the plain READY line (not prose) and normalize to **.
    plain_ready = (
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS: READY\n\n"
        "- [x] Table 1 (primary metrics by seed)\n"
    )
    assert _icml_ready_status_header(plain_ready) == "READY"
    demoted = _demote_icml_ready_status(plain_ready)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines())
    assert not any(
        ln.strip().startswith("STATUS: READY") for ln in demoted.splitlines()
    )
    # Richness status_ready bit for plain READY.
    assert _icml_ready_richness(plain_ready)[2] == 1


def test_icml_ready_status_header_accepts_atx_heading_status() -> None:
    """Tick 448: ATX heading ``# STATUS:`` / ``## **STATUS:**`` must parse like bold.

    Pre-448 required a non-heading start, so promoted heading stubs made demote
    no-op / G4 pack miss READY (or leave heading IN_PROGRESS on disk while the
    updater returned READY). Document titles without ``STATUS:`` must not match.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
    )

    assert _icml_ready_status_header("# STATUS: READY\n") == "READY"
    assert _icml_ready_status_header("## STATUS: IN_PROGRESS\n") == "IN_PROGRESS"
    assert _icml_ready_status_header("# **STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header(
        "## **STATUS: READY** — was IN_PROGRESS before pack\n"
    ) == "READY"
    assert _icml_ready_status_header("  ### STATUS: READY  \n") == "READY"
    # Document title without STATUS must not count as the header.
    title_only = (
        "# ICML Thesis 1 — Ready checklist\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "**STATUS: IN_PROGRESS**\n"
    )
    assert _icml_ready_status_header(title_only) == "IN_PROGRESS"
    # Mid-line prose still ignored; ATX READY still found.
    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "# STATUS: READY\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines())
    assert not any(
        "STATUS: READY" in ln and _icml_ready_status_header(ln + "\n") == "READY"
        for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1


def test_icml_ready_status_header_accepts_bold_closed_label_status() -> None:
    """Tick 449: ``**STATUS:** READY`` (bold label, value outside) must parse.

    Pre-449 required the token inside the same bold span (``**STATUS: READY**``),
    so the common markdown ``**Label:** value`` shape made demote no-op / G4 pack
    miss READY (header=None) and left ``**STATUS:** READY`` poisoned on disk.
    ``**STATUS:** Live …`` prose (HUMAN_UNBLOCK) must still not match.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
    )

    assert _icml_ready_status_header("**STATUS:** READY\n") == "READY"
    assert _icml_ready_status_header("**STATUS:** IN_PROGRESS\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(
        "**STATUS:** READY — was IN_PROGRESS before pack\n"
    ) == "READY"
    assert _icml_ready_status_header("  **STATUS:** READY  \n") == "READY"
    assert _icml_ready_status_header("## **STATUS:** READY\n") == "READY"
    assert _icml_ready_status_header("# **STATUS:** IN_PROGRESS\n") == "IN_PROGRESS"
    # Same-span bold form still works (Tick 446/447/448).
    assert _icml_ready_status_header("**STATUS: READY**\n") == "READY"
    # HUMAN_UNBLOCK-style label with non-token value must not count as header.
    assert (
        _icml_ready_status_header(
            "**STATUS:** Live G2→G3→G4 is blocked on NEBIUS.\n\n"
            "**STATUS: IN_PROGRESS**\n"
        )
        == "IN_PROGRESS"
    )
    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "**STATUS:** READY\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines())
    assert not any(
        ln.strip().startswith("**STATUS:** READY") for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1


def test_icml_ready_status_header_accepts_colon_outside_bold_status() -> None:
    """Tick 450: ``**STATUS**: READY`` (colon outside bold) must parse.

    Pre-450 required the colon inside the bold span (``**STATUS:**`` or
    ``**STATUS: TOKEN**``), so bold-label + colon-outside made demote no-op /
    G4 pack miss READY (header=None) and left ``**STATUS**: READY`` poisoned
    on disk. Non-token values after ``**STATUS**:`` must still not match.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
    )

    assert _icml_ready_status_header("**STATUS**: READY\n") == "READY"
    assert _icml_ready_status_header("**STATUS**: IN_PROGRESS\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(
        "**STATUS**: READY — was IN_PROGRESS before pack\n"
    ) == "READY"
    assert _icml_ready_status_header("  **STATUS**: READY  \n") == "READY"
    assert _icml_ready_status_header("## **STATUS**: READY\n") == "READY"
    assert _icml_ready_status_header("# **STATUS**: IN_PROGRESS\n") == "IN_PROGRESS"
    # Prior Tick 446–449 forms still work.
    assert _icml_ready_status_header("**STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("**STATUS:** READY\n") == "READY"
    # Non-token value after colon-outside bold must not count as header.
    assert (
        _icml_ready_status_header(
            "**STATUS**: Live G2→G3→G4 is blocked on NEBIUS.\n\n"
            "**STATUS: IN_PROGRESS**\n"
        )
        == "IN_PROGRESS"
    )
    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "**STATUS**: READY\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines())
    assert not any(
        ln.strip().startswith("**STATUS**: READY") for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1


def test_icml_ready_status_header_accepts_blockquote_list_bom_status() -> None:
    """Tick 451: blockquote / list / BOM STATUS headers must parse.

    Pre-451 required a bare / heading / bold start after strip, so
    ``> **STATUS: READY**`` / ``- STATUS: READY`` / BOM-prefixed first lines
    made demote no-op / G4 pack miss READY (header=None) and left poisoned
    READY on disk. Italic ``*STATUS*: READY`` (no space after ``*``) must
    still not match as a list marker.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
    )

    assert _icml_ready_status_header("> **STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("> **STATUS: IN_PROGRESS**\n") == "IN_PROGRESS"
    assert _icml_ready_status_header("> **STATUS:** READY\n") == "READY"
    assert _icml_ready_status_header("> **STATUS**: READY\n") == "READY"
    assert _icml_ready_status_header("- **STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("* STATUS: IN_PROGRESS\n") == "IN_PROGRESS"
    assert _icml_ready_status_header("+ **STATUS:** READY\n") == "READY"
    assert _icml_ready_status_header("1. **STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("2) STATUS: IN_PROGRESS\n") == "IN_PROGRESS"
    assert _icml_ready_status_header("> - **STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("> # STATUS: READY\n") == "READY"
    # UTF-8 BOM on file or line must not hide a READY header.
    assert _icml_ready_status_header("\ufeff**STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("\ufeffSTATUS: IN_PROGRESS\n") == "IN_PROGRESS"
    # Prior Tick 446–450 forms still work.
    assert _icml_ready_status_header("**STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("**STATUS:** READY\n") == "READY"
    assert _icml_ready_status_header("**STATUS**: READY\n") == "READY"
    # Tick 451 left italic ignored; Tick 452 accepts it (see italic test).
    # Non-token value after blockquote STATUS must not count as header.
    assert (
        _icml_ready_status_header(
            "> **STATUS:** Live G2→G3→G4 is blocked on NEBIUS.\n\n"
            "**STATUS: IN_PROGRESS**\n"
        )
        == "IN_PROGRESS"
    )
    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "> **STATUS: READY**\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines())
    assert not any(
        "> **STATUS: READY**" in ln for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1


def test_icml_ready_status_header_accepts_italic_underscore_status() -> None:
    """Tick 452: italic / underscore STATUS headers must parse.

    Pre-452 (Tick 451) left ``*STATUS*: READY`` / ``*STATUS: READY*`` /
    ``_STATUS: READY_`` unmatched so demote no-op'd / G4 pack missed READY
    on emphasis stubs. List ``* STATUS: …`` (space after ``*``) must still
    parse via the list+plain path; mid-line prose must not match.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
    )

    assert _icml_ready_status_header("*STATUS*: READY\n") == "READY"
    assert _icml_ready_status_header("*STATUS:* READY\n") == "READY"
    assert _icml_ready_status_header("*STATUS: READY*\n") == "READY"
    assert _icml_ready_status_header("*STATUS: IN_PROGRESS*\n") == "IN_PROGRESS"
    assert _icml_ready_status_header("_STATUS: READY_\n") == "READY"
    assert _icml_ready_status_header("_STATUS_: IN_PROGRESS\n") == "IN_PROGRESS"
    assert _icml_ready_status_header("_STATUS:_ READY\n") == "READY"
    # Containers + italic still work.
    assert _icml_ready_status_header("> *STATUS*: READY\n") == "READY"
    assert _icml_ready_status_header("# *STATUS: IN_PROGRESS*\n") == "IN_PROGRESS"
    # List marker (space after *) still matches via list+plain alt.
    assert _icml_ready_status_header("* STATUS: READY\n") == "READY"
    # Prior bold / plain / colon-out forms unchanged.
    assert _icml_ready_status_header("**STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("**STATUS**: READY\n") == "READY"
    assert _icml_ready_status_header("STATUS: IN_PROGRESS\n") == "IN_PROGRESS"
    # Non-token italic STATUS must not count as header.
    assert (
        _icml_ready_status_header(
            "*STATUS*: Live G2→G3→G4 is blocked on NEBIUS.\n\n"
            "*STATUS*: IN_PROGRESS\n"
        )
        == "IN_PROGRESS"
    )
    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "*STATUS*: READY\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines())
    assert not any("*STATUS*: READY" in ln for ln in demoted.splitlines())
    assert _icml_ready_richness(prose)[2] == 1


def test_icml_ready_status_header_accepts_dunder_triple_star_status() -> None:
    """Tick 453: ``__STATUS:…__`` / ``***STATUS:…***`` headers must parse.

    Pre-453 matched ``**`` / ``*`` / ``_`` only, so CommonMark double-underscore
    bold and triple-star bold+italic stubs made demote no-op / G4 pack miss
    READY. Prior bold / italic / underscore forms must still parse.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
    )

    assert _icml_ready_status_header("__STATUS: READY__\n") == "READY"
    assert _icml_ready_status_header("__STATUS__: IN_PROGRESS\n") == "IN_PROGRESS"
    assert _icml_ready_status_header("__STATUS:__ READY\n") == "READY"
    assert _icml_ready_status_header("***STATUS: READY***\n") == "READY"
    assert _icml_ready_status_header("***STATUS:*** IN_PROGRESS\n") == "IN_PROGRESS"
    assert _icml_ready_status_header("***STATUS: IN_PROGRESS***\n") == "IN_PROGRESS"
    # Containers + dunder / triple-star still work.
    assert _icml_ready_status_header("> __STATUS: READY__\n") == "READY"
    assert _icml_ready_status_header("# ***STATUS: IN_PROGRESS***\n") == "IN_PROGRESS"
    # Prior bold / italic / underscore / plain forms unchanged.
    assert _icml_ready_status_header("**STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("*STATUS*: READY\n") == "READY"
    assert _icml_ready_status_header("_STATUS: READY_\n") == "READY"
    assert _icml_ready_status_header("STATUS: IN_PROGRESS\n") == "IN_PROGRESS"
    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "__STATUS: READY__\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines())
    assert not any("__STATUS: READY__" in ln for ln in demoted.splitlines())
    assert _icml_ready_richness(prose)[2] == 1

    prose3 = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "***STATUS: READY***\n"
    )
    assert _icml_ready_status_header(prose3) == "READY"
    demoted3 = _demote_icml_ready_status(prose3)
    assert _icml_ready_status_header(demoted3) == "IN_PROGRESS"
    assert not any("***STATUS: READY***" in ln for ln in demoted3.splitlines())


def test_icml_ready_status_header_accepts_zwsp_nested_bold_dunder_status() -> None:
    """Tick 454: ZWSP-prefixed + nested bold↔dunder STATUS headers must parse.

    Pre-454 left ``\\u200b**STATUS: READY**`` / ``**__STATUS: READY__**`` /
    ``__**STATUS: READY**__`` unmatched so demote no-op'd / G4 pack missed
    READY on paste/nested stubs. Prior dunder / bold / italic forms must still
    parse.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _strip_icml_status_line_noise,
    )

    zwsp = "\u200b"
    assert _strip_icml_status_line_noise(f"{zwsp}**STATUS: READY**") == (
        "**STATUS: READY**"
    )
    assert _icml_ready_status_header(f"{zwsp}**STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header(f"{zwsp}{zwsp}STATUS: IN_PROGRESS\n") == (
        "IN_PROGRESS"
    )
    assert _icml_ready_status_header("**__STATUS: READY__**\n") == "READY"
    assert _icml_ready_status_header("**__STATUS__: IN_PROGRESS**\n") == (
        "IN_PROGRESS"
    )
    assert _icml_ready_status_header("__**STATUS: READY**__\n") == "READY"
    assert _icml_ready_status_header("__**STATUS:** IN_PROGRESS__\n") == (
        "IN_PROGRESS"
    )
    # Containers + ZWSP / nested still work.
    assert _icml_ready_status_header(f"> {zwsp}**STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("# **__STATUS: IN_PROGRESS__**\n") == (
        "IN_PROGRESS"
    )
    # Prior dunder / bold / italic / plain forms unchanged.
    assert _icml_ready_status_header("__STATUS: READY__\n") == "READY"
    assert _icml_ready_status_header("***STATUS: READY***\n") == "READY"
    assert _icml_ready_status_header("**STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("*STATUS*: READY\n") == "READY"
    assert _icml_ready_status_header("STATUS: IN_PROGRESS\n") == "IN_PROGRESS"

    prose_zw = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{zwsp}**STATUS: READY**\n"
    )
    assert _icml_ready_status_header(prose_zw) == "READY"
    demoted_zw = _demote_icml_ready_status(prose_zw)
    assert _icml_ready_status_header(demoted_zw) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted_zw
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_zw.splitlines()
    )
    assert not any(zwsp in ln for ln in demoted_zw.splitlines() if "STATUS:" in ln)
    assert _icml_ready_richness(prose_zw)[2] == 1

    prose_nest = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "**__STATUS: READY__**\n"
    )
    assert _icml_ready_status_header(prose_nest) == "READY"
    demoted_nest = _demote_icml_ready_status(prose_nest)
    assert _icml_ready_status_header(demoted_nest) == "IN_PROGRESS"
    assert not any(
        "**__STATUS: READY__**" in ln for ln in demoted_nest.splitlines()
    )

    prose_nest2 = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "__**STATUS: READY**__\n"
    )
    assert _icml_ready_status_header(prose_nest2) == "READY"
    demoted_nest2 = _demote_icml_ready_status(prose_nest2)
    assert _icml_ready_status_header(demoted_nest2) == "IN_PROGRESS"
    assert not any(
        "__**STATUS: READY**__" in ln for ln in demoted_nest2.splitlines()
    )


def test_icml_ready_status_header_accepts_html_entity_zwsp_nbsp_status() -> None:
    """Tick 455: HTML-entity ZWSP / nbsp STATUS headers must parse + demote.

    Pre-455 Unicode-only strip left ``&#8203;**STATUS: READY**`` /
    ``&ZeroWidthSpace;**STATUS:…**`` / ``**STATUS:&nbsp;READY**`` unmatched so
    demote no-op'd / G4 pack missed READY on Notion/Docs HTML→Markdown exports.
    Prior Unicode ZWSP / nested / dunder forms must still parse.
    """
    from icml_env_checks import (
        _decode_icml_status_html_entities,
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _strip_icml_status_line_noise,
    )

    assert _decode_icml_status_html_entities("&#8203;**STATUS: READY**") == (
        "\u200b**STATUS: READY**"
    )
    assert _decode_icml_status_html_entities("&ZeroWidthSpace;STATUS: READY") == (
        "\u200bSTATUS: READY"
    )
    assert _decode_icml_status_html_entities("**STATUS:&nbsp;READY**") == (
        "**STATUS:\u00a0READY**"
    )
    # Unknown entities left alone.
    assert _decode_icml_status_html_entities("&amp;**STATUS: READY**") == (
        "&amp;**STATUS: READY**"
    )
    assert _strip_icml_status_line_noise("&#8203;**STATUS: READY**") == (
        "**STATUS: READY**"
    )
    # Bold peels after nbsp decode (wrap sees leading ``**``; ZWSP-prefix above
    # keeps bold until header match).
    assert _strip_icml_status_line_noise("**STATUS:&nbsp;READY**") == (
        "STATUS:\u00a0READY"
    )
    assert _icml_ready_status_header("&#8203;**STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("&#x200b;**STATUS: IN_PROGRESS**\n") == (
        "IN_PROGRESS"
    )
    assert _icml_ready_status_header("&ZeroWidthSpace;**STATUS: READY**\n") == (
        "READY"
    )
    assert _icml_ready_status_header("**STATUS:&nbsp;READY**\n") == "READY"
    assert _icml_ready_status_header("**STATUS:&#160;IN_PROGRESS**\n") == (
        "IN_PROGRESS"
    )
    # Containers + HTML entity still work.
    assert _icml_ready_status_header("> &#8203;**STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("# **STATUS:&nbsp;IN_PROGRESS**\n") == (
        "IN_PROGRESS"
    )
    # Prior Unicode ZWSP / nested / dunder / bold forms unchanged.
    assert _icml_ready_status_header("\u200b**STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("**__STATUS: READY__**\n") == "READY"
    assert _icml_ready_status_header("__STATUS: READY__\n") == "READY"
    assert _icml_ready_status_header("**STATUS: READY**\n") == "READY"

    prose_ent = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "&#8203;**STATUS: READY**\n"
    )
    assert _icml_ready_status_header(prose_ent) == "READY"
    demoted_ent = _demote_icml_ready_status(prose_ent)
    assert _icml_ready_status_header(demoted_ent) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted_ent
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_ent.splitlines()
    )
    assert not any(
        "&#8203;" in ln and "STATUS: READY" in ln for ln in demoted_ent.splitlines()
    )
    assert _icml_ready_richness(prose_ent)[2] == 1

    prose_nbsp = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "**STATUS:&nbsp;READY**\n"
    )
    assert _icml_ready_status_header(prose_nbsp) == "READY"
    demoted_nbsp = _demote_icml_ready_status(prose_nbsp)
    assert _icml_ready_status_header(demoted_nbsp) == "IN_PROGRESS"
    assert not any(
        "&nbsp;" in ln and "STATUS: READY" in ln for ln in demoted_nbsp.splitlines()
    )


def test_icml_ready_status_header_accepts_html_tag_wrapped_status() -> None:
    """Tick 456: HTML-tag-wrapped STATUS headers must parse + demote.

    Pre-456 entity/ZWSP strip left ``<strong>STATUS: READY</strong>`` /
    ``<p><b>**STATUS:…**</b></p>`` / ``<span style=\"…\">**STATUS: READY**</span>``
    unmatched so demote no-op'd / G4 pack missed READY on Notion/Docs rich-paste
    and partial HTML→Markdown exports. Prior entity / ZWSP / nested forms must
    still parse.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _strip_icml_status_html_tags,
        _strip_icml_status_line_noise,
    )

    assert _strip_icml_status_html_tags("<strong>STATUS: READY</strong>") == (
        "STATUS: READY"
    )
    assert _strip_icml_status_html_tags(
        '<span style="font-weight:bold">**STATUS: READY**</span>'
    ) == "**STATUS: READY**"
    assert _strip_icml_status_html_tags("<p><b>STATUS: IN_PROGRESS</b></p>") == (
        "STATUS: IN_PROGRESS"
    )
    # Non-allowlisted tags left alone (do not eat comparisons).
    assert _strip_icml_status_html_tags("STATUS < 1") == "STATUS < 1"
    assert _strip_icml_status_html_tags("<table>STATUS: READY</table>") == (
        "<table>STATUS: READY</table>"
    )
    assert _strip_icml_status_line_noise("<strong>STATUS: READY</strong>") == (
        "STATUS: READY"
    )
    assert _strip_icml_status_line_noise(
        "<strong>&#8203;**STATUS: READY**</strong>"
    ) == "**STATUS: READY**"
    assert _icml_ready_status_header("<strong>STATUS: READY</strong>\n") == "READY"
    assert _icml_ready_status_header("<b>STATUS: IN_PROGRESS</b>\n") == "IN_PROGRESS"
    assert _icml_ready_status_header("<em>STATUS: READY</em>\n") == "READY"
    assert _icml_ready_status_header("<p><strong>STATUS: READY</strong></p>\n") == (
        "READY"
    )
    assert (
        _icml_ready_status_header("<strong>**STATUS: READY**</strong>\n") == "READY"
    )
    assert (
        _icml_ready_status_header(
            '<span style="font-weight:bold">**STATUS: IN_PROGRESS**</span>\n'
        )
        == "IN_PROGRESS"
    )
    # Containers + HTML tags still work.
    assert _icml_ready_status_header("> <strong>STATUS: READY</strong>\n") == "READY"
    assert _icml_ready_status_header("# <b>**STATUS: IN_PROGRESS**</b>\n") == (
        "IN_PROGRESS"
    )
    # Combined entity + tag.
    assert (
        _icml_ready_status_header("<strong>&#8203;**STATUS: READY**</strong>\n")
        == "READY"
    )
    # Prior entity / ZWSP / nested / bold forms unchanged.
    assert _icml_ready_status_header("&#8203;**STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("\u200b**STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("**__STATUS: READY__**\n") == "READY"
    assert _icml_ready_status_header("**STATUS: READY**\n") == "READY"

    prose_tag = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "<strong>STATUS: READY</strong>\n"
    )
    assert _icml_ready_status_header(prose_tag) == "READY"
    demoted_tag = _demote_icml_ready_status(prose_tag)
    assert _icml_ready_status_header(demoted_tag) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted_tag
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_tag.splitlines()
    )
    assert not any(
        "<strong>" in ln and "STATUS: READY" in ln for ln in demoted_tag.splitlines()
    )
    assert _icml_ready_richness(prose_tag)[2] == 1

    prose_span = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<span style="font-weight:bold">**STATUS: READY**</span>\n'
    )
    assert _icml_ready_status_header(prose_span) == "READY"
    demoted_span = _demote_icml_ready_status(prose_span)
    assert _icml_ready_status_header(demoted_span) == "IN_PROGRESS"
    assert not any(
        "<span" in ln and "STATUS: READY" in ln for ln in demoted_span.splitlines()
    )


def test_icml_ready_status_header_accepts_html_heading_and_md_wrap_status() -> None:
    """Tick 457: HTML heading + markdown backtick/strikethrough STATUS must parse.

    Pre-457 Tick 456 stripped ``strong``/``span``/``p`` but left ``<h1>STATUS:
    READY</h1>`` unmatched (ATX ``# STATUS:`` already worked via Tick 448), and
    chat/code paste `` `STATUS: READY` `` / ``~~STATUS: READY~~`` also missed —
    demote no-op'd / G4 pack missed READY.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _strip_icml_status_html_tags,
        _strip_icml_status_line_noise,
        _strip_icml_status_md_wrappers,
    )

    assert _strip_icml_status_html_tags("<h1>STATUS: READY</h1>") == "STATUS: READY"
    assert _strip_icml_status_html_tags("<h2>**STATUS: IN_PROGRESS**</h2>") == (
        "**STATUS: IN_PROGRESS**"
    )
    assert _strip_icml_status_html_tags("<kbd>STATUS: READY</kbd>") == "STATUS: READY"
    # Non-allowlisted tags still left alone.
    assert _strip_icml_status_html_tags("<table>STATUS: READY</table>") == (
        "<table>STATUS: READY</table>"
    )
    assert _strip_icml_status_md_wrappers("`STATUS: READY`") == "STATUS: READY"
    # Tick 458: iterative unwrap peels backtick then outer ``**``.
    assert _strip_icml_status_md_wrappers("`**STATUS: READY**`") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("~~STATUS: READY~~") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("STATUS: READY") == "STATUS: READY"
    assert _strip_icml_status_line_noise("<h1>STATUS: READY</h1>") == "STATUS: READY"
    assert _strip_icml_status_line_noise("`**STATUS: READY**`") == "STATUS: READY"
    assert _icml_ready_status_header("<h1>STATUS: READY</h1>\n") == "READY"
    assert _icml_ready_status_header("<h2>**STATUS: IN_PROGRESS**</h2>\n") == (
        "IN_PROGRESS"
    )
    assert _icml_ready_status_header("`STATUS: READY`\n") == "READY"
    assert _icml_ready_status_header("`**STATUS: READY**`\n") == "READY"
    assert _icml_ready_status_header("~~STATUS: IN_PROGRESS~~\n") == "IN_PROGRESS"
    assert _icml_ready_status_header("``STATUS: READY``\n") == "READY"
    # Combined heading + entity / prior forms.
    assert _icml_ready_status_header("<h1>&#8203;**STATUS: READY**</h1>\n") == "READY"
    assert _icml_ready_status_header("<strong>STATUS: READY</strong>\n") == "READY"
    assert _icml_ready_status_header("**STATUS: READY**\n") == "READY"

    prose_h1 = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "<h1>STATUS: READY</h1>\n"
    )
    assert _icml_ready_status_header(prose_h1) == "READY"
    demoted_h1 = _demote_icml_ready_status(prose_h1)
    assert _icml_ready_status_header(demoted_h1) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted_h1
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_h1.splitlines()
    )
    assert not any(
        "<h1>" in ln and "STATUS: READY" in ln for ln in demoted_h1.splitlines()
    )
    assert _icml_ready_richness(prose_h1)[2] == 1

    prose_bt = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "`STATUS: READY`\n"
    )
    assert _icml_ready_status_header(prose_bt) == "READY"
    demoted_bt = _demote_icml_ready_status(prose_bt)
    assert _icml_ready_status_header(demoted_bt) == "IN_PROGRESS"
    assert not any(
        ln.strip().startswith("`") and "STATUS: READY" in ln
        for ln in demoted_bt.splitlines()
    )


def test_icml_ready_status_header_accepts_html_container_and_obsidian_status() -> None:
    """Tick 458: HTML list/blockquote containers + Obsidian == STATUS must parse.

    Pre-458 Tick 451 matched markdown ``>`` / ``-`` prefixes and Tick 457
    stripped headings/backticks/~~, but Notion HTML exports
    ``<blockquote>STATUS: READY</blockquote>`` / ``<li>STATUS: READY</li>``
    and Obsidian ``==STATUS: READY==`` / nested ``**~~STATUS: READY~~**``
    still missed — demote no-op'd / G4 pack missed READY.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _strip_icml_status_html_tags,
        _strip_icml_status_line_noise,
        _strip_icml_status_md_wrappers,
    )

    assert _strip_icml_status_html_tags(
        "<blockquote>STATUS: READY</blockquote>"
    ) == "STATUS: READY"
    assert _strip_icml_status_html_tags("<li>**STATUS: IN_PROGRESS**</li>") == (
        "**STATUS: IN_PROGRESS**"
    )
    assert _strip_icml_status_html_tags("<ul><li>STATUS: READY</li></ul>") == (
        "STATUS: READY"
    )
    assert _strip_icml_status_html_tags("<pre>STATUS: READY</pre>") == "STATUS: READY"
    # Tick 459 allowlists table; keep a different non-allowlisted negative.
    assert _strip_icml_status_html_tags("<canvas>STATUS: READY</canvas>") == (
        "<canvas>STATUS: READY</canvas>"
    )
    assert _strip_icml_status_md_wrappers("==STATUS: READY==") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("==**STATUS: READY**==") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("**~~STATUS: READY~~**") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("~~**STATUS: READY**~~") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("`STATUS: READY`") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("STATUS: READY") == "STATUS: READY"
    assert _strip_icml_status_line_noise(
        "<blockquote>STATUS: READY</blockquote>"
    ) == "STATUS: READY"
    assert _strip_icml_status_line_noise("==**STATUS: READY**==") == "STATUS: READY"
    assert _icml_ready_status_header(
        "<blockquote>STATUS: READY</blockquote>\n"
    ) == "READY"
    assert _icml_ready_status_header("<li>**STATUS: IN_PROGRESS**</li>\n") == (
        "IN_PROGRESS"
    )
    assert _icml_ready_status_header("==STATUS: READY==\n") == "READY"
    assert _icml_ready_status_header("==**STATUS: READY**==\n") == "READY"
    assert _icml_ready_status_header("**~~STATUS: READY~~**\n") == "READY"
    assert _icml_ready_status_header("<h1>STATUS: READY</h1>\n") == "READY"
    assert _icml_ready_status_header("**STATUS: READY**\n") == "READY"

    prose_bq = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "<blockquote>STATUS: READY</blockquote>\n"
    )
    assert _icml_ready_status_header(prose_bq) == "READY"
    demoted_bq = _demote_icml_ready_status(prose_bq)
    assert _icml_ready_status_header(demoted_bq) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted_bq
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_bq.splitlines()
    )
    assert not any(
        "<blockquote>" in ln and "STATUS: READY" in ln
        for ln in demoted_bq.splitlines()
    )
    assert _icml_ready_richness(prose_bq)[2] == 1

    prose_eq = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "==STATUS: READY==\n"
    )
    assert _icml_ready_status_header(prose_eq) == "READY"
    demoted_eq = _demote_icml_ready_status(prose_eq)
    assert _icml_ready_status_header(demoted_eq) == "IN_PROGRESS"
    assert not any(
        ln.strip().startswith("==") and "STATUS: READY" in ln
        for ln in demoted_eq.splitlines()
    )


def test_icml_ready_status_header_accepts_html_table_semantic_and_md_pipe_status() -> None:
    """Tick 459: HTML table/semantic + markdown pipe STATUS must parse.

    Pre-459 Tick 458 stripped list/blockquote/Obsidian but Notion/Docs HTML
    ``<td>STATUS: READY</td>`` / ``<section>STATUS: READY</section>`` and
    GitHub one-cell pipes ``| STATUS: READY |`` still missed — demote no-op'd
    / G4 pack missed READY (Tick 458 even used ``<table>`` as a negative).
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _strip_icml_status_html_tags,
        _strip_icml_status_line_noise,
        _strip_icml_status_md_table_pipes,
        _strip_icml_status_md_wrappers,
    )

    assert _strip_icml_status_html_tags("<td>STATUS: READY</td>") == "STATUS: READY"
    assert _strip_icml_status_html_tags("<th>**STATUS: IN_PROGRESS**</th>") == (
        "**STATUS: IN_PROGRESS**"
    )
    assert _strip_icml_status_html_tags(
        "<table><tr><td>STATUS: READY</td></tr></table>"
    ) == "STATUS: READY"
    assert _strip_icml_status_html_tags("<section>STATUS: READY</section>") == (
        "STATUS: READY"
    )
    assert _strip_icml_status_html_tags("<article>**STATUS: READY**</article>") == (
        "**STATUS: READY**"
    )
    assert _strip_icml_status_html_tags("<caption>STATUS: READY</caption>") == (
        "STATUS: READY"
    )
    # Non-allowlisted tags still left alone.
    assert _strip_icml_status_html_tags("<canvas>STATUS: READY</canvas>") == (
        "<canvas>STATUS: READY</canvas>"
    )
    assert _strip_icml_status_md_table_pipes("| STATUS: READY |") == "STATUS: READY"
    assert _strip_icml_status_md_table_pipes("| **STATUS: READY** |") == (
        "**STATUS: READY**"
    )
    assert _strip_icml_status_md_table_pipes("|STATUS: READY|") == "STATUS: READY"
    # Multi-cell rows are not peeled (Tick 461: leave full row; no false READY).
    assert _strip_icml_status_md_table_pipes("| foo | STATUS: READY |") == (
        "| foo | STATUS: READY |"
    )
    assert _strip_icml_status_md_table_pipes("| STATUS: READY | note |") == (
        "| STATUS: READY | note |"
    )
    assert _strip_icml_status_md_wrappers("| ==STATUS: READY== |") == "STATUS: READY"
    assert _strip_icml_status_line_noise(
        "<td>STATUS: READY</td>"
    ) == "STATUS: READY"
    assert _strip_icml_status_line_noise("| **STATUS: READY** |") == "STATUS: READY"
    assert _icml_ready_status_header("<td>STATUS: READY</td>\n") == "READY"
    assert _icml_ready_status_header(
        "<table><tr><td>**STATUS: IN_PROGRESS**</td></tr></table>\n"
    ) == "IN_PROGRESS"
    assert _icml_ready_status_header("<section>STATUS: READY</section>\n") == "READY"
    assert _icml_ready_status_header("<article>**STATUS: READY**</article>\n") == (
        "READY"
    )
    assert _icml_ready_status_header("| STATUS: READY |\n") == "READY"
    assert _icml_ready_status_header("| **STATUS: READY** |\n") == "READY"
    assert _icml_ready_status_header("| ==STATUS: READY== |\n") == "READY"
    assert _icml_ready_status_header("| foo | STATUS: READY |\n") is None
    assert _icml_ready_status_header("| STATUS: READY | note |\n") is None
    assert _icml_ready_status_header("<blockquote>STATUS: READY</blockquote>\n") == (
        "READY"
    )
    assert _icml_ready_status_header("**STATUS: READY**\n") == "READY"

    prose_td = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "<td>STATUS: READY</td>\n"
    )
    assert _icml_ready_status_header(prose_td) == "READY"
    demoted_td = _demote_icml_ready_status(prose_td)
    assert _icml_ready_status_header(demoted_td) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted_td
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_td.splitlines()
    )
    assert not any(
        "<td>" in ln and "STATUS: READY" in ln for ln in demoted_td.splitlines()
    )
    assert _icml_ready_richness(prose_td)[2] == 1

    prose_pipe = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "| STATUS: READY |\n"
    )
    assert _icml_ready_status_header(prose_pipe) == "READY"
    demoted_pipe = _demote_icml_ready_status(prose_pipe)
    assert _icml_ready_status_header(demoted_pipe) == "IN_PROGRESS"
    assert not any(
        ln.strip().startswith("|") and "STATUS: READY" in ln
        for ln in demoted_pipe.splitlines()
    )


def test_icml_ready_status_header_accepts_wrap_around_md_pipe_status() -> None:
    """Tick 460: outer wrap-around-pipe STATUS must parse.

    Pre-460 Tick 459 peeled ``|…|`` only once before markdown wraps, so
    `` `| STATUS: READY |` `` / ``~~| STATUS:… |~~`` / ``==| STATUS:… |==`` /
    ``**| STATUS:… |**`` / `` `| **STATUS: READY** |` `` /
    ``> `| STATUS: READY |` `` left residual pipes after unwrap — demote
    no-op / G4 pack miss READY.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _strip_icml_status_line_noise,
        _strip_icml_status_md_wrappers,
    )

    assert _strip_icml_status_md_wrappers("`| STATUS: READY |`") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("~~| STATUS: READY |~~") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("==| STATUS: READY |==") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("**| STATUS: READY |**") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("__| STATUS: READY |__") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("`| **STATUS: READY** |`") == (
        "STATUS: READY"
    )
    assert _strip_icml_status_md_wrappers("> `| STATUS: READY |`") == "STATUS: READY"
    # Tick 459 pipe-inside-wrap still works.
    assert _strip_icml_status_md_wrappers("| ==STATUS: READY== |") == "STATUS: READY"
    # Multi-cell rows still do not become STATUS headers.
    assert _icml_ready_status_header("| foo | STATUS: READY |\n") is None

    assert _strip_icml_status_line_noise("`| STATUS: READY |`") == "STATUS: READY"
    assert _strip_icml_status_line_noise("~~| **STATUS: IN_PROGRESS** |~~") == (
        "STATUS: IN_PROGRESS"
    )
    assert _icml_ready_status_header("`| STATUS: READY |`\n") == "READY"
    assert _icml_ready_status_header("~~| STATUS: READY |~~\n") == "READY"
    assert _icml_ready_status_header("==| STATUS: READY |==\n") == "READY"
    assert _icml_ready_status_header("**| STATUS: READY |**\n") == "READY"
    assert _icml_ready_status_header("`| **STATUS: READY** |`\n") == "READY"
    assert _icml_ready_status_header("> `| STATUS: READY |`\n") == "READY"
    assert _icml_ready_status_header(
        "~~| **STATUS: IN_PROGRESS** |~~\n"
    ) == "IN_PROGRESS"
    # Prior Tick 459 forms still parse.
    assert _icml_ready_status_header("| STATUS: READY |\n") == "READY"
    assert _icml_ready_status_header("| ==STATUS: READY== |\n") == "READY"
    assert _icml_ready_status_header("<td>STATUS: READY</td>\n") == "READY"

    prose_wrap_pipe = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "`| STATUS: READY |`\n"
    )
    assert _icml_ready_status_header(prose_wrap_pipe) == "READY"
    demoted = _demote_icml_ready_status(prose_wrap_pipe)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines())
    assert not any(
        "`|" in ln and "STATUS: READY" in ln for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose_wrap_pipe)[2] == 1

    prose_strike_pipe = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "~~| STATUS: READY |~~\n"
    )
    assert _icml_ready_status_header(prose_strike_pipe) == "READY"
    demoted_strike = _demote_icml_ready_status(prose_strike_pipe)
    assert _icml_ready_status_header(demoted_strike) == "IN_PROGRESS"
    assert not any(
        "~~|" in ln and "STATUS: READY" in ln for ln in demoted_strike.splitlines()
    )


def test_icml_ready_status_header_accepts_quote_and_space_colon_status() -> None:
    """Tick 461: quote-wrap + space-before-colon STATUS; strict one-cell pipes.

    Pre-461 ``| STATUS: READY | note |`` peeled to ``STATUS: READY | note``
    and still matched READY (false positive). Quote wrappers and
    ``STATUS : READY`` missed demote / G4 pack rewrite.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _strip_icml_status_line_noise,
        _strip_icml_status_md_table_pipes,
        _strip_icml_status_md_wrappers,
    )

    # Strict one-cell pipe peel (multi-cell untouched).
    assert _strip_icml_status_md_table_pipes("| STATUS: READY |") == "STATUS: READY"
    assert _strip_icml_status_md_table_pipes("| STATUS: READY | note |") == (
        "| STATUS: READY | note |"
    )
    assert _strip_icml_status_md_table_pipes("| foo | STATUS: READY |") == (
        "| foo | STATUS: READY |"
    )
    assert _icml_ready_status_header("| STATUS: READY | note |\n") is None
    assert _icml_ready_status_header("| foo | STATUS: READY |\n") is None
    assert _icml_ready_status_header("| STATUS: READY |\n") == "READY"

    # Quote wrappers.
    assert _strip_icml_status_md_wrappers('"STATUS: READY"') == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("'STATUS: IN_PROGRESS'") == (
        "STATUS: IN_PROGRESS"
    )
    assert _strip_icml_status_md_wrappers('"**STATUS: READY**"') == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("\"| STATUS: READY |\"") == "STATUS: READY"
    assert _strip_icml_status_line_noise('"STATUS: READY"') == "STATUS: READY"
    assert _icml_ready_status_header('"STATUS: READY"\n') == "READY"
    assert _icml_ready_status_header("'STATUS: READY'\n") == "READY"
    assert _icml_ready_status_header('"**STATUS: IN_PROGRESS**"\n') == "IN_PROGRESS"

    # Space before colon.
    assert _icml_ready_status_header("STATUS : READY\n") == "READY"
    assert _icml_ready_status_header("**STATUS : IN_PROGRESS**\n") == "IN_PROGRESS"
    assert _icml_ready_status_header('"STATUS : READY"\n') == "READY"
    assert _icml_ready_status_header("| STATUS : READY |\n") == "READY"
    # Prior Tick 460 forms still parse.
    assert _icml_ready_status_header("`| STATUS: READY |`\n") == "READY"
    assert _icml_ready_status_header("**STATUS: READY**\n") == "READY"

    prose_quote = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '"STATUS: READY"\n'
    )
    assert _icml_ready_status_header(prose_quote) == "READY"
    demoted_q = _demote_icml_ready_status(prose_quote)
    assert _icml_ready_status_header(demoted_q) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted_q
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_q.splitlines())
    assert not any(
        '"' in ln and "STATUS: READY" in ln for ln in demoted_q.splitlines()
    )
    assert _icml_ready_richness(prose_quote)[2] == 1

    prose_space = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS : READY\n"
    )
    assert _icml_ready_status_header(prose_space) == "READY"
    demoted_s = _demote_icml_ready_status(prose_space)
    assert _icml_ready_status_header(demoted_s) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_s.splitlines())
    assert not any(
        ln.strip().startswith("STATUS : READY") for ln in demoted_s.splitlines()
    )

    # Multi-cell first-cell STATUS must not demote as a poisoned READY header.
    multi = (
        "# Title\n\n"
        "| STATUS: READY | note |\n\n"
        "**STATUS: IN_PROGRESS**\n"
    )
    assert _icml_ready_status_header(multi) == "IN_PROGRESS"


def test_icml_ready_status_header_accepts_task_list_and_token_wrap_status() -> None:
    """Tick 462: GitHub task-list checkbox + inline token-wrap STATUS.

    Pre-462 ``- [ ] STATUS: READY`` / ``STATUS: `READY` `` /
    ``STATUS: ~~READY~~`` missed demote / G4 pack rewrite.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _strip_icml_status_line_noise,
        _strip_icml_status_md_wrappers,
    )

    # Task-list checkbox peel (container prefix + header regex).
    assert _strip_icml_status_md_wrappers("- [ ] STATUS: READY") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("- [x] **STATUS: READY**") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("* [X] STATUS: IN_PROGRESS") == (
        "STATUS: IN_PROGRESS"
    )
    assert _strip_icml_status_line_noise("- [ ] STATUS: READY") == "STATUS: READY"
    assert _icml_ready_status_header("- [ ] STATUS: READY\n") == "READY"
    assert _icml_ready_status_header("- [x] **STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("- [ ] **STATUS: IN_PROGRESS**\n") == (
        "IN_PROGRESS"
    )
    assert _icml_ready_status_header("+ [x] STATUS : READY\n") == "READY"

    # Inline token wraps (backtick / strikethrough around READY|IN_PROGRESS).
    assert _icml_ready_status_header("STATUS: `READY`\n") == "READY"
    assert _icml_ready_status_header("STATUS: ~~READY~~\n") == "READY"
    assert _icml_ready_status_header("STATUS: `IN_PROGRESS`\n") == "IN_PROGRESS"
    assert _icml_ready_status_header("**STATUS: `READY`**\n") == "READY"
    assert _icml_ready_status_header("- [ ] STATUS: `READY`\n") == "READY"
    assert _icml_ready_status_header('"STATUS: ~~READY~~"\n') == "READY"
    # Prior Tick 461 forms still parse.
    assert _icml_ready_status_header('"STATUS: READY"\n') == "READY"
    assert _icml_ready_status_header("STATUS : READY\n") == "READY"
    assert _icml_ready_status_header("| STATUS: READY |\n") == "READY"
    # Multi-cell still not a header.
    assert _icml_ready_status_header("| STATUS: READY | note |\n") is None

    prose_task = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "- [ ] STATUS: READY\n"
    )
    assert _icml_ready_status_header(prose_task) == "READY"
    demoted_t = _demote_icml_ready_status(prose_task)
    assert _icml_ready_status_header(demoted_t) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted_t
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_t.splitlines())
    assert not any(
        "[ ]" in ln and "STATUS: READY" in ln for ln in demoted_t.splitlines()
    )
    assert _icml_ready_richness(prose_task)[2] == 1

    prose_token = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS: `READY`\n"
    )
    assert _icml_ready_status_header(prose_token) == "READY"
    demoted_k = _demote_icml_ready_status(prose_token)
    assert _icml_ready_status_header(demoted_k) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_k.splitlines())
    assert not any(
        "`READY`" in ln for ln in demoted_k.splitlines() if "STATUS" in ln
    )


def test_icml_ready_status_header_accepts_bare_ordered_blockquote_checkbox_status() -> None:
    """Tick 463: bare / ordered / blockquote checkbox STATUS headers.

    Pre-463 ``[ ] STATUS: READY`` / ``1. [ ] STATUS: READY`` /
    ``> [x] **STATUS: READY**`` / ``| [ ] STATUS: READY |`` missed demote /
    G4 pack rewrite (Tick 462 required ``[-*+]`` before ``[ ]``).
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _strip_icml_status_line_noise,
        _strip_icml_status_md_wrappers,
    )

    # Bare checkbox peel (no list marker).
    assert _strip_icml_status_md_wrappers("[ ] STATUS: READY") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("[x] **STATUS: READY**") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("[X] STATUS: IN_PROGRESS") == (
        "STATUS: IN_PROGRESS"
    )
    assert _strip_icml_status_line_noise("[ ] STATUS: READY") == "STATUS: READY"
    assert _icml_ready_status_header("[ ] STATUS: READY\n") == "READY"
    assert _icml_ready_status_header("[x] **STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("[ ] **STATUS: IN_PROGRESS**\n") == (
        "IN_PROGRESS"
    )
    assert _icml_ready_status_header("[ ] STATUS: `READY`\n") == "READY"
    assert _icml_ready_status_header("[x] STATUS: ~~READY~~\n") == "READY"

    # Ordered-list + checkbox.
    assert _strip_icml_status_md_wrappers("1. [ ] STATUS: READY") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("2) [x] **STATUS: READY**") == (
        "STATUS: READY"
    )
    assert _icml_ready_status_header("1. [ ] STATUS: READY\n") == "READY"
    assert _icml_ready_status_header("1. [x] **STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("3. [ ] STATUS : READY\n") == "READY"

    # Blockquote + bare checkbox.
    assert _strip_icml_status_md_wrappers("> [ ] STATUS: READY") == "STATUS: READY"
    assert _icml_ready_status_header("> [ ] STATUS: READY\n") == "READY"
    assert _icml_ready_status_header("> [x] **STATUS: READY**\n") == "READY"

    # Pipe + bare checkbox (peel pipe then checkbox).
    assert _icml_ready_status_header("| [ ] STATUS: READY |\n") == "READY"
    assert _icml_ready_status_header("| [x] **STATUS: READY** |\n") == "READY"
    # Multi-cell still not a header.
    assert _icml_ready_status_header("| [ ] STATUS: READY | note |\n") is None

    # Prior Tick 462 list+checkbox forms still parse.
    assert _icml_ready_status_header("- [ ] STATUS: READY\n") == "READY"
    assert _icml_ready_status_header("- [x] **STATUS: READY**\n") == "READY"
    assert _icml_ready_status_header("STATUS: `READY`\n") == "READY"

    prose_bare = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "[ ] STATUS: READY\n"
    )
    assert _icml_ready_status_header(prose_bare) == "READY"
    demoted_b = _demote_icml_ready_status(prose_bare)
    assert _icml_ready_status_header(demoted_b) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted_b
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_b.splitlines())
    assert not any(
        ln.strip().startswith("[ ]") and "STATUS: READY" in ln
        for ln in demoted_b.splitlines()
    )
    assert _icml_ready_richness(prose_bare)[2] == 1

    prose_ord = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "1. [ ] STATUS: READY\n"
    )
    assert _icml_ready_status_header(prose_ord) == "READY"
    demoted_o = _demote_icml_ready_status(prose_ord)
    assert _icml_ready_status_header(demoted_o) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_o.splitlines())
    assert not any(
        "1. [ ]" in ln and "STATUS: READY" in ln for ln in demoted_o.splitlines()
    )


def test_icml_ready_status_header_accepts_paren_bracket_brace_fullwidth_colon_status() -> None:
    """Tick 464: paren / bracket / brace / fullwidth-colon STATUS headers.

    Pre-464 ``(STATUS: READY)`` / ``[STATUS: READY]`` / ``{STATUS: READY}`` /
    ``（STATUS: READY）`` / ``STATUS：READY`` missed demote / G4 pack rewrite.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _strip_icml_status_line_noise,
        _strip_icml_status_md_wrappers,
    )

    # Paren / bracket / brace / fullwidth-paren peel.
    assert _strip_icml_status_md_wrappers("(STATUS: READY)") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("[STATUS: READY]") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("{STATUS: READY}") == "STATUS: READY"
    assert _strip_icml_status_md_wrappers("（STATUS: READY）") == "STATUS: READY"
    # Iterative wrap peel: outer paren then outer ``**`` → bare STATUS.
    assert _strip_icml_status_md_wrappers("(**STATUS: READY**)") == "STATUS: READY"
    assert _strip_icml_status_line_noise("(STATUS: READY)") == "STATUS: READY"
    assert _strip_icml_status_line_noise("[**STATUS: READY**]") == "STATUS: READY"

    assert _icml_ready_status_header("(STATUS: READY)\n") == "READY"
    assert _icml_ready_status_header("[STATUS: READY]\n") == "READY"
    assert _icml_ready_status_header("{STATUS: IN_PROGRESS}\n") == "IN_PROGRESS"
    assert _icml_ready_status_header("（**STATUS: READY**）\n") == "READY"
    assert _icml_ready_status_header('("STATUS: READY")\n') == "READY"
    assert _icml_ready_status_header("| (STATUS: READY) |\n") == "READY"

    # Fullwidth colon (CJK / Notion export).
    assert _icml_ready_status_header("STATUS：READY\n") == "READY"
    assert _icml_ready_status_header("**STATUS：READY**\n") == "READY"
    assert _icml_ready_status_header("STATUS： IN_PROGRESS\n") == "IN_PROGRESS"
    assert _icml_ready_status_header("(STATUS：READY)\n") == "READY"
    assert _icml_ready_status_header("[STATUS：READY]\n") == "READY"

    # Bare checkbox still peels (not mistaken for [STATUS:…] wrap).
    assert _strip_icml_status_md_wrappers("[ ] STATUS: READY") == "STATUS: READY"
    assert _icml_ready_status_header("[ ] STATUS: READY\n") == "READY"
    assert _icml_ready_status_header("- [x] **STATUS: READY**\n") == "READY"

    prose_paren = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "(STATUS: READY)\n"
    )
    assert _icml_ready_status_header(prose_paren) == "READY"
    demoted_p = _demote_icml_ready_status(prose_paren)
    assert _icml_ready_status_header(demoted_p) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted_p
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_p.splitlines())
    assert not any(
        ln.strip().startswith("(") and "STATUS: READY" in ln
        for ln in demoted_p.splitlines()
    )
    assert _icml_ready_richness(prose_paren)[2] == 1

    prose_fw = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS：READY\n"
    )
    assert _icml_ready_status_header(prose_fw) == "READY"
    demoted_fw = _demote_icml_ready_status(prose_fw)
    assert _icml_ready_status_header(demoted_fw) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_fw.splitlines())
    assert not any("STATUS：READY" in ln for ln in demoted_fw.splitlines())


def test_icml_ready_status_header_accepts_md_link_and_html_anchor_status() -> None:
    """Tick 465: markdown-link + HTML-anchor STATUS headers.

    Pre-465 ``[STATUS: READY](url)`` / ``[**STATUS: READY**](#anchor)`` /
    ``<a href=\"…\">STATUS: READY</a>`` missed demote / G4 pack rewrite —
    Tick 464 bare ``[STATUS:…]`` required the line to end at ``]``.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _strip_icml_status_line_noise,
        _strip_icml_status_md_wrappers,
    )

    # Markdown inline link peel (before bare-bracket wrap).
    assert (
        _strip_icml_status_md_wrappers("[STATUS: READY](https://example.com)")
        == "STATUS: READY"
    )
    assert (
        _strip_icml_status_md_wrappers("[**STATUS: READY**](#anchor)")
        == "STATUS: READY"
    )
    assert (
        _strip_icml_status_md_wrappers("[STATUS: IN_PROGRESS](./ICML_READY.md)")
        == "STATUS: IN_PROGRESS"
    )
    # Bare checkbox still peels (not mistaken for markdown link).
    assert _strip_icml_status_md_wrappers("[ ] STATUS: READY") == "STATUS: READY"
    # Bare bracket wrap (Tick 464) still peels when no trailing (url).
    assert _strip_icml_status_md_wrappers("[STATUS: READY]") == "STATUS: READY"

    assert _icml_ready_status_header(
        "[STATUS: READY](https://example.com)\n"
    ) == "READY"
    assert _icml_ready_status_header("[**STATUS: READY**](#anchor)\n") == "READY"
    assert (
        _icml_ready_status_header("[STATUS: IN_PROGRESS](./ICML_READY.md)\n")
        == "IN_PROGRESS"
    )
    assert (
        _icml_ready_status_header('<a href="https://x">STATUS: READY</a>\n')
        == "READY"
    )
    assert (
        _icml_ready_status_header('<a href="#">**STATUS: READY**</a>\n') == "READY"
    )
    assert (
        _icml_ready_status_header(
            '| [STATUS: READY](https://example.com) |\n'
        )
        == "READY"
    )
    assert (
        _icml_ready_status_header(
            "> [STATUS: READY](https://example.com)\n"
        )
        == "READY"
    )
    assert _strip_icml_status_line_noise(
        '<a href="https://x">STATUS: READY</a>'
    ) == "STATUS: READY"

    prose_link = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "[STATUS: READY](https://example.com)\n"
    )
    assert _icml_ready_status_header(prose_link) == "READY"
    demoted = _demote_icml_ready_status(prose_link)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines())
    assert not any(
        "](https://example.com)" in ln and "STATUS: READY" in ln
        for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose_link)[2] == 1

    prose_a = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<a href="#">STATUS: READY</a>\n'
    )
    assert _icml_ready_status_header(prose_a) == "READY"
    demoted_a = _demote_icml_ready_status(prose_a)
    assert _icml_ready_status_header(demoted_a) == "IN_PROGRESS"
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_a.splitlines())
    assert not any(
        "<a " in ln and "STATUS: READY" in ln for ln in demoted_a.splitlines()
    )


def test_icml_ready_status_header_accepts_md_link_nested_paren_url_status() -> None:
    """Tick 466: markdown-link STATUS with nested parentheses in the URL.

    Pre-466 ``[STATUS: READY](https://x.com/foo_(bar))`` missed demote /
    G4 pack rewrite — Tick 465 ``[^)]*`` stopped at the first ``)``.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_md_link,
        _strip_icml_status_md_wrappers,
    )

    nested = "[STATUS: READY](https://x.com/foo_(bar))"
    nested_anchor = "[**STATUS: READY**](https://example.com/path#status-(draft))"
    nested_prog = "[STATUS: IN_PROGRESS](https://x.com/a_(b)_c)"
    flat = "[STATUS: READY](https://example.com)"

    assert _peel_icml_status_md_link(nested) == "STATUS: READY"
    assert _peel_icml_status_md_link(nested_anchor) == "**STATUS: READY**"
    assert _peel_icml_status_md_link(nested_prog) == "STATUS: IN_PROGRESS"
    assert _peel_icml_status_md_link(flat) == "STATUS: READY"
    # Bare checkbox / bare bracket still not mistaken for links.
    assert _peel_icml_status_md_link("[ ] STATUS: READY") is None
    assert _peel_icml_status_md_link("[STATUS: READY]") is None
    # Trailing prose after closing paren must not peel.
    assert _peel_icml_status_md_link("[STATUS: READY](https://x.com/foo_(bar)) note") is None

    assert _strip_icml_status_md_wrappers(nested) == "STATUS: READY"
    assert _strip_icml_status_md_wrappers(nested_anchor) == "STATUS: READY"
    assert _icml_ready_status_header(nested + "\n") == "READY"
    assert _icml_ready_status_header(nested_anchor + "\n") == "READY"
    assert _icml_ready_status_header(nested_prog + "\n") == "IN_PROGRESS"
    assert (
        _icml_ready_status_header("| [STATUS: READY](https://x.com/foo_(bar)) |\n")
        == "READY"
    )
    assert (
        _icml_ready_status_header("> [STATUS: READY](https://x.com/foo_(bar))\n")
        == "READY"
    )

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "[STATUS: READY](https://github.com/org/repo/blob/main/docs/ICML_READY.md#status-(draft))\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines())
    assert not any(
        "foo_(bar)" in ln or "status-(draft)" in ln
        for ln in demoted.splitlines()
        if "STATUS: READY" in ln
    )
    assert _icml_ready_richness(prose)[2] == 1


def test_icml_ready_status_header_accepts_md_image_status() -> None:
    """Tick 467: markdown-image STATUS (shields.io / Notion badge exports).

    Pre-467 ``![STATUS: READY](url)`` missed demote / G4 pack rewrite —
    Tick 466 link peel required a bare ``[`` start, so the leading ``!``
    left image-badge READY stubs unmatched.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_md_link,
        _strip_icml_status_md_wrappers,
    )

    flat_img = "![STATUS: READY](https://img.shields.io/badge/STATUS-READY-green)"
    nested_img = "![STATUS: READY](https://img.shields.io/badge/STATUS-READY_(live)-green)"
    bold_img = "![**STATUS: READY**](https://cdn.example/badge_(draft).svg)"
    prog_img = "![STATUS: IN_PROGRESS](https://img.shields.io/badge/STATUS-IN_PROGRESS-yellow)"

    assert _peel_icml_status_md_link(flat_img) == "STATUS: READY"
    assert _peel_icml_status_md_link(nested_img) == "STATUS: READY"
    assert _peel_icml_status_md_link(bold_img) == "**STATUS: READY**"
    assert _peel_icml_status_md_link(prog_img) == "STATUS: IN_PROGRESS"
    # Trailing prose after image must not peel.
    assert _peel_icml_status_md_link(flat_img + " note") is None
    # Tick 466 nested-paren links still peel.
    assert _peel_icml_status_md_link("[STATUS: READY](https://x.com/foo_(bar))") == (
        "STATUS: READY"
    )

    assert _strip_icml_status_md_wrappers(flat_img) == "STATUS: READY"
    assert _strip_icml_status_md_wrappers(nested_img) == "STATUS: READY"
    assert _strip_icml_status_md_wrappers(bold_img) == "STATUS: READY"
    assert _icml_ready_status_header(flat_img + "\n") == "READY"
    assert _icml_ready_status_header(nested_img + "\n") == "READY"
    assert _icml_ready_status_header(bold_img + "\n") == "READY"
    assert _icml_ready_status_header(prog_img + "\n") == "IN_PROGRESS"
    assert (
        _icml_ready_status_header("| ![STATUS: READY](https://x.com/badge_(live).svg) |\n")
        == "READY"
    )
    assert (
        _icml_ready_status_header("> ![STATUS: READY](https://x.com/badge_(live).svg)\n")
        == "READY"
    )

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "![STATUS: READY](https://img.shields.io/badge/STATUS-READY_(live)-green)\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines())
    assert not any(
        "STATUS: READY" in ln and "![" in ln for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1


def test_icml_ready_status_header_accepts_html_picture_img_alt_status() -> None:
    """Tick 469: HTML ``<picture><img alt="STATUS:…">`` responsive badge exports.

    Pre-469 ``<picture><img alt="STATUS: READY" src="…">…</picture>`` missed
    demote / G4 pack rewrite — Tick 468 only peeled a full-line bare ``<img>``,
    and ``picture``/``source`` were not in the HTML-tag allowlist.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _strip_icml_status_html_tags,
        _strip_icml_status_md_wrappers,
    )

    flat_pic = (
        '<picture><img alt="STATUS: READY" '
        'src="https://img.shields.io/badge/STATUS-READY-green"></picture>'
    )
    with_source = (
        '<picture><source srcset="https://cdn.example/badge_(live).webp" '
        'type="image/webp">'
        '<img src="https://cdn.example/badge_(live).svg" '
        'alt="**STATUS: READY**" /></picture>'
    )
    prog_pic = (
        '<picture><img alt="STATUS: IN_PROGRESS" '
        'src="https://img.shields.io/badge/STATUS-IN_PROGRESS-yellow">'
        "</picture>"
    )

    # Allowlist strip exposes nested img for Tick 468 alt peel.
    assert (
        _strip_icml_status_html_tags(flat_pic)
        == '<img alt="STATUS: READY" '
        'src="https://img.shields.io/badge/STATUS-READY-green">'
    )
    assert _strip_icml_status_md_wrappers(flat_pic) == "STATUS: READY"
    assert _strip_icml_status_md_wrappers(with_source) == "STATUS: READY"
    assert _icml_ready_status_header(flat_pic + "\n") == "READY"
    assert _icml_ready_status_header(with_source + "\n") == "READY"
    assert _icml_ready_status_header(prog_pic + "\n") == "IN_PROGRESS"
    assert (
        _icml_ready_status_header(
            '| <picture><img alt="STATUS: READY" src="https://x.com/b.svg">'
            "</picture> |\n"
        )
        == "READY"
    )
    assert (
        _icml_ready_status_header(
            '> <picture><img alt="STATUS: READY" src="https://x.com/b.svg">'
            "</picture>\n"
        )
        == "READY"
    )
    # Tick 468 bare img + Tick 467 md-image still work.
    assert (
        _icml_ready_status_header(
            '<img alt="STATUS: READY" src="https://x.com/b.svg">\n'
        )
        == "READY"
    )

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<picture><source srcset="https://cdn.example/badge_(live).webp">'
        '<img alt="STATUS: READY" '
        'src="https://img.shields.io/badge/STATUS-READY_(live)-green">'
        "</picture>\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert not any(
        "STATUS: READY" in ln and "<picture" in ln.lower()
        for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1


def test_icml_ready_status_header_accepts_html_img_title_aria_status() -> None:
    """Tick 470: HTML ``<img title=…>`` / ``aria-label=…`` STATUS badge exports.

    Pre-470 Tick 468/469 only peeled ``alt=``, so a11y/tooltip badge exports
    (``<img title="STATUS: READY" src="…">`` /
    ``<img aria-label="**STATUS: READY**" src="…">`` /
    ``<img alt="badge" title="STATUS: READY" src="…">``) missed demote /
    G4 pack rewrite.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_img_alt,
        _strip_icml_status_md_wrappers,
    )

    title_img = (
        '<img title="STATUS: READY" '
        'src="https://img.shields.io/badge/STATUS-READY-green">'
    )
    aria_img = (
        '<img src="https://cdn.example/badge_(live).svg" '
        'aria-label="**STATUS: READY**" />'
    )
    decorative_alt = (
        '<img alt="badge" title="STATUS: READY" '
        'src="https://cdn.example/badge_(live).svg">'
    )
    prog_title = (
        '<img title="STATUS: IN_PROGRESS" '
        'src="https://img.shields.io/badge/STATUS-IN_PROGRESS-yellow">'
    )
    # Prefer STATUS-looking alt over decorative title.
    alt_wins = (
        '<img alt="STATUS: READY" title="tooltip" '
        'src="https://cdn.example/badge.svg">'
    )

    assert _peel_icml_status_html_img_alt(title_img) == "STATUS: READY"
    assert _peel_icml_status_html_img_alt(aria_img) == "**STATUS: READY**"
    assert _peel_icml_status_html_img_alt(decorative_alt) == "STATUS: READY"
    assert _peel_icml_status_html_img_alt(prog_title) == "STATUS: IN_PROGRESS"
    assert _peel_icml_status_html_img_alt(alt_wins) == "STATUS: READY"
    # Tick 468 alt-only still peels.
    assert (
        _peel_icml_status_html_img_alt(
            '<img alt="STATUS: READY" src="https://x.com/b.svg">'
        )
        == "STATUS: READY"
    )
    # No STATUS attrs → refuse.
    assert (
        _peel_icml_status_html_img_alt('<img src="https://x.com/b.svg">') is None
    )
    assert _strip_icml_status_md_wrappers(title_img) == "STATUS: READY"
    assert _strip_icml_status_md_wrappers(aria_img) == "STATUS: READY"
    assert _strip_icml_status_md_wrappers(decorative_alt) == "STATUS: READY"
    assert _icml_ready_status_header(title_img + "\n") == "READY"
    assert _icml_ready_status_header(aria_img + "\n") == "READY"
    assert _icml_ready_status_header(decorative_alt + "\n") == "READY"
    assert _icml_ready_status_header(prog_title + "\n") == "IN_PROGRESS"
    assert (
        _icml_ready_status_header(
            '| <img title="STATUS: READY" src="https://x.com/b.svg"> |\n'
        )
        == "READY"
    )
    assert (
        _icml_ready_status_header(
            '> <img aria-label="STATUS: READY" src="https://x.com/b.svg">\n'
        )
        == "READY"
    )
    # picture + title nested img (allowlist strip → title peel).
    assert (
        _icml_ready_status_header(
            '<picture><img title="STATUS: READY" '
            'src="https://x.com/b.svg"></picture>\n'
        )
        == "READY"
    )

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<img alt="badge_(live)" title="STATUS: READY" '
        'src="https://img.shields.io/badge/STATUS-READY_(live)-green">\n'
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert not any(
        "STATUS: READY" in ln and "<img" in ln.lower()
        for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1


def test_icml_ready_status_header_accepts_html_svg_title_status() -> None:
    """Tick 471: HTML inline SVG ``<title>STATUS:…</title>`` badge exports.

    Pre-471 Tick 468–470 only peeled ``<img>`` attrs, so shields.io / Notion
    SVG badge exports (``<svg…><title>STATUS: READY</title>…</svg>``) missed
    demote / G4 pack rewrite. Allowlist-stripping ``svg``/``title`` would
    concatenate residual ``<text>``/``<desc>`` onto the header.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_svg_title,
        _strip_icml_status_md_wrappers,
    )

    flat_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" role="img">'
        "<title>STATUS: READY</title></svg>"
    )
    bold_svg = (
        '<svg viewBox="0 0 110 20" role="img">'
        "<title>**STATUS: READY**</title>"
        '<text x="0" y="15">badge</text></svg>'
    )
    prog_svg = (
        '<svg role="img"><title>STATUS: IN_PROGRESS</title>'
        "<desc>ICML Thesis 1</desc></svg>"
    )
    # Non-STATUS title must refuse peel (decorative SVG).
    deco = '<svg><title>ICML badge</title><text>ok</text></svg>'

    assert _peel_icml_status_html_svg_title(flat_svg) == "STATUS: READY"
    assert _peel_icml_status_html_svg_title(bold_svg) == "**STATUS: READY**"
    assert _peel_icml_status_html_svg_title(prog_svg) == "STATUS: IN_PROGRESS"
    assert _peel_icml_status_html_svg_title(deco) is None
    assert _peel_icml_status_html_svg_title(flat_svg + " note") is None
    assert _peel_icml_status_html_svg_title('<img alt="STATUS: READY" src="x">') is None
    assert _strip_icml_status_md_wrappers(flat_svg) == "STATUS: READY"
    assert _strip_icml_status_md_wrappers(bold_svg) == "STATUS: READY"
    # Residual <text> must NOT concatenate onto the STATUS token.
    assert _strip_icml_status_md_wrappers(bold_svg) != "**STATUS: READY**badge"
    assert _icml_ready_status_header(flat_svg + "\n") == "READY"
    assert _icml_ready_status_header(bold_svg + "\n") == "READY"
    assert _icml_ready_status_header(prog_svg + "\n") == "IN_PROGRESS"
    assert (
        _icml_ready_status_header(f"| {flat_svg} |\n") == "READY"
    )
    assert (
        _icml_ready_status_header(f"> {flat_svg}\n") == "READY"
    )

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{bold_svg}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert not any(
        "<svg" in ln.lower() and "STATUS: READY" in ln
        for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1


def test_icml_ready_status_header_accepts_html_svg_aria_title_attr_status() -> None:
    """Tick 472: HTML SVG root ``aria-label=`` / ``title=`` STATUS badge exports.

    Pre-472 Tick 471 only peeled nested ``<title>``, so a11y/tooltip SVG
    badge exports (``<svg aria-label="STATUS: READY" …>`` /
    ``<svg title="STATUS: READY"><title>Badge</title>…``) missed demote /
    G4 pack rewrite when nested ``<title>`` was decorative or omitted.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_svg_title,
        _strip_icml_status_md_wrappers,
    )

    aria_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" role="img" '
        'aria-label="STATUS: READY">'
        '<text x="0" y="15">badge</text></svg>'
    )
    title_attr_svg = (
        '<svg viewBox="0 0 110 20" title="**STATUS: READY**" role="img">'
        "<title>Badge</title>"
        '<text x="0" y="15">ok</text></svg>'
    )
    # Nested STATUS wins when attrs are decorative (Tick 471 compat).
    nested_wins = (
        '<svg aria-label="badge_(live)" role="img">'
        "<title>STATUS: IN_PROGRESS</title></svg>"
    )
    # aria-label STATUS beats decorative nested title.
    aria_beats_nested = (
        '<svg aria-label="STATUS: READY" role="img">'
        "<title>ICML badge</title></svg>"
    )
    deco = '<svg title="ICML badge"><title>Badge</title></svg>'

    assert _peel_icml_status_html_svg_title(aria_svg) == "STATUS: READY"
    assert _peel_icml_status_html_svg_title(title_attr_svg) == "**STATUS: READY**"
    assert _peel_icml_status_html_svg_title(nested_wins) == "STATUS: IN_PROGRESS"
    assert _peel_icml_status_html_svg_title(aria_beats_nested) == "STATUS: READY"
    assert _peel_icml_status_html_svg_title(deco) is None
    assert _peel_icml_status_html_svg_title(aria_svg + " note") is None
    assert _strip_icml_status_md_wrappers(aria_svg) == "STATUS: READY"
    assert _strip_icml_status_md_wrappers(title_attr_svg) == "STATUS: READY"
    assert _strip_icml_status_md_wrappers(aria_beats_nested) == "STATUS: READY"
    # Residual <text> must NOT concatenate onto the STATUS token.
    assert _strip_icml_status_md_wrappers(aria_svg) != "STATUS: READYbadge"
    assert _icml_ready_status_header(aria_svg + "\n") == "READY"
    assert _icml_ready_status_header(title_attr_svg + "\n") == "READY"
    assert _icml_ready_status_header(nested_wins + "\n") == "IN_PROGRESS"
    assert (
        _icml_ready_status_header(f"| {aria_svg} |\n") == "READY"
    )
    assert (
        _icml_ready_status_header(f"> {aria_svg}\n") == "READY"
    )

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{aria_beats_nested}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert not any(
        "<svg" in ln.lower() and "STATUS: READY" in ln
        for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1


def test_icml_ready_status_header_accepts_html_svg_desc_status() -> None:
    """Tick 473: HTML SVG nested ``<desc>STATUS:…</desc>`` badge exports.

    Pre-473 Tick 471/472 only peeled root attrs + nested ``<title>``, so a11y
    long-description badge exports (``<svg…><title>Badge</title>
    <desc>STATUS: READY</desc>…`` / ``<svg…><desc>**STATUS: READY**</desc>…``)
    missed demote / G4 pack rewrite when title/attrs were decorative or
    omitted.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_svg_title,
        _strip_icml_status_md_wrappers,
    )

    desc_only = (
        '<svg xmlns="http://www.w3.org/2000/svg" role="img">'
        "<desc>STATUS: READY</desc>"
        '<text x="0" y="15">badge</text></svg>'
    )
    deco_title_desc = (
        '<svg viewBox="0 0 110 20" role="img">'
        "<title>Badge_(live)</title>"
        "<desc>**STATUS: READY**</desc>"
        '<text x="0" y="15">ok</text></svg>'
    )
    prog_desc = (
        '<svg role="img"><title>draft</title>'
        "<desc>STATUS: IN_PROGRESS</desc></svg>"
    )
    # Nested STATUS title still beats decorative desc (Tick 471 compat).
    title_beats_desc = (
        '<svg role="img"><title>STATUS: READY</title>'
        "<desc>longer badge blurb</desc></svg>"
    )
    # aria-label STATUS still beats decorative title+desc (Tick 472 compat).
    aria_beats_desc = (
        '<svg aria-label="STATUS: READY" role="img">'
        "<title>Badge</title><desc>detail</desc></svg>"
    )
    deco = (
        '<svg role="img"><title>Badge</title>'
        "<desc>ICML badge detail</desc></svg>"
    )

    assert _peel_icml_status_html_svg_title(desc_only) == "STATUS: READY"
    assert _peel_icml_status_html_svg_title(deco_title_desc) == "**STATUS: READY**"
    assert _peel_icml_status_html_svg_title(prog_desc) == "STATUS: IN_PROGRESS"
    assert _peel_icml_status_html_svg_title(title_beats_desc) == "STATUS: READY"
    assert _peel_icml_status_html_svg_title(aria_beats_desc) == "STATUS: READY"
    assert _peel_icml_status_html_svg_title(deco) is None
    assert _peel_icml_status_html_svg_title(desc_only + " note") is None
    assert _strip_icml_status_md_wrappers(desc_only) == "STATUS: READY"
    assert _strip_icml_status_md_wrappers(deco_title_desc) == "STATUS: READY"
    # Residual <text> must NOT concatenate onto the STATUS token.
    assert _strip_icml_status_md_wrappers(desc_only) != "STATUS: READYbadge"
    assert _icml_ready_status_header(desc_only + "\n") == "READY"
    assert _icml_ready_status_header(deco_title_desc + "\n") == "READY"
    assert _icml_ready_status_header(prog_desc + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(f"| {desc_only} |\n") == "READY"
    assert _icml_ready_status_header(f"> {desc_only}\n") == "READY"
    # Tick 472 aria-label still peels.
    assert _icml_ready_status_header(
        '<svg aria-label="STATUS: READY" role="img"></svg>\n'
    ) == "READY"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{deco_title_desc}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert not any(
        "<svg" in ln.lower() and "STATUS: READY" in ln
        for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1


def test_icml_ready_status_header_accepts_html_svg_text_status() -> None:
    """Tick 474: HTML SVG nested ``<text>STATUS:…</text>`` badge exports.

    Pre-474 Tick 471–473 only peeled attrs / ``<title>`` / ``<desc>``, so
    Figma / Illustrator / shields-like visible-label badge exports
    (``<svg…><title>Badge</title><text>STATUS: READY</text>…`` /
    ``<svg…><text><tspan>**STATUS: READY**</tspan></text>…``) missed demote
    / G4 pack rewrite when a11y name was decorative or omitted.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_svg_title,
        _strip_icml_status_md_wrappers,
    )

    text_only = (
        '<svg xmlns="http://www.w3.org/2000/svg" role="img">'
        '<text x="0" y="15">STATUS: READY</text></svg>'
    )
    deco_title_text = (
        '<svg viewBox="0 0 110 20" role="img">'
        "<title>Badge_(live)</title>"
        "<desc>ICML badge detail</desc>"
        '<text x="4" y="14">**STATUS: READY**</text></svg>'
    )
    tspan_text = (
        '<svg role="img"><title>draft</title>'
        "<text><tspan fill=\"#fff\">STATUS: IN_PROGRESS</tspan></text></svg>"
    )
    # Nested STATUS desc still beats decorative text (Tick 473 compat).
    desc_beats_text = (
        '<svg role="img"><desc>STATUS: READY</desc>'
        '<text x="0" y="15">ok</text></svg>'
    )
    # Nested STATUS title still beats decorative text (Tick 471 compat).
    title_beats_text = (
        '<svg role="img"><title>STATUS: READY</title>'
        '<text x="0" y="15">badge</text></svg>'
    )
    # aria-label STATUS still beats decorative title+text (Tick 472 compat).
    aria_beats_text = (
        '<svg aria-label="STATUS: READY" role="img">'
        "<title>Badge</title>"
        '<text x="0" y="15">detail</text></svg>'
    )
    deco = (
        '<svg role="img"><title>Badge</title>'
        '<text x="0" y="15">ICML badge</text></svg>'
    )
    # Split shields-like labels without ``STATUS:`` in one node refuse peel.
    split_labels = (
        '<svg role="img"><text>STATUS</text><text>READY</text></svg>'
    )

    assert _peel_icml_status_html_svg_title(text_only) == "STATUS: READY"
    assert _peel_icml_status_html_svg_title(deco_title_text) == "**STATUS: READY**"
    assert _peel_icml_status_html_svg_title(tspan_text) == "STATUS: IN_PROGRESS"
    assert _peel_icml_status_html_svg_title(desc_beats_text) == "STATUS: READY"
    assert _peel_icml_status_html_svg_title(title_beats_text) == "STATUS: READY"
    assert _peel_icml_status_html_svg_title(aria_beats_text) == "STATUS: READY"
    assert _peel_icml_status_html_svg_title(deco) is None
    assert _peel_icml_status_html_svg_title(split_labels) is None
    assert _peel_icml_status_html_svg_title(text_only + " note") is None
    assert _strip_icml_status_md_wrappers(text_only) == "STATUS: READY"
    assert _strip_icml_status_md_wrappers(deco_title_text) == "STATUS: READY"
    assert _strip_icml_status_md_wrappers(tspan_text) == "STATUS: IN_PROGRESS"
    assert _icml_ready_status_header(text_only + "\n") == "READY"
    assert _icml_ready_status_header(deco_title_text + "\n") == "READY"
    assert _icml_ready_status_header(tspan_text + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(f"| {text_only} |\n") == "READY"
    assert _icml_ready_status_header(f"> {text_only}\n") == "READY"
    # Tick 473 desc still peels.
    assert _icml_ready_status_header(
        '<svg role="img"><desc>STATUS: READY</desc></svg>\n'
    ) == "READY"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{deco_title_text}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert not any(
        "<svg" in ln.lower() and "STATUS: READY" in ln
        for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1


def test_icml_ready_status_header_accepts_html_svg_foreign_object_status() -> None:
    """Tick 475: HTML SVG nested ``<foreignObject>STATUS:…</foreignObject>``.

    Pre-475 Tick 471–474 only peeled attrs / ``<title>`` / ``<desc>`` /
    ``<text>``, so Figma / browser HTML-in-SVG label badge exports
    (``<svg…><title>Badge</title><foreignObject><div>STATUS: READY</div>
    </foreignObject>…`` /
    ``<svg…><foreignObject><span>**STATUS: READY**</span></foreignObject>``)
    missed demote / G4 pack rewrite when a11y name was decorative or omitted.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_svg_title,
        _strip_icml_status_md_wrappers,
    )

    fo_only = (
        '<svg xmlns="http://www.w3.org/2000/svg" role="img">'
        '<foreignObject width="120" height="20">'
        '<div xmlns="http://www.w3.org/1999/xhtml">STATUS: READY</div>'
        "</foreignObject></svg>"
    )
    deco_title_fo = (
        '<svg viewBox="0 0 110 20" role="img">'
        "<title>Badge_(live)</title>"
        "<desc>ICML badge detail</desc>"
        "<foreignObject width=\"110\" height=\"20\">"
        "<span>**STATUS: READY**</span></foreignObject></svg>"
    )
    fo_prog = (
        '<svg role="img"><title>draft</title>'
        "<foreignObject><p>STATUS: IN_PROGRESS</p></foreignObject></svg>"
    )
    # Nested STATUS text still beats decorative foreignObject (Tick 474 compat).
    text_beats_fo = (
        '<svg role="img"><text x="0" y="15">STATUS: READY</text>'
        "<foreignObject><div>ok</div></foreignObject></svg>"
    )
    # Nested STATUS desc still beats decorative foreignObject (Tick 473 compat).
    desc_beats_fo = (
        '<svg role="img"><desc>STATUS: READY</desc>'
        "<foreignObject><div>ok</div></foreignObject></svg>"
    )
    # Nested STATUS title still beats decorative foreignObject (Tick 471 compat).
    title_beats_fo = (
        '<svg role="img"><title>STATUS: READY</title>'
        "<foreignObject><div>badge</div></foreignObject></svg>"
    )
    # aria-label STATUS still beats decorative title+foreignObject (Tick 472).
    aria_beats_fo = (
        '<svg aria-label="STATUS: READY" role="img">'
        "<title>Badge</title>"
        "<foreignObject><div>detail</div></foreignObject></svg>"
    )
    deco = (
        '<svg role="img"><title>Badge</title>'
        "<foreignObject><div>ICML badge</div></foreignObject></svg>"
    )

    assert _peel_icml_status_html_svg_title(fo_only) == "STATUS: READY"
    assert _peel_icml_status_html_svg_title(deco_title_fo) == "**STATUS: READY**"
    assert _peel_icml_status_html_svg_title(fo_prog) == "STATUS: IN_PROGRESS"
    assert _peel_icml_status_html_svg_title(text_beats_fo) == "STATUS: READY"
    assert _peel_icml_status_html_svg_title(desc_beats_fo) == "STATUS: READY"
    assert _peel_icml_status_html_svg_title(title_beats_fo) == "STATUS: READY"
    assert _peel_icml_status_html_svg_title(aria_beats_fo) == "STATUS: READY"
    assert _peel_icml_status_html_svg_title(deco) is None
    assert _peel_icml_status_html_svg_title(fo_only + " note") is None
    assert _strip_icml_status_md_wrappers(fo_only) == "STATUS: READY"
    assert _strip_icml_status_md_wrappers(deco_title_fo) == "STATUS: READY"
    assert _strip_icml_status_md_wrappers(fo_prog) == "STATUS: IN_PROGRESS"
    assert _icml_ready_status_header(fo_only + "\n") == "READY"
    assert _icml_ready_status_header(deco_title_fo + "\n") == "READY"
    assert _icml_ready_status_header(fo_prog + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(f"| {fo_only} |\n") == "READY"
    assert _icml_ready_status_header(f"> {fo_only}\n") == "READY"
    # Tick 474 text still peels.
    assert _icml_ready_status_header(
        '<svg role="img"><text>STATUS: READY</text></svg>\n'
    ) == "READY"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{deco_title_fo}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert not any(
        "<svg" in ln.lower() and "STATUS: READY" in ln
        for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1


def test_icml_ready_status_header_accepts_html_svg_multiline_status() -> None:
    """Tick 476: pretty-printed multi-line ``<svg>…</svg>`` STATUS badges.

    Pre-476 Tick 471–475 required a full-line ``<svg>…</svg>``, so Figma /
    Illustrator / browser "Copy as SVG" exports spanning lines
    (``<svg>\\n  <title>Badge</title>\\n  <text>STATUS: READY</text>\\n</svg>`` /
    multi-line ``<foreignObject><div>STATUS:…</div></foreignObject>``) missed
    demote / G4 pack rewrite — except accidental HTML ``<div>`` allowlist peels
    that rewrote only the inner STATUS line and left broken SVG markup.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _take_icml_status_multiline_svg_block,
    )

    multi_text = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="120" height="24">\n'
        "  <title>Badge</title>\n"
        '  <text x="0" y="16">STATUS: READY</text>\n'
        "</svg>"
    )
    multi_fo = (
        '<svg role="img" xmlns="http://www.w3.org/2000/svg">\n'
        "  <title>Badge_(live)</title>\n"
        '  <foreignObject width="110" height="20">\n'
        '    <div xmlns="http://www.w3.org/1999/xhtml">STATUS: READY</div>\n'
        "  </foreignObject>\n"
        "</svg>"
    )
    multi_prog = (
        '<svg role="img">\n'
        "  <title>draft</title>\n"
        "  <text>**STATUS: IN_PROGRESS**</text>\n"
        "</svg>"
    )
    multi_deco = (
        '<svg xmlns="http://www.w3.org/2000/svg">\n'
        "  <title>Badge</title>\n"
        "  <text>ICML badge</text>\n"
        "</svg>"
    )
    # Single-line still handled by Tick 471–475 (no multi-line take).
    one_line = '<svg role="img"><text>STATUS: READY</text></svg>'

    lines_text = multi_text.splitlines()
    taken = _take_icml_status_multiline_svg_block(lines_text, 0)
    assert taken is not None
    n, collapsed = taken
    assert n == 4
    assert "<text" in collapsed and "STATUS: READY" in collapsed
    assert _take_icml_status_multiline_svg_block([one_line], 0) is None

    assert _icml_ready_status_header(multi_text + "\n") == "READY"
    assert _icml_ready_status_header(multi_fo + "\n") == "READY"
    assert _icml_ready_status_header(multi_prog + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(multi_deco + "\n") is None
    assert _icml_ready_status_header(one_line + "\n") == "READY"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{multi_text}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    # Whole SVG block replaced (not an inner-line rewrite leaving broken markup).
    assert "<svg" not in demoted.lower()
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    # Decorative multi-line SVG must stay pretty-printed when demote prepends.
    deco_prose = (
        "# Title\n\n"
        f"{multi_deco}\n\n"
        "Do not set STATUS: READY until criteria pass.\n"
    )
    demoted_deco = _demote_icml_ready_status(deco_prose)
    assert "  <title>Badge</title>" in demoted_deco
    assert "  <text>ICML badge</text>" in demoted_deco


def test_icml_ready_status_header_accepts_html_img_multiline_status() -> None:
    """Tick 477: pretty-printed multi-line ``<img …>`` STATUS badges.

    Pre-477 Tick 468–470 required a full-line ``<img …>``, so Notion / Docs /
    Prettier / browser HTML-format exports spanning lines
    (``<img\\n  alt="STATUS: READY"\\n  src="…"/>`` /
    ``<img\\n  title="**STATUS: READY**"\\n  src="…">``) missed demote /
    G4 pack rewrite after Tick 476 only collapsed multi-line ``<svg>``.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _take_icml_status_multiline_img_block,
    )

    multi_alt = (
        "<img\n"
        '  alt="STATUS: READY"\n'
        '  src="https://img.shields.io/badge/status-ready-green.svg"\n'
        "/>"
    )
    multi_title = (
        "<img\n"
        '  title="**STATUS: READY**"\n'
        '  src="https://cdn.example/badge_(live).svg"\n'
        ">"
    )
    multi_aria = (
        "<img\n"
        '  aria-label="STATUS: READY"\n'
        '  alt="badge"\n'
        '  src="https://x.com/b.svg"\n'
        "/>"
    )
    multi_prog = (
        "<img\n"
        '  alt="STATUS: IN_PROGRESS"\n'
        '  src="https://img.shields.io/badge/status-wip-yellow.svg"\n'
        "/>"
    )
    multi_deco = (
        "<img\n"
        '  alt="ICML badge"\n'
        '  src="https://x.com/b.svg"\n'
        "/>"
    )
    # Single-line still handled by Tick 468–470 (no multi-line take).
    one_line = '<img alt="STATUS: READY" src="https://x.com/b.svg" />'

    lines_alt = multi_alt.splitlines()
    taken = _take_icml_status_multiline_img_block(lines_alt, 0)
    assert taken is not None
    n, collapsed = taken
    assert n == 4
    assert 'alt="STATUS: READY"' in collapsed
    assert _take_icml_status_multiline_img_block([one_line], 0) is None
    # Blank mid-tag must not collapse.
    assert (
        _take_icml_status_multiline_img_block(
            ["<img", "", 'alt="STATUS: READY"', "/>"], 0
        )
        is None
    )

    assert _icml_ready_status_header(multi_alt + "\n") == "READY"
    assert _icml_ready_status_header(multi_title + "\n") == "READY"
    assert _icml_ready_status_header(multi_aria + "\n") == "READY"
    assert _icml_ready_status_header(multi_prog + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(multi_deco + "\n") is None
    assert _icml_ready_status_header(one_line + "\n") == "READY"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{multi_alt}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    # Whole img block replaced (not an inner-attr rewrite leaving broken markup).
    assert "<img" not in demoted.lower()
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    # Decorative multi-line img must stay pretty-printed when demote prepends.
    deco_prose = (
        "# Title\n\n"
        f"{multi_deco}\n\n"
        "Do not set STATUS: READY until criteria pass.\n"
    )
    demoted_deco = _demote_icml_ready_status(deco_prose)
    assert '  alt="ICML badge"' in demoted_deco
    assert '  src="https://x.com/b.svg"' in demoted_deco


def test_icml_ready_status_header_accepts_html_picture_img_multiline_status() -> None:
    """Tick 478: mid-line ``<img`` after ``<picture>``/``<source>`` multiline.

    Pre-478 Tick 477 required ``^<img`` at line start, so Notion / Docs /
    Prettier exports that open the img mid-line after wrappers
    (``<picture><source…><img\\n  alt="STATUS: READY"\\n  src="…"/>\\n</picture>``)
    missed demote / G4 pack rewrite after Tick 469 single-line picture +
    Tick 477 line-start multiline img.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _take_icml_status_multiline_img_block,
    )

    picture_ml = (
        '<picture><source srcset="https://cdn.example/badge_(live).webp" '
        'type="image/webp"><img\n'
        '  alt="STATUS: READY"\n'
        '  src="https://img.shields.io/badge/status-ready-green.svg"\n'
        "/></picture>"
    )
    picture_title = (
        "<picture><img\n"
        '  title="**STATUS: READY**"\n'
        '  src="https://cdn.example/badge_(live).svg"\n'
        "></picture>"
    )
    figure_ml = (
        "<figure><img\n"
        '  aria-label="STATUS: READY"\n'
        '  alt="badge"\n'
        '  src="https://x.com/b.svg"\n'
        "/></figure>"
    )
    picture_prog = (
        '<picture><source srcset="a.webp"><img\n'
        '  alt="STATUS: IN_PROGRESS"\n'
        '  src="https://img.shields.io/badge/status-wip-yellow.svg"\n'
        "/></picture>"
    )
    # Single-line picture+img still handled by Tick 469 (no multi-line take).
    one_line = (
        '<picture><img alt="STATUS: READY" '
        'src="https://x.com/b.svg" /></picture>'
    )

    lines = picture_ml.splitlines()
    taken = _take_icml_status_multiline_img_block(lines, 0)
    assert taken is not None
    n, collapsed = taken
    assert n == 4
    assert 'alt="STATUS: READY"' in collapsed
    assert "<picture>" in collapsed.lower()
    assert _take_icml_status_multiline_img_block([one_line], 0) is None
    # Blank mid-tag must not collapse (Tick 477 parity).
    assert (
        _take_icml_status_multiline_img_block(
            [
                '<picture><source srcset="a.webp"><img',
                "",
                'alt="STATUS: READY"',
                "/></picture>",
            ],
            0,
        )
        is None
    )

    assert _icml_ready_status_header(picture_ml + "\n") == "READY"
    assert _icml_ready_status_header(picture_title + "\n") == "READY"
    assert _icml_ready_status_header(figure_ml + "\n") == "READY"
    assert _icml_ready_status_header(picture_prog + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(one_line + "\n") == "READY"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{picture_ml}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    # Whole picture+img block replaced (not an inner-line rewrite).
    assert "<img" not in demoted.lower()
    assert "<picture" not in demoted.lower()
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1


def test_icml_ready_status_header_accepts_html_svg_inline_multiline_status() -> None:
    """Tick 479: mid-line ``<svg`` after ``<div>``/``<a>``/``<figure>`` multiline.

    Pre-479 Tick 476 required ``^<svg`` at line start, so Notion / Docs /
    Figma exports that open the svg mid-line after wrappers
    (``<div role="img"><svg\\n  aria-label="STATUS: READY"\\n>…</svg></div>``)
    missed demote / G4 pack rewrite after Tick 476 line-start multiline svg
    + Tick 478 mid-line img twin.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _take_icml_status_multiline_svg_block,
    )

    div_ml = (
        '<div role="img"><svg\n'
        '  aria-label="STATUS: READY"\n'
        '  width="120" height="20">\n'
        "<title>Badge</title>\n"
        "</svg></div>"
    )
    a_ml = (
        '<a href="https://img.shields.io/badge/status-ready-green"><svg\n'
        '  role="img"\n'
        '  aria-label="**STATUS: READY**"\n'
        ">\n"
        "<title>x</title>\n"
        "</svg></a>"
    )
    figure_ml = (
        '<figure class="badge"><svg\n'
        '  title="STATUS: READY"\n'
        ">\n"
        "<desc>ICML</desc>\n"
        "</svg></figure>"
    )
    div_prog = (
        '<div role="img"><svg\n'
        '  aria-label="STATUS: IN_PROGRESS"\n'
        ">\n"
        "<title>WIP</title>\n"
        "</svg></div>"
    )
    # Single-line wrapped svg still handled by Tick 471–475 + allowlist strip.
    one_line = (
        '<div role="img"><svg aria-label="STATUS: READY" width="1">'
        "<title>B</title></svg></div>"
    )
    # Line-start multiline (Tick 476) still collapses.
    line_start = (
        "<svg\n"
        '  aria-label="STATUS: READY"\n'
        ">\n"
        "<title>Badge</title>\n"
        "</svg>"
    )

    lines = div_ml.splitlines()
    taken = _take_icml_status_multiline_svg_block(lines, 0)
    assert taken is not None
    n, collapsed = taken
    assert n == 5
    assert 'aria-label="STATUS: READY"' in collapsed
    assert "<div" in collapsed.lower()
    assert _take_icml_status_multiline_svg_block([one_line], 0) is None
    ls_taken = _take_icml_status_multiline_svg_block(line_start.splitlines(), 0)
    assert ls_taken is not None

    assert _icml_ready_status_header(div_ml + "\n") == "READY"
    assert _icml_ready_status_header(a_ml + "\n") == "READY"
    assert _icml_ready_status_header(figure_ml + "\n") == "READY"
    assert _icml_ready_status_header(div_prog + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(one_line + "\n") == "READY"
    assert _icml_ready_status_header(line_start + "\n") == "READY"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{div_ml}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    # Whole wrapper+svg block replaced (not an inner-line rewrite).
    assert "<svg" not in demoted.lower()
    assert "<div" not in demoted.lower()
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1


def test_icml_ready_status_header_accepts_md_link_softwrap_status() -> None:
    """Tick 480: soft-wrapped markdown link/image STATUS badges.

    Pre-480 Tick 465–467 required a single-line ``[…](…)`` / ``![…](…)``, so
    Prettier / GitHub / MD soft-wrap exports spanning lines
    (``![STATUS: READY](\\nhttps://…/badge.svg)`` /
    ``[**STATUS: READY**](\\nhttps://x.com/foo_(bar))`` /
    ``![STATUS: READY]\\n(https://…)``) missed demote / G4 pack rewrite after
    Tick 476–479 only collapsed multi-line HTML ``<svg>`` / ``<img>``.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _take_icml_status_multiline_md_link_block,
    )

    img_paren = (
        "![STATUS: READY](\n"
        "https://img.shields.io/badge/status-ready-green.svg)"
    )
    link_nested = (
        "[**STATUS: READY**](\n"
        "https://x.com/foo_(bar))"
    )
    img_split_paren = (
        "![STATUS: READY]\n"
        "(https://cdn.example/badge_(live).svg)"
    )
    img_prog = (
        "![STATUS: IN_PROGRESS](\n"
        "https://img.shields.io/badge/status-wip-yellow.svg)"
    )
    # Single-line still handled by Tick 465–467 (no multi-line take).
    one_line = "![STATUS: READY](https://img.shields.io/badge/status-ready-green.svg)"
    # Incomplete / blank mid-block must not collapse.
    incomplete = "![STATUS: READY](\nhttps://example.com/badge.svg"
    blank_mid = "![STATUS: READY](\n\nhttps://example.com/badge.svg)"

    lines = img_paren.splitlines()
    taken = _take_icml_status_multiline_md_link_block(lines, 0)
    assert taken is not None
    n, collapsed = taken
    assert n == 2
    assert collapsed == (
        "![STATUS: READY](https://img.shields.io/badge/status-ready-green.svg)"
    )
    assert _take_icml_status_multiline_md_link_block([one_line], 0) is None
    assert _take_icml_status_multiline_md_link_block(incomplete.splitlines(), 0) is None
    assert _take_icml_status_multiline_md_link_block(blank_mid.splitlines(), 0) is None

    split_taken = _take_icml_status_multiline_md_link_block(
        img_split_paren.splitlines(), 0
    )
    assert split_taken is not None
    assert split_taken[1] == "![STATUS: READY](https://cdn.example/badge_(live).svg)"

    nested_taken = _take_icml_status_multiline_md_link_block(
        link_nested.splitlines(), 0
    )
    assert nested_taken is not None
    assert nested_taken[1] == "[**STATUS: READY**](https://x.com/foo_(bar))"

    assert _icml_ready_status_header(img_paren + "\n") == "READY"
    assert _icml_ready_status_header(link_nested + "\n") == "READY"
    assert _icml_ready_status_header(img_split_paren + "\n") == "READY"
    assert _icml_ready_status_header(img_prog + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(one_line + "\n") == "READY"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{img_paren}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    # Whole soft-wrapped image block replaced (not prepend-only leaving READY alt).
    assert "![STATUS: READY]" not in demoted
    assert "STATUS: READY](" not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    # Nested-paren soft-wrap link demotes similarly.
    link_prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{link_nested}\n"
    )
    demoted_link = _demote_icml_ready_status(link_prose)
    assert _icml_ready_status_header(demoted_link) == "IN_PROGRESS"
    assert "[**STATUS: READY**]" not in demoted_link


def test_icml_ready_status_header_accepts_html_a_title_aria_status() -> None:
    """Tick 481: HTML ``<a>``/``<button>`` title/aria-label STATUS badges.

    Pre-481 Tick 465 allowlist-stripped ``a``/``button`` to *inner text only*,
    so Notion / Docs / GitHub a11y badge exports whose STATUS lives only in
    quoted ``title=`` / ``aria-label=`` with decorative body
    (``<a href="…" title="STATUS: READY">badge</a>`` /
    ``<button aria-label="STATUS: READY">Go</button>`` /
    Prettier multi-line ``<a\\n  title="STATUS: READY"\\n>badge</a>``)
    missed demote / G4 pack rewrite after Tick 470/472 covered the same
    attrs on ``<img>``/``<svg>``.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_a_title,
        _take_icml_status_multiline_a_block,
    )

    flat_a = '<a href="https://x" title="STATUS: READY">badge</a>'
    aria_a = '<a href="#" aria-label="**STATUS: READY**">Go</a>'
    btn = '<button aria-label="STATUS: READY">Go</button>'
    btn_title = '<button title="STATUS: IN_PROGRESS">x</button>'
    body_only = '<a href="#">STATUS: READY</a>'
    deco_title_body = '<a title="Click me" href="#">STATUS: READY</a>'
    soft = (
        "<a\n"
        '  href="https://x"\n'
        '  title="STATUS: READY"\n'
        ">badge</a>"
    )
    soft_btn = (
        "<button\n"
        '  aria-label="STATUS: READY"\n'
        ">Go</button>"
    )
    wrapped = '<p><a href="#" title="STATUS: READY">badge</a></p>'
    one_line_complete = flat_a
    incomplete = "<a\n  title=\"STATUS: READY\""
    blank_mid = "<a\n\n  title=\"STATUS: READY\">badge</a>"

    assert _peel_icml_status_html_a_title(flat_a) == "STATUS: READY"
    assert _peel_icml_status_html_a_title(aria_a) == "**STATUS: READY**"
    assert _peel_icml_status_html_a_title(btn) == "STATUS: READY"
    assert _peel_icml_status_html_a_title(btn_title) == "STATUS: IN_PROGRESS"
    assert _peel_icml_status_html_a_title(body_only) is None
    assert _peel_icml_status_html_a_title(deco_title_body) is None
    assert _peel_icml_status_html_a_title(wrapped) == "STATUS: READY"

    assert _take_icml_status_multiline_a_block([one_line_complete], 0) is None
    taken = _take_icml_status_multiline_a_block(soft.splitlines(), 0)
    assert taken is not None
    n, collapsed = taken
    assert n == 4
    assert 'title="STATUS: READY"' in collapsed
    assert _peel_icml_status_html_a_title(collapsed) == "STATUS: READY"
    assert _take_icml_status_multiline_a_block(incomplete.splitlines(), 0) is None
    assert _take_icml_status_multiline_a_block(blank_mid.splitlines(), 0) is None

    assert _icml_ready_status_header(flat_a + "\n") == "READY"
    assert _icml_ready_status_header(aria_a + "\n") == "READY"
    assert _icml_ready_status_header(btn + "\n") == "READY"
    assert _icml_ready_status_header(btn_title + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(body_only + "\n") == "READY"
    assert _icml_ready_status_header(deco_title_body + "\n") == "READY"
    assert _icml_ready_status_header(soft + "\n") == "READY"
    assert _icml_ready_status_header(soft_btn + "\n") == "READY"
    assert _icml_ready_status_header(wrapped + "\n") == "READY"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{soft}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert 'title="STATUS: READY"' not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    prose_btn = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{btn}\n"
    )
    demoted_btn = _demote_icml_ready_status(prose_btn)
    assert _icml_ready_status_header(demoted_btn) == "IN_PROGRESS"
    assert "aria-label=\"STATUS: READY\"" not in demoted_btn


def test_icml_ready_status_header_accepts_html_span_label_title_aria_status() -> None:
    """Tick 482: HTML span/label/div/summary title/aria-label STATUS badges.

    Pre-482 Tick 465–481 allowlist-stripped these tags to *inner text only*,
    and Tick 481 only peeled ``a``/``button`` attrs, so Notion / Docs /
    GitHub a11y badge exports whose STATUS lives only in quoted ``title=`` /
    ``aria-label=`` with decorative body
    (``<span title="STATUS: READY">badge</span>`` /
    ``<label aria-label="STATUS: READY">x</label>`` /
    Prettier multi-line ``<span\\n  title="STATUS: READY"\\n>badge</span>``)
    missed demote / G4 pack rewrite.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_span_title,
        _take_icml_status_multiline_span_block,
    )

    flat_span = '<span title="STATUS: READY">badge</span>'
    aria_label = '<label aria-label="**STATUS: READY**">x</label>'
    div_role = '<div role="status" title="STATUS: READY">…</div>'
    summary = '<summary title="STATUS: IN_PROGRESS">Details</summary>'
    body_only = "<span>STATUS: READY</span>"
    deco_title_body = '<span title="Click me">STATUS: READY</span>'
    soft = (
        "<span\n"
        '  title="STATUS: READY"\n'
        ">badge</span>"
    )
    soft_label = (
        "<label\n"
        '  aria-label="STATUS: READY"\n'
        ">x</label>"
    )
    wrapped = '<p><span title="STATUS: READY">badge</span></p>'
    incomplete = "<span\n  title=\"STATUS: READY\""
    blank_mid = "<span\n\n  title=\"STATUS: READY\">badge</span>"

    assert _peel_icml_status_html_span_title(flat_span) == "STATUS: READY"
    assert _peel_icml_status_html_span_title(aria_label) == "**STATUS: READY**"
    assert _peel_icml_status_html_span_title(div_role) == "STATUS: READY"
    assert _peel_icml_status_html_span_title(summary) == "STATUS: IN_PROGRESS"
    assert _peel_icml_status_html_span_title(body_only) is None
    assert _peel_icml_status_html_span_title(deco_title_body) is None
    assert _peel_icml_status_html_span_title(wrapped) == "STATUS: READY"

    assert _take_icml_status_multiline_span_block([flat_span], 0) is None
    taken = _take_icml_status_multiline_span_block(soft.splitlines(), 0)
    assert taken is not None
    n, collapsed = taken
    assert n == 3
    assert 'title="STATUS: READY"' in collapsed
    assert _peel_icml_status_html_span_title(collapsed) == "STATUS: READY"
    assert _take_icml_status_multiline_span_block(incomplete.splitlines(), 0) is None
    assert _take_icml_status_multiline_span_block(blank_mid.splitlines(), 0) is None

    assert _icml_ready_status_header(flat_span + "\n") == "READY"
    assert _icml_ready_status_header(aria_label + "\n") == "READY"
    assert _icml_ready_status_header(div_role + "\n") == "READY"
    assert _icml_ready_status_header(summary + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(body_only + "\n") == "READY"
    assert _icml_ready_status_header(deco_title_body + "\n") == "READY"
    assert _icml_ready_status_header(soft + "\n") == "READY"
    assert _icml_ready_status_header(soft_label + "\n") == "READY"
    assert _icml_ready_status_header(wrapped + "\n") == "READY"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{soft}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert 'title="STATUS: READY"' not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    prose_label = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{aria_label}\n"
    )
    demoted_label = _demote_icml_ready_status(prose_label)
    assert _icml_ready_status_header(demoted_label) == "IN_PROGRESS"
    assert 'aria-label="**STATUS: READY**"' not in demoted_label


def test_icml_ready_status_header_accepts_html_inline_title_aria_status() -> None:
    """Tick 483: HTML p/strong/h1/td/… title/aria-label STATUS badges.

    Pre-483 Tick 465–482 allowlist-stripped remaining formatting / container /
    table / semantic tags to *inner text only*, and Tick 482 only peeled
    ``span``/``label``/``div``/``summary``/``figcaption``/``mark`` attrs, so
    Notion / Docs / GitHub a11y badge exports whose STATUS lives only in
    quoted ``title=`` / ``aria-label=`` with decorative body
    (``<p title="STATUS: READY">badge</p>`` /
    ``<strong aria-label="STATUS: READY">x</strong>`` /
    ``<h1 title="STATUS: READY">Badge</h1>`` /
    Prettier ``<p\\n  title="STATUS: READY"\\n>badge</p>``)
    missed demote / G4 pack rewrite.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_inline_title,
        _take_icml_status_multiline_inline_block,
    )

    flat_p = '<p title="STATUS: READY">badge</p>'
    strong_aria = '<strong aria-label="**STATUS: READY**">x</strong>'
    h1_title = '<h1 title="STATUS: READY">Badge</h1>'
    td_title = '<td title="STATUS: READY">badge</td>'
    section_aria = '<section aria-label="STATUS: READY">…</section>'
    li_title = '<li title="STATUS: IN_PROGRESS">item</li>'
    body_only = "<p>STATUS: READY</p>"
    deco_title_body = '<p title="Click me">STATUS: READY</p>'
    soft = (
        "<p\n"
        '  title="STATUS: READY"\n'
        ">badge</p>"
    )
    soft_strong = (
        "<strong\n"
        '  aria-label="STATUS: READY"\n'
        ">x</strong>"
    )
    wrapped = '<div><p title="STATUS: READY">badge</p></div>'
    incomplete = "<p\n  title=\"STATUS: READY\""
    blank_mid = "<p\n\n  title=\"STATUS: READY\">badge</p>"

    assert _peel_icml_status_html_inline_title(flat_p) == "STATUS: READY"
    assert _peel_icml_status_html_inline_title(strong_aria) == "**STATUS: READY**"
    assert _peel_icml_status_html_inline_title(h1_title) == "STATUS: READY"
    assert _peel_icml_status_html_inline_title(td_title) == "STATUS: READY"
    assert _peel_icml_status_html_inline_title(section_aria) == "STATUS: READY"
    assert _peel_icml_status_html_inline_title(li_title) == "STATUS: IN_PROGRESS"
    assert _peel_icml_status_html_inline_title(body_only) is None
    assert _peel_icml_status_html_inline_title(deco_title_body) is None
    assert _peel_icml_status_html_inline_title(wrapped) == "STATUS: READY"
    # Tick 482 span tags must not be claimed by the Tick 483 inline peeler.
    assert (
        _peel_icml_status_html_inline_title(
            '<span title="STATUS: READY">badge</span>'
        )
        is None
    )

    assert _take_icml_status_multiline_inline_block([flat_p], 0) is None
    taken = _take_icml_status_multiline_inline_block(soft.splitlines(), 0)
    assert taken is not None
    n, collapsed = taken
    assert n == 3
    assert 'title="STATUS: READY"' in collapsed
    assert _peel_icml_status_html_inline_title(collapsed) == "STATUS: READY"
    assert _take_icml_status_multiline_inline_block(incomplete.splitlines(), 0) is None
    assert _take_icml_status_multiline_inline_block(blank_mid.splitlines(), 0) is None

    assert _icml_ready_status_header(flat_p + "\n") == "READY"
    assert _icml_ready_status_header(strong_aria + "\n") == "READY"
    assert _icml_ready_status_header(h1_title + "\n") == "READY"
    assert _icml_ready_status_header(td_title + "\n") == "READY"
    assert _icml_ready_status_header(section_aria + "\n") == "READY"
    assert _icml_ready_status_header(li_title + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(body_only + "\n") == "READY"
    assert _icml_ready_status_header(deco_title_body + "\n") == "READY"
    assert _icml_ready_status_header(soft + "\n") == "READY"
    assert _icml_ready_status_header(soft_strong + "\n") == "READY"
    assert _icml_ready_status_header(wrapped + "\n") == "READY"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{soft}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert 'title="STATUS: READY"' not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    prose_strong = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{strong_aria}\n"
    )
    demoted_strong = _demote_icml_ready_status(prose_strong)
    assert _icml_ready_status_header(demoted_strong) == "IN_PROGRESS"
    assert 'aria-label="**STATUS: READY**"' not in demoted_strong

    prose_h1 = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{h1_title}\n"
    )
    demoted_h1 = _demote_icml_ready_status(prose_h1)
    assert _icml_ready_status_header(demoted_h1) == "IN_PROGRESS"
    assert 'title="STATUS: READY"' not in demoted_h1


def test_icml_ready_status_header_accepts_html_aria_description_status() -> None:
    """Tick 484: HTML aria-description STATUS on allowlisted a11y badges.

    Pre-484 Tick 481–483 peeled ``title=`` / ``aria-label=`` only, so Notion /
    Docs / GitHub a11y long-description badge exports whose STATUS lives only
    in ``aria-description=`` with decorative body
    (``<p aria-description="STATUS: READY">badge</p>`` /
    ``<span aria-description="STATUS: READY">x</span>`` /
    ``<a aria-description="STATUS: READY">Go</a>`` /
    ``<img aria-description="STATUS: READY" src="…">`` /
    Prettier ``<p\\n  aria-description="STATUS: READY"\\n>badge</p>``)
    still collapsed to decorative body after allowlist strip and missed
    demote / G4 pack rewrite.
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_a_title,
        _peel_icml_status_html_img_alt,
        _peel_icml_status_html_inline_title,
        _peel_icml_status_html_span_title,
        _peel_icml_status_html_svg_title,
        _take_icml_status_multiline_inline_block,
    )

    flat_p = '<p aria-description="STATUS: READY">badge</p>'
    span_desc = '<span aria-description="STATUS: READY">x</span>'
    a_desc = '<a aria-description="STATUS: READY">Go</a>'
    strong_desc = '<strong aria-description="**STATUS: READY**">x</strong>'
    img_desc = '<img aria-description="STATUS: READY" src="https://x.com/b.svg">'
    svg_desc = (
        '<svg aria-description="STATUS: READY"><title>Badge</title></svg>'
    )
    prog = '<p aria-description="STATUS: IN_PROGRESS">badge</p>'
    body_only = "<p>STATUS: READY</p>"
    deco_desc_body = '<p aria-description="Click me">STATUS: READY</p>'
    title_wins = (
        '<p title="STATUS: IN_PROGRESS" '
        'aria-description="STATUS: READY">badge</p>'
    )
    label_wins = (
        '<p aria-label="STATUS: IN_PROGRESS" '
        'aria-description="STATUS: READY">badge</p>'
    )
    soft = (
        "<p\n"
        '  aria-description="STATUS: READY"\n'
        ">badge</p>"
    )

    assert _peel_icml_status_html_inline_title(flat_p) == "STATUS: READY"
    assert _peel_icml_status_html_span_title(span_desc) == "STATUS: READY"
    assert _peel_icml_status_html_a_title(a_desc) == "STATUS: READY"
    assert _peel_icml_status_html_inline_title(strong_desc) == "**STATUS: READY**"
    assert _peel_icml_status_html_img_alt(img_desc) == "STATUS: READY"
    assert _peel_icml_status_html_svg_title(svg_desc) == "STATUS: READY"
    assert _peel_icml_status_html_inline_title(prog) == "STATUS: IN_PROGRESS"
    assert _peel_icml_status_html_inline_title(body_only) is None
    assert _peel_icml_status_html_inline_title(deco_desc_body) is None
    assert _peel_icml_status_html_inline_title(title_wins) == "STATUS: IN_PROGRESS"
    assert _peel_icml_status_html_inline_title(label_wins) == "STATUS: IN_PROGRESS"

    taken = _take_icml_status_multiline_inline_block(soft.splitlines(), 0)
    assert taken is not None
    n, collapsed = taken
    assert n == 3
    assert 'aria-description="STATUS: READY"' in collapsed
    assert _peel_icml_status_html_inline_title(collapsed) == "STATUS: READY"

    assert _icml_ready_status_header(flat_p + "\n") == "READY"
    assert _icml_ready_status_header(span_desc + "\n") == "READY"
    assert _icml_ready_status_header(a_desc + "\n") == "READY"
    assert _icml_ready_status_header(strong_desc + "\n") == "READY"
    assert _icml_ready_status_header(img_desc + "\n") == "READY"
    assert _icml_ready_status_header(svg_desc + "\n") == "READY"
    assert _icml_ready_status_header(prog + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(soft + "\n") == "READY"
    assert _icml_ready_status_header(title_wins + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(label_wins + "\n") == "IN_PROGRESS"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{soft}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert 'aria-description="STATUS: READY"' not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    prose_span = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{span_desc}\n"
    )
    demoted_span = _demote_icml_ready_status(prose_span)
    assert _icml_ready_status_header(demoted_span) == "IN_PROGRESS"
    assert 'aria-description="STATUS: READY"' not in demoted_span

    prose_a = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{a_desc}\n"
    )
    demoted_a = _demote_icml_ready_status(prose_a)
    assert _icml_ready_status_header(demoted_a) == "IN_PROGRESS"
    assert 'aria-description="STATUS: READY"' not in demoted_a


def test_icml_ready_status_header_accepts_html_entity_colon_status() -> None:
    """Tick 486: HTML-entity STATUS colons (``&#58;`` / ``&colon;`` / ``&#x3a;``).

    Pre-486 Tick 455 decoded only invisibles/nbsp, so CMS/XSS-escaped
    exports whose STATUS separator is an entity (``STATUS&#58; READY`` /
    ``STATUS&colon;READY`` / ``**STATUS&#58; READY**`` /
    ``STATUS&#xff1a;READY`` / ``<p title="STATUS&#58; READY">badge</p>`` /
    Prettier ``<p\\n  title="STATUS&colon; READY"\\n>badge</p>``) missed
    demote / G4 pack rewrite.
    """
    from icml_env_checks import (
        _decode_icml_status_html_entities,
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_inline_title,
        _strip_icml_status_line_noise,
        _take_icml_status_multiline_inline_block,
    )

    assert _decode_icml_status_html_entities("STATUS&#58; READY") == "STATUS: READY"
    assert _decode_icml_status_html_entities("STATUS&colon;READY") == "STATUS:READY"
    assert _decode_icml_status_html_entities("STATUS&#x3a; READY") == "STATUS: READY"
    assert _decode_icml_status_html_entities("STATUS&#x3A;IN_PROGRESS") == (
        "STATUS:IN_PROGRESS"
    )
    assert _decode_icml_status_html_entities("STATUS&#xff1a;READY") == (
        "STATUS\uff1aREADY"
    )
    # Unknown entities still left alone (Tick 455 contract).
    assert _decode_icml_status_html_entities("&amp;**STATUS: READY**") == (
        "&amp;**STATUS: READY**"
    )
    # Prior invisibles/nbsp still decode.
    assert _decode_icml_status_html_entities("**STATUS:&nbsp;READY**") == (
        "**STATUS:\u00a0READY**"
    )

    assert _strip_icml_status_line_noise("STATUS&#58; READY") == "STATUS: READY"
    # Bold wrappers peel after entity decode (Tick 456/453 path).
    assert _strip_icml_status_line_noise("**STATUS&colon; READY**") == "STATUS: READY"
    assert _icml_ready_status_header("STATUS&#58; READY\n") == "READY"
    assert _icml_ready_status_header("STATUS&colon;READY\n") == "READY"
    assert _icml_ready_status_header("**STATUS&#58; READY**\n") == "READY"
    assert _icml_ready_status_header("STATUS&#x3a; IN_PROGRESS\n") == "IN_PROGRESS"
    assert _icml_ready_status_header("STATUS&#xff1a;READY\n") == "READY"
    # Attr peels after entity decode (Tick 483/485 surfaces).
    attr_ent = '<p title="STATUS&#58; READY">badge</p>'
    assert _decode_icml_status_html_entities(attr_ent) == (
        '<p title="STATUS: READY">badge</p>'
    )
    assert (
        _peel_icml_status_html_inline_title(
            _decode_icml_status_html_entities(attr_ent)
        )
        == "STATUS: READY"
    )
    assert _icml_ready_status_header(attr_ent + "\n") == "READY"
    named_attr = '<span aria-label="STATUS&colon; READY">x</span>'
    assert _icml_ready_status_header(named_attr + "\n") == "READY"
    img_ent = '<img alt="STATUS&#58;READY" src="https://x.com/b.svg">'
    assert _icml_ready_status_header(img_ent + "\n") == "READY"
    soft = (
        "<p\n"
        '  title="STATUS&colon; READY"\n'
        ">badge</p>"
    )
    taken = _take_icml_status_multiline_inline_block(soft.splitlines(), 0)
    assert taken is not None
    n, collapsed = taken
    assert n == 3
    assert "STATUS&colon; READY" in collapsed or "STATUS: READY" in (
        _decode_icml_status_html_entities(collapsed)
    )
    assert _icml_ready_status_header(soft + "\n") == "READY"
    # Prior Tick 455 / 485 forms unchanged.
    assert _icml_ready_status_header("**STATUS:&nbsp;READY**\n") == "READY"
    assert _icml_ready_status_header("<p title=STATUS:READY>badge</p>\n") == "READY"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS&#58; READY\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert "&#58;" not in demoted or "STATUS&#58; READY" not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    prose_attr = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{soft}\n"
    )
    demoted_attr = _demote_icml_ready_status(prose_attr)
    assert _icml_ready_status_header(demoted_attr) == "IN_PROGRESS"
    assert "STATUS&colon;" not in demoted_attr
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_attr.splitlines()
    )


def test_icml_ready_status_header_accepts_html_double_escaped_status() -> None:
    """Tick 487: double-escaped HTML STATUS (``&amp;#58;`` / ``&lt;p…&gt;``).

    Pre-487 Tick 486 decoded only a single entity layer, so CMS/XSS
    double-escaped exports (``STATUS&amp;#58; READY`` /
    ``STATUS&amp;colon;READY`` / ``STATUS&#38;#58; READY`` /
    ``&lt;p title=&quot;STATUS: READY&quot;&gt;badge&lt;/p&gt;`` /
    Prettier ``&lt;p\\n  title=&quot;STATUS&amp;colon; READY&quot;\\n&gt;…``)
    missed demote / G4 pack rewrite. Lone ``&amp;**STATUS…`` stays untouched.
    """
    from icml_env_checks import (
        _decode_icml_status_html_entities,
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_inline_title,
        _strip_icml_status_line_noise,
    )

    assert _decode_icml_status_html_entities("STATUS&amp;#58; READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities("STATUS&amp;colon;READY") == (
        "STATUS:READY"
    )
    assert _decode_icml_status_html_entities("STATUS&#38;#58; READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities("STATUS&#x26;#x3a; READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities("STATUS&amp;amp;#58; READY") == (
        "STATUS: READY"
    )
    # Tick 486 unknown-entity contract: lone &amp; before non-entity stays.
    assert _decode_icml_status_html_entities("&amp;**STATUS: READY**") == (
        "&amp;**STATUS: READY**"
    )
    # Escaped HTML badge → real tags.
    esc = "&lt;p title=&quot;STATUS: READY&quot;&gt;badge&lt;/p&gt;"
    assert _decode_icml_status_html_entities(esc) == (
        '<p title="STATUS: READY">badge</p>'
    )
    assert (
        _peel_icml_status_html_inline_title(_decode_icml_status_html_entities(esc))
        == "STATUS: READY"
    )
    # Combined double-amp colon inside escaped attr.
    esc_colon = (
        "&lt;p title=&quot;STATUS&amp;colon; READY&quot;&gt;badge&lt;/p&gt;"
    )
    assert _decode_icml_status_html_entities(esc_colon) == (
        '<p title="STATUS: READY">badge</p>'
    )

    assert _strip_icml_status_line_noise("STATUS&amp;#58; READY") == "STATUS: READY"
    assert _icml_ready_status_header("STATUS&amp;#58; READY\n") == "READY"
    assert _icml_ready_status_header("STATUS&amp;colon;READY\n") == "READY"
    assert _icml_ready_status_header("STATUS&#38;#58; IN_PROGRESS\n") == (
        "IN_PROGRESS"
    )
    assert _icml_ready_status_header(esc + "\n") == "READY"
    assert _icml_ready_status_header(esc_colon + "\n") == "READY"
    # Numeric lt/gt/quot.
    num_esc = "&#60;p title=&#34;STATUS: READY&#34;&#62;badge&#60;/p&#62;"
    assert _icml_ready_status_header(num_esc + "\n") == "READY"
    # Prior Tick 486 forms unchanged.
    assert _icml_ready_status_header("STATUS&#58; READY\n") == "READY"
    assert _icml_ready_status_header("<p title=STATUS:READY>badge</p>\n") == "READY"
    # Lone &amp;**STATUS still not a false READY header by itself when
    # wrapped as the only candidate — leading &amp; blocks token match.
    assert _icml_ready_status_header("&amp;**STATUS: READY**\n") is None

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS&amp;#58; READY\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "STATUS&amp;#58; READY" not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    prose_esc = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{esc}\n"
    )
    demoted_esc = _demote_icml_ready_status(prose_esc)
    assert _icml_ready_status_header(demoted_esc) == "IN_PROGRESS"
    assert "&lt;p" not in demoted_esc
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_esc.splitlines()
    )


def test_icml_ready_status_header_accepts_js_unicode_escaped_status() -> None:
    """Tick 488: JSON/JS unicode+hex STATUS escapes (``\\u003a`` / ``\\x3a``).

    Pre-488 Tick 487 decoded HTML entities only, so JSON/API/CMS string
    exports (``STATUS\\u003a READY`` / ``STATUS\\x3a READY`` /
    ``STATUS\\u003a\\u0020READY`` /
    ``\\u003cp title=\\u0022STATUS\\u003a READY\\u0022\\u003ebadge\\u003c/p\\u003e`` /
    ``STATUS\\uff1aREADY``) missed demote / G4 pack rewrite. Unknown
    ``\\u0041`` stays literal (no false STATUS token). Lone
    ``&amp;**STATUS…`` contract preserved.
    """
    from icml_env_checks import (
        _decode_icml_status_html_entities,
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_inline_title,
        _strip_icml_status_line_noise,
    )

    assert _decode_icml_status_html_entities(r"STATUS\u003a READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities(r"STATUS\u003A READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities(r"STATUS\x3a READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities(r"STATUS\x3A READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities(r"STATUS\u003a\u0020READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities(r"STATUS\uff1aREADY") == (
        "STATUS：READY"
    )
    # Unknown codepoint stays literal (cannot invent STATUS).
    assert _decode_icml_status_html_entities(r"STATUS\u0041 READY") == (
        r"STATUS\u0041 READY"
    )
    # Tick 486/487 contracts unchanged.
    assert _decode_icml_status_html_entities("&amp;**STATUS: READY**") == (
        "&amp;**STATUS: READY**"
    )
    assert _decode_icml_status_html_entities("STATUS&amp;#58; READY") == (
        "STATUS: READY"
    )
    # JSON-escaped HTML badge → real tags → peelable title.
    esc = (
        r"\u003cp title=\u0022STATUS\u003a READY\u0022\u003e"
        r"badge\u003c/p\u003e"
    )
    assert _decode_icml_status_html_entities(esc) == (
        '<p title="STATUS: READY">badge</p>'
    )
    assert (
        _peel_icml_status_html_inline_title(_decode_icml_status_html_entities(esc))
        == "STATUS: READY"
    )

    assert _strip_icml_status_line_noise(r"STATUS\u003a READY") == "STATUS: READY"
    assert _icml_ready_status_header(r"STATUS\u003a READY" + "\n") == "READY"
    assert _icml_ready_status_header(r"STATUS\x3a READY" + "\n") == "READY"
    assert _icml_ready_status_header(r"STATUS\u003a\u0020IN_PROGRESS" + "\n") == (
        "IN_PROGRESS"
    )
    assert _icml_ready_status_header(esc + "\n") == "READY"
    assert _icml_ready_status_header(r"STATUS\uff1aREADY" + "\n") == "READY"
    # Unknown escape is not a READY header.
    assert _icml_ready_status_header(r"STATUS\u0041 READY" + "\n") is None
    # Prior Tick 487 forms unchanged.
    assert _icml_ready_status_header("STATUS&amp;#58; READY\n") == "READY"
    assert _icml_ready_status_header("&amp;**STATUS: READY**\n") is None

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        r"STATUS\u003a READY" + "\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert r"STATUS\u003a READY" not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    prose_esc = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{esc}\n"
    )
    demoted_esc = _demote_icml_ready_status(prose_esc)
    assert _icml_ready_status_header(demoted_esc) == "IN_PROGRESS"
    assert r"\u003c" not in demoted_esc
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_esc.splitlines()
    )


def test_icml_ready_status_header_accepts_url_percent_encoded_status() -> None:
    """Tick 489: URL percent-encoded STATUS (``%3A`` / ``%20`` / ``%3C``).

    Pre-489 Tick 488 decoded HTML entities + JS/JSON escapes only, so badge
    URL / query-string / CMS link exports (``STATUS%3A%20READY`` /
    ``STATUS%3A+READY`` / ``STATUS%253A%20READY`` /
    ``%3Cp%20title%3D%22STATUS%3A%20READY%22%3Ebadge%3C%2Fp%3E`` /
    ``STATUS%3AIN_PROGRESS``) missed demote / G4 pack rewrite. Unknown
    ``%41`` stays literal (no false STATUS token). Tick 486/487/488 contracts
    preserved; bare ``STATUS: READY+x`` does not rewrite ``+`` (no ``%XX``).
    """
    from icml_env_checks import (
        _decode_icml_status_html_entities,
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_inline_title,
        _strip_icml_status_line_noise,
    )

    assert _decode_icml_status_html_entities("STATUS%3A READY") == "STATUS: READY"
    assert _decode_icml_status_html_entities("STATUS%3a READY") == "STATUS: READY"
    assert _decode_icml_status_html_entities("STATUS%3A%20READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities("STATUS%3A+READY") == "STATUS: READY"
    assert _decode_icml_status_html_entities("STATUS%3A%2BREADY") == (
        "STATUS: READY"
    )
    # Double-encoded colon: %253A → %3A → :
    assert _decode_icml_status_html_entities("STATUS%253A%20READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities("STATUS%3AIN_PROGRESS") == (
        "STATUS:IN_PROGRESS"
    )
    # Unknown codepoint stays literal (cannot invent STATUS).
    assert _decode_icml_status_html_entities("STATUS%41 READY") == (
        "STATUS%41 READY"
    )
    # Bare + without percent-encoding stays literal.
    assert _decode_icml_status_html_entities("STATUS: READY+note") == (
        "STATUS: READY+note"
    )
    # Tick 486/487/488 contracts unchanged.
    assert _decode_icml_status_html_entities("&amp;**STATUS: READY**") == (
        "&amp;**STATUS: READY**"
    )
    assert _decode_icml_status_html_entities("STATUS&amp;#58; READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities(r"STATUS\u003a READY") == (
        "STATUS: READY"
    )
    # URL-encoded HTML badge → real tags → peelable title.
    esc = "%3Cp%20title%3D%22STATUS%3A%20READY%22%3Ebadge%3C%2Fp%3E"
    assert _decode_icml_status_html_entities(esc) == (
        '<p title="STATUS: READY">badge</p>'
    )
    assert (
        _peel_icml_status_html_inline_title(_decode_icml_status_html_entities(esc))
        == "STATUS: READY"
    )

    assert _strip_icml_status_line_noise("STATUS%3A%20READY") == "STATUS: READY"
    assert _icml_ready_status_header("STATUS%3A%20READY\n") == "READY"
    assert _icml_ready_status_header("STATUS%3A+READY\n") == "READY"
    assert _icml_ready_status_header("STATUS%253A%20READY\n") == "READY"
    assert _icml_ready_status_header("STATUS%3AIN_PROGRESS\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(esc + "\n") == "READY"
    # Unknown escape is not a READY header.
    assert _icml_ready_status_header("STATUS%41 READY\n") is None
    # Prior Tick 486–488 forms unchanged.
    assert _icml_ready_status_header("STATUS&amp;#58; READY\n") == "READY"
    assert _icml_ready_status_header(r"STATUS\u003a READY" + "\n") == "READY"
    assert _icml_ready_status_header("&amp;**STATUS: READY**\n") is None

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS%3A%20READY\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "STATUS%3A%20READY" not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    prose_esc = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{esc}\n"
    )
    demoted_esc = _demote_icml_ready_status(prose_esc)
    assert _icml_ready_status_header(demoted_esc) == "IN_PROGRESS"
    assert "%3C" not in demoted_esc
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_esc.splitlines()
    )


def test_icml_ready_status_header_accepts_quoted_printable_status() -> None:
    """Tick 490: MIME quoted-printable STATUS (``=3A`` / ``=20`` / ``=3C``).

    Pre-490 Tick 489 decoded HTML/JS/URL percent only, so email / MIME / CMS
    QP exports (``STATUS=3A READY`` / ``STATUS=3A=20READY`` /
    ``STATUS=3AIN_PROGRESS`` / ``=3Cp title=3D=22STATUS=3A READY=22=3E…`` /
    soft-break ``STATUS=3A=\\n READY`` / double-encoded ``STATUS=253A=20READY``)
    missed demote / G4 pack rewrite. Unknown ``=41`` stays literal; bare
    ``STATUS: READY=note`` / ``STATUS: a=b`` without allowlisted ``=XX`` stay
    untouched; Tick 486–489 contracts preserved.
    """
    from icml_env_checks import (
        _decode_icml_status_html_entities,
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_inline_title,
        _strip_icml_status_line_noise,
    )

    assert _decode_icml_status_html_entities("STATUS=3A READY") == "STATUS: READY"
    assert _decode_icml_status_html_entities("STATUS=3a READY") == "STATUS: READY"
    assert _decode_icml_status_html_entities("STATUS=3A=20READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities("STATUS=3AIN_PROGRESS") == (
        "STATUS:IN_PROGRESS"
    )
    # Double-encoded colon: =253A → =3A → :
    assert _decode_icml_status_html_entities("STATUS=253A=20READY") == (
        "STATUS: READY"
    )
    # Soft line break within a single decode string.
    assert _decode_icml_status_html_entities("STATUS=3A=\n READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities("STATUS=3A=\r\n READY") == (
        "STATUS: READY"
    )
    # Unknown codepoint stays literal (cannot invent STATUS).
    assert _decode_icml_status_html_entities("STATUS=41 READY") == (
        "STATUS=41 READY"
    )
    # Bare = without allowlisted hex stays literal.
    assert _decode_icml_status_html_entities("STATUS: READY=note") == (
        "STATUS: READY=note"
    )
    assert _decode_icml_status_html_entities("STATUS: a=b") == "STATUS: a=b"
    # Tick 486–489 contracts unchanged.
    assert _decode_icml_status_html_entities("&amp;**STATUS: READY**") == (
        "&amp;**STATUS: READY**"
    )
    assert _decode_icml_status_html_entities("STATUS&amp;#58; READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities(r"STATUS\u003a READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities("STATUS%3A%20READY") == (
        "STATUS: READY"
    )
    # Mixed QP + percent.
    assert _decode_icml_status_html_entities("STATUS=3A%20READY") == (
        "STATUS: READY"
    )
    # QP-encoded HTML badge → real tags → peelable title.
    esc = "=3Cp title=3D=22STATUS=3A READY=22=3Ebadge=3C/p=3E"
    assert _decode_icml_status_html_entities(esc) == (
        '<p title="STATUS: READY">badge</p>'
    )
    assert (
        _peel_icml_status_html_inline_title(_decode_icml_status_html_entities(esc))
        == "STATUS: READY"
    )

    assert _strip_icml_status_line_noise("STATUS=3A=20READY") == "STATUS: READY"
    assert _icml_ready_status_header("STATUS=3A READY\n") == "READY"
    assert _icml_ready_status_header("STATUS=3A=20READY\n") == "READY"
    assert _icml_ready_status_header("STATUS=253A=20READY\n") == "READY"
    assert _icml_ready_status_header("STATUS=3AIN_PROGRESS\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(esc + "\n") == "READY"
    # Soft-break across physical lines (iterator joins).
    assert _icml_ready_status_header("STATUS=3A=\n READY\n") == "READY"
    assert _icml_ready_status_header("STATUS=3A=20=\nREADY\n") == "READY"
    # Unknown escape is not a READY header.
    assert _icml_ready_status_header("STATUS=41 READY\n") is None
    # Prior Tick 486–489 forms unchanged.
    assert _icml_ready_status_header("STATUS&amp;#58; READY\n") == "READY"
    assert _icml_ready_status_header(r"STATUS\u003a READY" + "\n") == "READY"
    assert _icml_ready_status_header("STATUS%3A%20READY\n") == "READY"
    assert _icml_ready_status_header("&amp;**STATUS: READY**\n") is None
    assert _icml_ready_status_header("STATUS: READY=note\n") == "READY"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS=3A=20READY\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "STATUS=3A" not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    prose_soft = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        "STATUS=3A=\n"
        " READY\n"
    )
    demoted_soft = _demote_icml_ready_status(prose_soft)
    assert _icml_ready_status_header(demoted_soft) == "IN_PROGRESS"
    assert "STATUS=3A=" not in demoted_soft
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in demoted_soft.splitlines()
    )

    prose_esc = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{esc}\n"
    )
    demoted_esc = _demote_icml_ready_status(prose_esc)
    assert _icml_ready_status_header(demoted_esc) == "IN_PROGRESS"
    assert "=3C" not in demoted_esc
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_esc.splitlines()
    )


def test_icml_ready_status_header_accepts_rfc2047_encoded_word_status() -> None:
    """Tick 491: RFC 2047 encoded-word STATUS (``=?UTF-8?Q?…?=`` / ``?B?``).

    Pre-491 Tick 490 peeled bare QP ``=XX`` but left MIME encoded-word wrappers
    + Q ``_``-as-space, so email / MIME gateway exports
    (``=?UTF-8?Q?STATUS=3A_READY?=`` / ``=?utf-8?q?STATUS=3A=20READY?=`` /
    ``=?UTF-8?B?U1RBVFVTOiBSRUFEWQ==?=`` / adjacent
    ``=?UTF-8?Q?STATUS=3A_?= =?UTF-8?Q?READY?=`` / Q HTML badge) missed demote /
    G4 pack rewrite. Unknown charset / invalid base64 stay literal; Tick
    486–490 contracts preserved.
    """
    import base64

    from icml_env_checks import (
        _decode_icml_status_html_entities,
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_inline_title,
        _peel_icml_status_rfc2047_encoded_words,
        _strip_icml_status_line_noise,
    )

    q_ready = "=?UTF-8?Q?STATUS=3A_READY?="
    q_ready_lower = "=?utf-8?q?STATUS=3A=20READY?="
    # Literal underscore in IN_PROGRESS must be =5F (Q ``_`` is always space).
    q_prog = "=?UTF-8?Q?STATUS=3A_IN=5FPROGRESS?="
    q_adj = "=?UTF-8?Q?STATUS=3A_?= =?UTF-8?Q?READY?="
    b_ready = "=?UTF-8?B?" + base64.b64encode(b"STATUS: READY").decode("ascii") + "?="
    b_bold = (
        "=?UTF-8?B?"
        + base64.b64encode(b"**STATUS: READY**").decode("ascii")
        + "?="
    )
    q_html = (
        "=?UTF-8?Q?=3Cp_title=3D=22STATUS=3A_READY=22=3Ebadge=3C/p=3E?="
    )
    unknown_cs = "=?X-UNKNOWN?Q?STATUS=3A_READY?="
    bad_b64 = "=?UTF-8?B?!!!!?="

    assert _peel_icml_status_rfc2047_encoded_words(q_ready) == "STATUS=3A READY"
    assert _decode_icml_status_html_entities(q_ready) == "STATUS: READY"
    assert _decode_icml_status_html_entities(q_ready_lower) == "STATUS: READY"
    assert _decode_icml_status_html_entities(q_prog) == "STATUS: IN_PROGRESS"
    assert _decode_icml_status_html_entities(q_adj) == "STATUS: READY"
    assert _decode_icml_status_html_entities(b_ready) == "STATUS: READY"
    assert _decode_icml_status_html_entities(b_bold) == "**STATUS: READY**"
    assert _decode_icml_status_html_entities(q_html) == (
        '<p title="STATUS: READY">badge</p>'
    )
    assert (
        _peel_icml_status_html_inline_title(
            _decode_icml_status_html_entities(q_html)
        )
        == "STATUS: READY"
    )
    # Unknown charset stays wrapped (cannot invent STATUS); inner QP may still
    # peel allowlisted =XX inside the literal word (Tick 490 contract).
    assert _decode_icml_status_html_entities(unknown_cs) == (
        "=?X-UNKNOWN?Q?STATUS:_READY?="
    )
    assert _decode_icml_status_html_entities(bad_b64) == bad_b64
    assert _icml_ready_status_header(unknown_cs + "\n") is None
    assert _icml_ready_status_header(bad_b64 + "\n") is None
    # Tick 486–490 contracts unchanged.
    assert _decode_icml_status_html_entities("STATUS=3A=20READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities("STATUS%3A%20READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities(r"STATUS\u003a READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities("STATUS&amp;#58; READY") == (
        "STATUS: READY"
    )
    assert _decode_icml_status_html_entities("&amp;**STATUS: READY**") == (
        "&amp;**STATUS: READY**"
    )

    assert _strip_icml_status_line_noise(q_ready) == "STATUS: READY"
    assert _icml_ready_status_header(q_ready + "\n") == "READY"
    assert _icml_ready_status_header(q_ready_lower + "\n") == "READY"
    assert _icml_ready_status_header(q_prog + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(q_adj + "\n") == "READY"
    assert _icml_ready_status_header(b_ready + "\n") == "READY"
    assert _icml_ready_status_header(b_bold + "\n") == "READY"
    assert _icml_ready_status_header(q_html + "\n") == "READY"
    assert _icml_ready_status_header(unknown_cs + "\n") is None
    assert _icml_ready_status_header(bad_b64 + "\n") is None
    # Prior Tick 486–490 forms unchanged.
    assert _icml_ready_status_header("STATUS=3A=20READY\n") == "READY"
    assert _icml_ready_status_header("STATUS%3A%20READY\n") == "READY"
    assert _icml_ready_status_header(r"STATUS\u003a READY" + "\n") == "READY"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{q_ready}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "=?UTF-8?Q?" not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    prose_b = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{b_ready}\n"
    )
    demoted_b = _demote_icml_ready_status(prose_b)
    assert _icml_ready_status_header(demoted_b) == "IN_PROGRESS"
    assert "=?UTF-8?B?" not in demoted_b
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted_b.splitlines()
    )

    prose_html = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{q_html}\n"
    )
    demoted_html = _demote_icml_ready_status(prose_html)
    assert _icml_ready_status_header(demoted_html) == "IN_PROGRESS"
    assert "=?UTF-8?Q?" not in demoted_html
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in demoted_html.splitlines()
    )


def test_icml_ready_status_header_accepts_bare_base64_status() -> None:
    """Tick 492: bare base64 STATUS payload (RFC 2047 wrappers stripped).

    Pre-492 Tick 491 peeled ``=?UTF-8?B?…?=`` only, so email / log / chat
    copy-paste of the payload alone (``U1RBVFVTOiBSRUFEWQ==`` /
    ``**U1RBVFVTOiBSRUFEWQ==**`` / bold QP-inside-b64) missed demote / G4
    pack rewrite. Invalid / non-STATUS base64 and QP mid-``=`` forms stay
    literal; Tick 486–491 contracts preserved.
    """
    import base64

    from icml_env_checks import (
        _decode_icml_status_html_entities,
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_bare_base64,
        _strip_icml_status_line_noise,
    )

    bare_ready = base64.b64encode(b"STATUS: READY").decode("ascii")
    bare_prog = base64.b64encode(b"STATUS: IN_PROGRESS").decode("ascii")
    bare_bold = base64.b64encode(b"**STATUS: READY**").decode("ascii")
    bare_qp = base64.b64encode(b"STATUS=3A=20READY").decode("ascii")
    junk = base64.b64encode(b"hello world!!").decode("ascii")
    # Mid-string ``=`` is QP, not bare base64 (validate rejects).
    qp_literal = "STATUS=3A=20READY"

    assert _peel_icml_status_bare_base64(bare_ready) == "STATUS: READY"
    assert _decode_icml_status_html_entities(bare_ready) == "STATUS: READY"
    assert _decode_icml_status_html_entities(bare_prog) == "STATUS: IN_PROGRESS"
    assert _decode_icml_status_html_entities(bare_bold) == "**STATUS: READY**"
    assert _decode_icml_status_html_entities(bare_qp) == "STATUS: READY"
    assert _peel_icml_status_bare_base64(junk) == junk
    assert _decode_icml_status_html_entities(junk) == junk
    # Tick 490 QP contract unchanged (not mistaken for bare base64).
    assert _decode_icml_status_html_entities(qp_literal) == "STATUS: READY"
    assert _peel_icml_status_bare_base64(qp_literal) == qp_literal
    # Tick 491 wrapped B-encoding still works.
    wrapped = (
        "=?UTF-8?B?"
        + base64.b64encode(b"STATUS: READY").decode("ascii")
        + "?="
    )
    assert _decode_icml_status_html_entities(wrapped) == "STATUS: READY"

    assert _strip_icml_status_line_noise(bare_ready) == "STATUS: READY"
    assert _strip_icml_status_line_noise(f"**{bare_ready}**") == "STATUS: READY"
    assert _icml_ready_status_header(bare_ready + "\n") == "READY"
    assert _icml_ready_status_header(bare_prog + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(f"**{bare_ready}**\n") == "READY"
    assert _icml_ready_status_header(bare_qp + "\n") == "READY"
    assert _icml_ready_status_header(junk + "\n") is None

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{bare_ready}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert bare_ready not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    prose_bold = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"**{bare_ready}**\n"
    )
    demoted_bold = _demote_icml_ready_status(prose_bold)
    assert _icml_ready_status_header(demoted_bold) == "IN_PROGRESS"
    assert bare_ready not in demoted_bold
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in demoted_bold.splitlines()
    )


def test_icml_ready_status_header_accepts_data_uri_base64_status() -> None:
    """Tick 493: data-URI base64 STATUS payload (RFC 2397 wrapper kept).

    Pre-493 Tick 492 peeled bare base64 only, so chat / email / Markdown
    badge paste of ``data:text/plain;base64,U1RBVFVTOiBSRUFEWQ==`` /
    ``data:text/plain;charset=utf-8;base64,…`` / ``data:;base64,…`` /
    bold-wrapped ``**data:…;base64,…**`` / data-URI-of-QP missed demote /
    G4 pack rewrite. Non-base64 data URIs, invalid / non-STATUS payloads,
    and Tick 486–492 contracts stay untouched.
    """
    import base64

    from icml_env_checks import (
        _decode_icml_status_html_entities,
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_bare_base64,
        _peel_icml_status_data_uri_base64,
        _strip_icml_status_line_noise,
    )

    bare_ready = base64.b64encode(b"STATUS: READY").decode("ascii")
    bare_prog = base64.b64encode(b"STATUS: IN_PROGRESS").decode("ascii")
    bare_bold = base64.b64encode(b"**STATUS: READY**").decode("ascii")
    bare_qp = base64.b64encode(b"STATUS=3A=20READY").decode("ascii")
    junk = base64.b64encode(b"hello world!!").decode("ascii")

    uri_ready = f"data:text/plain;base64,{bare_ready}"
    uri_prog = f"data:text/plain;charset=utf-8;base64,{bare_prog}"
    uri_empty_type = f"data:;base64,{bare_ready}"
    uri_octet = f"data:application/octet-stream;base64,{bare_bold}"
    uri_qp = f"data:text/plain;base64,{bare_qp}"
    uri_junk = f"data:text/plain;base64,{junk}"
    uri_plain = "data:text/plain,STATUS:%20READY"  # not ;base64,

    assert _peel_icml_status_data_uri_base64(uri_ready) == "STATUS: READY"
    assert _decode_icml_status_html_entities(uri_ready) == "STATUS: READY"
    assert _decode_icml_status_html_entities(uri_prog) == "STATUS: IN_PROGRESS"
    assert _decode_icml_status_html_entities(uri_empty_type) == "STATUS: READY"
    assert _decode_icml_status_html_entities(uri_octet) == "**STATUS: READY**"
    assert _decode_icml_status_html_entities(uri_qp) == "STATUS: READY"
    assert _peel_icml_status_data_uri_base64(uri_junk) == uri_junk
    assert _decode_icml_status_html_entities(uri_junk) == uri_junk
    # Tick 493 base64 peeler still leaves plain data URIs untouched; Tick 494
    # peels them via ``_peel_icml_status_data_uri_plain`` / decode.
    assert _peel_icml_status_data_uri_base64(uri_plain) == uri_plain
    assert _decode_icml_status_html_entities(uri_plain) == "STATUS: READY"
    assert _icml_ready_status_header(uri_plain + "\n") == "READY"
    # Tick 492 bare base64 contract unchanged.
    assert _peel_icml_status_bare_base64(bare_ready) == "STATUS: READY"
    assert _peel_icml_status_data_uri_base64(bare_ready) == bare_ready

    assert _strip_icml_status_line_noise(uri_ready) == "STATUS: READY"
    assert _strip_icml_status_line_noise(f"**{uri_ready}**") == "STATUS: READY"
    assert _icml_ready_status_header(uri_ready + "\n") == "READY"
    assert _icml_ready_status_header(uri_prog + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(f"**{uri_ready}**\n") == "READY"
    assert _icml_ready_status_header(uri_qp + "\n") == "READY"
    assert _icml_ready_status_header(uri_junk + "\n") is None

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{uri_ready}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert uri_ready not in demoted
    assert bare_ready not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    prose_bold = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"**{uri_ready}**\n"
    )
    demoted_bold = _demote_icml_ready_status(prose_bold)
    assert _icml_ready_status_header(demoted_bold) == "IN_PROGRESS"
    assert uri_ready not in demoted_bold
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in demoted_bold.splitlines()
    )


def test_icml_ready_status_header_accepts_data_uri_plain_status() -> None:
    """Tick 494: plain / percent-encoded data-URI STATUS (no ;base64).

    Pre-494 Tick 493 peeled ``data:…;base64,…`` only, so chat / email /
    Markdown badge paste of ``data:text/plain,STATUS%3A%20READY`` /
    ``data:text/plain;charset=utf-8,STATUS%3A%20READY`` /
    ``data:,STATUS:%20READY`` / ``data:text/plain,STATUS: READY`` /
    bold-wrapped ``**data:text/plain,STATUS%3A%20READY**`` missed demote /
    G4 pack rewrite. Non-STATUS plain data URIs and Tick 486–493 contracts
    stay untouched.
    """
    import base64

    from icml_env_checks import (
        _decode_icml_status_html_entities,
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_data_uri_base64,
        _peel_icml_status_data_uri_plain,
        _strip_icml_status_line_noise,
    )

    uri_pct = "data:text/plain,STATUS%3A%20READY"
    uri_charset = "data:text/plain;charset=utf-8,STATUS%3A%20READY"
    uri_empty = "data:,STATUS:%20READY"
    uri_literal = "data:text/plain,STATUS: READY"
    uri_prog = "data:text/plain,STATUS%3A%20IN_PROGRESS"
    uri_plus = "data:text/plain,STATUS%3A+READY"
    uri_junk = "data:text/plain,hello%20world"
    uri_b64 = (
        "data:text/plain;base64,"
        + base64.b64encode(b"STATUS: READY").decode("ascii")
    )

    assert _peel_icml_status_data_uri_plain(uri_pct) == "STATUS: READY"
    assert _peel_icml_status_data_uri_plain(uri_charset) == "STATUS: READY"
    assert _peel_icml_status_data_uri_plain(uri_empty) == "STATUS: READY"
    assert _peel_icml_status_data_uri_plain(uri_literal) == "STATUS: READY"
    assert _peel_icml_status_data_uri_plain(uri_prog) == "STATUS: IN_PROGRESS"
    assert _peel_icml_status_data_uri_plain(uri_plus) == "STATUS: READY"
    assert _peel_icml_status_data_uri_plain(uri_junk) == uri_junk
    # Tick 493 owns ``;base64,`` — plain peeler must not claim it.
    assert _peel_icml_status_data_uri_plain(uri_b64) == uri_b64
    assert _peel_icml_status_data_uri_base64(uri_b64) == "STATUS: READY"
    assert _peel_icml_status_data_uri_base64(uri_pct) == uri_pct

    assert _decode_icml_status_html_entities(uri_pct) == "STATUS: READY"
    assert _decode_icml_status_html_entities(uri_charset) == "STATUS: READY"
    assert _decode_icml_status_html_entities(uri_empty) == "STATUS: READY"
    assert _decode_icml_status_html_entities(uri_prog) == "STATUS: IN_PROGRESS"
    # Tick 489 may peel ``%20`` inside non-STATUS data URIs; wrapper stays
    # (plain peeler refuses without STATUS hint).
    decoded_junk = _decode_icml_status_html_entities(uri_junk)
    assert decoded_junk == "data:text/plain,hello world"
    assert _icml_ready_status_header(decoded_junk + "\n") is None

    assert _strip_icml_status_line_noise(uri_pct) == "STATUS: READY"
    assert _strip_icml_status_line_noise(f"**{uri_pct}**") == "STATUS: READY"
    assert _icml_ready_status_header(uri_pct + "\n") == "READY"
    assert _icml_ready_status_header(uri_charset + "\n") == "READY"
    assert _icml_ready_status_header(uri_empty + "\n") == "READY"
    assert _icml_ready_status_header(uri_literal + "\n") == "READY"
    assert _icml_ready_status_header(uri_prog + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(f"**{uri_pct}**\n") == "READY"
    assert _icml_ready_status_header(uri_junk + "\n") is None
    # Tick 493 base64 path still works.
    assert _icml_ready_status_header(uri_b64 + "\n") == "READY"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{uri_pct}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert uri_pct not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    prose_bold = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"**{uri_pct}**\n"
    )
    demoted_bold = _demote_icml_ready_status(prose_bold)
    assert _icml_ready_status_header(demoted_bold) == "IN_PROGRESS"
    assert uri_pct not in demoted_bold
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in demoted_bold.splitlines()
    )


def test_icml_ready_status_header_accepts_bare_hex_status() -> None:
    """Tick 495: bare hex STATUS payload (log / packet / hex-dump paste).

    Pre-495 Tick 492–494 covered base64 / data-URI only, so hex-encoded
    STATUS (``5354415455533A205245414459`` / spaced ``53 54 …`` /
    colon ``53:54:…`` / dash ``53-54-…`` / ``0x``-prefixed /
    bold-wrapped ``**5354…4459**``) missed demote / G4 pack rewrite.
    Non-STATUS hex and Tick 486–494 contracts stay untouched.
    """
    import base64

    from icml_env_checks import (
        _decode_icml_status_html_entities,
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_bare_base64,
        _peel_icml_status_bare_hex,
        _strip_icml_status_line_noise,
    )

    hex_ready = "STATUS: READY".encode("utf-8").hex().upper()
    hex_ready_lower = hex_ready.lower()
    hex_prog = "STATUS: IN_PROGRESS".encode("utf-8").hex().upper()
    hex_spaced = " ".join(hex_ready[i : i + 2] for i in range(0, len(hex_ready), 2))
    hex_colon = ":".join(hex_ready[i : i + 2] for i in range(0, len(hex_ready), 2))
    hex_dash = "-".join(hex_ready[i : i + 2] for i in range(0, len(hex_ready), 2))
    hex_0x = "0x" + hex_ready
    hex_junk = "hello world!!".encode("utf-8").hex().upper()
    bare_b64 = base64.b64encode(b"STATUS: READY").decode("ascii")

    assert _peel_icml_status_bare_hex(hex_ready) == "STATUS: READY"
    assert _peel_icml_status_bare_hex(hex_ready_lower) == "STATUS: READY"
    assert _peel_icml_status_bare_hex(hex_prog) == "STATUS: IN_PROGRESS"
    assert _peel_icml_status_bare_hex(hex_spaced) == "STATUS: READY"
    assert _peel_icml_status_bare_hex(hex_colon) == "STATUS: READY"
    assert _peel_icml_status_bare_hex(hex_dash) == "STATUS: READY"
    assert _peel_icml_status_bare_hex(hex_0x) == "STATUS: READY"
    assert _peel_icml_status_bare_hex(hex_junk) == hex_junk
    # Tick 492 owns bare base64 — hex peeler must not claim it.
    assert _peel_icml_status_bare_hex(bare_b64) == bare_b64
    assert _peel_icml_status_bare_base64(bare_b64) == "STATUS: READY"
    # Pure-hex alphabet may match base64 charset but fails STATUS hint.
    assert _peel_icml_status_bare_base64(hex_ready) == hex_ready

    assert _decode_icml_status_html_entities(hex_ready) == "STATUS: READY"
    assert _decode_icml_status_html_entities(hex_spaced) == "STATUS: READY"
    assert _decode_icml_status_html_entities(hex_colon) == "STATUS: READY"
    assert _decode_icml_status_html_entities(hex_prog) == "STATUS: IN_PROGRESS"
    assert _decode_icml_status_html_entities(hex_junk) == hex_junk

    assert _strip_icml_status_line_noise(hex_ready) == "STATUS: READY"
    assert _strip_icml_status_line_noise(f"**{hex_ready}**") == "STATUS: READY"
    assert _strip_icml_status_line_noise(hex_spaced) == "STATUS: READY"
    assert _icml_ready_status_header(hex_ready + "\n") == "READY"
    assert _icml_ready_status_header(hex_ready_lower + "\n") == "READY"
    assert _icml_ready_status_header(hex_spaced + "\n") == "READY"
    assert _icml_ready_status_header(hex_colon + "\n") == "READY"
    assert _icml_ready_status_header(hex_dash + "\n") == "READY"
    assert _icml_ready_status_header(hex_0x + "\n") == "READY"
    assert _icml_ready_status_header(hex_prog + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(f"**{hex_ready}**\n") == "READY"
    assert _icml_ready_status_header(hex_junk + "\n") is None
    # Tick 492 base64 path still works.
    assert _icml_ready_status_header(bare_b64 + "\n") == "READY"

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{hex_ready}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert hex_ready not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    prose_spaced = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{hex_spaced}\n"
    )
    demoted_spaced = _demote_icml_ready_status(prose_spaced)
    assert _icml_ready_status_header(demoted_spaced) == "IN_PROGRESS"
    assert hex_spaced not in demoted_spaced

    prose_bold = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"**{hex_ready}**\n"
    )
    demoted_bold = _demote_icml_ready_status(prose_bold)
    assert _icml_ready_status_header(demoted_bold) == "IN_PROGRESS"
    assert hex_ready not in demoted_bold
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in demoted_bold.splitlines()
    )


def test_icml_ready_status_header_accepts_carray_hex_status() -> None:
    """Tick 496: C-array / comma / per-byte 0x hex STATUS payloads.

    Pre-496 Tick 495 covered continuous / space / colon / dash / single
    leading ``0x`` only, so C / debugger dumps
    (``53,54,…`` / ``0x53,0x54,…`` / ``0x53 0x54 …`` /
    ``{0x53, 0x54, …}`` / bold-wrapped) missed demote / G4 pack rewrite.
    Tick 495 contracts + non-STATUS stay untouched.
    """
    from icml_env_checks import (
        _decode_icml_status_html_entities,
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_bare_hex,
        _strip_icml_status_line_noise,
    )

    raw = b"STATUS: READY"
    raw_prog = b"STATUS: IN_PROGRESS"
    hex_comma = ",".join(f"{b:02x}" for b in raw)
    hex_comma_sp = ", ".join(f"{b:02X}" for b in raw)
    hex_0x_comma = ",".join(f"0x{b:02x}" for b in raw)
    hex_0x_sp = " ".join(f"0x{b:02X}" for b in raw)
    hex_carray = "{" + ", ".join(f"0x{b:02x}" for b in raw) + "}"
    hex_carray_plain = "{" + ",".join(f"{b:02x}" for b in raw) + "}"
    hex_prog = ",".join(f"0x{b:02x}" for b in raw_prog)
    hex_cont = raw.hex().upper()  # Tick 495 contract
    hex_junk = ",".join(f"{b:02x}" for b in b"hello world!!")

    assert _peel_icml_status_bare_hex(hex_comma) == "STATUS: READY"
    assert _peel_icml_status_bare_hex(hex_comma_sp) == "STATUS: READY"
    assert _peel_icml_status_bare_hex(hex_0x_comma) == "STATUS: READY"
    assert _peel_icml_status_bare_hex(hex_0x_sp) == "STATUS: READY"
    assert _peel_icml_status_bare_hex(hex_carray) == "STATUS: READY"
    assert _peel_icml_status_bare_hex(hex_carray_plain) == "STATUS: READY"
    assert _peel_icml_status_bare_hex(hex_prog) == "STATUS: IN_PROGRESS"
    assert _peel_icml_status_bare_hex(hex_cont) == "STATUS: READY"
    assert _peel_icml_status_bare_hex(hex_junk) == hex_junk

    assert _decode_icml_status_html_entities(hex_comma) == "STATUS: READY"
    assert _decode_icml_status_html_entities(hex_0x_comma) == "STATUS: READY"
    assert _decode_icml_status_html_entities(hex_carray) == "STATUS: READY"
    assert _strip_icml_status_line_noise(f"**{hex_0x_comma}**") == "STATUS: READY"
    assert _strip_icml_status_line_noise(hex_carray) == "STATUS: READY"

    assert _icml_ready_status_header(hex_comma + "\n") == "READY"
    assert _icml_ready_status_header(hex_comma_sp + "\n") == "READY"
    assert _icml_ready_status_header(hex_0x_comma + "\n") == "READY"
    assert _icml_ready_status_header(hex_0x_sp + "\n") == "READY"
    assert _icml_ready_status_header(hex_carray + "\n") == "READY"
    assert _icml_ready_status_header(hex_carray_plain + "\n") == "READY"
    assert _icml_ready_status_header(hex_prog + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(f"**{hex_0x_comma}**\n") == "READY"
    assert _icml_ready_status_header(hex_junk + "\n") is None

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{hex_0x_comma}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert hex_0x_comma not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    prose_carray = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{hex_carray}\n"
    )
    demoted_c = _demote_icml_ready_status(prose_carray)
    assert _icml_ready_status_header(demoted_c) == "IN_PROGRESS"
    assert hex_carray not in demoted_c

    prose_bold = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"**{hex_comma}**\n"
    )
    demoted_bold = _demote_icml_ready_status(prose_bold)
    assert _icml_ready_status_header(demoted_bold) == "IN_PROGRESS"
    assert hex_comma not in demoted_bold
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**"
        for ln in demoted_bold.splitlines()
    )


def test_icml_ready_status_header_accepts_html_unquoted_attr_status() -> None:
    """Tick 485: unquoted HTML STATUS attrs on allowlisted a11y badges.

    Pre-485 ATTR peels required quotes, so minified HTML / some CMS /
    shields-like badge exports whose STATUS lives only in unquoted attrs
    with decorative body (``<p title=STATUS:READY>badge</p>`` /
    ``<span aria-label=STATUS:READY>x</span>`` /
    ``<a aria-description=STATUS:READY>Go</a>`` /
    ``<img alt=STATUS:READY src=…>`` /
    ``<svg title=STATUS:READY>…</svg>`` /
    Prettier ``<p\\n  title=STATUS:READY\\n>badge</p>``) missed demote /
    G4 pack rewrite. Spaced unquoted ``title=STATUS: READY`` remains a miss
    (invalid HTML attr value).
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _icml_status_html_attr_value,
        _peel_icml_status_html_a_title,
        _peel_icml_status_html_img_alt,
        _peel_icml_status_html_inline_title,
        _peel_icml_status_html_span_title,
        _peel_icml_status_html_svg_title,
        _take_icml_status_multiline_inline_block,
        _ICML_STATUS_HTML_INLINE_ATTR_RE,
    )

    flat_p = "<p title=STATUS:READY>badge</p>"
    span_uq = "<span aria-label=STATUS:READY>x</span>"
    a_uq = "<a aria-description=STATUS:READY>Go</a>"
    img_uq = '<img alt=STATUS:READY src="https://x.com/b.svg">'
    img_src_uq = "<img alt=STATUS:READY src=b.svg>"
    svg_uq = "<svg title=STATUS:READY><title>Badge</title></svg>"
    prog = "<p title=STATUS:IN_PROGRESS>badge</p>"
    quoted_ok = '<p title="STATUS: READY">badge</p>'
    spaced_miss = "<p title=STATUS: READY>badge</p>"
    soft = "<p\n  title=STATUS:READY\n>badge</p>"

    assert _peel_icml_status_html_inline_title(flat_p) == "STATUS:READY"
    assert _peel_icml_status_html_span_title(span_uq) == "STATUS:READY"
    assert _peel_icml_status_html_a_title(a_uq) == "STATUS:READY"
    assert _peel_icml_status_html_img_alt(img_uq) == "STATUS:READY"
    assert _peel_icml_status_html_img_alt(img_src_uq) == "STATUS:READY"
    assert _peel_icml_status_html_svg_title(svg_uq) == "STATUS:READY"
    assert _peel_icml_status_html_inline_title(prog) == "STATUS:IN_PROGRESS"
    assert _peel_icml_status_html_inline_title(quoted_ok) == "STATUS: READY"
    assert _peel_icml_status_html_inline_title(spaced_miss) is None

    am = _ICML_STATUS_HTML_INLINE_ATTR_RE.search(" title=STATUS:READY")
    assert am is not None
    assert _icml_status_html_attr_value(am) == "STATUS:READY"
    am_q = _ICML_STATUS_HTML_INLINE_ATTR_RE.search(' title="STATUS: READY"')
    assert am_q is not None
    assert _icml_status_html_attr_value(am_q) == "STATUS: READY"

    taken = _take_icml_status_multiline_inline_block(soft.splitlines(), 0)
    assert taken is not None
    n, collapsed = taken
    assert n == 3
    assert "title=STATUS:READY" in collapsed
    assert _peel_icml_status_html_inline_title(collapsed) == "STATUS:READY"

    assert _icml_ready_status_header(flat_p + "\n") == "READY"
    assert _icml_ready_status_header(span_uq + "\n") == "READY"
    assert _icml_ready_status_header(a_uq + "\n") == "READY"
    assert _icml_ready_status_header(img_uq + "\n") == "READY"
    assert _icml_ready_status_header(img_src_uq + "\n") == "READY"
    assert _icml_ready_status_header(svg_uq + "\n") == "READY"
    assert _icml_ready_status_header(prog + "\n") == "IN_PROGRESS"
    assert _icml_ready_status_header(soft + "\n") == "READY"
    assert _icml_ready_status_header(spaced_miss + "\n") is None

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{soft}\n"
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert "title=STATUS:READY" not in demoted
    assert any(
        ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1

    prose_img = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        f"{img_src_uq}\n"
    )
    demoted_img = _demote_icml_ready_status(prose_img)
    assert _icml_ready_status_header(demoted_img) == "IN_PROGRESS"
    assert "alt=STATUS:READY" not in demoted_img


def test_icml_ready_status_header_accepts_html_img_alt_status() -> None:
    """Tick 468: HTML ``<img alt="STATUS:…">`` (Notion/Docs badge exports).

    Pre-468 ``<img alt="STATUS: READY" src="…">`` missed demote / G4 pack
    rewrite — Tick 467 only peeled markdown ``![…](…)``, and ``img`` is not
    in the HTML-tag allowlist (stripping would drop the alt).
    """
    from icml_env_checks import (
        _demote_icml_ready_status,
        _icml_ready_richness,
        _icml_ready_status_header,
        _peel_icml_status_html_img_alt,
        _strip_icml_status_md_wrappers,
    )

    flat_img = '<img alt="STATUS: READY" src="https://img.shields.io/badge/STATUS-READY-green">'
    src_first = (
        '<img src="https://cdn.example/badge_(live).svg" '
        'alt="**STATUS: READY**" />'
    )
    single_q = "<img alt='STATUS: READY' src=\"https://x.com/b.svg\">"
    prog_img = (
        '<img alt="STATUS: IN_PROGRESS" '
        'src="https://img.shields.io/badge/STATUS-IN_PROGRESS-yellow">'
    )

    assert _peel_icml_status_html_img_alt(flat_img) == "STATUS: READY"
    assert _peel_icml_status_html_img_alt(src_first) == "**STATUS: READY**"
    assert _peel_icml_status_html_img_alt(single_q) == "STATUS: READY"
    assert _peel_icml_status_html_img_alt(prog_img) == "STATUS: IN_PROGRESS"
    # Trailing prose after the tag must not peel.
    assert _peel_icml_status_html_img_alt(flat_img + " note") is None
    # No alt → refuse.
    assert _peel_icml_status_html_img_alt('<img src="https://x.com/b.svg">') is None
    # Tick 467 markdown images still peel via link helper / wrappers.
    assert _strip_icml_status_md_wrappers(
        "![STATUS: READY](https://img.shields.io/badge/STATUS-READY-green)"
    ) == "STATUS: READY"

    assert _strip_icml_status_md_wrappers(flat_img) == "STATUS: READY"
    assert _strip_icml_status_md_wrappers(src_first) == "STATUS: READY"
    assert _strip_icml_status_md_wrappers(single_q) == "STATUS: READY"
    assert _icml_ready_status_header(flat_img + "\n") == "READY"
    assert _icml_ready_status_header(src_first + "\n") == "READY"
    assert _icml_ready_status_header(single_q + "\n") == "READY"
    assert _icml_ready_status_header(prog_img + "\n") == "IN_PROGRESS"
    assert (
        _icml_ready_status_header(
            '| <img alt="STATUS: READY" src="https://x.com/badge_(live).svg"> |\n'
        )
        == "READY"
    )
    assert (
        _icml_ready_status_header(
            '> <img alt="STATUS: READY" src="https://x.com/badge_(live).svg">\n'
        )
        == "READY"
    )
    assert (
        _icml_ready_status_header(
            '<p><img alt="STATUS: READY" src="https://x.com/b.svg"></p>\n'
        )
        == "READY"
    )

    prose = (
        "# Title\n\n"
        "Do not set STATUS: READY until criteria pass.\n\n"
        '<img alt="STATUS: READY" src="https://img.shields.io/badge/STATUS-READY_(live)-green">\n'
    )
    assert _icml_ready_status_header(prose) == "READY"
    demoted = _demote_icml_ready_status(prose)
    assert _icml_ready_status_header(demoted) == "IN_PROGRESS"
    assert "Do not set STATUS: READY until criteria pass." in demoted
    assert any(ln.strip() == "**STATUS: IN_PROGRESS**" for ln in demoted.splitlines())
    assert not any(
        "<img" in ln.lower() and "STATUS: READY" in ln for ln in demoted.splitlines()
    )
    assert _icml_ready_richness(prose)[2] == 1


def test_merge_paper_artifacts_prefers_richer_live_over_thin_stub() -> None:
    """Tick 440: offline stub mentioning Live Table must not wipe filled live pack.

    Pre-440 durable merge always preferred replayed local when it contained
    ``Live Table`` / ``live GPQA``. The committed offline stub already has those
    phrases (empty Live Table 1), so concurrent tip rebase could drop onto's
    post-G4 auto-filled PRIMARY table.
    """
    from icml_env_checks import (
        _merge_durable_conflict_bytes,
        prefer_richer_figure_bytes,
        prefer_richer_paper_artifacts,
    )

    thin_stub = (
        "# ICML paper artifacts\n\n"
        "### Live GPQA\n\n"
        "| Seed | B final acc | D final acc | Winner |\n"
        "|------|-------------|-------------|--------|\n"
        "| — | — | — | — |\n\n"
        "_Live Table 1 columns match G4 stub empty until live G4._\n\n"
        "## Table 2 — Mechanism / validity\n\n"
        "<!-- LIVE_TABLE2_H2_START -->\n"
        "| H2 trait skew (live API) | — | — |\n"
        "<!-- LIVE_TABLE2_H2_END -->\n"
    )
    rich_live = (
        "# ICML paper artifacts\n\n"
        "### Live GPQA\n\n"
        "_Auto-filled by `scripts/run_g4_multiseed.py` at 2026-09-26T22:00Z_\n\n"
        "| Seed | B final acc | D final acc | B gens@30% | D gens@30% | Winner |\n"
        "|------|-------------|-------------|------------|------------|--------|\n"
        "| 1 | 0.20 | 0.32 | — | 4 | D |\n"
        "| 2 | 0.22 | 0.31 | — | 5 | D |\n"
        "| 3 | 0.25 | 0.33 | 3 | 3 | D |\n"
        "| 4 | 0.21 | 0.30 | — | 4 | D |\n"
        "| 5 | 0.24 | 0.34 | — | 4 | D |\n\n"
        "PRIMARY flags: gens30=True cost30=True gens25=False cost25=False; "
        "primary_final_pass=True mean_final_gap=0.096; D final wins=5/5. "
        "Run IDs B=[1211, 1212, 1213, 1214, 1215] D=[1311, 1312, 1313, 1314, 1315].\n"
        "H5 ρ>0.3 on live D runs: **5/5**.\n"
        "H2 live DNA skew: **PASS** (d_wins_h2=5/5 h2_preferred_pass=True).\n\n"
        "## Table 2 — Mechanism / validity\n\n"
        "<!-- LIVE_TABLE2_H2_START -->\n"
        "| H2 trait skew (live API) | d_wins_h2=5/5 preferred_share=0.75; "
        "skew_pass=True | yes |\n"
        "<!-- LIVE_TABLE2_H2_END -->\n"
        "<!-- LIVE_TABLE2_H5_START -->\n"
        "| H5 Spearman ρ (live) | 5/5 ρ>0.3 | yes |\n"
        "<!-- LIVE_TABLE2_H5_END -->\n"
    )
    # onto (ours) = rich live; replayed local (theirs) = thin stub with Live Table phrase
    merged = prefer_richer_paper_artifacts(rich_live, thin_stub)
    assert "Auto-filled by" in merged
    assert "primary_final_pass=True" in merged
    assert "| 1 | 0.20 | 0.32 |" in merged
    assert merged.count("| 1 |") == 1

    # Symmetric: rich local beats thin onto.
    merged2 = prefer_richer_paper_artifacts(thin_stub, rich_live)
    assert "Auto-filled by" in merged2
    assert "D final wins=5/5" in merged2

    # Durable conflict bytes path (ours=stage2 onto, theirs=stage3 local).
    out = _merge_durable_conflict_bytes(
        "docs/paper_artifacts.md",
        rich_live.encode("utf-8"),
        thin_stub.encode("utf-8"),
    )
    assert out is not None
    assert b"Auto-filled by" in out
    assert b"primary_final_pass=True" in out

    # Figures: larger non-empty wins over tiny local.
    big = b"\x89PNG" + (b"X" * 200)
    tiny = b"\x89PNG" + (b"y" * 10)
    assert prefer_richer_figure_bytes(big, tiny) == big
    assert prefer_richer_figure_bytes(tiny, big) == big
    fig = _merge_durable_conflict_bytes(
        "docs/figures/fig1_learning_curves.png", big, tiny
    )
    assert fig == big


def test_rebase_tip_merges_durable_budget_conflict(
    tmp_path: Path, monkeypatch
) -> None:
    """Tick 438: concurrent budget_spent edits must merge+continue (not abort).

    Pre-438 Tick 437 aborted on any rebase conflict. Two tip VMs that both
    write ``docs/icml_budget_spent.json`` then left the higher spend
    local-only after NF push. Tick 438 unions spend/stages and continues.
    """
    import json
    import subprocess

    from icml_env_checks import (
        commit_durable_ledgers_after_live,
        tip_commits_ahead_of_origin,
    )
    import icml_env_checks as m

    bare = tmp_path / "bare.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)

    tip_branch = "cursor/icml-epistemic-results-tip438"

    tip_repo = tmp_path / "tip"
    tip_repo.mkdir()
    subprocess.run(["git", "init"], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", tip_branch],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(bare)],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    docs = tip_repo / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps({"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 0, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "-u", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )

    stale = tmp_path / "stale"
    subprocess.run(
        ["git", "clone", str(bare), str(stale)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-B", tip_branch, f"origin/{tip_branch}"],
        cwd=stale,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=stale,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=stale,
        check=True,
        capture_output=True,
    )

    # Local durable: higher spend + G3.
    (stale / "docs" / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 7.37,
                "stages_complete": ["G2", "G3"],
                "run_ids": [1300, 1201],
                "updated_at": "2026-09-26T12:00:00Z",
                "detail": "local g3",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "docs/icml_budget_spent.json"],
        cwd=stale,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "local durable spend"],
        cwd=stale,
        check=True,
        capture_output=True,
    )

    # Concurrent tip also edits budget_spent (lower spend) + READY — conflict.
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 2.1,
                "stages_complete": ["G2"],
                "run_ids": [1300],
                "updated_at": "2026-09-26T10:00:00Z",
                "detail": "tip g2",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "ICML_READY.md").write_text("STATUS: IN_PROGRESS\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tip_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "tip ahead concurrent budget"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", f"HEAD:refs/heads/{tip_branch}"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
    )
    tip_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tip_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    subprocess.run(
        ["git", "fetch", "origin", f"+refs/heads/{tip_branch}:refs/remotes/origin/{tip_branch}"],
        cwd=stale,
        check=True,
        capture_output=True,
    )

    monkeypatch.setattr(m, "prefer_tip_pr_commit_branch", lambda pr=None: tip_branch)
    monkeypatch.delenv("ICML_CLOUD_BOOT_BRANCH", raising=False)

    ok, detail = commit_durable_ledgers_after_live(stale)
    assert ok is True, detail
    assert "438" in detail or "durable conflict" in detail.lower(), detail

    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", tip_sha, "HEAD"],
            cwd=stale,
            check=False,
            capture_output=True,
        ).returncode
        == 0
    ), f"HEAD must contain concurrent tip; detail={detail}"

    origin_spent = json.loads(
        subprocess.run(
            ["git", "show", f"origin/{tip_branch}:docs/icml_budget_spent.json"],
            cwd=stale,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    assert origin_spent["spent_usd"] == 7.37
    assert "G3" in origin_spent["stages_complete"]
    assert 1201 in origin_spent["run_ids"]
    assert tip_commits_ahead_of_origin(stale) == 0


def test_prepare_and_commit_prior_live_evidence_tip_apply_roundtrip(
    tmp_path: Path,
) -> None:
    """Tick 420: dirty evidence alone → prepare unblocks discard; commit lands SHA."""
    import json
    import subprocess

    from icml_env_checks import (
        ICML_PRIOR_LIVE_EVIDENCE_RELPATH,
        ICML_PRIOR_LIVE_STASH_RELPATH,
        commit_prior_live_evidence_if_dirty,
        discard_ephemeral_icml_dirt,
        prepare_prior_live_evidence_for_tip_apply,
        tip_apply_blocking_dirty_paths,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    docs.mkdir()
    empty_ev = {
        "updated_at": "2026-01-01T00:00:00Z",
        "tick": 389,
        "tick_note": "empty",
        "gates": {},
    }
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps(empty_ev, indent=2) + "\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    live_gates = {
        "docs/gate4_report.json": {
            "prior_live_metrics": {
                "comparison": {"d_wins_gens30": 4, "n_pairs": 5},
                "executed": True,
                "primary_pass": True,
            }
        }
    }
    dirty_ev = {
        "updated_at": "2026-09-25T06:00:00Z",
        "tick": 389,
        "tick_note": "live capture",
        "gates": live_gates,
    }
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps(dirty_ev, indent=2) + "\n", encoding="utf-8"
    )

    # Pre-Tick-420: dirty evidence alone blocks discard (Tick 390).
    ok_blocked, detail_blocked = discard_ephemeral_icml_dirt(repo)
    assert ok_blocked is False
    assert "non-ephemeral" in detail_blocked or "evidence" in detail_blocked.lower()

    ok_prep, prep_detail = prepare_prior_live_evidence_for_tip_apply(repo)
    assert ok_prep is True, prep_detail
    # Tick 421 supersedes prepare messaging (still parks evidence; may say 421).
    assert ("420" in prep_detail) or ("421" in prep_detail)
    stash = json.loads((repo / ICML_PRIOR_LIVE_STASH_RELPATH).read_text(encoding="utf-8"))
    assert stash["gates"]["docs/gate4_report.json"]["prior_live_metrics"][
        "comparison"
    ]["d_wins_gens30"] == 4

    ok_disc, disc_detail = discard_ephemeral_icml_dirt(repo)
    assert ok_disc is True, disc_detail
    assert tip_apply_blocking_dirty_paths(repo) == []

    # Simulate tip --apply wiping evidence then reinject writing it dirty again.
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps(dirty_ev, indent=2) + "\n", encoding="utf-8"
    )
    ok_commit, commit_detail = commit_prior_live_evidence_if_dirty(repo)
    assert ok_commit is True, commit_detail
    assert ("420" in commit_detail) or ("421" in commit_detail) or ("committed" in commit_detail.lower())
    assert tip_apply_blocking_dirty_paths(repo) == []
    committed = json.loads(
        subprocess.check_output(
            ["git", "show", f"HEAD:{ICML_PRIOR_LIVE_EVIDENCE_RELPATH}"],
            cwd=repo,
            text=True,
        )
    )
    assert committed["gates"]["docs/gate4_report.json"]["prior_live_metrics"][
        "comparison"
    ]["d_wins_gens30"] == 4




def test_prepare_and_commit_durable_ledgers_when_budget_and_evidence_dirty(
    tmp_path: Path,
) -> None:
    """Tick 421: dirty budget_spent + evidence must park/restore/commit together."""
    import json
    import subprocess

    from icml_env_checks import (
        ICML_BUDGET_SPENT_RELPATH,
        ICML_PRIOR_LIVE_EVIDENCE_RELPATH,
        commit_prior_live_evidence_if_dirty,
        discard_ephemeral_icml_dirt,
        prepare_prior_live_evidence_for_tip_apply,
        reinject_budget_spent_stash,
        reinject_prior_live_stash,
        tip_apply_blocking_dirty_paths,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"], cwd=repo, check=True, capture_output=True
    )
    docs = repo / "docs"
    docs.mkdir()
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 389, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {"spent_usd": 0.0, "stages_complete": [], "run_ids": []}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text(
        "docs/icml_prior_live_stash.json\ndocs/icml_budget_spent_stash.json\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True
    )

    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps(
            {
                "tick": 389,
                "gates": {
                    "docs/gate4_report.json": {
                        "prior_live_metrics": {"executed": True, "primary_pass": True}
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 4.25,
                "stages_complete": ["g2", "g3", "g4"],
                "run_ids": ["1211", "1311"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    ok_prep, prep_detail = prepare_prior_live_evidence_for_tip_apply(repo)
    assert ok_prep is True, prep_detail
    assert "421" in prep_detail
    assert tip_apply_blocking_dirty_paths(repo) == []
    ok_disc, disc_detail = discard_ephemeral_icml_dirt(repo)
    assert ok_disc is True, disc_detail

    subprocess.run(["git", "reset", "--hard"], cwd=repo, check=True, capture_output=True)
    ok_b, b_detail = reinject_budget_spent_stash(repo)
    ok_p, p_detail = reinject_prior_live_stash(repo)
    assert ok_b is True, b_detail
    assert ok_p is True, p_detail
    ledger = json.loads((docs / "icml_budget_spent.json").read_text(encoding="utf-8"))
    assert ledger["spent_usd"] == 4.25
    ok_commit, commit_detail = commit_prior_live_evidence_if_dirty(repo)
    assert ok_commit is True, commit_detail
    assert tip_apply_blocking_dirty_paths(repo) == []
    committed = json.loads(
        subprocess.check_output(
            ["git", "show", f"HEAD:{ICML_BUDGET_SPENT_RELPATH}"],
            cwd=repo,
            text=True,
        )
    )
    assert committed["spent_usd"] == 4.25
    assert ICML_PRIOR_LIVE_EVIDENCE_RELPATH.endswith("evidence.json")


def test_prepare_budget_only_dirty_parks_without_evidence(
    tmp_path: Path,
) -> None:
    """Tick 421: budget_spent-only dirt must also park (not prepare-noop)."""
    import json
    import subprocess

    from icml_env_checks import (
        prepare_prior_live_evidence_for_tip_apply,
        tip_apply_blocking_dirty_paths,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"], cwd=repo, check=True, capture_output=True
    )
    docs = repo / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps({"spent_usd": 0.0, "stages_complete": []}, indent=2) + "\n",
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text(
        "docs/icml_budget_spent_stash.json\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True
    )
    (docs / "icml_budget_spent.json").write_text(
        json.dumps({"spent_usd": 1.5, "stages_complete": ["g2"]}, indent=2) + "\n",
        encoding="utf-8",
    )
    ok_prep, prep_detail = prepare_prior_live_evidence_for_tip_apply(repo)
    assert ok_prep is True, prep_detail
    assert "budget_spent" in prep_detail
    assert tip_apply_blocking_dirty_paths(repo) == []


def test_commit_prior_live_evidence_refuses_other_non_ephemeral_dirt(
    tmp_path: Path,
) -> None:
    """Tick 420: never auto-commit evidence when real code edits are dirty."""
    import json
    import subprocess

    from icml_env_checks import (
        commit_prior_live_evidence_if_dirty,
        prepare_prior_live_evidence_for_tip_apply,
    )

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    docs.mkdir()
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps({"tick": 389, "gates": {}}, indent=2) + "\n", encoding="utf-8"
    )
    (repo / "scripts").mkdir()
    (repo / "scripts" / "real_edit.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    (docs / "icml_prior_live_evidence.json").write_text(
        json.dumps(
            {
                "tick": 389,
                "gates": {
                    "docs/gate2_report.json": {"prior_live_post": [{"ok": True}]}
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (repo / "scripts" / "real_edit.py").write_text("x = 2\n", encoding="utf-8")

    ok_prep, prep_detail = prepare_prior_live_evidence_for_tip_apply(repo)
    assert ok_prep is False
    assert "refused" in prep_detail.lower()
    ok_commit, commit_detail = commit_prior_live_evidence_if_dirty(repo)
    assert ok_commit is False
    assert "refused" in commit_detail.lower()


def test_stash_prior_live_from_live_executed_gate3() -> None:
    """Tick 387: live-executed gate3 top-level comparison becomes prior_live."""
    from icml_env_checks import _stash_prior_live_from_gate_json

    blob = _stash_prior_live_from_gate_json(
        {
            "mode": "live",
            "executed": True,
            "comparison": {"d_wins_gens30": 1, "n_pairs": 1},
            "h5_by_d_run": {"run_1301": {"spearman_rho": 0.6}},
            "h2_by_d_run": {},
        }
    )
    assert blob is not None
    assert blob["prior_live_metrics"]["comparison"]["d_wins_gens30"] == 1
    assert blob["prior_live_metrics"]["executed"] is True


def test_stash_prior_live_from_live_gate2_post() -> None:
    """Tick 387: live gate2 post becomes prior_live_post."""
    from icml_env_checks import _stash_prior_live_from_gate_json

    blob = _stash_prior_live_from_gate_json(
        {
            "mode": "live",
            "post": [
                {"name": "nonzero_fitness", "ok": True, "detail": "0.2"},
                {"name": "belief_store", "ok": True, "detail": "yes"},
            ],
        }
    )
    assert blob is not None
    assert len(blob["prior_live_post"]) == 2
    assert blob["prior_live_post"][0]["name"] == "nonzero_fitness"


def test_persist_prior_live_writes_committed_evidence(tmp_path: Path) -> None:
    """Tick 389: persist writes both gitignored stash and committed evidence."""
    import json

    from icml_env_checks import (
        ICML_PRIOR_LIVE_EVIDENCE_RELPATH,
        ICML_PRIOR_LIVE_STASH_RELPATH,
        persist_prior_live_stash_from_working_tree,
    )

    repo = tmp_path / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    (docs / "gate4_report.json").write_text(
        json.dumps(
            {
                "mode": "preflight",
                "executed": False,
                "prior_live_metrics": {
                    "comparison": {"d_wins_gens30": 4, "n_pairs": 5},
                    "executed": True,
                    "paper_refreshed": True,
                    "ready_status": "READY",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    info = persist_prior_live_stash_from_working_tree(repo)
    assert info["ok"] is True
    assert "docs/gate4_report.json" in info["captured"]
    stash = json.loads((repo / ICML_PRIOR_LIVE_STASH_RELPATH).read_text(encoding="utf-8"))
    evidence = json.loads(
        (repo / ICML_PRIOR_LIVE_EVIDENCE_RELPATH).read_text(encoding="utf-8")
    )
    assert stash["gates"]["docs/gate4_report.json"]["prior_live_metrics"][
        "ready_status"
    ] == "READY"
    assert evidence["gates"]["docs/gate4_report.json"]["prior_live_metrics"][
        "comparison"
    ]["d_wins_gens30"] == 4
    assert evidence["tick"] == 389


def test_reinject_prior_live_falls_back_to_committed_evidence(
    tmp_path: Path,
) -> None:
    """Tick 389: reinject uses committed evidence when stash is absent (fresh boot)."""
    import json

    from icml_env_checks import (
        ICML_PRIOR_LIVE_EVIDENCE_RELPATH,
        ICML_PRIOR_LIVE_STASH_RELPATH,
        reinject_prior_live_stash,
    )

    repo = tmp_path / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    clean = {
        "mode": "preflight",
        "executed": False,
        "comparison": None,
        "paper_refreshed": False,
    }
    (docs / "gate4_report.json").write_text(
        json.dumps(clean, indent=2) + "\n", encoding="utf-8"
    )
    evidence = {
        "tick": 389,
        "tick_note": "cross-VM",
        "gates": {
            "docs/gate4_report.json": {
                "prior_live_metrics": {
                    "comparison": {"d_wins_gens30": 3, "n_pairs": 5},
                    "executed": True,
                    "paper_refreshed": True,
                    "ready_status": "IN_PROGRESS",
                }
            }
        },
    }
    (repo / ICML_PRIOR_LIVE_EVIDENCE_RELPATH).write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    assert not (repo / ICML_PRIOR_LIVE_STASH_RELPATH).is_file()
    ok, detail = reinject_prior_live_stash(repo)
    assert ok is True
    assert "evidence" in detail
    assert "reinjected" in detail
    after = json.loads((docs / "gate4_report.json").read_text(encoding="utf-8"))
    assert after["prior_live_metrics"]["comparison"]["d_wins_gens30"] == 3


def test_ensure_prior_live_evidence_initialized(tmp_path: Path) -> None:
    """Tick 389: empty evidence file created once (budget-ledger parity)."""
    from icml_env_checks import ensure_prior_live_evidence_initialized

    path, created = ensure_prior_live_evidence_initialized(tmp_path)
    assert created is True
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["gates"] == {}
    path2, created2 = ensure_prior_live_evidence_initialized(tmp_path)
    assert created2 is False
    assert path2 == path


def test_tip_apply_blocks_dirty_prior_live_evidence(tmp_path: Path) -> None:
    """Tick 390: dirty committed evidence is a tip-apply blocker (ledger parity)."""
    import json
    import subprocess

    from icml_env_checks import (
        ICML_PRIOR_LIVE_EVIDENCE_RELPATH,
        tip_apply_blocking_dirty_paths,
    )

    repo = tmp_path / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    evidence = repo / ICML_PRIOR_LIVE_EVIDENCE_RELPATH
    evidence.write_text(
        json.dumps(
            {
                "updated_at": "2026-09-09T00:00:00Z",
                "tick": 389,
                "tick_note": "empty",
                "gates": {},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", ICML_PRIOR_LIVE_EVIDENCE_RELPATH],
        cwd=str(repo),
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "empty evidence"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    evidence.write_text(
        json.dumps(
            {
                "updated_at": "2026-09-09T02:00:00Z",
                "tick": 390,
                "tick_note": "live gates",
                "gates": {
                    "docs/gate4_report.json": {
                        "prior_live_metrics": {
                            "comparison": {"d_wins_gens30": 4},
                            "executed": True,
                        }
                    }
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    blocking = tip_apply_blocking_dirty_paths(repo)
    assert ICML_PRIOR_LIVE_EVIDENCE_RELPATH in [
        p.replace("\\", "/") for p in blocking
    ]


def test_discard_ephemeral_blocks_dirty_prior_live_evidence(
    tmp_path: Path,
) -> None:
    """Tick 390: discard_ephemeral treats dirty evidence as non-ephemeral block."""
    import json
    import subprocess

    from icml_env_checks import (
        ICML_PRIOR_LIVE_EVIDENCE_RELPATH,
        discard_ephemeral_icml_dirt,
    )

    repo = tmp_path / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    evidence = repo / ICML_PRIOR_LIVE_EVIDENCE_RELPATH
    evidence.write_text(
        json.dumps({"tick": 389, "gates": {}, "tick_note": "empty"}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (docs / "gate4_report.json").write_text(
        json.dumps({"mode": "preflight"}, indent=2) + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", ICML_PRIOR_LIVE_EVIDENCE_RELPATH, "docs/gate4_report.json"],
        cwd=str(repo),
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "baseline"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    (docs / "gate4_report.json").write_text(
        json.dumps({"mode": "preflight", "n": 1}, indent=2) + "\n",
        encoding="utf-8",
    )
    evidence.write_text(
        json.dumps(
            {
                "tick": 390,
                "gates": {
                    "docs/gate3_report.json": {
                        "prior_live_metrics": {"executed": True, "comparison": {}}
                    }
                },
                "tick_note": "live",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ok, detail = discard_ephemeral_icml_dirt(repo)
    assert ok is False
    assert "non-ephemeral dirty" in detail
    assert "icml_prior_live_evidence.json" in detail


def test_recover_tip_apply_source_does_not_filter_evidence() -> None:
    """Tick 390/391: recover_tip --apply uses shared tip_apply filter (not evidence)."""
    from pathlib import Path

    recover = (
        Path(__file__).resolve().parents[1] / "scripts" / "icml_recover_tip.py"
    ).read_text(encoding="utf-8")
    assert "tip_apply_blocking_dirty_paths" in recover
    assert "Tick 390" in recover
    assert "Tick 391" in recover
    assert "evidence_norm" not in recover
    # Must not hard-code stash-only filter anymore (Tick 391 shared ignore set).
    assert "rest == stash_norm" not in recover


def test_tip_apply_ignores_gitignore_lag_boot_and_call(tmp_path: Path) -> None:
    """Tick 391: boot/call dirt must not block tip --apply when .gitignore lags."""
    import json
    import subprocess

    from icml_env_checks import (
        ICML_CLOUD_BOOT_BRANCH_RELPATH,
        ICML_OPEN_GIT_PR_CALL_RELPATH,
        ICML_PRIOR_LIVE_EVIDENCE_RELPATH,
        TIP_APPLY_GITIGNORE_LAG_RELPATHS,
        tip_apply_blocking_dirty_paths,
    )

    repo = tmp_path / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    # Intentionally NO .gitignore — chicken-egg greenfield / main boot.
    (docs / "placeholder.md").write_text("ok\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    (docs / "icml_cloud_boot_branch.txt").write_text(
        "cursor/icml-epistemic-results-dd06\n", encoding="utf-8"
    )
    (docs / "icml_open_git_pr_call.json").write_text(
        json.dumps({"branch": "cursor/icml-epistemic-results-f49c"}) + "\n",
        encoding="utf-8",
    )
    assert ICML_CLOUD_BOOT_BRANCH_RELPATH in TIP_APPLY_GITIGNORE_LAG_RELPATHS
    assert ICML_OPEN_GIT_PR_CALL_RELPATH in TIP_APPLY_GITIGNORE_LAG_RELPATHS
    assert ICML_PRIOR_LIVE_EVIDENCE_RELPATH not in TIP_APPLY_GITIGNORE_LAG_RELPATHS
    blocking = tip_apply_blocking_dirty_paths(repo)
    norms = [p.replace("\\", "/") for p in blocking]
    assert ICML_CLOUD_BOOT_BRANCH_RELPATH not in norms
    assert ICML_OPEN_GIT_PR_CALL_RELPATH not in norms
    assert norms == []


def test_boot_recover_chicken_egg_filters_boot_without_env_checks(
    tmp_path: Path,
) -> None:
    """Tick 392: without tip module, porcelain boot file must not block --apply."""
    import subprocess

    repo = tmp_path / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    # Greenfield: no .gitignore, no scripts/icml_env_checks.py.
    (docs / "placeholder.md").write_text("ok\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    (docs / "icml_cloud_boot_branch.txt").write_text(
        "cursor/icml-epistemic-results-6152\n", encoding="utf-8"
    )
    (docs / "icml_open_git_pr_call.json").write_text("{}\n", encoding="utf-8")
    (docs / "real_dirt.py").write_text("x=1\n", encoding="utf-8")
    porcelain = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=str(repo), text=True
    )
    assert "icml_cloud_boot_branch.txt" in porcelain
    assert "real_dirt.py" in porcelain

    # Mirror the Tick 392 inline filter from icml_boot_recover.sh (no tip module).
    filtered = subprocess.check_output(
        [
            "python3",
            "-c",
            """
import subprocess
IGNORE = {
    "docs/icml_cloud_boot_branch.txt",
    "docs/icml_open_git_pr_call.json",
    "docs/icml_prior_live_stash.json",
}
out = subprocess.run(
    ["git", "status", "--porcelain"],
    capture_output=True,
    text=True,
    check=False,
)
for line in (out.stdout or "").splitlines():
    if len(line) < 4:
        continue
    path = line[3:]
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    path = path.strip().strip('"').replace("\\\\", "/").lstrip("./")
    if path in IGNORE:
        continue
    print(line)
""",
        ],
        cwd=str(repo),
        text=True,
    )
    assert "icml_cloud_boot_branch.txt" not in filtered
    assert "icml_open_git_pr_call.json" not in filtered
    assert "real_dirt.py" in filtered

    boot = (REPO / "scripts" / "icml_boot_recover.sh").read_text(encoding="utf-8")
    cron = (REPO / "scripts" / "icml_cron_entry.sh").read_text(encoding="utf-8")
    assert "Tick 392" in boot
    assert "Tick 392" in cron
    assert "docs/icml_cloud_boot_branch.txt" in boot
    assert "mirror TIP_APPLY_GITIGNORE_LAG_RELPATHS" in boot
    assert "mirror TIP_APPLY_GITIGNORE_LAG_RELPATHS" in cron


def test_discard_ephemeral_gitignore_lag_boot_ok(tmp_path: Path) -> None:
    """Tick 391: discard clears ephemerals even when boot file is unignored dirt."""
    import subprocess

    from icml_env_checks import (
        ICML_CLOUD_BOOT_BRANCH_RELPATH,
        discard_ephemeral_icml_dirt,
    )

    repo = tmp_path / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    # No .gitignore — boot file would otherwise be non-ephemeral dirty.
    (docs / "gate2_report.md").write_text("clean\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    (docs / "gate2_report.md").write_text("dirty\n", encoding="utf-8")
    boot_path = repo / ICML_CLOUD_BOOT_BRANCH_RELPATH
    boot_path.write_text("cursor/icml-epistemic-results-dd06\n", encoding="utf-8")
    ok, detail = discard_ephemeral_icml_dirt(repo)
    assert ok, detail
    assert boot_path.is_file(), "Tick 391: boot file must survive discard"
    assert (docs / "gate2_report.md").read_text(encoding="utf-8") == "clean\n"


def test_recover_tip_apply_source_mentions_prior_live() -> None:
    """Tick 388: recover_tip.py --apply must wire discard + reinject (Tick 387 hole)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    recover = (root / "scripts" / "icml_recover_tip.py").read_text(encoding="utf-8")
    assert "discard_ephemeral_icml_dirt" in recover
    assert "reinject_prior_live_stash" in recover
    assert "Tick 388" in recover
    assert "prior_live_reinject" in recover
    # Must not only refuse dirty — must discard ephemerals first (stash path).
    assert "ephemeral_discard" in recover


def test_recover_tip_apply_wires_prior_live_stash(tmp_path: Path, monkeypatch) -> None:
    """Tick 388: apply_tip discards+stashes prior_live then reinjects after hard-reset."""
    import json
    import subprocess
    import sys

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "icml@test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "icml"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    docs = repo / "docs"
    docs.mkdir()
    scripts = repo / "scripts"
    scripts.mkdir()
    # Minimal checkout script so apply_tip anti-churn path is a no-op success.
    (scripts / "icml_checkout_tip_pr_branch.sh").write_text(
        "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
    )
    clean_g4 = {
        "mode": "preflight",
        "executed": False,
        "comparison": None,
        "paper_refreshed": False,
    }
    (docs / "gate4_report.json").write_text(
        json.dumps(clean_g4, indent=2) + "\n", encoding="utf-8"
    )
    (docs / "gate4_report.md").write_text("# gate4\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    tip_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()

    dirty_g4 = {
        "mode": "preflight",
        "executed": False,
        "comparison": None,
        "paper_refreshed": False,
        "prior_live_metrics": {
            "comparison": {"d_wins_gens30": 4, "n_pairs": 5},
            "executed": True,
            "paper_refreshed": True,
            "primary_pass": True,
            "h2_pass": True,
            "h5_pass": True,
            "ready_status": "READY",
        },
    }
    (docs / "gate4_report.json").write_text(
        json.dumps(dirty_g4, indent=2) + "\n", encoding="utf-8"
    )

    # Import recover_tip with REPO_ROOT redirected to the temp repo.
    sys.path.insert(0, str(repo / "scripts"))
    # Ensure scripts/icml_env_checks is importable from the real tree.
    real_scripts = Path(__file__).resolve().parents[1] / "scripts"
    sys.path.insert(0, str(real_scripts))
    import icml_recover_tip as recover_mod

    monkeypatch.setattr(recover_mod, "REPO_ROOT", repo)

    rc = recover_mod.apply_tip(tip_sha)
    assert rc == 0

    after = json.loads((docs / "gate4_report.json").read_text(encoding="utf-8"))
    # Hard-reset restored clean committed JSON, then reinject restored prior_live.
    assert after.get("prior_live_metrics") is not None
    assert after["prior_live_metrics"]["ready_status"] == "READY"
    assert after["prior_live_metrics"]["comparison"]["d_wins_gens30"] == 4


def test_resolve_icml_target_agent_profile_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ICML_TARGET_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_TARGET_AGENT_PROFILE", raising=False)
    assert resolve_icml_target_agent_profile() == DEFAULT_ICML_TARGET_AGENT_PROFILE
    assert DEFAULT_ICML_TARGET_AGENT_PROFILE == "kimi-nebius-target"
    flags = icml_target_profile_cli_flags()
    assert flags == ["--target-agent-profile", "kimi-nebius-target"]


def test_resolve_icml_target_agent_profile_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ICML_TARGET_AGENT_PROFILE", "qwen-nebius-target")
    assert resolve_icml_target_agent_profile() == "qwen-nebius-target"
    monkeypatch.delenv("ICML_TARGET_AGENT_PROFILE", raising=False)
    monkeypatch.setenv("SIA_TARGET_AGENT_PROFILE", "gptoss-nebius-target")
    assert resolve_icml_target_agent_profile() == "gptoss-nebius-target"


def test_probe_icml_target_profile_nebius_default() -> None:
    ok, detail = probe_icml_target_profile_nebius()
    assert ok is True
    assert "nebius" in detail.lower()
    assert "kimi" in detail.lower() or "Kimi" in detail


def test_probe_icml_target_profile_rejects_default_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ICML_TARGET_AGENT_PROFILE", "default-target")
    ok, detail = probe_icml_target_profile_nebius()
    assert ok is False
    assert "anthropic" in detail.lower() or "want nebius" in detail


def test_resolve_icml_meta_agent_profile_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    assert resolve_icml_meta_agent_profile() == DEFAULT_ICML_META_AGENT_PROFILE
    assert DEFAULT_ICML_META_AGENT_PROFILE == "kimi-nebius-pydantic-meta"
    assert icml_meta_requires_anthropic() is False
    flags = icml_meta_profile_cli_flags()
    assert flags == ["--meta-agent-profile", "kimi-nebius-pydantic-meta"]
    ok, detail = probe_icml_meta_profile()
    assert ok is True
    assert "nebius" in detail.lower()


def test_icml_meta_default_meta_requires_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ICML_META_AGENT_PROFILE", "default-meta")
    assert icml_meta_requires_anthropic() is True
    ok, detail = probe_icml_meta_profile()
    assert ok is True
    assert "anthropic" in detail.lower()


def test_secrets_ok_with_nebius_only_under_nebius_meta(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 289: Anthropic optional when Nebius pydantic-ai meta is default."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    monkeypatch.setenv("NEBIUS_API_KEY", "nb-test")
    monkeypatch.setenv("HF_TOKEN", "hf-test")
    # Avoid picking up repo .env
    monkeypatch.setattr("icml_env_checks.load_icml_dotenv", lambda: [])
    monkeypatch.setattr("icml_env_checks.resolve_diamond_csv_path", lambda: None)
    status = collect_icml_secrets_status()
    assert status["meta_requires_anthropic"] is False
    assert status["secrets_ok_for_paid_sia"] is True
    assert status["fetch_diamond_ok"] is True
    assert "ANTHROPIC_API_KEY missing" not in status["blockers"]


def test_icml_human_required_secrets_phrase_anthropic_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tick 292: default Nebius meta must not demand Anthropic in human text."""
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    line = icml_human_required_secrets_phrase(for_fetch_diamond=True)
    assert "NEBIUS_API_KEY" in line
    assert "HF_TOKEN" in line or "gpqa_diamond.csv" in line
    assert "optional" in line.lower()
    # Must not lead with a hard Anthropic+Nebius conjunction.
    assert not line.startswith("ANTHROPIC_API_KEY + NEBIUS_API_KEY")
    anth = icml_human_required_secrets_phrase(
        for_fetch_diamond=False, profile="default-meta"
    )
    assert anth.startswith("ANTHROPIC_API_KEY + NEBIUS_API_KEY")


def test_portal_save_target_anthropic_optional() -> None:
    """Tick 308: portal_save_target must not hard-require Anthropic under Nebius meta."""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "docs" / "icml_portal_save_target.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    required = data.get("required_secrets") or []
    optional = data.get("optional_secrets") or []
    assert "NEBIUS_API_KEY" in required
    assert "ANTHROPIC_API_KEY" not in required
    assert "ANTHROPIC_API_KEY" in optional
    actions = " | ".join(data.get("external_actions") or [])
    assert "ANTHROPIC_API_KEY, NEBIUS_API_KEY, HF_TOKEN" not in actions
    assert "optional" in actions.lower()
    assert "NEBIUS_API_KEY" in actions


def test_env_example_and_section4_anthropic_optional() -> None:
    """Tick 309–322: .env.example + §3.3/4.1/4.4/4.5/6.2/6.3/8.2/9/12/13/18/21 + README + load_env + finish/present ICML-honest + python3."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    env_example = (root / ".env.example").read_text(encoding="utf-8")
    # Uncommented ANTHROPIC assignment would still look "required" to operators.
    active_anth = [
        ln
        for ln in env_example.splitlines()
        if ln.strip().startswith("ANTHROPIC_API_KEY=")
    ]
    assert not active_anth, (
        ".env.example must comment out ANTHROPIC_API_KEY under Nebius meta "
        f"(found active lines: {active_anth})"
    )
    assert "NEBIUS_API_KEY=" in env_example
    assert "optional" in env_example.lower()
    # Must not lead with legacy "Required — Meta + Feedback (Claude)" framing.
    assert "Required — Meta + Feedback agents (Claude SDK)" not in env_example

    master = (root / "docs" / "HACKATHON_MASTER_PLAN.md").read_text(encoding="utf-8")
    # Section 4.1 ICML note: Anthropic optional; Nebius covers meta under Tick 289+.
    assert "ICML Thesis 1 (Tick 289/308/309/310/311/312/313/314/315/316/317/318)" in master
    assert "do **not** wait on Anthropic" in master
    # Tick 315: §4.4 must list ICML Nebius defaults (not Anthropic/Nemotron as "all runs").
    assert "Approved model assignment (default for all runs)" not in master
    assert "TO BE CREATED in Phase 0" not in master
    assert "`kimi-nebius-pydantic-meta`" in master
    assert "`kimi-nebius-target`" in master
    assert "Kimi-K2.6 (ICML default)" in master
    assert "$0.95" in master and "$4.00" in master
    # After §4.4 rewrite, Anthropic default-meta must not be the sole "all runs" table lead.
    assert "ICML Thesis 1 live default (Tick 288/289/315" in master
    # Tick 316: §3.3 + §6.3 must not steer agents to Claude meta + Nemotron target.
    assert "Use Nemotron (cheapest fast option) for target" not in master
    assert "ICML Thesis 1 live default (Tick 288/289/316" in master
    assert "ICML §3.3 + §6.3 Nebius inference architecture (Tick 316)" in master
    assert "Claude Haiku          Nemotron / Qwen / Kimi" not in master
    # Tick 317: §13 Exact run commands + Phase 2 + §18 + §21.7 must not Nemotron-only for ICML.
    assert "ICML Thesis 1 live default (Tick 288/289/317)" in master
    assert "ICML §13/§18/§21.7 Kimi command surfaces (Tick 317)" in master
    assert "same target profile (`nemotron-nebius-target`)" not in master
    assert (
        "sia run --task gpqa --max_gen 5 --run_id 910 --no-web `\n"
        "  --target-agent-profile nemotron-nebius-target"
    ) not in master
    # Tick 310: Section 6.2 + Section 21 Tick 24/25/30 must not hard-pair Anthropic+Nebius.
    assert "hard-stops without `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY`" not in master
    assert (
        "when `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` + `HF_TOKEN` (accepted dataset access) are present"
        not in master
    )
    assert (
        "Live still blocked on `ANTHROPIC_API_KEY` + `NEBIUS_API_KEY` + `HF_TOKEN`"
        not in master
    )
    assert "**Gate:** Both keys set before any paid run." not in master
    assert "Gate (ICML Thesis 1 / Tick 289–328)" in master
    assert "Gate (ICML Thesis 1 / Tick 289–327)" not in master
    assert "Gate (ICML Thesis 1 / Tick 289–326)" not in master
    assert "Gate (ICML Thesis 1 / Tick 289–321)" not in master
    assert "Gate (ICML Thesis 1 / Tick 289–319)" not in master
    assert "Gate (ICML Thesis 1 / Tick 289–318)" not in master
    # Tick 313: §8.2 spending rules + Phase 0.2 must not hard-pair Anthropic for ICML.
    assert "Check Nebius + Anthropic dashboard before starting Phase 2." not in master
    assert "ICML Thesis 1 (Tick 313)" in master
    assert "Phase 0.2 Anthropic is **optional**" in master
    # Tick 314: Section 12 must not claim cloud API keys are DONE (agents skip secrets).
    assert "| `ANTHROPIC_API_KEY` configured | **DONE** | In `.env` |" not in master
    assert "| `NEBIUS_API_KEY` configured | **DONE** | In `.env` |" not in master
    assert "**ABSENT (cloud)**" in master
    assert "**OPTIONAL (ICML)**" in master
    assert "`HF_TOKEN` / diamond CSV" in master
    assert "ICML Section 12 cloud secrets honesty (Tick 314)" in master
    assert "ICML Section 4.4 Nebius model defaults (Tick 315)" in master
    # Stale Tick-30 paper_artifacts claim must not survive as Anthropic-hard-required.
    paper = (root / "docs" / "paper_artifacts.md").read_text(encoding="utf-8")
    assert (
        "live still blocked on missing `ANTHROPIC_API_KEY` / `NEBIUS_API_KEY` / `HF_TOKEN`"
        not in paper
    )
    # Tick 310: README quick start must not sole-require Anthropic.
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "set ANTHROPIC_API_KEY=your_key_here" not in readme
    assert "NEBIUS_API_KEY" in readme
    assert "optional" in readme.lower()
    assert "load_env.sh" in readme
    # Tick 318: README must lead ICML with cron/Kimi — not chess/Qwen-only or unapproved LawBench.
    assert "bash scripts/icml_cron_entry.sh" in readme
    assert "kimi-nebius-pydantic-meta" in readme
    assert "kimi-nebius-target" in readme
    assert "ICML Thesis 1 live stack" in readme
    assert "Do **not** run full LawBench without explicit human approval" in readme
    assert "sia run --task lawbench --max_gen 5 --run_id baseline" not in readme
    assert "ICML README Kimi command surfaces (Tick 318)" in master
    # Tick 319: judge-facing SUBMISSION + PRESENTATION must lead ICML (README still links them).
    # Tick 399: evidence IDs must track current offline_bvd_summary (not Tick-300 1890–1904).
    submission = (root / "docs" / "SUBMISSION.md").read_text(encoding="utf-8")
    presentation = (root / "docs" / "PRESENTATION.md").read_text(encoding="utf-8")
    assert "ICML Thesis 1" in submission
    assert "bash scripts/icml_cron_entry.sh" in submission
    assert "kimi-nebius-pydantic-meta" in submission
    assert "kimi-nebius-target" in submission
    assert "Do **not** run full LawBench without explicit human approval" in submission
    assert "1930–1934" in submission or "1930-1934" in submission
    assert "1940–1944" in submission or "1940-1944" in submission
    assert "run_1940" in submission
    assert "Future: web search, committee debate, Darwinian evolution in our sibling repo." not in presentation
    assert "ICML Thesis 1" in presentation
    assert "bash scripts/icml_cron_entry.sh" in presentation
    assert "Do not** run full LawBench" in presentation or "Do **not** run full LawBench" in presentation
    assert "1930–1934" in presentation or "1930-1934" in presentation
    assert "1940–1944" in presentation or "1940-1944" in presentation
    assert "ICML SUBMISSION + PRESENTATION judge surfaces (Tick 319)" in master
    assert "ICML judge-surface offline ID lock (Tick 399)" in master
    # Tick 400: operator-facing human-unblock must not freeze Tick-300 IDs.
    unblock = (root / "docs" / "ICML_HUMAN_UNBLOCK.md").read_text(encoding="utf-8")
    dual_idx = unblock.find("## Dual human unblock")
    dual = unblock[dual_idx : dual_idx + 900] if dual_idx != -1 else unblock[:900]
    assert "1930–1934" in dual or "1930-1934" in dual
    assert "1940–1944" in dual or "1940-1944" in dual
    assert "`1890–1904`" not in dual and "`1890-1904`" not in dual
    assert "ICML human-unblock offline ID lock (Tick 400)" in master
    # Tick 401: README evidence checklist must not freeze Tick-300 IDs.
    assert "1930–1934" in readme or "1930-1934" in readme
    assert "1940–1944" in readme or "1940-1944" in readme
    assert "1890–1904" not in readme and "1890-1904" not in readme
    assert "ICML README offline ID lock (Tick 401)" in master
    # Tick 320: judge one-command demos must be ICML-honest (no false READY).
    finish = (root / "scripts" / "finish_hackathon.py").read_text(encoding="utf-8")
    present = (root / "scripts" / "present_hackathon.py").read_text(encoding="utf-8")
    assert "ICML Thesis 1" in finish or "ICML THESIS 1" in finish
    assert "icml_cron_entry.sh" in finish
    assert "LawBench" in finish
    assert 'print("\\nREADY FOR SUBMISSION.")' not in finish
    assert "Do NOT treat this script's exit-0 as ICML_READY" in finish
    assert "offline_bvd_summary" in finish
    assert "ICML Thesis 1" in present or "ICML THESIS 1" in present
    assert "icml_cron_entry.sh" in present
    assert "LawBench" in present
    assert "offline_bvd_summary" in present
    assert "_offline_evidence_ids_blurb" in present
    assert "IDs 1890-1904" not in present and "IDs 1890–1904" not in present
    assert "ICML finish/present judge demos (Tick 320)" in master
    # Tick 445: finish/present STATUS read must be header-only (Tick 442/444 parity).
    assert "_icml_ready_status_header" in finish and "_icml_ready_status_header" in present
    assert r're.search(r"\*\*STATUS:' not in finish
    assert r're.search(r"\*\*STATUS:' not in present
    assert "ICML judge STATUS header-only (Tick 445)" in master
    # Tick 446: STATUS header token parse (READY + trailing IN_PROGRESS note).
    assert "_ICML_READY_STATUS_HEADER_RE" in (
        (root / "scripts" / "icml_env_checks.py").read_text(encoding="utf-8")
    )
    assert "ICML STATUS header token parse (Tick 446)" in master
    # Tick 447: plain (no ``**``) STATUS headers must parse + demote/update.
    env_checks = (root / "scripts" / "icml_env_checks.py").read_text(encoding="utf-8")
    # Tick 450 evolved ``STATUS:`` → ``STATUS(?:\*\*)?:`` (colon-outside-bold);
    # Tick 461 further allows optional whitespace before ``:`` (``STATUS :``).
    # still requires optional leading ``**`` so bare STATUS lines match.
    assert (
        r"^(?:\*\*)?STATUS:" in env_checks
        or "(?:\\*\\*)?STATUS:" in env_checks
        or r"(?:\*\*)?STATUS(?:\*\*)?:" in env_checks
        or "(?:\\*\\*)?STATUS(?:\\*\\*)?:" in env_checks
        or r"(?:\*\*)?STATUS(?:\*\*)?\s*:" in env_checks
        or "(?:\\*\\*)?STATUS(?:\\*\\*)?\\s*:" in env_checks
        # Tick 464: colon may be `_ICML_STATUS_COLON` (`[:：]`) via string concat.
        or (
            r"(?:\*\*)?STATUS(?:\*\*)?\s*" in env_checks
            and "_ICML_STATUS_COLON" in env_checks
        )
    )
    assert "_icml_ready_status_line_match" in env_checks
    g4_src = (root / "scripts" / "run_g4_multiseed.py").read_text(encoding="utf-8")
    assert "_icml_ready_status_line_match" in g4_src
    assert "ICML plain STATUS header (Tick 447)" in master
    # Tick 448: ATX heading STATUS (``# STATUS:`` / ``## **STATUS:**``).
    assert "#{1,6}" in env_checks or r"#{1,6}" in env_checks
    assert "ICML ATX heading STATUS header (Tick 448)" in master
    # Tick 449: bold-closed label ``**STATUS:** READY`` (token outside bold).
    # Tick 450 evolved colon placement; Tick 452 split alts so the READY token
    # may sit after a shared group — still require optional ``**`` after ``:``
    # on the bold/plain STATUS arm.
    assert (
        r"STATUS:\s*(?:\*\*)?\s*(READY|IN_PROGRESS)" in env_checks
        or "STATUS:\\s*(?:\\*\\*)?\\s*(READY|IN_PROGRESS)" in env_checks
        or r"STATUS(?:\*\*)?:\s*(?:\*\*)?\s*(READY|IN_PROGRESS)" in env_checks
        or "STATUS(?:\\*\\*)?:\\s*(?:\\*\\*)?\\s*(READY|IN_PROGRESS)" in env_checks
        or r"STATUS(?:\*\*)?:\s*(?:\*\*)?\s*" in env_checks
        or "STATUS(?:\\*\\*)?:\\s*(?:\\*\\*)?\\s*" in env_checks
        or r"STATUS(?:\*\*)?\s*:\s*(?:\*\*)?\s*" in env_checks
        or "STATUS(?:\\*\\*)?\\s*:\\s*(?:\\*\\*)?\\s*" in env_checks
        # Tick 464: colon via ``_ICML_STATUS_COLON`` string concat.
        or (
            r"(?:\*\*)?STATUS(?:\*\*)?\s*" in env_checks
            and "_ICML_STATUS_COLON" in env_checks
            and r"\s*(?:\*\*)?\s*" in env_checks
        )
    )
    assert "(READY|IN_PROGRESS)" in env_checks
    assert "ICML bold-closed label STATUS header (Tick 449)" in master
    assert "test_icml_ready_status_header_accepts_bold_closed_label_status" in (
        (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 450: colon-outside-bold ``**STATUS**: READY`` (Tick 461: optional ``\s*`` before ``:``).
    assert (
        r"STATUS(?:\*\*)?:" in env_checks
        or "STATUS(?:\\*\\*)?:" in env_checks
        or r"STATUS(?:\*\*)?\s*:" in env_checks
        or "STATUS(?:\\*\\*)?\\s*:" in env_checks
        or (
            r"STATUS(?:\*\*)?\s*" in env_checks
            and "_ICML_STATUS_COLON" in env_checks
        )
    )
    assert "ICML colon-outside-bold STATUS header (Tick 450)" in master
    assert "test_icml_ready_status_header_accepts_colon_outside_bold_status" in (
        (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 451: blockquote / list container + BOM STATUS headers.
    assert r"(?:>\s*)?" in env_checks or "(?:>\\s*)?" in env_checks
    assert r"[-*+]\s+" in env_checks or "[-*+]\\s+" in env_checks
    assert "\\ufeff" in env_checks or "\ufeff" in env_checks
    assert "ICML blockquote/list/BOM STATUS header (Tick 451)" in master
    assert "test_icml_ready_status_header_accepts_blockquote_list_bom_status" in (
        (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 452: italic / underscore emphasis STATUS headers.
    assert r"\*STATUS\*?" in env_checks or "\\*STATUS\\*?" in env_checks
    assert "_STATUS_?" in env_checks
    assert "(?!\\w)" in env_checks or r"(?!\w)" in env_checks
    assert "ICML italic/underscore STATUS header (Tick 452)" in master
    assert "test_icml_ready_status_header_accepts_italic_underscore_status" in (
        (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 453: double-underscore bold / triple-star bold+italic STATUS headers.
    assert r"\*{3}STATUS" in env_checks or "\\*{3}STATUS" in env_checks
    assert "__STATUS(?:__)?" in env_checks or "__STATUS(?:__)?" in env_checks
    assert "ICML dunder/triple-star STATUS header (Tick 453)" in master
    assert "test_icml_ready_status_header_accepts_dunder_triple_star_status" in (
        (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 454: ZWSP strip + nested bold↔dunder STATUS headers.
    assert "_strip_icml_status_line_noise" in env_checks
    assert "_ICML_STATUS_INVISIBLE_CHARS_RE" in env_checks
    assert r"\*\*__STATUS" in env_checks or "\\*\\*__STATUS" in env_checks
    assert r"__\*\*STATUS" in env_checks or "__\\*\\*STATUS" in env_checks
    assert r"\*\*__|__\*\*" in env_checks or "\\*\\*__|__\\*\\*" in env_checks
    assert "ICML ZWSP/nested bold-dunder STATUS header (Tick 454)" in master
    assert "test_icml_ready_status_header_accepts_zwsp_nested_bold_dunder_status" in (
        (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 455: HTML-entity ZWSP / nbsp decode before Unicode strip.
    assert "_decode_icml_status_html_entities" in env_checks
    assert "_ICML_STATUS_HTML_ENTITY_RE" in env_checks
    assert "ZeroWidthSpace" in env_checks
    assert "ICML HTML-entity ZWSP/nbsp STATUS header (Tick 455)" in master
    assert "test_icml_ready_status_header_accepts_html_entity_zwsp_nbsp_status" in (
        (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 456: HTML-tag wrappers stripped before STATUS match.
    assert "_strip_icml_status_html_tags" in env_checks
    assert "_ICML_STATUS_HTML_TAG_RE" in env_checks
    assert "strong|b|em|i|p|div|span" in env_checks
    assert "ICML HTML-tag-wrapped STATUS header (Tick 456)" in master
    assert "test_icml_ready_status_header_accepts_html_tag_wrapped_status" in (
        (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 457: HTML heading tags + markdown backtick/strikethrough wrappers.
    assert "h[1-6]" in env_checks
    assert "_strip_icml_status_md_wrappers" in env_checks
    assert "_ICML_STATUS_MD_WRAP_RE" in env_checks
    assert "ICML HTML-heading + markdown-wrap STATUS header (Tick 457)" in master
    assert "test_icml_ready_status_header_accepts_html_heading_and_md_wrap_status" in (
        (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 458: HTML container tags + Obsidian == / nested md wrappers.
    assert "blockquote|li|ul|ol" in env_checks
    assert r"(?:==)(.*?)(?:==)" in env_checks or "(?:==)(.*?)(?:==)" in env_checks
    assert "ICML HTML-container + Obsidian STATUS header (Tick 458)" in master
    assert "test_icml_ready_status_header_accepts_html_container_and_obsidian_status" in (
        (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 459: HTML table/semantic + markdown pipe-table STATUS.
    assert "table|thead|tbody|tfoot|tr|td|th" in env_checks
    assert "section|article|header|main" in env_checks
    assert "_strip_icml_status_md_table_pipes" in env_checks
    assert "_ICML_STATUS_MD_PIPE_RE" in env_checks
    assert "ICML HTML-table + semantic + md-pipe STATUS header (Tick 459)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_table_semantic_and_md_pipe_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 460: iterative wrap+pipe (+ container prefix) STATUS peel.
    assert "_ICML_STATUS_MD_CONTAINER_PREFIX_RE" in env_checks
    assert "ICML wrap-around md-pipe STATUS header (Tick 460)" in master
    assert (
        "test_icml_ready_status_header_accepts_wrap_around_md_pipe_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 461: quote-wrap + space-before-colon + strict one-cell pipe peel.
    assert r'^(?:")(.*?)(?:")$' in env_checks or '^(?:")(.*?)(?:")$' in env_checks
    assert r"([^|]*?)" in env_checks  # one-cell pipe inner
    assert "ICML quote + space-colon STATUS header (Tick 461)" in master
    assert (
        "test_icml_ready_status_header_accepts_quote_and_space_colon_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 462: GitHub task-list checkbox + inline token-wrap STATUS.
    assert r"\[[ xX]\]" in env_checks or "[[ xX]]" in env_checks
    assert r"(?:`+|~~)?" in env_checks or "(?:`+|~~)?" in env_checks
    assert "ICML task-list + token-wrap STATUS header (Tick 462)" in master
    assert (
        "test_icml_ready_status_header_accepts_task_list_and_token_wrap_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 463: bare / ordered / blockquote checkbox STATUS (no ``[-*+]`` required).
    assert r"\[[ xX]\]\s+" in env_checks or "[[ xX]]\\s+" in env_checks
    assert r"(?:[-*+]|\d+[.)])" in env_checks or "(?:[-*+]|\\d+[.)])" in env_checks
    assert "ICML bare + ordered checkbox STATUS header (Tick 463)" in master
    assert (
        "test_icml_ready_status_header_accepts_bare_ordered_blockquote_checkbox_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 464: paren / bracket / brace wrap + fullwidth colon STATUS.
    assert r"^\((.*?)\)$" in env_checks or "^\\((.*?)\\)$" in env_checks
    assert "_ICML_STATUS_COLON" in env_checks
    assert "[:：]" in env_checks or "[:\\uff1a]" in env_checks or "：]" in env_checks
    assert "ICML paren/bracket/brace + fullwidth-colon STATUS header (Tick 464)" in master
    assert (
        "test_icml_ready_status_header_accepts_paren_bracket_brace_fullwidth_colon_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 465: markdown-link + HTML-anchor STATUS.
    assert "_ICML_STATUS_MD_LINK_RE" in env_checks
    assert r"^\[([^\]]*)\]\([^)]*\)\s*$" in env_checks or "\\[([^\\]]*)\\]\\([^)]*\\)" in env_checks
    # Tick 469 extended allowlist to ``a|button|picture|source)`` — still must
    # include ``a|button`` (anchor peel); accept either suffix.
    assert (
        "|a|button)" in env_checks
        or "a|button)" in env_checks
        or "a|button|picture|source)" in env_checks
    )
    assert r"(?:\s[^>]*)?\s*/?>" in env_checks or "[^>]*" in env_checks
    assert "ICML md-link + HTML-anchor STATUS header (Tick 465)" in master
    assert (
        "test_icml_ready_status_header_accepts_md_link_and_html_anchor_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 466: nested-paren URL markdown-link STATUS (balanced destination scan).
    assert "_peel_icml_status_md_link" in env_checks
    assert "Balanced-paren scan" in env_checks or "balanced nested" in env_checks
    assert "ICML md-link nested-paren URL STATUS header (Tick 466)" in master
    assert (
        "test_icml_ready_status_header_accepts_md_link_nested_paren_url_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 467: markdown-image STATUS (shields.io / Notion badge exports).
    assert 'startswith("![")' in env_checks or "startswith('![')" in env_checks
    assert "ICML md-image STATUS header (Tick 467)" in master
    assert (
        "test_icml_ready_status_header_accepts_md_image_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 468: HTML ``<img alt="STATUS:…">`` STATUS (Notion/Docs badge exports).
    assert "_peel_icml_status_html_img_alt" in env_checks
    assert "_ICML_STATUS_HTML_IMG_TAG_RE" in env_checks
    assert r'\balt\s*=\s*(?:"([^"]*)"|' in env_checks or "alt" in env_checks
    assert "ICML html-img-alt STATUS header (Tick 468)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_img_alt_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 469: HTML ``<picture><img alt="STATUS:…">`` responsive badge exports.
    assert "picture|source)" in env_checks or "picture|source|" in env_checks
    assert "ICML html-picture STATUS header (Tick 469)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_picture_img_alt_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 470: HTML ``<img title=…>`` / ``aria-label=…`` STATUS badge exports.
    assert "aria-label" in env_checks
    assert "_ICML_STATUS_HTML_IMG_ATTR_RE" in env_checks
    assert "ICML html-img-title-aria STATUS header (Tick 470)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_img_title_aria_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 471: HTML inline SVG ``<title>STATUS:…</title>`` badge exports.
    assert "_peel_icml_status_html_svg_title" in env_checks
    assert "_ICML_STATUS_HTML_SVG_TAG_RE" in env_checks
    assert "ICML html-svg-title STATUS header (Tick 471)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_svg_title_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 472: HTML SVG root ``aria-label=`` / ``title=`` STATUS badge exports.
    assert "_ICML_STATUS_HTML_SVG_OPEN_RE" in env_checks
    assert "_ICML_STATUS_HTML_SVG_ATTR_RE" in env_checks
    assert "ICML html-svg-aria-title-attr STATUS header (Tick 472)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_svg_aria_title_attr_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 473: HTML SVG nested ``<desc>STATUS:…</desc>`` badge exports.
    assert "_ICML_STATUS_HTML_SVG_DESC_RE" in env_checks
    assert "nested_descs" in env_checks or "nested <desc>" in env_checks
    assert "ICML html-svg-desc STATUS header (Tick 473)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_svg_desc_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 474: HTML SVG nested ``<text>STATUS:…</text>`` badge exports.
    assert "_ICML_STATUS_HTML_SVG_TEXT_RE" in env_checks
    assert "_svg_inner_plain_text" in env_checks
    assert "nested_texts" in env_checks or "nested <text>" in env_checks
    assert "ICML html-svg-text STATUS header (Tick 474)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_svg_text_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 475: HTML SVG nested ``<foreignObject>STATUS:…</foreignObject>``.
    assert "_ICML_STATUS_HTML_SVG_FOREIGN_OBJECT_RE" in env_checks
    assert "nested_foreign" in env_checks or "nested <foreignObject>" in env_checks
    assert "ICML html-svg-foreignObject STATUS header (Tick 475)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_svg_foreign_object_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 476: pretty-printed multi-line ``<svg>…</svg>`` STATUS badge exports.
    assert "_take_icml_status_multiline_svg_block" in env_checks
    assert "_iter_icml_ready_status_units" in env_checks
    assert "ICML html-svg-multiline STATUS header (Tick 476)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_svg_multiline_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 477: pretty-printed multi-line ``<img …>`` STATUS badge exports.
    assert "_take_icml_status_multiline_img_block" in env_checks
    assert "_ICML_STATUS_IMG_BLOCK_OPEN_RE" in env_checks
    assert "ICML html-img-multiline STATUS header (Tick 477)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_img_multiline_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 478: mid-line ``<img`` after ``<picture>``/``<source>`` multiline.
    assert "_ICML_STATUS_IMG_INLINE_OPEN_RE" in env_checks
    assert "_ICML_STATUS_HTML_IMG_COMPLETE_RE" in env_checks
    assert "ICML html-picture-img-multiline STATUS header (Tick 478)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_picture_img_multiline_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 479: mid-line ``<svg`` after ``<div>``/``<a>``/``<figure>`` multiline.
    assert "_ICML_STATUS_SVG_INLINE_OPEN_RE" in env_checks
    assert "_ICML_STATUS_HTML_SVG_COMPLETE_RE" in env_checks
    assert "ICML html-svg-inline-multiline STATUS header (Tick 479)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_svg_inline_multiline_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 480: soft-wrapped markdown link/image STATUS.
    assert "_take_icml_status_multiline_md_link_block" in env_checks
    assert "_ICML_STATUS_MD_LINK_OPEN_RE" in env_checks
    assert "ICML md-link-softwrap STATUS header (Tick 480)" in master
    assert (
        "test_icml_ready_status_header_accepts_md_link_softwrap_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 481: HTML <a>/<button> title/aria-label STATUS (+ multiline).
    assert "_peel_icml_status_html_a_title" in env_checks
    assert "_take_icml_status_multiline_a_block" in env_checks
    assert "_ICML_STATUS_HTML_A_COMPLETE_RE" in env_checks
    assert "ICML html-a-title-aria STATUS header (Tick 481)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_a_title_aria_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 482: HTML span/label/div/… title/aria-label STATUS (+ multiline).
    assert "_peel_icml_status_html_span_title" in env_checks
    assert "_take_icml_status_multiline_span_block" in env_checks
    assert "_ICML_STATUS_HTML_SPAN_COMPLETE_RE" in env_checks
    assert "ICML html-span-label-title-aria STATUS header (Tick 482)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_span_label_title_aria_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 483: HTML p/strong/h1/td/… title/aria-label STATUS (+ multiline).
    assert "_peel_icml_status_html_inline_title" in env_checks
    assert "_take_icml_status_multiline_inline_block" in env_checks
    assert "_ICML_STATUS_HTML_INLINE_COMPLETE_RE" in env_checks
    assert "ICML html-inline-title-aria STATUS header (Tick 483)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_inline_title_aria_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 484: HTML aria-description STATUS on allowlisted a11y badges.
    assert "aria-description" in env_checks
    assert 'r"""\\b(title|aria-label|aria-description)' in env_checks or (
        "(title|aria-label|aria-description)" in env_checks
    )
    assert "ICML html-aria-description STATUS header (Tick 484)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_aria_description_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 485: unquoted HTML STATUS attrs (minified / CMS badge exports).
    assert "_ICML_STATUS_HTML_ATTR_VALUE" in env_checks
    assert "_icml_status_html_attr_value" in env_checks
    assert '|([^\\s"\'=<>`]+))' in env_checks
    assert "ICML html-unquoted-attr STATUS header (Tick 485)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_unquoted_attr_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 486: HTML-entity STATUS colon (&#58; / &colon; / &#x3a; / &#xff1a;).
    assert "&colon;" in env_checks or "colon" in env_checks
    assert "0x3A" in env_checks or "0x3a" in env_checks
    assert "ICML html-entity-colon STATUS header (Tick 486)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_entity_colon_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 487: double-escaped HTML STATUS (&amp;#58; / &lt;p title=&quot;…&quot;&gt;).
    assert "_ICML_STATUS_DOUBLE_AMP_RE" in env_checks
    assert "&amp;" in env_checks
    assert '"lt":' in env_checks or "'lt':" in env_checks
    assert "ICML html-double-escaped STATUS header (Tick 487)" in master
    assert (
        "test_icml_ready_status_header_accepts_html_double_escaped_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 488: JSON/JS unicode+hex STATUS escapes (\u003a / \x3a / \u003c…).
    assert "_ICML_STATUS_JS_ESCAPE_RE" in env_checks
    assert r"\\u(" in env_checks or "\\\\u(" in env_checks
    assert "0x20" in env_checks
    assert "ICML js-unicode-escaped STATUS header (Tick 488)" in master
    assert (
        "test_icml_ready_status_header_accepts_js_unicode_escaped_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 489: URL percent-encoded STATUS (%3A / %20 / %3C… / form +).
    assert "_ICML_STATUS_URL_PERCENT_RE" in env_checks
    assert "%([0-9a-fA-F]{2})" in env_checks or r"%([0-9a-fA-F]{2})" in env_checks
    assert "0x25" in env_checks and "0x3D" in env_checks and "0x2F" in env_checks
    assert "ICML url-percent-encoded STATUS header (Tick 489)" in master
    assert (
        "test_icml_ready_status_header_accepts_url_percent_encoded_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 490: MIME quoted-printable STATUS (=3A / =20 / =3C… / soft-break).
    assert "_ICML_STATUS_QUOTED_PRINTABLE_RE" in env_checks
    assert "_ICML_STATUS_QP_SOFT_BREAK_RE" in env_checks
    assert "=([0-9a-fA-F]{2})" in env_checks or r"=([0-9a-fA-F]{2})" in env_checks
    assert "_take_icml_status_qp_soft_break_block" in env_checks
    assert "ICML quoted-printable STATUS header (Tick 490)" in master
    assert (
        "test_icml_ready_status_header_accepts_quoted_printable_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 491: RFC 2047 encoded-word STATUS (=?UTF-8?Q?…?= / =?UTF-8?B?…?=).
    assert "_ICML_STATUS_RFC2047_WORD_RE" in env_checks
    assert "_ICML_STATUS_RFC2047_RUN_RE" in env_checks
    assert "_peel_icml_status_rfc2047_encoded_words" in env_checks
    assert "0x5F" in env_checks  # Q =5F → underscore for IN_PROGRESS
    assert "ICML rfc2047-encoded-word STATUS header (Tick 491)" in master
    assert (
        "test_icml_ready_status_header_accepts_rfc2047_encoded_word_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 492: bare base64 STATUS payload (RFC 2047 wrappers stripped).
    assert "_ICML_STATUS_BARE_BASE64_RE" in env_checks
    assert "_peel_icml_status_bare_base64" in env_checks
    assert "ICML bare-base64 STATUS header (Tick 492)" in master
    assert (
        "test_icml_ready_status_header_accepts_bare_base64_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 493: data-URI base64 STATUS (RFC 2397 wrapper kept on paste).
    assert "_ICML_STATUS_DATA_URI_RE" in env_checks
    assert "_peel_icml_status_data_uri_base64" in env_checks
    assert "data:" in env_checks and ";base64," in env_checks
    assert "ICML data-URI base64 STATUS header (Tick 493)" in master
    assert (
        "test_icml_ready_status_header_accepts_data_uri_base64_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 494: plain / percent-encoded data-URI STATUS (no ;base64).
    assert "_ICML_STATUS_DATA_URI_PLAIN_RE" in env_checks
    assert "_peel_icml_status_data_uri_plain" in env_checks
    assert "STATUS%3A%20READY" in env_checks or "unquote" in env_checks
    assert "ICML data-URI plain STATUS header (Tick 494)" in master
    assert (
        "test_icml_ready_status_header_accepts_data_uri_plain_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 495: bare hex STATUS (log / packet / hex-dump paste).
    assert "_ICML_STATUS_BARE_HEX_CONT_RE" in env_checks
    assert "_ICML_STATUS_BARE_HEX_SEP_RE" in env_checks
    assert "_peel_icml_status_bare_hex" in env_checks
    assert "5354415455533A205245414459" in env_checks or "fromhex" in env_checks
    assert "ICML bare-hex STATUS header (Tick 495)" in master
    assert (
        "test_icml_ready_status_header_accepts_bare_hex_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 496: C-array / comma / per-byte 0x hex STATUS.
    assert "_ICML_STATUS_BARE_HEX_COMMA_RE" in env_checks
    assert "_ICML_STATUS_BARE_HEX_0X_BYTE_RE" in env_checks
    assert "_ICML_STATUS_BARE_HEX_CARRAY_RE" in env_checks
    assert "0x53,0x54" in env_checks or "C-array" in env_checks
    assert "ICML C-array/comma-hex STATUS header (Tick 496)" in master
    assert (
        "test_icml_ready_status_header_accepts_carray_hex_status"
        in (root / "tests" / "test_icml_env_checks.py").read_text(encoding="utf-8")
    )
    # Tick 321: cold-cloud finish must bootstrap/SKIP pytest and always print ICML footer.
    assert "_ensure_pytest" in finish
    assert "_print_icml_footer" in finish
    assert "pip install" in finish and "--user" in finish
    assert "not an ICML PRIMARY failure" in finish
    assert "ICML finish pytest bootstrap (Tick 321)" in master
    # Tick 322: cold-cloud / Linux judge path must prefer python3 (no bare `python` shim).
    assert "python3 scripts/finish_hackathon.py" in submission
    assert "python3 scripts/present_hackathon.py" in submission
    assert "python3 scripts/present_hackathon.py" in presentation
    assert "python3 scripts/finish_hackathon.py" in presentation
    assert "python3 scripts/finish_hackathon.py" in readme
    assert "python3 scripts/present_hackathon.py" in readme
    # finish/present must print the live interpreter, not a hardcoded bare `python` shim.
    assert "Path(sys.executable).name" in finish
    assert "Path(sys.executable).name" in present
    assert 'python scripts/finish_hackathon.py\n  python scripts/present_hackathon.py' not in finish
    assert "ICML python3-safe judge entrypoints (Tick 322)" in master
    # Tick 323: gate Next / refuse / prepare / verify_keys must use live interpreter
    # basename (cold Linux has no bare `python` shim) — not hardcoded `python scripts/…`.
    py = icml_python_cli()
    assert py  # usually python3 on Linux/cloud
    env_checks = (root / "scripts" / "icml_env_checks.py").read_text(encoding="utf-8")
    assert "def icml_python_cli" in env_checks
    g2 = (root / "scripts" / "run_g2_smoke.py").read_text(encoding="utf-8")
    g3 = (root / "scripts" / "run_g3_pilot.py").read_text(encoding="utf-8")
    g4 = (root / "scripts" / "run_g4_multiseed.py").read_text(encoding="utf-8")
    pipeline = (root / "scripts" / "run_icml_live_pipeline.py").read_text(encoding="utf-8")
    verify = (root / "scripts" / "verify_keys.py").read_text(encoding="utf-8")
    diamond = (root / "scripts" / "prepare_gpqa_diamond.py").read_text(encoding="utf-8")
    smoke = (root / "scripts" / "prepare_gpqa_smoke_data.py").read_text(encoding="utf-8")
    assert "icml_python_cli" in g2 and "icml_python_cli" in g3 and "icml_python_cli" in g4
    assert "icml_python_cli" in pipeline and "icml_python_cli" in diamond
    assert "icml_python_cli" in smoke
    assert "`python scripts/prepare_gpqa_diamond.py" not in g2
    assert "`python scripts/run_g2_smoke.py --live" not in g2
    assert "`python scripts/run_g3_pilot.py --live" not in g3
    assert "`python scripts/run_g4_multiseed.py --live" not in g4
    assert "python scripts/icml_recover_tip.py --apply" not in g2
    assert "python scripts/icml_recover_tip.py --apply" not in g3
    assert "python scripts/icml_recover_tip.py --apply" not in g4
    assert "Recover tip: python scripts/icml_recover_tip.py --apply" not in pipeline
    assert 'python scripts/verify_keys.py"' not in verify
    assert "Path(sys.executable).name" in verify or "icml_python_cli" in verify
    assert "{py} scripts/run_g2_smoke.py --live" in diamond
    assert "ICML python3-safe gate Next (Tick 323)" in master
    # Tick 324: Section 21.7 protocol copy-paste must use python3 (not bare python).
    marker_217 = "### 21.7 Suggested cheap GPQA commands"
    idx_217 = master.find(marker_217)
    assert idx_217 >= 0
    idx_218 = master.find("### 21.8", idx_217)
    assert idx_218 > idx_217
    section_217 = master[idx_217:idx_218]
    assert "python3 scripts/prepare_gpqa_smoke_data.py" in section_217
    assert "python3 scripts/prepare_gpqa_diamond.py" in section_217
    assert "python3 scripts/run_g2_smoke.py" in section_217
    assert "python3 scripts/run_g3_pilot.py" in section_217
    assert "python3 scripts/run_g4_multiseed.py" in section_217
    assert "python3 scripts/run_icml_live_pipeline.py" in section_217
    assert "\npython scripts/" not in section_217
    assert "ICML python3-safe Section 21.7 (Tick 324)" in master
    # Tick 326: gate/pipeline/prepare/recover/epistemic --help Examples must use
    # python3 (cold Linux has no bare `python` shim) — same class of fail as §21.7.
    recover = (root / "scripts" / "icml_recover_tip.py").read_text(encoding="utf-8")
    epi = (root / "scripts" / "epistemic_results.py").read_text(encoding="utf-8")
    for label, body in (
        ("run_g2_smoke", g2),
        ("run_g3_pilot", g3),
        ("run_g4_multiseed", g4),
        ("run_icml_live_pipeline", pipeline),
        ("prepare_gpqa_diamond", diamond),
        ("prepare_gpqa_smoke_data", smoke),
        ("icml_recover_tip", recover),
        ("epistemic_results", epi),
    ):
        assert "python3 scripts/" in body, f"{label} must show python3 examples"
        assert "\n  python scripts/" not in body, (
            f"{label} --help Examples still lead with bare python scripts/…"
        )
    assert "ICML python3-safe script --help Examples (Tick 326)" in master
    # Tick 327: dual human unblock — secrets AND merge tip → main (cron boots main).
    unblock = (root / "docs" / "ICML_HUMAN_UNBLOCK.md").read_text(encoding="utf-8")
    assert "Dual human unblock (Tick 327" in unblock
    assert "Merge the latest tip PR into `main`" in unblock
    assert "cron boots from **`main`**" in unblock or "Cron boots from **`main`**" in unblock
    assert "ICML dual human unblock — secrets + merge tip→main (Tick 327)" in master
    # Tick 328: machine-readable dual unblock — secrets status / tip status /
    # pipeline Next surface merge tip→main when main lacks ICML tip files.
    env_checks = (root / "scripts" / "icml_env_checks.py").read_text(encoding="utf-8")
    assert "def main_has_icml_tip_files" in env_checks
    assert "main_has_icml_tip" in env_checks
    assert "_merge_tip_to_main_human_next" in env_checks
    assert "Merge the latest ICML tip PR into `main`" in env_checks
    assert "ICML machine-readable dual unblock (Tick 328)" in master
    # Tick 329: cron prints *full* human_next on --preflight-only / auto /
    # live-refuse (Tick 328 wrote merge tip into JSON but preflight stayed silent).
    cron = (root / "scripts" / "icml_cron_entry.sh").read_text(encoding="utf-8")
    assert "print_human_next" in cron
    assert "Human next (dual unblock)" in cron
    assert "ICML cron full human_next on blocked paths (Tick 329)" in master
    # Tick 330: concrete tip PR URL in human_next / tip+secrets JSON (300+ drafts).
    assert "def resolve_icml_tip_pr" in env_checks
    assert "tip_pr_url" in env_checks
    assert "Concrete tip PR" in env_checks
    assert "ICML concrete tip PR URL in human_next (Tick 330)" in master
    # Tick 331: tip lineage also scans cursor/bc-* cloud cron boot branches.
    assert "cursor/bc-" in env_checks
    assert "_TIP_FOR_EACH_REF_PATTERNS" in env_checks
    assert "cursor/bc-*" in cron
    assert "cursor/bc-*" in (root / "scripts" / "icml_pick_remote_tip.sh").read_text(
        encoding="utf-8"
    )
    assert "Tick 331" in unblock
    assert "ICML tip lineage scans cursor/bc-* cron boots (Tick 331)" in master
    # Tick 332: HUMAN_UNBLOCK chicken-egg (+ script headers) must also
    # fetch/scan cursor/bc-* — Tick 331 fixed pickers/AGENTS only.
    assert "cursor/bc-*" in unblock
    # The copy-paste chicken-egg block (not only the Tick 331 prose) must scan bc-*.
    assert (
        "refs/remotes/origin/cursor/bc-*" in unblock
        or "'refs/remotes/origin/cursor/bc-*'" in unblock
    )
    assert "Tick 332" in unblock
    assert "ICML HUMAN_UNBLOCK chicken-egg scans cursor/bc-* (Tick 332)" in master
    boot = (root / "scripts" / "icml_boot_recover.sh").read_text(encoding="utf-8")
    assert "cursor/bc-*" in boot
    assert "cursor/bc-*" in cron
    # Tick 333: same-SHA sibling tip PR fallback (not unrelated ICML PR).
    assert "same-SHA" in unblock or "same-SHA sibling" in unblock
    assert "Tick 333" in unblock
    assert "ICML same-SHA sibling tip PR fallback (Tick 333)" in master
    assert "same-SHA sibling tip PR fallback" in env_checks
    assert "_sha_prefix_equal" in env_checks
    assert "_gh_pr_list_for_head" in env_checks
    # Tick 334: unpushed greenfield tip_ref still resolves via HEAD/local SHA.
    assert "_tip_sha_for_pr_resolve" in env_checks
    assert "Tick 334" in unblock
    assert "HEAD/local" in unblock or "unpushed" in unblock.lower()
    assert "ICML tip PR HEAD/local SHA fallback (Tick 334)" in master
    # Tick 335: tip PR mergeability (MERGEABLE/CLEAN) in human_next + JSON.
    assert "_tip_pr_mergeability_note" in env_checks
    assert "mergeable" in env_checks
    assert "mergeStateStatus" in env_checks
    assert "tip_pr_mergeable" in env_checks
    assert "Tick 335" in unblock
    assert "MERGEABLE" in unblock or "mergeability" in unblock.lower()
    assert "ICML tip PR mergeability in human_next (Tick 335)" in master
    # Tick 505: UNKNOWN mergeability refresh via gh pr view.
    assert "refresh_pr_mergeability" in env_checks
    assert "_gh_pr_view_mergeability" in env_checks
    assert "ICML UNKNOWN tip PR mergeability refresh (Tick 505)" in master
    assert "Tick 505" in unblock
    # Tick 506: tip PR title/body NEBIUS-only when on-disk diamond ready.
    assert "icml_diamond_source_ready_for_nebius_only" in env_checks
    assert "ICML tip PR title NEBIUS-only ondisk (Tick 506)" in master
    assert "Tick 506" in unblock
    assert "test_suggested_open_git_pr_title_nebius_only_when_ondisk_diamond" in (
        root / "tests" / "test_icml_env_checks.py"
    ).read_text(encoding="utf-8")
    # Tick 336: gh copy-paste merge commands + tip-PR churn warning.
    assert "_tip_pr_merge_commands" in env_checks
    assert "tip_pr_merge_commands" in env_checks
    assert "gh pr ready" in env_checks
    assert "gh pr merge" in env_checks
    assert "Tick 336" in unblock
    assert "copy-paste" in unblock.lower() or "gh pr" in unblock
    assert "ICML tip PR gh copy-paste merge commands (Tick 336)" in master
    # Tick 337: tip PR anti-churn — prefer_tip_pr_commit_branch / checkout script.
    assert "def prefer_tip_pr_commit_branch" in env_checks
    assert "tip_pr_commit_branch" in env_checks
    assert "tip_pr_anti_churn" in env_checks
    assert "do NOT open a new tip PR" in env_checks
    assert "Tick 337" in unblock
    assert "anti-churn" in unblock.lower() or "tip_pr_commit_branch" in unblock
    assert "ICML tip PR anti-churn (Tick 337)" in master
    checkout = (root / "scripts" / "icml_checkout_tip_pr_branch.sh").read_text(
        encoding="utf-8"
    )
    assert "tip_pr_commit_branch" in checkout
    assert "anti-churn" in checkout.lower()
    # Tick 338: cron_entry auto-checkouts tip_pr_commit_branch (closes Tick-337 gap).
    cron_entry = (root / "scripts" / "icml_cron_entry.sh").read_text(encoding="utf-8")
    assert "tip_pr_anti_churn_checkout" in cron_entry
    assert "icml_checkout_tip_pr_branch.sh" in cron_entry
    assert "Tick 338" in cron_entry
    assert "Tick 338" in unblock
    assert "auto-checkout" in unblock.lower() or "auto-checkouts" in unblock.lower()
    assert "ICML cron tip PR anti-churn auto-checkout (Tick 338)" in master
    assert "Tick 338 cron auto-checkout" in env_checks or "Tick 338" in env_checks
    # Tick 339: tip recover --apply also auto-checkouts (closes Tick-338 chicken-egg gap).
    boot_recover = (root / "scripts" / "icml_boot_recover.sh").read_text(encoding="utf-8")
    recover_tip = (root / "scripts" / "icml_recover_tip.py").read_text(encoding="utf-8")
    assert "tip_pr_anti_churn_checkout" in boot_recover
    assert "icml_checkout_tip_pr_branch.sh" in boot_recover
    assert "Tick 339" in boot_recover
    assert "tip_pr_anti_churn_checkout" in recover_tip
    assert "icml_checkout_tip_pr_branch.sh" in recover_tip
    assert "Tick 339" in recover_tip
    assert "Tick 339" in unblock
    assert "boot_recover" in unblock.lower() or "recover" in unblock.lower()
    assert "ICML tip recover --apply anti-churn checkout (Tick 339)" in master
    assert "Tick 339" in env_checks
    # Tick 388: recover_tip --apply also stashes/reinjects prior_live (Tick 387 hole).
    assert "discard_ephemeral_icml_dirt" in recover_tip
    assert "reinject_prior_live_stash" in recover_tip
    assert "Tick 388" in recover_tip
    assert "Tick 388" in unblock
    assert "ICML recover_tip prior_live stash (Tick 388)" in master
    # Tick 389: committed prior_live evidence for cross-VM (budget-ledger parity).
    assert "ICML_PRIOR_LIVE_EVIDENCE_RELPATH" in env_checks
    assert "ensure_prior_live_evidence_initialized" in env_checks
    assert "prior_live_evidence_path" in env_checks
    assert "icml_prior_live_evidence.json" in env_checks
    assert "Tick 389" in env_checks
    assert "Tick 389" in unblock
    assert "ICML committed prior_live evidence (Tick 389)" in master
    assert "ensure_prior_live_evidence_initialized" in cron_entry
    assert "tip_apply_blocking_dirty_paths" in env_checks
    assert "tip_apply_blocking_dirty_paths" in cron_entry
    assert "tip_apply_blocking_dirty_paths" in boot_recover
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert "icml_prior_live_stash.json" in gitignore
    assert "icml_prior_live_evidence.json" not in [
        ln.strip()
        for ln in gitignore.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    evidence = root / "docs" / "icml_prior_live_evidence.json"
    assert evidence.is_file()
    # Tick 390: dirty committed evidence blocks tip --apply (true ledger parity).
    assert "Tick 390" in env_checks
    assert "true budget-ledger parity" in env_checks or "budget-ledger parity" in env_checks
    assert "Tick 390" in recover_tip
    assert "evidence_norm" not in recover_tip
    assert "ICML tip-apply blocks dirty prior_live evidence (Tick 390)" in master
    assert "Tick 390" in unblock
    # Tick 391: tip-apply ignores gitignore-lag durables (boot/call/stash).
    assert "TIP_APPLY_GITIGNORE_LAG_RELPATHS" in env_checks
    assert "is_tip_apply_ignored_dirty" in env_checks
    assert "Tick 391" in env_checks
    assert "Tick 391" in recover_tip
    assert "tip_apply_blocking_dirty_paths" in recover_tip
    assert "ICML tip-apply gitignore-lag durables (Tick 391)" in master
    assert "Tick 391" in unblock
    # Tick 392: chicken-egg boot_recover/cron filter without tip module.
    assert "Tick 392" in boot_recover
    assert "Tick 392" in cron_entry
    assert "mirror TIP_APPLY_GITIGNORE_LAG_RELPATHS" in boot_recover
    assert "mirror TIP_APPLY_GITIGNORE_LAG_RELPATHS" in cron_entry
    assert "ICML chicken-egg tip-apply without tip module (Tick 392)" in master
    assert "Tick 392" in unblock
    # Tick 393: secrets-first generic tip PR body (no frozen Tick 392 changelog).
    assert "Tick 393" in env_checks
    assert "secrets-first and tick-generic" in env_checks
    assert "test_suggested_open_git_pr_body_secrets_first_generic" in env_checks
    assert "ICML secrets-first generic tip PR body (Tick 393)" in master
    assert "Tick 393" in unblock
    # Tick 394: secrets status auto-detects synthetic GPQA without pipeline flag.
    assert "def detect_gpqa_is_synthetic" in env_checks
    assert "Tick 394" in env_checks
    assert "test_detect_gpqa_is_synthetic_and_secrets_auto_probe" in env_checks
    assert "ICML secrets-status auto-detect synthetic GPQA (Tick 394)" in master
    assert "Tick 394" in unblock
    # Tick 395: cron refreshes secrets after preflight (smoke appears mid-run).
    cron_entry395 = (root / "scripts" / "icml_cron_entry.sh").read_text(encoding="utf-8")
    assert "refresh_secrets_after_preflight" in cron_entry395
    assert "Tick 395" in cron_entry395
    assert "Tick 395" in env_checks
    assert "test_cron_refreshes_secrets_after_preflight" in env_checks
    assert "ICML cron secrets refresh after preflight (Tick 395)" in master
    assert "Tick 395" in unblock
    # Tick 396: steered-window H2 (min_generation=3 under delay-all).
    epi = (root / "scripts" / "epistemic_results.py").read_text(encoding="utf-8")
    ready = (root / "docs" / "ICML_READY.md").read_text(encoding="utf-8")
    assert "H2_DEFAULT_MIN_GENERATION" in epi
    assert "Tick 396" in epi
    assert "H2_DEFAULT_MIN_GENERATION = 3" in epi or "min_generation" in epi
    assert "test_compute_h2_steered_window_excludes_fair_bred_gens" in (
        root / "SIA" / "tests" / "test_epistemic_results.py"
    ).read_text(encoding="utf-8")
    assert "ICML steered-window H2 (Tick 396)" in master
    assert "Tick 396" in ready
    assert "Tick 396" in unblock
    # Tick 397: post-adoption H2 tail (last 2 gens, floor gen≥3).
    assert "H2_DEFAULT_TAIL_GENERATIONS" in epi
    assert "resolve_h2_min_generation" in epi
    assert "Tick 397" in epi
    assert "test_compute_h2_post_adoption_tail_excludes_discovery_lag" in (
        root / "SIA" / "tests" / "test_epistemic_results.py"
    ).read_text(encoding="utf-8")
    assert "ICML post-adoption H2 tail (Tick 397)" in master
    assert "Tick 397" in ready
    assert "Tick 397" in unblock
    # Tick 398: case study reports post-adoption H2 tail (aligns with Tick 397 aggregate).
    offline_cs = (root / "scripts" / "offline_bvd_case_study.py").read_text(
        encoding="utf-8"
    )
    assert "post_adoption_preferred_share" in offline_cs
    assert "Tick 398" in offline_cs
    assert "test_extract_case_study_post_adoption_tail_excludes_discovery_lag" in (
        root / "tests" / "test_offline_case_study_steered.py"
    ).read_text(encoding="utf-8")
    assert "ICML case-study post-adoption H2 (Tick 398)" in master
    assert "Tick 398" in ready
    assert "Tick 398" in unblock
    # Tick 340: open_git_pr never-omit-branch (MCP defaults to boot branch).
    assert "def build_icml_open_git_pr_hint" in env_checks
    assert "def write_icml_open_git_pr_hint" in env_checks
    assert "open_git_pr_branch" in env_checks
    assert "open_git_pr_never_omit_branch" in env_checks
    assert "never_omit_branch" in env_checks
    assert "icml_open_git_pr.json" in env_checks
    assert "Tick 340" in env_checks
    assert "Tick 340" in unblock
    assert "never omit" in unblock.lower() or "NEVER omit" in unblock or "open_git_pr" in unblock
    assert "ICML open_git_pr never-omit-branch (Tick 340)" in master
    cron_entry340 = (root / "scripts" / "icml_cron_entry.sh").read_text(encoding="utf-8")
    assert "Tick 340" in cron_entry340
    assert "NEVER omit branch=" in cron_entry340 or "never omit" in cron_entry340.lower()
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "Tick 340" in agents
    assert "open_git_pr" in agents
    assert "omit" in agents.lower()
    assert "docs/icml_open_git_pr.json" in EPHEMERAL_ICML_RELPATHS
    hint = build_icml_open_git_pr_hint(
        {
            "number": 337,
            "url": "https://github.com/kshivam4781/DarwinianSIA/pull/337",
            "head_ref": "cursor/icml-epistemic-results-f49c",
            "mergeable": "MERGEABLE",
            "merge_state_status": "CLEAN",
            "is_draft": True,
        }
    )
    assert hint is not None
    assert hint["open_git_pr_branch"] == "cursor/icml-epistemic-results-f49c"
    assert hint["never_omit_branch"] is True
    # Tick 341: main-boot AGENTS chicken-egg bootstrap (not a tip PR).
    assert "Tick 341" in agents
    assert "icml-main-agents-bootstrap" in agents or "main-agents-bootstrap" in agents
    assert "Tick 341" in unblock
    assert "icml-main-agents-bootstrap" in unblock
    assert "ICML main-boot AGENTS chicken-egg bootstrap (Tick 341)" in master
    # Tick 342: bootstrap PR URL + gh copy-paste in human_next / secrets+tip JSON.
    assert "resolve_icml_agents_bootstrap_pr" in env_checks
    assert "agents_bootstrap_pr_url" in env_checks
    assert "_merge_agents_bootstrap_human_next" in env_checks
    assert "Tick 342" in unblock
    assert "ICML AGENTS bootstrap PR in human_next (Tick 342)" in master
    progress = (root / "docs" / "ICML_PROGRESS.md").read_text(encoding="utf-8")
    assert "Tick 341" in progress
    assert "Tick 342" in progress
    # Tick 343: PRIMARY-first human_next when diamond blocked.
    assert "Tick 343" in env_checks
    assert "PRIMARY-first" in env_checks or "primary-first" in env_checks.lower()
    assert "Tick 343" in unblock
    assert "ICML PRIMARY-first human_next (Tick 343)" in master
    assert "Tick 343" in progress
    # Tick 344: secrets-first suggested open_git_pr title when tip_pr_title_stale.
    assert "suggested_open_git_pr_title" in env_checks
    assert "tip_pr_title_stale" in env_checks
    assert "parse_tick_from_pr_title" in env_checks
    assert "Tick 344" in env_checks
    assert "Tick 344" in unblock
    assert "ICML secrets-first open_git_pr title (Tick 344)" in master
    assert "Tick 344" in progress
    cron_entry344 = (root / "scripts" / "icml_cron_entry.sh").read_text(encoding="utf-8")
    assert "suggested_open_git_pr_title" in cron_entry344 or "tip_pr_title_stale" in cron_entry344
    # Tick 345: gh pr edit --title when open_git_pr MCP leaves GitHub title stale.
    assert "_tip_pr_title_edit_commands" in env_checks
    assert "tip_pr_title_edit_commands" in env_checks
    assert "Tick 345" in env_checks
    assert "Tick 345" in unblock
    assert "ICML tip PR title edit commands (Tick 345)" in master
    assert "Tick 345" in progress
    assert "tip_pr_title_edit_commands" in cron_entry344 or "gh pr edit" in cron_entry344
    # Tick 346: MCP also freezes GitHub body — --body-file secrets-first refresh.
    assert "suggested_open_git_pr_body" in env_checks
    assert "ICML_TIP_PR_BODY_RELPATH" in env_checks
    assert "icml_tip_pr_body.md" in env_checks
    assert "--body-file" in env_checks
    assert "Tick 346" in env_checks
    assert "Tick 346" in unblock
    assert "ICML tip PR body-file refresh (Tick 346)" in master
    assert "Tick 346" in progress
    assert "body-file" in cron_entry344 or "tip_pr_body" in cron_entry344
    assert "docs/icml_tip_pr_body.md" in EPHEMERAL_ICML_RELPATHS
    # Tick 347: tip_pr_body_stale independent of title_stale (body-only paste).
    assert "tip_pr_body_stale" in env_checks
    assert "parse_tick_from_pr_body" in env_checks
    assert "Tick 347" in env_checks
    assert "Tick 347" in unblock
    assert "ICML tip_pr_body_stale independent of title (Tick 347)" in master
    assert "Tick 347" in progress
    # Tick 348: open_git_pr also pass description= from tip_pr_body.md when body_stale.
    assert "open_git_pr_pass_description" in env_checks
    assert "open_git_pr_description_file" in env_checks
    assert "Tick 348" in env_checks
    assert "description=" in env_checks
    assert "Tick 348" in unblock
    assert "ICML open_git_pr pass description (Tick 348)" in master
    assert "Tick 348" in progress
    cron_entry348 = (root / "scripts" / "icml_cron_entry.sh").read_text(encoding="utf-8")
    assert "Tick 348" in cron_entry348
    assert "description=" in cron_entry348
    # Tick 349: open_git_pr_description kept inline in JSON (Tick 348 dropped it).
    assert "open_git_pr_description" in env_checks
    assert "Tick 349" in env_checks
    assert "inline" in env_checks.lower() or "open_git_pr_description" in env_checks
    assert "Tick 349" in unblock
    assert "ICML open_git_pr description inline (Tick 349)" in master
    assert "Tick 349" in progress
    cron_entry349 = cron_entry348
    assert "Tick 349" in cron_entry349
    assert "open_git_pr_description" in cron_entry349
    # Tick 350: atomic open_git_pr_call.json with branch/title/description.
    assert "ICML_OPEN_GIT_PR_CALL_RELPATH" in env_checks
    assert "icml_open_git_pr_call.json" in env_checks
    assert "Tick 350" in env_checks
    assert "Tick 350" in unblock
    assert "ICML open_git_pr call JSON (Tick 350)" in master
    assert "Tick 350" in progress
    cron_entry350 = (root / "scripts" / "icml_cron_entry.sh").read_text(encoding="utf-8")
    assert "Tick 350" in cron_entry350
    assert "icml_open_git_pr_call.json" in cron_entry350
    # Tick 359: call JSON left EPHEMERAL (was restored to stale committed boot).
    assert "docs/icml_open_git_pr_call.json" not in EPHEMERAL_ICML_RELPATHS
    assert prefer_tip_pr_commit_branch(
        {
            "head_ref": "cursor/icml-epistemic-results-f49c",
            "mergeable": "MERGEABLE",
            "merge_state_status": "CLEAN",
        }
    ) == "cursor/icml-epistemic-results-f49c"
    # Tick 351: UNKNOWN/null mergeable anti-churn + cron tip_pr_head_ref fallback.
    assert prefer_tip_pr_commit_branch(
        {
            "head_ref": "cursor/icml-epistemic-results-f49c",
            "mergeable": "UNKNOWN",
        }
    ) == "cursor/icml-epistemic-results-f49c"
    assert prefer_tip_pr_commit_branch(
        {"head_ref": "cursor/icml-epistemic-results-f49c", "mergeable": None}
    ) == "cursor/icml-epistemic-results-f49c"
    assert "Tick 351" in env_checks
    assert "UNKNOWN" in env_checks
    cron_entry351 = (root / "scripts" / "icml_cron_entry.sh").read_text(encoding="utf-8")
    assert "Tick 351" in cron_entry351
    assert "tip_pr_head_ref" in cron_entry351
    checkout_sh = (root / "scripts" / "icml_checkout_tip_pr_branch.sh").read_text(
        encoding="utf-8"
    )
    assert "Tick 351" in checkout_sh
    assert "tip_pr_head_ref" in checkout_sh
    assert "Tick 351" in unblock
    assert "ICML tip PR anti-churn UNKNOWN mergeable (Tick 351)" in master
    assert "Tick 351" in progress
    # Tick 352: cloud_boot_branch in call JSON + cron print + docs lock.
    assert "def detect_cloud_boot_branch" in env_checks
    assert "cloud_boot_branch" in env_checks
    assert "omit_branch_opens_pr_on" in env_checks
    assert "Tick 352" in env_checks
    assert "correct working branch" in env_checks
    assert "Tick 352" in unblock
    assert "ICML cloud_boot_branch open_git_pr warn (Tick 352)" in master
    assert "Tick 352" in progress
    cron_entry352 = (root / "scripts" / "icml_cron_entry.sh").read_text(encoding="utf-8")
    assert "Tick 352" in cron_entry352
    assert "cloud_boot_branch" in cron_entry352
    assert "Tick 352" in (root / "AGENTS.md").read_text(encoding="utf-8")
    # Tick 353–357: cron early boot capture + ignore env==tip + persist boot file
    # + Tick 355: do not clobber boot file when preserved env equals tip
    # + Tick 356: gitignore boot file + exclude from ephemeral discard
    # + Tick 357: reject short boot poison + checkout persists before tip
    # + Tick 358: checkout refreshes open_git_pr call JSON cloud_boot_branch
    # + Tick 359: call JSON gitignored + excluded from ephemeral discard.
    assert "ICML_CLOUD_BOOT_BRANCH" in env_checks
    assert "persist_cloud_boot_branch" in env_checks
    assert "ICML_CLOUD_BOOT_BRANCH_RELPATH" in env_checks
    assert "_is_valid_cloud_boot_branch_name" in env_checks
    assert "refresh_open_git_pr_after_tip_checkout" in env_checks
    assert "Tick 354" in env_checks
    assert "Tick 355" in env_checks
    assert "Tick 356" in env_checks
    assert "Tick 357" in env_checks
    assert "Tick 358" in env_checks
    assert "Tick 359" in env_checks
    assert "icml_cloud_boot_branch.txt" in env_checks
    cron_entry354 = (root / "scripts" / "icml_cron_entry.sh").read_text(encoding="utf-8")
    assert "Tick 353" in cron_entry354
    assert "Tick 354" in cron_entry354
    assert "Tick 355" in cron_entry354
    assert "Tick 359" in cron_entry354
    assert "refreshed_open_git_pr_call_already_on" in cron_entry354
    assert "icml_cloud_boot_branch.txt" in cron_entry354
    assert "already on tip" in cron_entry354
    assert "Tick 355 false capture" in cron_entry354
    # Tick 356: boot file must NOT be ephemeral (discard used to unlink it).
    assert "docs/icml_cloud_boot_branch.txt" not in EPHEMERAL_ICML_RELPATHS
    assert "docs/icml_cloud_boot_branch.txt" in (root / ".gitignore").read_text(
        encoding="utf-8"
    )
    assert "Tick 356" in (root / ".gitignore").read_text(encoding="utf-8")
    # Tick 359: call JSON must NOT be ephemeral / must be gitignored.
    assert "docs/icml_open_git_pr_call.json" not in EPHEMERAL_ICML_RELPATHS
    assert "docs/icml_open_git_pr_call.json" in (root / ".gitignore").read_text(
        encoding="utf-8"
    )
    assert "Tick 359" in (root / ".gitignore").read_text(encoding="utf-8")
    checkout357 = (root / "scripts" / "icml_checkout_tip_pr_branch.sh").read_text(
        encoding="utf-8"
    )
    assert "Tick 357" in checkout357
    assert "persist_cloud_boot_branch" in checkout357
    assert "Tick 358" in checkout357
    assert "refresh_open_git_pr_after_tip_checkout" in checkout357
    assert "Tick 354" in unblock
    assert "Tick 355" in unblock
    assert "Tick 356" in unblock
    assert "Tick 357" in unblock
    assert "Tick 358" in unblock
    assert "Tick 359" in unblock
    assert "ICML cron early boot-branch capture (Tick 353)" in master
    assert "ICML false-boot ignore + persist (Tick 354)" in master
    assert "ICML cron no tip-boot-file clobber (Tick 355)" in master
    assert "ICML boot-file gitignore + discard survive (Tick 356)" in master
    assert "ICML reject short boot poison + checkout persist (Tick 357)" in master
    assert "ICML checkout refreshes open_git_pr call JSON (Tick 358)" in master
    assert "ICML call-JSON gitignore + discard survive (Tick 359)" in master
    assert "Tick 354" in progress
    assert "Tick 355" in progress
    assert "Tick 356" in progress
    assert "Tick 357" in progress
    assert "Tick 358" in progress
    assert "Tick 359" in progress
    assert "Tick 354" in (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "Tick 355" in (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "Tick 356" in (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "Tick 357" in (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "Tick 358" in (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "Tick 359" in (root / "AGENTS.md").read_text(encoding="utf-8")
    # Tick 311: load_env.ps1 must be Nebius-first and mark Anthropic optional.
    load_env = (root / "scripts" / "load_env.ps1").read_text(encoding="utf-8")
    assert "NEBIUS_API_KEY" in load_env
    assert "HF_TOKEN" in load_env
    assert "optional" in load_env.lower()
    # Status lines must lead with Nebius, not Anthropic-first "missing" framing.
    nebius_pos = load_env.find("NEBIUS_API_KEY")
    anth_status_pos = load_env.find("ANTHROPIC_API_KEY: SET")
    assert nebius_pos >= 0 and anth_status_pos > nebius_pos, (
        "load_env.ps1 must report NEBIUS before Anthropic status lines"
    )
    assert "ANTHROPIC_API_KEY: missing" not in load_env
    # Tick 312: Linux/cloud twin load_env.sh — same Nebius-first / Anthropic-optional.
    load_sh = (root / "scripts" / "load_env.sh").read_text(encoding="utf-8")
    assert "NEBIUS_API_KEY" in load_sh
    assert "HF_TOKEN" in load_sh
    assert "optional" in load_sh.lower()
    nebius_sh = load_sh.find("NEBIUS_API_KEY")
    anth_sh = load_sh.find("ANTHROPIC_API_KEY: SET")
    assert nebius_sh >= 0 and anth_sh > nebius_sh, (
        "load_env.sh must report NEBIUS before Anthropic status lines"
    )
    assert "ANTHROPIC_API_KEY: missing" not in load_sh
    assert "source scripts/load_env.sh" in load_sh or ". scripts/load_env.sh" in load_sh


def test_icml_g3g4_nebius_budget_fit_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tick 293–296: Nebius budget-fit; pop4 diversity; max_gen6; Anthropic historical."""
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    for key in (
        "SIA_G3G4_EVAL_SUBSET",
        "SIA_G3G4_POPULATION_SIZE",
        "SIA_G3G4_ELITE_COUNT",
        "SIA_G3G4_MAX_GEN",
        "SIA_G2_ESTIMATE_USD",
        "SIA_G3_PAIR_ESTIMATE_USD",
        "SIA_G4_PAIR_ESTIMATE_USD",
    ):
        monkeypatch.delenv(key, raising=False)

    neb = icml_g3g4_live_shape()
    assert neb == {
        "eval_subset": 5,
        "population_size": 4,
        "elite_count": 2,
        "max_gen": 6,
    }
    # Elite does not change agent-eval count; keep ≥2 for two-parent crossover.
    assert neb["elite_count"] >= 2
    assert neb["elite_count"] <= neb["population_size"]
    # Tick 296: cost-neutral vs Tick 293–295 (4×5×6 == 3×8×5 == 120 agent-evals).
    assert (
        neb["population_size"] * neb["eval_subset"] * neb["max_gen"] == 120
    )
    # Tick 296: pop≥4 so ≥2 non-elite offspring/gen (pop3 collapses PRIMARY/H5).
    assert neb["population_size"] - neb["elite_count"] >= 2
    assert icml_diamond_n_for_stack() == 5
    assert default_g2_estimate_usd() == pytest.approx(2.0)
    assert default_g3_pair_estimate_usd() == pytest.approx(3.0)
    assert default_g4_pair_estimate_usd() == pytest.approx(2.8)
    # Full stack must fit under $20 with margin for reconcile noise.
    stack = (
        default_g2_estimate_usd()
        + default_g3_pair_estimate_usd()
        + 5 * default_g4_pair_estimate_usd()
    )
    assert stack <= 20.0
    assert stack == pytest.approx(19.0)

    # Tick 294: env elite=1 must not survive when pop≥2 (crossover collapse).
    monkeypatch.setenv("SIA_G3G4_ELITE_COUNT", "1")
    floored = icml_g3g4_live_shape()
    assert floored["elite_count"] == 2
    monkeypatch.delenv("SIA_G3G4_ELITE_COUNT", raising=False)

    anth = icml_g3g4_live_shape(profile="default-meta")
    assert anth == {
        "eval_subset": 15,
        "population_size": 4,
        "elite_count": 2,
        "max_gen": 5,
    }
    assert default_g2_estimate_usd(profile="default-meta") == pytest.approx(1.0)
    assert default_g3_pair_estimate_usd(profile="default-meta") == pytest.approx(4.0)
    assert default_g4_pair_estimate_usd(profile="default-meta") == pytest.approx(3.0)


def test_extract_sia_shape_flags_ignores_g2_smoke() -> None:
    g2 = [
        "sia",
        "run",
        "--task",
        "gpqa",
        "--darwinian",
        "--population_size",
        "2",
        "--elite_count",
        "1",
        "--max_gen",
        "2",
        "--eval_subset",
        "5",
    ]
    assert extract_sia_shape_flags(g2) is None


def test_extract_sia_shape_flags_parses_g3g4() -> None:
    cmd = [
        "/usr/bin/python3",
        "-m",
        "sia",
        "run",
        "--task",
        "gpqa",
        "--darwinian",
        "--population_size",
        "4",
        "--elite_count",
        "2",
        "--max_gen",
        "6",
        "--eval_subset",
        "5",
    ]
    assert extract_sia_shape_flags(cmd) == {
        "population_size": 4,
        "elite_count": 2,
        "max_gen": 6,
        "eval_subset": 5,
    }


def test_committed_g3g4_recipes_match_live_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tick 298: prevent Tick-297 stale pop3 recipe drift after shape changes."""
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    for key in (
        "SIA_G3G4_EVAL_SUBSET",
        "SIA_G3G4_POPULATION_SIZE",
        "SIA_G3G4_ELITE_COUNT",
        "SIA_G3G4_MAX_GEN",
    ):
        monkeypatch.delenv(key, raising=False)

    ok, problems = committed_g3g4_recipes_match_live_shape()
    assert ok, problems

    # Negative check: parser spots stale pop3 text.
    stale = (
        "sia run --task gpqa --darwinian --population_size 3 --elite_count 2 "
        "--max_gen 4 --eval_subset 10 --no-web --seed 1\n"
    )
    stale_shapes = iter_shape_flag_dicts_from_text(stale)
    assert stale_shapes == [
        {
            "population_size": 3,
            "elite_count": 2,
            "max_gen": 4,
            "eval_subset": 10,
        }
    ]
    assert stale_shapes[0] != icml_g3g4_live_shape()


def test_committed_offline_bvd_matches_live_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 300–301: offline summary + gate3 + paper ID citations match live."""
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    for key in (
        "SIA_G3G4_EVAL_SUBSET",
        "SIA_G3G4_POPULATION_SIZE",
        "SIA_G3G4_ELITE_COUNT",
        "SIA_G3G4_MAX_GEN",
    ):
        monkeypatch.delenv(key, raising=False)

    # Repo tip should already be locked after Tick 300–301 artifact refresh.
    ok, problems = committed_offline_bvd_matches_live_shape()
    assert ok, problems

    shape = icml_g3g4_live_shape()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "offline_bvd_summary.json").write_text(
        json.dumps(
            {
                "shape": {
                    "eval_subset": 3,
                    "population_size": 4,
                    "elite_count": 2,
                    "max_gen": 6,
                },
                "b_run_ids": [1890, 1891, 1892, 1893, 1894],
                "d_run_ids": [1900, 1901, 1902, 1903, 1904],
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text(
        "<!-- OFFLINE_G3_PILOT_START -->\n"
        f"| B | 11 | {shape['population_size']} | {shape['elite_count']} | "
        f"{shape['max_gen']} | 3 | `1830` |\n"
        "<!-- OFFLINE_G3_PILOT_END -->\n",
        encoding="utf-8",
    )
    bad_ok, bad_problems = committed_offline_bvd_matches_live_shape(repo_root=tmp_path)
    assert bad_ok is False
    assert any("offline_bvd_summary.json shape" in p for p in bad_problems)


def test_committed_offline_bvd_rejects_empty_figures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 302: shape+IDs ok still fails when figures list is empty."""
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    for key in (
        "SIA_G3G4_EVAL_SUBSET",
        "SIA_G3G4_POPULATION_SIZE",
        "SIA_G3G4_ELITE_COUNT",
        "SIA_G3G4_MAX_GEN",
    ):
        monkeypatch.delenv(key, raising=False)

    shape = icml_g3g4_live_shape()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "offline_bvd_summary.json").write_text(
        json.dumps(
            {
                "shape": shape,
                "b_run_ids": [1890, 1891, 1892, 1893, 1894],
                "d_run_ids": [1900, 1901, 1902, 1903, 1904],
                "figures": [],
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text(
        "<!-- OFFLINE_G3_PILOT_START -->\n"
        f"| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Run IDs |\n"
        f"| B | 11 | {shape['population_size']} | {shape['elite_count']} | "
        f"{shape['max_gen']} | {shape['eval_subset']} | `1890–1894` |\n"
        "<!-- OFFLINE_G3_PILOT_END -->\n",
        encoding="utf-8",
    )
    (docs / "case_study_offline.md").write_text(
        "**Run:** `runs/run_1900`\n", encoding="utf-8"
    )
    (docs / "paper_artifacts.md").write_text(
        "Offline pilot `1890–1894` / `1900–1904`\n\n"
        "## Case study (offline)\n\n"
        "Lift (`run_1900`).\n"
        "fig1_learning_curves.png fig2_mechanism.png\n",
        encoding="utf-8",
    )
    (docs / "ICML_READY.md").write_text(
        "### 1. PRIMARY\n- Evidence: offline `1890–1894` vs `1900–1904`\n\n"
        "### 3. VALIDITY — H5\n"
        "- Evidence: offline D `1900–1904` → ρ>0.3 on 5/5\n",
        encoding="utf-8",
    )
    (docs / "HACKATHON_MASTER_PLAN.md").write_text(
        "| Offline B vs D case-study pilot | **DONE** | "
        "Latest Tick 300 `1890–1894` / `1900–1904` |\n",
        encoding="utf-8",
    )
    ok, problems = committed_offline_bvd_matches_live_shape(repo_root=tmp_path)
    assert ok is False
    assert any("figures" in p for p in problems)
    assert any("Tick 302" in p for p in problems)


def test_committed_offline_bvd_rejects_stale_paper_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 301: shape-ok summary still fails if paper pack cites Tick-23 IDs."""
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    for key in (
        "SIA_G3G4_EVAL_SUBSET",
        "SIA_G3G4_POPULATION_SIZE",
        "SIA_G3G4_ELITE_COUNT",
        "SIA_G3G4_MAX_GEN",
    ):
        monkeypatch.delenv(key, raising=False)

    shape = icml_g3g4_live_shape()
    docs = tmp_path / "docs"
    docs.mkdir()
    figs = docs / "figures"
    figs.mkdir()
    f1 = figs / "fig1_learning_curves.png"
    f2 = figs / "fig2_mechanism.png"
    f1.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 1200)
    f2.write_bytes(b"\x89PNG\r\n\x1a\n" + b"1" * 1200)
    (docs / "offline_bvd_summary.json").write_text(
        json.dumps(
            {
                "shape": shape,
                "b_run_ids": [1890, 1891, 1892, 1893, 1894],
                "d_run_ids": [1900, 1901, 1902, 1903, 1904],
                "figures": [
                    "docs/figures/fig1_learning_curves.png",
                    "docs/figures/fig2_mechanism.png",
                ],
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text(
        "<!-- OFFLINE_G3_PILOT_START -->\n"
        f"| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Run IDs |\n"
        f"| B | 11 | {shape['population_size']} | {shape['elite_count']} | "
        f"{shape['max_gen']} | {shape['eval_subset']} | `1890–1894` |\n"
        "<!-- OFFLINE_G3_PILOT_END -->\n",
        encoding="utf-8",
    )
    # Stale Tick-23 citations only (no current 1890/1900 ranges).
    (docs / "case_study_offline.md").write_text(
        "**Run:** `runs/run_1840`\n", encoding="utf-8"
    )
    (docs / "paper_artifacts.md").write_text(
        "Offline pilot 1830–1834 / 1840–1844\n\n"
        "## Case study (offline)\n\n"
        "See docs; lift +0.0436 (`run_1840`, Tick 23).\n",
        encoding="utf-8",
    )
    (docs / "ICML_READY.md").write_text(
        "### 1. PRIMARY\n- Evidence: offline `1830–1834` vs `1840–1844`\n\n"
        "### 3. VALIDITY — H5\n"
        "- Evidence: offline D `1840–1844` → ρ>0.3 on 5/5\n",
        encoding="utf-8",
    )
    (docs / "HACKATHON_MASTER_PLAN.md").write_text(
        "| Offline B vs D case-study pilot | **DONE** | "
        "Latest Tick 23 `1830–1834` / `1840–1844` |\n",
        encoding="utf-8",
    )
    ok, problems = committed_offline_bvd_matches_live_shape(repo_root=tmp_path)
    assert ok is False
    joined = " ".join(problems)
    assert "case_study_offline.md" in joined or "paper_artifacts.md" in joined
    assert "Tick 301" in joined


def test_committed_offline_bvd_rejects_stale_human_unblock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 400: shape-ok pack still fails if ICML_HUMAN_UNBLOCK cites old IDs."""
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    for key in (
        "SIA_G3G4_EVAL_SUBSET",
        "SIA_G3G4_POPULATION_SIZE",
        "SIA_G3G4_ELITE_COUNT",
        "SIA_G3G4_MAX_GEN",
    ):
        monkeypatch.delenv(key, raising=False)

    shape = icml_g3g4_live_shape()
    docs = tmp_path / "docs"
    docs.mkdir()
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    figs = docs / "figures"
    figs.mkdir()
    f1 = figs / "fig1_learning_curves.png"
    f2 = figs / "fig2_mechanism.png"
    f1.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 1200)
    f2.write_bytes(b"\x89PNG\r\n\x1a\n" + b"1" * 1200)
    (docs / "offline_bvd_summary.json").write_text(
        json.dumps(
            {
                "shape": shape,
                "b_run_ids": [1930, 1931, 1932, 1933, 1934],
                "d_run_ids": [1940, 1941, 1942, 1943, 1944],
                "figures": [
                    "docs/figures/fig1_learning_curves.png",
                    "docs/figures/fig2_mechanism.png",
                ],
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text(
        "<!-- OFFLINE_G3_PILOT_START -->\n"
        f"| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Run IDs |\n"
        f"| B | 11 | {shape['population_size']} | {shape['elite_count']} | "
        f"{shape['max_gen']} | {shape['eval_subset']} | `1930–1934` |\n"
        "<!-- OFFLINE_G3_PILOT_END -->\n",
        encoding="utf-8",
    )
    (docs / "case_study_offline.md").write_text(
        "**Run:** `runs/run_1940`\n", encoding="utf-8"
    )
    (docs / "paper_artifacts.md").write_text(
        "Offline pilot `1930–1934` / `1940–1944`\n\n"
        "## Case study (offline)\n\n"
        "Lift (`run_1940`).\n"
        "fig1_learning_curves.png fig2_mechanism.png\n",
        encoding="utf-8",
    )
    (docs / "ICML_READY.md").write_text(
        "### 1. PRIMARY\n- Evidence: offline `1930–1934` vs `1940–1944`\n\n"
        "### 3. VALIDITY — H5\n"
        "- Evidence: offline D `1940–1944` → ρ>0.3 on 5/5\n",
        encoding="utf-8",
    )
    (docs / "HACKATHON_MASTER_PLAN.md").write_text(
        "| Offline B vs D case-study pilot | **DONE** | "
        "Latest Tick 397 `1930–1934` / `1940–1944` |\n",
        encoding="utf-8",
    )
    # Current Tick-399 judge surfaces (so only HUMAN_UNBLOCK fails).
    (docs / "SUBMISSION.md").write_text(
        "Offline B vs D `1930–1934` / `1940–1944`\n`run_1940`\n",
        encoding="utf-8",
    )
    (docs / "PRESENTATION.md").write_text(
        "Offline Bvd IDs `1930–1934` / `1940–1944`.\n",
        encoding="utf-8",
    )
    (scripts / "present_hackathon.py").write_text(
        "import json\n"
        "from pathlib import Path\n"
        "def _offline_evidence_ids_blurb():\n"
        "    return 'from offline_bvd_summary'\n",
        encoding="utf-8",
    )
    # Stale Tick-300 dual-unblock intro (paper/judge pack above is current).
    (docs / "ICML_HUMAN_UNBLOCK.md").write_text(
        "# ICML\n\n"
        "## Dual human unblock (Tick 327–342 — read first)\n\n"
        "Two human actions remain. Code/offline stack is ready (PRIMARY-shaped offline\n"
        "`1890–1904`, G2 dry-run green).\n",
        encoding="utf-8",
    )
    ok, problems = committed_offline_bvd_matches_live_shape(repo_root=tmp_path)
    assert ok is False
    joined = " ".join(problems)
    assert "Tick 400" in joined
    assert "ICML_HUMAN_UNBLOCK.md" in joined


def test_committed_offline_bvd_rejects_stale_readme(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 401: shape-ok pack still fails if README evidence checklist cites old IDs."""
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    for key in (
        "SIA_G3G4_EVAL_SUBSET",
        "SIA_G3G4_POPULATION_SIZE",
        "SIA_G3G4_ELITE_COUNT",
        "SIA_G3G4_MAX_GEN",
    ):
        monkeypatch.delenv(key, raising=False)

    shape = icml_g3g4_live_shape()
    docs = tmp_path / "docs"
    docs.mkdir()
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    figs = docs / "figures"
    figs.mkdir()
    f1 = figs / "fig1_learning_curves.png"
    f2 = figs / "fig2_mechanism.png"
    f1.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 1200)
    f2.write_bytes(b"\x89PNG\r\n\x1a\n" + b"1" * 1200)
    (docs / "offline_bvd_summary.json").write_text(
        json.dumps(
            {
                "shape": shape,
                "b_run_ids": [1930, 1931, 1932, 1933, 1934],
                "d_run_ids": [1940, 1941, 1942, 1943, 1944],
                "figures": [
                    "docs/figures/fig1_learning_curves.png",
                    "docs/figures/fig2_mechanism.png",
                ],
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text(
        "<!-- OFFLINE_G3_PILOT_START -->\n"
        f"| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Run IDs |\n"
        f"| B | 11 | {shape['population_size']} | {shape['elite_count']} | "
        f"{shape['max_gen']} | {shape['eval_subset']} | `1930–1934` |\n"
        "<!-- OFFLINE_G3_PILOT_END -->\n",
        encoding="utf-8",
    )
    (docs / "case_study_offline.md").write_text(
        "**Run:** `runs/run_1940`\n", encoding="utf-8"
    )
    (docs / "paper_artifacts.md").write_text(
        "Offline pilot `1930–1934` / `1940–1944`\n\n"
        "## Case study (offline)\n\n"
        "Lift (`run_1940`).\n"
        "fig1_learning_curves.png fig2_mechanism.png\n",
        encoding="utf-8",
    )
    (docs / "ICML_READY.md").write_text(
        "### 1. PRIMARY\n- Evidence: offline `1930–1934` vs `1940–1944`\n\n"
        "### 3. VALIDITY — H5\n"
        "- Evidence: offline D `1940–1944` → ρ>0.3 on 5/5\n",
        encoding="utf-8",
    )
    (docs / "HACKATHON_MASTER_PLAN.md").write_text(
        "| Offline B vs D case-study pilot | **DONE** | "
        "Latest Tick 397 `1930–1934` / `1940–1944` |\n",
        encoding="utf-8",
    )
    (docs / "SUBMISSION.md").write_text(
        "Offline B vs D `1930–1934` / `1940–1944`\n`run_1940`\n",
        encoding="utf-8",
    )
    (docs / "PRESENTATION.md").write_text(
        "Offline Bvd IDs `1930–1934` / `1940–1944`.\n",
        encoding="utf-8",
    )
    (scripts / "present_hackathon.py").write_text(
        "import json\n"
        "from pathlib import Path\n"
        "def _offline_evidence_ids_blurb():\n"
        "    return 'from offline_bvd_summary'\n",
        encoding="utf-8",
    )
    (docs / "ICML_HUMAN_UNBLOCK.md").write_text(
        "# ICML\n\n"
        "## Dual human unblock (Tick 327–342 — read first)\n\n"
        "Two human actions remain. Code/offline stack is ready (PRIMARY-shaped offline\n"
        "`1930–1934` / `1940–1944`, G2 dry-run green).\n",
        encoding="utf-8",
    )
    # Stale Tick-300 README checklist (all other surfaces current).
    (tmp_path / "README.md").write_text(
        "# SIA-CABS\n\n"
        "## Submission / ICML evidence checklist\n\n"
        "1. Offline / dry-run evidence: `docs/offline_bvd_summary.json` "
        "(IDs `1890–1904`)\n",
        encoding="utf-8",
    )
    ok, problems = committed_offline_bvd_matches_live_shape(repo_root=tmp_path)
    assert ok is False
    joined = " ".join(problems)
    assert "Tick 401" in joined
    assert "README.md" in joined


def test_committed_offline_bvd_rejects_stale_judge_surfaces(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 399: shape-ok pack still fails if SUBMISSION/PRESENTATION cite old IDs."""
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    for key in (
        "SIA_G3G4_EVAL_SUBSET",
        "SIA_G3G4_POPULATION_SIZE",
        "SIA_G3G4_ELITE_COUNT",
        "SIA_G3G4_MAX_GEN",
    ):
        monkeypatch.delenv(key, raising=False)

    shape = icml_g3g4_live_shape()
    docs = tmp_path / "docs"
    docs.mkdir()
    figs = docs / "figures"
    figs.mkdir()
    (figs / "fig1_learning_curves.png").write_bytes(b"x" * 1500)
    (figs / "fig2_mechanism.png").write_bytes(b"y" * 1500)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (docs / "offline_bvd_summary.json").write_text(
        json.dumps(
            {
                "shape": shape,
                "b_run_ids": [1930, 1931, 1932, 1933, 1934],
                "d_run_ids": [1940, 1941, 1942, 1943, 1944],
                "figures": [
                    "docs/figures/fig1_learning_curves.png",
                    "docs/figures/fig2_mechanism.png",
                ],
            }
        ),
        encoding="utf-8",
    )
    (docs / "gate3_report.md").write_text(
        "<!-- OFFLINE_G3_PILOT_START -->\n"
        f"| Cond | Seeds | Pop | Elite | max_gen | eval_subset | Run IDs |\n"
        f"| B | 11 | {shape['population_size']} | {shape['elite_count']} | "
        f"{shape['max_gen']} | {shape['eval_subset']} | `1930–1934` |\n"
        "<!-- OFFLINE_G3_PILOT_END -->\n",
        encoding="utf-8",
    )
    (docs / "case_study_offline.md").write_text(
        "**Run:** `runs/run_1940`\n", encoding="utf-8"
    )
    (docs / "paper_artifacts.md").write_text(
        "Offline pilot `1930–1934` / `1940–1944`\n\n"
        "## Case study (offline)\n\n"
        "Lift (`run_1940`).\n"
        "fig1_learning_curves.png fig2_mechanism.png\n",
        encoding="utf-8",
    )
    (docs / "ICML_READY.md").write_text(
        "### 1. PRIMARY\n- Evidence: offline `1930–1934` vs `1940–1944`\n\n"
        "### 3. VALIDITY — H5\n"
        "- Evidence: offline D `1940–1944` → ρ>0.3 on 5/5\n",
        encoding="utf-8",
    )
    (docs / "HACKATHON_MASTER_PLAN.md").write_text(
        "| Offline B vs D case-study pilot | **DONE** | "
        "Latest Tick 397 `1930–1934` / `1940–1944` |\n",
        encoding="utf-8",
    )
    # Stale Tick-300 judge surfaces (paper pack above is current).
    (docs / "SUBMISSION.md").write_text(
        "Offline B vs D `1890–1894` / `1900–1904`\n`run_1900`\n",
        encoding="utf-8",
    )
    (docs / "PRESENTATION.md").write_text(
        "Offline Bvd IDs `1890–1904`.\n",
        encoding="utf-8",
    )
    (scripts / "present_hackathon.py").write_text(
        'print("EVIDENCE: IDs 1890-1904")\n',
        encoding="utf-8",
    )
    ok, problems = committed_offline_bvd_matches_live_shape(repo_root=tmp_path)
    assert ok is False
    joined = " ".join(problems)
    assert "Tick 399" in joined
    assert "SUBMISSION.md" in joined or "PRESENTATION.md" in joined


def _mk_costed_complete_run(run_dir: Path, *, cost_usd: float = 0.3) -> None:
    agent = run_dir / "gen_1" / "agent_0"
    agent.mkdir(parents=True, exist_ok=True)
    (agent / "results.json").write_text(
        json.dumps({"accuracy": 0.2, "total_cost_usd": cost_usd}),
        encoding="utf-8",
    )


def test_hydrate_direct_gate_bills_unbilled_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 377: unbilled local completes bump spent and persist to ledger."""
    monkeypatch.delenv("SIA_BUDGET_SPENT_USD", raising=False)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 2.0,
                "stages_complete": ["G2"],
                "run_ids": [1300],
                "detail": "G2 only",
            }
        ),
        encoding="utf-8",
    )
    runs = tmp_path / "runs"
    b = runs / "run_1211"
    d = runs / "run_1311"
    _mk_costed_complete_run(b, cost_usd=0.4)
    _mk_costed_complete_run(d, cost_usd=0.4)

    def _resolve(rid: int):
        return {1211: b, 1311: d}.get(rid)

    spent, detail = hydrate_direct_gate_budget_spent(
        [1211, 1212, 1311, 1312],
        pair_estimate_usd=2.8,
        resolve_run_dir=_resolve,
        repo_root=tmp_path,
    )
    assert spent > 2.0
    assert "Tick 377" in detail
    assert "unbilled" in detail
    assert float(os.environ["SIA_BUDGET_SPENT_USD"]) == pytest.approx(spent)
    ledger = json.loads((docs / "icml_budget_spent.json").read_text(encoding="utf-8"))
    assert 1211 in ledger["run_ids"] and 1311 in ledger["run_ids"]
    assert "G2" in ledger["stages_complete"]
    assert "G4" not in ledger["stages_complete"]


def test_hydrate_direct_gate_skips_ledger_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 377: IDs already in ledger are not double-billed."""
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 5.5,
                "stages_complete": ["G2"],
                "run_ids": [1300, 1211, 1311],
                "detail": "already billed partial G4",
            }
        ),
        encoding="utf-8",
    )
    runs = tmp_path / "runs"
    b = runs / "run_1211"
    d = runs / "run_1311"
    _mk_costed_complete_run(b, cost_usd=0.4)
    _mk_costed_complete_run(d, cost_usd=0.4)

    def _resolve(rid: int):
        return {1211: b, 1311: d}.get(rid)

    spent, detail = hydrate_direct_gate_budget_spent(
        [1211, 1311],
        pair_estimate_usd=2.8,
        resolve_run_dir=_resolve,
        repo_root=tmp_path,
    )
    assert spent == pytest.approx(5.5)
    assert "no unbilled local completes" in detail
    ledger = json.loads((docs / "icml_budget_spent.json").read_text(encoding="utf-8"))
    assert ledger["spent_usd"] == pytest.approx(5.5)


def test_hydrate_direct_gate_run_estimate_usd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 378: single-run G2 fallback uses run_estimate_usd (not /2 pair)."""
    monkeypatch.delenv("SIA_BUDGET_SPENT_USD", raising=False)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 1.0,
                "stages_complete": [],
                "run_ids": [],
                "detail": "empty",
            }
        ),
        encoding="utf-8",
    )
    run_dir = tmp_path / "runs" / "run_1300"
    # No total_cost_usd → fallback estimate path
    agent = run_dir / "gen_1" / "agent_0"
    agent.mkdir(parents=True, exist_ok=True)
    (agent / "results.json").write_text(
        json.dumps({"accuracy": 0.1}),
        encoding="utf-8",
    )

    spent, detail = hydrate_direct_gate_budget_spent(
        [1300],
        run_estimate_usd=1.5,
        resolve_run_dir=lambda rid: run_dir if rid == 1300 else None,
        repo_root=tmp_path,
    )
    assert spent == pytest.approx(2.5)  # 1.0 ledger + 1.5 run estimate
    assert "Tick 377/378" in detail
    ledger = json.loads((docs / "icml_budget_spent.json").read_text(encoding="utf-8"))
    assert 1300 in ledger["run_ids"]
    assert "G2" not in ledger["stages_complete"]


def test_persist_direct_gate_stamps_stage_and_bills(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 379: complete planned runs bill + stamp stages_complete."""
    monkeypatch.delenv("SIA_BUDGET_SPENT_USD", raising=False)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 0.5,
                "stages_complete": [],
                "run_ids": [],
                "detail": "empty",
            }
        ),
        encoding="utf-8",
    )
    run_dir = tmp_path / "runs" / "run_1300"
    _mk_costed_complete_run(run_dir, cost_usd=0.2)

    spent, detail = persist_direct_gate_stage_spend(
        "G2",
        [1300],
        run_estimate_usd=1.5,
        resolve_run_dir=lambda rid: run_dir if rid == 1300 else None,
        repo_root=tmp_path,
    )
    assert spent > 0.5
    assert "Tick 379" in detail
    assert "stamped=True" in detail
    ledger = json.loads((docs / "icml_budget_spent.json").read_text(encoding="utf-8"))
    assert 1300 in ledger["run_ids"]
    assert "G2" in ledger["stages_complete"]
    assert float(os.environ["SIA_BUDGET_SPENT_USD"]) == pytest.approx(spent)


def test_persist_direct_gate_incomplete_does_not_stamp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 379: partial completes bill but do not stamp the stage."""
    monkeypatch.delenv("SIA_BUDGET_SPENT_USD", raising=False)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 1.0,
                "stages_complete": ["G2"],
                "run_ids": [1300],
                "detail": "G2 done",
            }
        ),
        encoding="utf-8",
    )
    b = tmp_path / "runs" / "run_1201"
    _mk_costed_complete_run(b, cost_usd=0.3)
    # D run missing → incomplete G3

    spent, detail = persist_direct_gate_stage_spend(
        "G3",
        [1201, 1301],
        pair_estimate_usd=3.0,
        resolve_run_dir=lambda rid: b if rid == 1201 else None,
        repo_root=tmp_path,
    )
    assert spent > 1.0
    assert "stamped=True" not in detail or "stamped=False" in detail
    # Helper returns early with incomplete message when no stamp and after bill
    ledger = json.loads((docs / "icml_budget_spent.json").read_text(encoding="utf-8"))
    assert 1201 in ledger["run_ids"]
    assert "G3" not in ledger["stages_complete"]


def test_persist_direct_gate_no_double_bill(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Tick 379: already-ledgered IDs are not re-billed; stage can still stamp."""
    monkeypatch.setenv("SIA_BUDGET_SPENT_USD", "0")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "icml_budget_spent.json").write_text(
        json.dumps(
            {
                "spent_usd": 2.0,
                "stages_complete": [],
                "run_ids": [1300],
                "detail": "hydrate billed G2 without stage stamp",
            }
        ),
        encoding="utf-8",
    )
    run_dir = tmp_path / "runs" / "run_1300"
    _mk_costed_complete_run(run_dir, cost_usd=0.9)

    spent, detail = persist_direct_gate_stage_spend(
        "G2",
        [1300],
        run_estimate_usd=1.5,
        resolve_run_dir=lambda rid: run_dir if rid == 1300 else None,
        repo_root=tmp_path,
    )
    assert spent == pytest.approx(2.0)
    assert "stamped=True" in detail
    ledger = json.loads((docs / "icml_budget_spent.json").read_text(encoding="utf-8"))
    assert ledger["spent_usd"] == pytest.approx(2.0)
    assert "G2" in ledger["stages_complete"]


def test_direct_gate_ledger_skip_true_when_stage_complete(tmp_path: Path) -> None:
    """Tick 380: skip when ledger stages_complete + run_ids match planned."""
    docs = tmp_path / "docs"
    docs.mkdir()
    ledger = docs / "icml_budget_spent.json"
    ledger.write_text(
        json.dumps(
            {
                "spent_usd": 1.5,
                "stages_complete": ["G2"],
                "run_ids": [1300],
                "detail": "G2 done",
            }
        ),
        encoding="utf-8",
    )
    skip, detail = direct_gate_ledger_skip("G2", [1300], path=ledger)
    assert skip is True
    assert "Tick 380" in detail
    assert "skip paid G2" in detail


def test_direct_gate_ledger_skip_false_on_id_mismatch(tmp_path: Path) -> None:
    """Tick 380: do not skip when planned run_id is absent from ledger."""
    docs = tmp_path / "docs"
    docs.mkdir()
    ledger = docs / "icml_budget_spent.json"
    ledger.write_text(
        json.dumps(
            {
                "spent_usd": 1.5,
                "stages_complete": ["G2"],
                "run_ids": [1300],
                "detail": "G2 done",
            }
        ),
        encoding="utf-8",
    )
    skip, detail = direct_gate_ledger_skip("G2", [1301], path=ledger)
    assert skip is False
    assert "does not mark" in detail

    skip_g3, _ = direct_gate_ledger_skip("G3", [1201, 1301], path=ledger)
    assert skip_g3 is False
