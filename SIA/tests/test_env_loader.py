"""Tests for .env loading."""

from pathlib import Path

from sia.env_loader import load_project_dotenv, required_keys_present


def test_load_project_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("NEBIUS_API_KEY=test-nebius-key\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)

    loaded = load_project_dotenv()
    assert loaded == env_file.resolve()
    assert __import__("os").getenv("NEBIUS_API_KEY") == "test-nebius-key"


def test_required_keys_present(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "x")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    status = required_keys_present("NEBIUS_API_KEY", "ANTHROPIC_API_KEY")
    assert status == {"NEBIUS_API_KEY": True, "ANTHROPIC_API_KEY": False}
