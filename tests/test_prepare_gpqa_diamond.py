"""Tests for scripts/prepare_gpqa_diamond.py (Tick 25 real GPQA materializer)."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from prepare_gpqa_diamond import (  # noqa: E402
    SOURCE_TAG,
    hf_row_to_sia,
    load_rows_from_csv,
    materialize_from_csv,
    rows_to_sia_questions,
    write_diamond_task_tree,
)
from prepare_gpqa_smoke_data import is_synthetic_smoke  # noqa: E402


def _fake_hf_row(i: int = 0) -> dict[str, str]:
    # Invented content — not from GPQA (license forbids publishing examples).
    return {
        "Question": f"Harness physics item {i}: what is 2+2?",
        "Correct Answer": "four",
        "Incorrect Answer 1": "three",
        "Incorrect Answer 2": "five",
        "Incorrect Answer 3": "zero",
        "High-level domain": "Physics",
        "Subdomain": "Arithmetic",
    }


def test_hf_row_to_sia_shuffles_and_marks_correct() -> None:
    import random

    row = _fake_hf_row(1)
    q = hf_row_to_sia(row, qid=7, rng=random.Random(0))
    assert q["id"] == 7
    assert q["source"] == SOURCE_TAG
    assert q["domain"] == "Physics"
    assert set(q["options"]) == {"A", "B", "C", "D"}
    assert q["options"][q["correct_answer_letter"]] == "four"
    assert "three" in q["options"].values()


def test_rows_to_sia_questions_respects_n() -> None:
    rows = [_fake_hf_row(i) for i in range(10)]
    qs = rows_to_sia_questions(rows, n=3, seed=42)
    assert len(qs) == 3
    assert qs[0]["id"] == 0


def test_write_diamond_not_synthetic(tmp_path: Path) -> None:
    task_dir = tmp_path / "gpqa"
    task_dir.mkdir()
    qs = rows_to_sia_questions([_fake_hf_row(i) for i in range(5)], n=5, seed=1)
    write_diamond_task_tree(task_dir, qs)

    pub = json.loads((task_dir / "data" / "public" / "diamond_questions.json").read_text())
    priv = json.loads((task_dir / "data" / "private" / "diamond_questions.json").read_text())
    assert "correct_answer_letter" not in pub[0]
    assert priv[0]["correct_answer_letter"] in "ABCD"
    assert priv[0]["source"] == SOURCE_TAG
    assert is_synthetic_smoke(task_dir) is False


def test_materialize_from_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "gpqa_diamond.csv"
    rows = [_fake_hf_row(i) for i in range(8)]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    root = tmp_path / "repo"
    task = root / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)

    wrote = materialize_from_csv(
        csv_path,
        ["SIA"],
        n=5,
        seed=2,
        force=True,
        repo_root=root,
    )
    assert any("gpqa" in p for p in wrote)
    assert is_synthetic_smoke(task) is False
    priv = json.loads((task / "data" / "private" / "diamond_questions.json").read_text())
    assert len(priv) == 5


def test_load_rows_from_csv_roundtrip(tmp_path: Path) -> None:
    csv_path = tmp_path / "mini.csv"
    row = _fake_hf_row(0)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        w.writeheader()
        w.writerow(row)
    loaded = load_rows_from_csv(csv_path)
    assert loaded[0]["Correct Answer"] == "four"


def test_download_gpqa_diamond_csv_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from prepare_gpqa_diamond import download_gpqa_diamond_csv

    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="HF_TOKEN"):
        download_gpqa_diamond_csv(token=None)
