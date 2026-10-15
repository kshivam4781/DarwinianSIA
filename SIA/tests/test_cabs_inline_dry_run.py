"""G1 gate: Condition D dry-run writes belief_store + scoped bias before gen≥2."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from sia.config import Config
from sia.context_manager import ContextManager
from sia.evolution.cabs_bridge import load_mutation_bias
from sia.evolution.cabs_inline import ensure_cabs_importable
from sia.evolution.dna import MEMORY_MODES
from sia.evolution.population import run_darwinian_loop
from sia.layout import RunLayout
from sia.profiles import load_meta_agent_profile, load_target_agent_profile
from sia.run_setup import RunSetup, TaskFiles


def _make_gpqa_task(tmp_path: Path) -> tuple[str, str]:
    task_dir = tmp_path / "gpqa"
    shared = tmp_path / "_shared"
    ref = task_dir / "reference"
    pub = task_dir / "data" / "public"
    priv = task_dir / "data" / "private"
    for d in (shared, ref, pub, priv):
        d.mkdir(parents=True)

    questions = [
        {
            "id": i,
            "Question": f"Q{i}",
            "options": {"A": "1", "B": "2"},
            "correct_answer_letter": "A",
        }
        for i in range(5)
    ]
    (pub / "diamond_questions.json").write_text(json.dumps(questions), encoding="utf-8")
    (priv / "diamond_questions.json").write_text(json.dumps(questions), encoding="utf-8")
    (pub / "task.md").write_text("# GPQA G1 dry-run fixture", encoding="utf-8")
    (ref / "reference_target_agent.py").write_text("print('ref')", encoding="utf-8")
    (ref / "SAMPLE_TASK_DESCRIPTIONS.md").write_text("samples", encoding="utf-8")
    (shared / "sample_agent_execution.json").write_text("[]", encoding="utf-8")
    return str(task_dir), str(shared)


@pytest.mark.skipif(not ensure_cabs_importable(), reason="cabs package not available")
@patch("sia.context_manager.ContextManager._generate_llm_summary", return_value=None)
@patch("sia.run_setup._create_venv")
def test_condition_d_dry_run_g1_belief_store_and_bias(mock_venv, mock_llm, tmp_path, monkeypatch):
    """Section 21.5 G1: --cabs-inline dry-run refreshes belief_store; breeding sees scoped bias."""
    mock_venv.return_value = None
    monkeypatch.setattr("sia.layout.venv_python_path", lambda _venv: sys.executable)

    task_dir, _shared = _make_gpqa_task(tmp_path)
    run_id = 1401
    run_dir = tmp_path / "runs" / f"run_{run_id}"
    venv_dir = run_dir / "venv"
    venv_dir.mkdir(parents=True)

    context_mgr = ContextManager(
        str(run_dir),
        {
            "task_dir": task_dir,
            "meta_model": "m",
            "task_model": "m",
            "agent_impl": "claude",
            "max_gen": 2,
            "cabs_inline": True,
        },
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
    task_files = TaskFiles("samples", "ref", {}, "# GPQA G1 dry-run fixture")
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
        enable_cabs=True,
        cabs_inline=True,
    )

    layout = RunLayout(str(run_dir))
    store = Path(run_dir) / "belief_store"
    assert (store / "beliefs.json").is_file()
    beliefs = json.loads((store / "beliefs.json").read_text(encoding="utf-8")).get("beliefs", [])
    assert len(beliefs) >= 1

    epi = store / "epistemic_value.jsonl"
    assert epi.is_file()
    rows = [json.loads(line) for line in epi.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert {r["generation"] for r in rows} >= {1, 2}
    assert all("epistemic_value" in r for r in rows)

    # Gen≥2 DNA present (breeding completed after gen-1 inline analyze)
    for agent_id in (0, 1):
        dna_path = Path(layout.gen_agent_dir(2, agent_id)) / "agent_dna.json"
        assert dna_path.is_file()

    bias = load_mutation_bias(str(run_dir))
    assert bias, "G1 requires non-empty contradiction-scoped mutation bias before/after gen≥2"
    if "memory" in bias:
        assert set(bias["memory"]).issubset(set(MEMORY_MODES))
        assert set(bias["memory"]) != set(MEMORY_MODES)

    # Dry-run must use DNA-deterministic fitness (not trivial mock-eval 1.0 for all).
    fits = []
    for gen in (1, 2):
        for agent_id in (0, 1):
            results_path = Path(layout.gen_agent_dir(gen, agent_id)) / "results.json"
            results = json.loads(results_path.read_text(encoding="utf-8"))
            assert results.get("dry_run") is True
            fits.append(float(results["accuracy"]))
    assert all(0.05 <= f <= 0.95 for f in fits)
    assert len(set(fits)) >= 2, "expected varied dry-run fitness for offline H5 Δfitness"
