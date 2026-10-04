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
    collect_icml_secrets_status,
    collect_icml_tip_status,
    ensure_icml_runtime_deps,
    ensure_sia_on_pythonpath,
    ensure_uv_on_path,
    live_pipeline_next_steps,
    parse_latest_icml_tick,
    probe_per_run_venv_capable,
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
    state = {"hub": False}

    def _imp(name: str) -> bool:
        if name == "huggingface_hub":
            return state["hub"]
        return False

    monkeypatch.setattr("icml_env_checks._module_importable", _imp)

    def _pip(*packages: str):
        assert "huggingface_hub" in packages
        state["hub"] = True
        return True, "pip installed huggingface_hub"

    monkeypatch.setattr("icml_env_checks._pip_install_user", _pip)
    ok, detail = ensure_icml_runtime_deps(allow_install=True)
    assert ok is True
    assert "bootstrapped huggingface_hub" in detail
    assert state["hub"] is True


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
    partial = live_pipeline_next_steps(secrets_ok=True, fetch_diamond_ok=False)
    assert "HF_TOKEN" in partial[0] or "gpqa_diamond.csv" in partial[0]
    assert "fetch_diamond_ok" in partial[0]
    assert "preflight-only" in partial[1]
    full = live_pipeline_next_steps(secrets_ok=True, fetch_diamond_ok=True)
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
    blocked = live_pipeline_next_steps(secrets_ok=False)
    assert "ANTHROPIC_API_KEY" in blocked[0]
    assert "icml_cron_entry.sh" in blocked[1]
    assert "optional" in blocked[2].lower()
    # Legacy caller (no fetch_diamond_ok): secrets_ok still means "go".
    ready = live_pipeline_next_steps(secrets_ok=True)
    assert "Secrets present" in ready[0]
    assert "icml_cron_entry.sh" in ready[1]


def test_live_pipeline_next_steps_tip_before_secrets() -> None:
    steps = live_pipeline_next_steps(
        secrets_ok=False,
        tip_ok=False,
        tip_ref="origin/cursor/icml-epistemic-results-de52",
    )
    assert "icml_cron_entry.sh" in steps[0]
    assert "ANTHROPIC_API_KEY" in steps[1]


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
    """Tick 271–278: recover→live/preflight; lineage tip pick; HF/CSV fetch_diamond gate."""
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
        assert "icml-epistemic" in ref
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
