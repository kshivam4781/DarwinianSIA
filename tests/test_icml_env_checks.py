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
    icml_diamond_n_for_stack,
    icml_g3g4_live_shape,
    icml_human_required_secrets_phrase,
    icml_meta_profile_cli_flags,
    icml_meta_requires_anthropic,
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
    """Tick 266: missing huggingface_hub triggers package install helper."""
    monkeypatch.setattr(
        "icml_env_checks.ensure_uv_on_path",
        lambda *, allow_install=True: (True, "uv available at /tmp/uv"),
    )
    monkeypatch.setattr(
        "icml_env_checks.ensure_sia_on_pythonpath",
        lambda: (True, "sia importable via PYTHONPATH=/tmp/SIA"),
    )
    state = {"hub": False, "pydantic_ai": False}

    def _imp(name: str) -> bool:
        if name == "huggingface_hub":
            return state["hub"]
        if name == "pydantic_ai":
            return state["pydantic_ai"]
        return False

    monkeypatch.setattr("icml_env_checks._module_importable", _imp)

    def _pip(*packages: str):
        # Tick 289: also bootstraps pydantic-ai (pip name) for Nebius meta.
        assert "huggingface_hub" in packages or "pydantic-ai" in packages
        if "huggingface_hub" in packages:
            state["hub"] = True
        if "pydantic-ai" in packages or "pydantic_ai" in packages:
            state["pydantic_ai"] = True
        return True, f"pip installed {', '.join(packages)}"

    monkeypatch.setattr("icml_env_checks._pip_install_user", _pip)
    ok, detail = ensure_icml_runtime_deps(allow_install=True)
    assert ok is True
    assert "bootstrapped" in detail
    assert "huggingface_hub" in detail
    assert state["hub"] is True
    assert state["pydantic_ai"] is True


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
    monkeypatch.setattr("icml_env_checks.main_has_icml_tip_files", lambda **_k: False)
    monkeypatch.setattr(
        "icml_env_checks.resolve_diamond_csv_path", lambda **_k: None
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
    assert status["main_has_icml_tip"] is False
    assert "NEBIUS" in status["human_next"][0]
    assert "automation" in status["human_next"][0].lower() or "Add" in status["human_next"][0]
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


def test_tip_pr_mergeability_note_and_merge_next() -> None:
    """Tick 335–337: MERGEABLE/CLEAN + gh copy-paste + anti-churn in human_next."""
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
    steps = live_pipeline_next_steps(
        secrets_ok=False,
        tip_ok=False,
        tip_ref="origin/cursor/icml-epistemic-results-de52",
        main_has_icml_tip=True,
    )
    assert "icml_cron_entry.sh" in steps[0]
    assert "NEBIUS_API_KEY" in steps[1]


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
    submission = (root / "docs" / "SUBMISSION.md").read_text(encoding="utf-8")
    presentation = (root / "docs" / "PRESENTATION.md").read_text(encoding="utf-8")
    assert "ICML Thesis 1" in submission
    assert "bash scripts/icml_cron_entry.sh" in submission
    assert "kimi-nebius-pydantic-meta" in submission
    assert "kimi-nebius-target" in submission
    assert "Do **not** run full LawBench without explicit human approval" in submission
    assert "1890–1894" in submission or "1890-1894" in submission or "`1890–1894`" in submission
    assert "Future: web search, committee debate, Darwinian evolution in our sibling repo." not in presentation
    assert "ICML Thesis 1" in presentation
    assert "bash scripts/icml_cron_entry.sh" in presentation
    assert "Do not** run full LawBench" in presentation or "Do **not** run full LawBench" in presentation
    assert "ICML SUBMISSION + PRESENTATION judge surfaces (Tick 319)" in master
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
    assert "1890" in present
    assert "ICML finish/present judge demos (Tick 320)" in master
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
    assert prefer_tip_pr_commit_branch(
        {
            "head_ref": "cursor/icml-epistemic-results-f49c",
            "mergeable": "MERGEABLE",
            "merge_state_status": "CLEAN",
        }
    ) == "cursor/icml-epistemic-results-f49c"
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
