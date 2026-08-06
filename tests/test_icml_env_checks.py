"""Tests for scripts/icml_env_checks.py (Tick 32 per-run venv probe)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from icml_env_checks import probe_per_run_venv_capable  # noqa: E402


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

    import venv

    def _boom(*_a, **_k):
        raise Exception(
            "The virtual environment was not created successfully because "
            "ensurepip is not available."
        )

    monkeypatch.setattr(venv, "create", _boom)
    ok, detail = probe_per_run_venv_capable()
    assert ok is False
    assert "ensurepip" in detail or "failed" in detail.lower()
