"""Tests for eval subset materialization and scoring."""

from pathlib import Path

import pandas as pd

from sia.eval_subset import evaluate_gen_dir_subset, materialize_subset_dataset


def test_lawbench_subset_dataset(tmp_path):
    task_dir = tmp_path / "lawbench"
    public = task_dir / "data" / "public"
    private = task_dir / "data" / "private"
    public.mkdir(parents=True)
    private.mkdir(parents=True)
    pd.DataFrame({"id": [0, 1, 2, 3], "text": ["a", "b", "c", "d"]}).to_csv(public / "test.csv", index=False)
    pd.DataFrame({"id": [0, 1, 2, 3], "label": ["L0", "L1", "L2", "L3"]}).to_csv(private / "test.csv", index=False)
    (public / "classes.json").write_text('["L0","L1"]', encoding="utf-8")

    subset_dir = materialize_subset_dataset(str(task_dir), str(tmp_path / "run"), 2, task_name="lawbench")
    subset_test = pd.read_csv(Path(subset_dir) / "test.csv")
    assert len(subset_test) == 2


def test_lawbench_subset_eval(tmp_path):
    task_dir = tmp_path / "lawbench"
    public = task_dir / "data" / "public"
    private = task_dir / "data" / "private"
    public.mkdir(parents=True)
    private.mkdir(parents=True)
    pd.DataFrame({"id": [0, 1, 2], "text": ["a", "b", "c"]}).to_csv(public / "test.csv", index=False)
    pd.DataFrame({"id": [0, 1, 2], "label": ["L0", "L1", "L2"]}).to_csv(private / "test.csv", index=False)

    gen = tmp_path / "gen"
    gen.mkdir()
    pd.DataFrame({"id": [0, 1], "label": ["L0", "L1"]}).to_csv(gen / "submission.csv", index=False)

    results = evaluate_gen_dir_subset(str(gen), str(task_dir), 2)
    assert results is not None
    assert results["accuracy"] == 1.0
    assert results["n_total"] == 2
    assert (gen / "results.json").is_file()
