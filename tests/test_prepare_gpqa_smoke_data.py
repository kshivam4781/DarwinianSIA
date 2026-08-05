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
    prepare_task_tree,
)


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
