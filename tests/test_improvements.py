"""Tests for Tier 1-2 CABS improvements."""

import json
from pathlib import Path

from cabs.belief_engine import BeliefEngine
from cabs.belief_store import BeliefStore, SCHEMA_VERSION
from cabs.feedback_beliefs import parse_beliefs_file
from cabs.prompt_injection import inject_into_prompt
from cabs.resolution_tracker import check_resolutions
from cabs.sia_prompt_addons import feedback_beliefs_instruction, meta_task_hints


def test_schema_version_in_store(tmp_path):
    store = BeliefStore(tmp_path / "belief_store")
    data = json.loads(store.beliefs_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == SCHEMA_VERSION


def test_feedback_beliefs_json_parsing(tmp_path):
    path = tmp_path / "beliefs.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "beliefs": [
                    {
                        "belief": "Memory helps on hard chess positions because context carries prior moves",
                        "topic": "memory",
                        "polarity": "positive",
                        "confidence": 0.85,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    beliefs = parse_beliefs_file(path, generation=2)
    assert len(beliefs) == 1
    assert beliefs[0].topic == "memory"
    assert beliefs[0].metadata["source"] == "beliefs.json"


def test_belief_deduplication_by_topic_polarity(tmp_path):
    store = BeliefStore(tmp_path / "belief_store")
    from cabs.belief_store import Belief

    b1 = Belief(belief="Memory helps", topic="memory", polarity="positive", confidence=0.8, generation=1)
    b2 = Belief(belief="Memory still helps on hard tasks", topic="memory", polarity="positive", confidence=0.7, generation=2)
    store.append_beliefs([b1])
    store.append_beliefs([b2])
    assert len(store.load_beliefs()) == 1


def test_cabs_prepend_injection(tmp_path):
    store = BeliefStore(tmp_path / "belief_store")
    store.append_contradictions(
        [
            {
                "id": "c1",
                "topic": "memory",
                "belief_a_id": "a",
                "belief_b_id": "b",
                "belief_a": "Memory helps",
                "belief_b": "Memory hurts",
                "detected_at_gen": 2,
                "priority": 0.9,
                "status": "open",
            }
        ]
    )
    out = inject_into_prompt("MAIN PROMPT BODY", str(store.root))
    assert out.index("CABS") < out.index("MAIN PROMPT BODY")


def test_resolution_tracking_marks_question_resolved():
    questions = [
        {
            "id": "rq1",
            "question": "When does memory help versus hurt?",
            "topic": "memory",
            "status": "open",
            "contradiction_id": "c1",
        }
    ]
    contradictions = [
        {
            "id": "c1",
            "topic": "memory",
            "belief_a": "Memory helps",
            "belief_b": "Memory hurts",
            "status": "open",
        }
    ]
    improvement = (
        "We will investigate memory on easy versus hard slices and compare enable/disable settings."
    )
    updated_q, updated_c = check_resolutions(improvement, questions, contradictions, generation=3)
    assert updated_q[0]["status"] == "resolved"
    assert updated_c[0]["status"] == "resolved"


def test_feedback_beliefs_instruction_contains_path():
    text = feedback_beliefs_instruction(1, "/tmp/gen_2")
    assert "beliefs.json" in text
    assert "gen_2" in text or "/tmp/gen_2" in text


def test_meta_chess_hint_for_longcot():
    assert "solution =" in meta_task_hints("longcot-chess")


def test_ingest_feedback_beliefs_triggers_contradiction(tmp_path):
    run_dir = tmp_path / "run"
    gen1 = run_dir / "gen_1"
    gen2 = run_dir / "gen_2"
    gen1.mkdir(parents=True)
    gen2.mkdir(parents=True)
    (gen1 / "improvement.md").write_text("- Memory helps on hard examples.\n", encoding="utf-8")
    (gen2 / "beliefs.json").write_text(
        json.dumps(
            {
                "beliefs": [
                    {
                        "belief": "Memory hurts on easy chess puzzles due to added noise in context",
                        "topic": "memory",
                        "polarity": "negative",
                        "confidence": 0.8,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    engine = BeliefEngine.for_run(run_dir)
    engine.process_generation(run_dir, 1)
    result = engine.ingest_feedback_beliefs(run_dir, gen2, source_generation=1)

    assert result.beliefs_added >= 1
    contradictions = engine.store.get_open_contradictions()
    assert len(contradictions) >= 1


def test_resolution_in_pipeline(tmp_path):
    run_dir = tmp_path / "run"
    for gen, text in (
        (1, "- Memory helps on hard examples.\n"),
        (2, "- Memory hurts on easy examples.\n"),
        (3, "- Investigate memory on easy vs hard slices; disable memory on easy tasks.\n"),
    ):
        gdir = run_dir / f"gen_{gen}"
        gdir.mkdir(parents=True)
        (gdir / "improvement.md").write_text(text, encoding="utf-8")

    engine = BeliefEngine.for_run(run_dir)
    engine.process_generation(run_dir, 1)
    engine.process_generation(run_dir, 2)
    r3 = engine.process_generation(run_dir, 3)

    resolved = [q for q in engine.store.load_research_questions() if q.get("status") == "resolved"]
    assert len(resolved) >= 1
    assert r3.resolutions >= 1
