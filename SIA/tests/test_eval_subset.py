"""Tests for eval subset materialization and scoring."""

from __future__ import annotations

import builtins
import importlib
import json
import sys
from pathlib import Path

import pytest


def test_gpqa_subset_materialize_without_pandas(tmp_path, monkeypatch):
    """Tick 287: GPQA --eval_subset must not require host pandas (module-level import)."""
    real_import = builtins.__import__

    def _block_pandas(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "pandas" or name.startswith("pandas."):
            raise ModuleNotFoundError("No module named 'pandas'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_pandas)
    sys.modules.pop("pandas", None)
    sys.modules.pop("sia.eval_subset", None)

    mod = importlib.import_module("sia.eval_subset")

    task_dir = tmp_path / "gpqa"
    public = task_dir / "data" / "public"
    public.mkdir(parents=True)
    questions = [
        {"id": i, "question": f"Q{i}", "correct_answer_letter": "A"} for i in range(5)
    ]
    (public / "diamond_questions.json").write_text(
        json.dumps(questions), encoding="utf-8"
    )

    subset_dir = mod.materialize_subset_dataset(
        str(task_dir), str(tmp_path / "run"), 3, task_name="gpqa"
    )
    out = json.loads(
        (Path(subset_dir) / "diamond_questions.json").read_text(encoding="utf-8")
    )
    assert len(out) == 3


@pytest.fixture
def pd():
    return pytest.importorskip("pandas")


def test_lawbench_subset_dataset(tmp_path, pd):
    from sia.eval_subset import materialize_subset_dataset

    task_dir = tmp_path / "lawbench"
    public = task_dir / "data" / "public"
    private = task_dir / "data" / "private"
    public.mkdir(parents=True)
    private.mkdir(parents=True)
    pd.DataFrame({"id": [0, 1, 2, 3], "text": ["a", "b", "c", "d"]}).to_csv(
        public / "test.csv", index=False
    )
    pd.DataFrame({"id": [0, 1, 2, 3], "label": ["L0", "L1", "L2", "L3"]}).to_csv(
        private / "test.csv", index=False
    )
    (public / "classes.json").write_text('["L0","L1"]', encoding="utf-8")

    subset_dir = materialize_subset_dataset(
        str(task_dir), str(tmp_path / "run"), 2, task_name="lawbench"
    )
    subset_test = pd.read_csv(Path(subset_dir) / "test.csv")
    assert len(subset_test) == 2


def test_lawbench_subset_eval(tmp_path, pd):
    from sia.eval_subset import evaluate_gen_dir_subset

    task_dir = tmp_path / "lawbench"
    public = task_dir / "data" / "public"
    private = task_dir / "data" / "private"
    public.mkdir(parents=True)
    private.mkdir(parents=True)
    pd.DataFrame({"id": [0, 1, 2], "text": ["a", "b", "c"]}).to_csv(
        public / "test.csv", index=False
    )
    pd.DataFrame({"id": [0, 1, 2], "label": ["L0", "L1", "L2"]}).to_csv(
        private / "test.csv", index=False
    )

    gen = tmp_path / "gen"
    gen.mkdir()
    pd.DataFrame({"id": [0, 1], "label": ["L0", "L1"]}).to_csv(
        gen / "submission.csv", index=False
    )

    results = evaluate_gen_dir_subset(str(gen), str(task_dir), 2)
    assert results is not None
    assert results["accuracy"] == 1.0
    assert results["n_total"] == 2
    assert (gen / "results.json").is_file()
