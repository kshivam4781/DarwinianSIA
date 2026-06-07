"""Integration test: darwinian dry-run completes without LLM calls."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from sia.config import Config
from sia.context_manager import ContextManager
from sia.evolution.population import run_darwinian_loop
from sia.layout import RunLayout
from sia.profiles import load_meta_agent_profile, load_target_agent_profile
from sia.run_setup import RunSetup, TaskFiles, setup_run_directory


def _make_gpqa_task(tmp_path):
    task_dir = tmp_path / "gpqa"
    shared = tmp_path / "_shared"
    ref = task_dir / "reference"
    pub = task_dir / "data" / "public"
    priv = task_dir / "data" / "private"
    for d in (shared, ref, pub, priv):
        d.mkdir(parents=True)

    questions = [{"id": i, "Question": f"Q{i}", "options": {"A": "1", "B": "2"}, "correct_answer_letter": "A"} for i in range(5)]
    priv_q = [{**q, "correct_answer_letter": "A"} for q in questions]
    (pub / "diamond_questions.json").write_text(json.dumps(questions), encoding="utf-8")
    (priv / "diamond_questions.json").write_text(json.dumps(priv_q), encoding="utf-8")
    (pub / "task.md").write_text("# GPQA test", encoding="utf-8")
    (ref / "reference_target_agent.py").write_text("print('ref')", encoding="utf-8")
    (ref / "SAMPLE_TASK_DESCRIPTIONS.md").write_text("samples", encoding="utf-8")
    (shared / "sample_agent_execution.json").write_text("[]", encoding="utf-8")
    return str(task_dir), str(shared)


@patch("sia.context_manager.ContextManager._generate_llm_summary", return_value=None)
@patch("sia.run_setup._create_venv")
def test_darwinian_dry_run_two_generations(mock_venv, mock_llm, tmp_path, monkeypatch):
    mock_venv.return_value = None
    monkeypatch.setattr("sia.layout.venv_python_path", lambda _venv: sys.executable)
    task_dir, shared_dir = _make_gpqa_task(tmp_path)
    run_id = 9001
    run_dir = tmp_path / "runs" / f"run_{run_id}"
    venv_dir = run_dir / "venv"
    venv_dir.mkdir(parents=True)

    context_mgr = ContextManager(
        str(run_dir),
        {"task_dir": task_dir, "meta_model": "m", "task_model": "m", "agent_impl": "claude", "max_gen": 2},
    )
    context_mgr.initialize()

    run_setup = RunSetup(
        run_directory=str(run_dir),
        meta_agent_working_directory=str(run_dir / "gen_1"),
        venv_dir=str(venv_dir),
        context_mgr=context_mgr,
    )
    (run_dir / "gen_1").mkdir(exist_ok=True)

    from sia.eval_subset import materialize_subset_dataset

    subset_dir = materialize_subset_dataset(task_dir, str(run_dir), 3, task_name="gpqa")

    task_files = TaskFiles("samples", "ref", {}, "# GPQA test")
    meta = load_meta_agent_profile("default-meta")
    target = load_target_agent_profile("default-target")

    run_darwinian_loop(
        max_gen=2,
        run_setup=run_setup,
        task_files=task_files,
        abs_dataset_dir=subset_dir,
        dataset_dir=subset_dir,
        meta_profile=meta,
        sandbox="none",
        env_config=Config(),
        task_model=target.model,
        target_provider=target.provider,
        focus="harness",
        training_sandbox="modal",
        resolved_ref=None,
        reference_dir=None,
        population_size=2,
        elite_count=1,
        mutation_rate=0.5,
        seed=42,
        eval_subset=3,
        resume=False,
        dry_run=True,
        task_name="gpqa",
        task_root=str(task_dir),
    )

    layout = RunLayout(str(run_dir))
    civ_path = layout.civilization_json
    assert Path(civ_path).is_file()
    civ = json.loads(Path(civ_path).read_text(encoding="utf-8"))
    assert len(civ["generations"]) == 2

    for gen in (1, 2):
        for agent_id in (0, 1):
            agent_dir = Path(layout.gen_agent_dir(gen, agent_id))
            assert (agent_dir / "agent_dna.json").is_file()
            assert (agent_dir / "target_agent.py").is_file()
            assert (agent_dir / "results.json").is_file()
