"""Tests for the CABS belief pipeline."""

import json
from pathlib import Path

from cabs.belief_engine import BeliefEngine
from cabs.belief_extractor import extract_beliefs_from_generation, load_generation_context
from cabs.contradiction_detector import detect_contradictions
from cabs.prompt_injection import format_cabs_context
from cabs.research_question_generator import generate_research_questions


def _make_generation(tmp_path: Path, generation: int, improvement: str, results: dict | None = None) -> Path:
    run_dir = tmp_path / "runs" / "run_cabs"
    gen_dir = run_dir / f"gen_{generation}"
    gen_dir.mkdir(parents=True)
    (gen_dir / "improvement.md").write_text(improvement, encoding="utf-8")
    (gen_dir / "target_agent.py").write_text(
        "def solve():\n    memory = []\n    plan = []\n    tool = search()\n",
        encoding="utf-8",
    )
    if results is not None:
        (gen_dir / "results.json").write_text(json.dumps(results), encoding="utf-8")
    return run_dir


def test_extract_beliefs_from_improvement(tmp_path):
    run_dir = _make_generation(
        tmp_path,
        2,
        "- Memory helps on hard legal reasoning examples.\n- Added retry logic for robustness.\n",
        {"accuracy": 0.42},
    )
    ctx = load_generation_context(run_dir, 2)
    beliefs = extract_beliefs_from_generation(ctx)
    topics = {b.topic for b in beliefs}
    assert "memory" in topics or "error_handling" in topics
    assert any(b.topic == "benchmark_score" for b in beliefs)


def test_contradiction_detection(tmp_path):
    beliefs = [
        {
            "id": "belief_a",
            "belief": "Planning depth > 5 helps performance",
            "topic": "planning",
            "polarity": "positive",
            "confidence": 0.82,
            "status": "active",
        },
        {
            "id": "belief_b",
            "belief": "Planning depth > 5 caused timeout failures",
            "topic": "planning",
            "polarity": "negative",
            "confidence": 0.81,
            "status": "active",
        },
    ]
    contradictions = detect_contradictions(beliefs, generation=3)
    assert len(contradictions) == 1
    assert contradictions[0].topic == "planning"


def test_research_question_generation():
    contradictions = [
        {
            "id": "contradiction_1",
            "topic": "memory",
            "belief_a": "Memory helps lawbench",
            "belief_b": "Memory hurts easy tasks",
            "priority": 0.9,
        }
    ]
    questions = generate_research_questions(contradictions)
    assert len(questions) == 1
    assert "memory" in questions[0].question.lower()


def test_end_to_end_pipeline_creates_contradiction(tmp_path):
    run_dir = _make_generation(
        tmp_path,
        1,
        "- Memory helps on hard examples because context carries legal references.\n",
        {"accuracy": 0.35},
    )
    _make_generation(
        tmp_path,
        2,
        "- Memory hurts performance on easy examples and adds latency.\n",
        {"accuracy": 0.33},
    )

    engine = BeliefEngine.for_run(run_dir)
    engine.process_generation(run_dir, 1)
    result = engine.process_generation(run_dir, 2)

    store = engine.store
    beliefs = store.load_beliefs()
    contradictions = store.get_open_contradictions()
    questions = store.get_open_research_questions()

    assert len(beliefs) >= 2
    assert len(contradictions) >= 1
    assert len(questions) >= 1
    assert result.knowledge_gain_score > 0

    agenda = result.agenda
    rendered = format_cabs_context(agenda)
    assert "Active Contradictions" in rendered
    assert (run_dir / "gen_2" / "cabs_report.json").exists()
