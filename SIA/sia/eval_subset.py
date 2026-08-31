"""Evaluation subset support: limit benchmark size for dev runs."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from sia.io_utils import write_text
from sia.layout import Names


def _require_pandas() -> Any:
    """Lazy-import pandas (Tick 287).

    Host ``python -m sia`` on Cursor/cloud images often lacks pandas even after
    the per-run venv install. GPQA subset materialize/eval is JSON-only and must
    not hard-fail on ``import pandas`` at module load — otherwise every
    ``--eval_subset`` G2/G3/G4 dry-run and live run aborts before Darwinian.
    LawBench paths still need pandas and import it here.
    """
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via GPQA path
        raise ModuleNotFoundError(
            "pandas is required for LawBench eval_subset; install pandas or use "
            "task gpqa (JSON-only, no pandas)."
        ) from exc
    return pd


def materialize_subset_dataset(
    task_dir: str,
    run_dir: str,
    subset_size: int,
    task_name: str | None = None,
) -> str:
    """Build (or reuse) a dataset directory containing only the first ``subset_size`` samples.

    Returns absolute path to the subset dataset directory (``.../data/public`` layout).
    """
    if subset_size <= 0:
        raise ValueError(f"eval_subset must be positive, got {subset_size}")

    public_src = os.path.join(task_dir, Names.DATA_PUBLIC)
    cache_root = os.path.join(run_dir, "_eval_subset", str(subset_size))
    public_dst = os.path.join(cache_root, Names.DATA_PUBLIC)
    marker = os.path.join(cache_root, ".subset_ok")

    if os.path.isfile(marker):
        return os.path.abspath(public_dst)

    os.makedirs(public_dst, exist_ok=True)

    task = task_name or Path(task_dir).name
    if task == "lawbench":
        _materialize_lawbench_subset(public_src, public_dst, subset_size)
    elif task == "gpqa":
        _materialize_gpqa_subset(public_src, public_dst, subset_size)
    else:
        _materialize_generic_subset(public_src, public_dst, subset_size)

    write_text(marker, f"subset_size={subset_size}\n")
    return os.path.abspath(public_dst)


def _copy_static_public_files(public_src: str, public_dst: str, skip: set[str]) -> None:
    for name in os.listdir(public_src):
        if name in skip:
            continue
        src = os.path.join(public_src, name)
        dst = os.path.join(public_dst, name)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)


def _materialize_lawbench_subset(public_src: str, public_dst: str, n: int) -> None:
    pd = _require_pandas()
    test_src = os.path.join(public_src, "test.csv")
    test_df = pd.read_csv(test_src).head(n)
    _copy_static_public_files(public_src, public_dst, skip={"test.csv"})
    test_df.to_csv(os.path.join(public_dst, "test.csv"), index=False)


def _materialize_gpqa_subset(public_src: str, public_dst: str, n: int) -> None:
    data_src = os.path.join(public_src, "diamond_questions.json")
    questions = json.loads(Path(data_src).read_text(encoding="utf-8"))
    subset = questions[:n]
    _copy_static_public_files(public_src, public_dst, skip={"diamond_questions.json"})
    Path(public_dst, "diamond_questions.json").write_text(json.dumps(subset, indent=2), encoding="utf-8")


def _materialize_generic_subset(public_src: str, public_dst: str, n: int) -> None:
    """Best-effort: truncate test.csv if present, else copy everything."""
    if os.path.isfile(os.path.join(public_src, "test.csv")):
        _materialize_lawbench_subset(public_src, public_dst, n)
    else:
        shutil.copytree(public_src, public_dst, dirs_exist_ok=True)


def resolve_task_root(task_dir: str) -> str:
    """Return the task package root (parent of ``data/``) from a dataset or task path."""
    p = Path(task_dir)
    if (p / "data" / "private").exists() or (p / "data" / "public").exists():
        return str(p)
    if p.name == "public" and p.parent.name == "data":
        return str(p.parent.parent)
    return str(p)


def evaluate_gen_dir_subset(gen_directory: str, task_dir: str, subset_size: int) -> dict | None:
    """Score only the first ``subset_size`` ground-truth items; write ``results.json``."""
    task_root = resolve_task_root(task_dir)
    task = Path(task_root).name
    gen = Path(gen_directory)

    if task == "lawbench":
        results = _evaluate_lawbench_subset(gen, task_root, subset_size)
    elif task == "gpqa":
        results = _evaluate_gpqa_subset(gen, task_root, subset_size)
    else:
        return None

    results_path = gen / Names.RESULTS_JSON
    results_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def _evaluate_lawbench_subset(gen: Path, task_dir: str, n: int) -> dict:
    pd = _require_pandas()
    truth_path = Path(task_dir) / "data" / "private" / "test.csv"
    truth = pd.read_csv(truth_path)
    public_test = Path(task_dir) / Names.DATA_PUBLIC / "test.csv"
    subset_ids = pd.read_csv(public_test).head(n)["id"]
    truth = truth[truth["id"].isin(subset_ids)]

    submission = None
    for fname in ("submission.csv", "predictions.csv"):
        candidate = gen / fname
        if candidate.exists():
            submission = candidate
            break
    if submission is None:
        return {"accuracy": 0.0, "n_correct": 0, "n_total": len(truth), "eval_subset": n, "status": "no_submission"}

    pred = pd.read_csv(submission)
    label_col = "label" if "label" in pred.columns else pred.columns[-1]
    pred = pred.rename(columns={label_col: "pred_label"})
    merged = truth.merge(pred[["id", "pred_label"]], on="id", how="left")
    merged["pred_label"] = merged["pred_label"].fillna("__missing__")
    correct = merged["pred_label"].values == merged["label"].values
    return {
        "accuracy": float(correct.mean()) if len(correct) else 0.0,
        "n_correct": int(correct.sum()),
        "n_total": len(correct),
        "eval_subset": n,
    }


def _evaluate_gpqa_subset(gen: Path, task_dir: str, n: int) -> dict:
    truth_path = Path(task_dir) / "data" / "private" / "diamond_questions.json"
    questions = json.loads(truth_path.read_text(encoding="utf-8"))[:n]
    correct_answers = {
        item["id"]: item["correct_answer_letter"]
        for item in questions
        if item.get("id") is not None and item.get("correct_answer_letter")
    }

    submission_path = None
    results_dir = gen / "results"
    if results_dir.is_dir():
        json_files = sorted(results_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if json_files:
            submission_path = json_files[0]
    if submission_path is None:
        for pattern in ("results*.json", "submission*.json", "output*.json"):
            matches = list(gen.glob(pattern))
            if matches:
                submission_path = max(matches, key=lambda p: p.stat().st_mtime)
                break

    if submission_path is None:
        return {
            "accuracy": 0.0,
            "n_correct": 0,
            "n_total": len(correct_answers),
            "eval_subset": n,
            "status": "no_submission",
        }

    submission = json.loads(submission_path.read_text(encoding="utf-8"))
    submission_answers: dict[int, str] = {}
    if "details" in submission:
        for detail in submission["details"]:
            qid = detail.get("question_id")
            if qid is not None:
                submission_answers[qid] = str(detail.get("model_answer", "")).strip().upper()[:1]
    elif "answers" in submission:
        for qid_str, answer in submission["answers"].items():
            try:
                submission_answers[int(qid_str)] = str(answer).strip().upper()[:1]
            except ValueError:
                continue

    correct = 0
    for qid, letter in correct_answers.items():
        if submission_answers.get(qid) == letter:
            correct += 1
    total = len(correct_answers)
    return {
        "accuracy": correct / total if total else 0.0,
        "n_correct": correct,
        "n_total": total,
        "eval_subset": n,
    }
