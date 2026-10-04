"""Tick 308: verify_keys Anthropic-optional under Nebius meta."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


@pytest.fixture()
def verify_keys_mod():
    if "verify_keys" in sys.modules:
        return importlib.reload(sys.modules["verify_keys"])
    return importlib.import_module("verify_keys")


def test_anthropic_optional_under_default_nebius_meta(
    monkeypatch: pytest.MonkeyPatch, verify_keys_mod
) -> None:
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    assert verify_keys_mod.anthropic_is_required() is False
    checks = verify_keys_mod.required_key_checks()
    by_name = {name: required for name, _fn, required in checks}
    assert by_name["Anthropic"] is False
    assert by_name["Nebius"] is True
    assert by_name["Tavily"] is False


def test_anthropic_required_under_default_meta(
    monkeypatch: pytest.MonkeyPatch, verify_keys_mod
) -> None:
    monkeypatch.setenv("ICML_META_AGENT_PROFILE", "default-meta")
    assert verify_keys_mod.anthropic_is_required() is True
    checks = verify_keys_mod.required_key_checks()
    by_name = {name: required for name, _fn, required in checks}
    assert by_name["Anthropic"] is True


def test_main_exit_ok_without_anthropic_when_nebius_mocked(
    monkeypatch: pytest.MonkeyPatch, verify_keys_mod, capsys
) -> None:
    """Absent Anthropic must not fail exit under Nebius meta (Tick 308)."""
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setenv("NEBIUS_API_KEY", "test-nebius-key")

    monkeypatch.setattr(
        verify_keys_mod, "check_nebius", lambda: (True, "Nebius key works (mocked)")
    )
    monkeypatch.setattr(
        verify_keys_mod,
        "check_anthropic",
        lambda: (False, "ANTHROPIC_API_KEY is not set"),
    )
    monkeypatch.setattr(
        verify_keys_mod,
        "check_tavily",
        lambda: (False, "TAVILY_API_KEY is not set (optional for Layer 2)"),
    )

    rc = verify_keys_mod.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "[SKIP] Anthropic:" in out
    assert "[PASS] Nebius:" in out
    assert "optional" in out.lower()
