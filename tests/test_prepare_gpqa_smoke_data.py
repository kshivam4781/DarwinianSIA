"""Tests for scripts/prepare_gpqa_smoke_data.py (G2 layout unblock)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from prepare_gpqa_smoke_data import (  # noqa: E402
    check_task_tree,
    is_synthetic_smoke,
    live_g2_next_steps_message,
    prepare_task_tree,
)


def test_live_g2_next_steps_anthropic_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tick 307: smoke Next lines must not hard-demand Anthropic under Nebius meta."""
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    text = live_g2_next_steps_message()
    assert "NEBIUS_API_KEY" in text
    assert "optional" in text.lower()
    assert "ANTHROPIC_API_KEY + NEBIUS_API_KEY" not in text
    assert "icml_cron_entry.sh" in text


def test_prepare_task_tree_writes_public_private_schema(tmp_path: Path) -> None:
    task_dir = tmp_path / "gpqa"
    task_dir.mkdir()
    prepare_task_tree(task_dir, n=5)

    missing = check_task_tree(task_dir)
    assert missing == []

    pub = json.loads((task_dir / "data" / "public" / "diamond_questions.json").read_text())
    priv = json.loads((task_dir / "data" / "private" / "diamond_questions.json").read_text())
    assert len(pub) == 5
    assert len(priv) == 5
    assert "correct_answer_letter" not in pub[0]
    assert priv[0]["correct_answer_letter"] == "A"
    assert (task_dir / "data" / "public" / "task.md").is_file()


def test_check_task_tree_reports_missing(tmp_path: Path) -> None:
    task_dir = tmp_path / "gpqa"
    task_dir.mkdir()
    missing = check_task_tree(task_dir)
    assert len(missing) == 3


def test_is_synthetic_smoke_true_for_prepared_fixture(tmp_path: Path) -> None:
    task_dir = tmp_path / "gpqa"
    task_dir.mkdir()
    prepare_task_tree(task_dir, n=3)
    assert is_synthetic_smoke(task_dir) is True
