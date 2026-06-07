"""Cross-repo JSON merge contract tests (Section 19 / 20.1)."""

import json
from pathlib import Path

from cabs.belief_store import SCHEMA_VERSION
from cabs.dna_mapping import topic_to_dna_field
from cabs.research_question_generator import generate_research_questions


def test_research_question_contract_fields():
    contradictions = [
        {
            "id": "c1",
            "topic": "tool_use",
            "belief_a": "tools help",
            "belief_b": "tools hurt",
            "priority": 0.9,
        }
    ]
    questions = generate_research_questions(contradictions)
    assert len(questions) == 1
    q = questions[0].to_dict()
    assert q["dna_field"] == "tool_strategy"
    assert q["topic"] == "tool_use"
    assert q["status"] == "open"


def test_belief_store_schema_version(tmp_path):
    from cabs.belief_store import BeliefStore

    store = BeliefStore(tmp_path / "belief_store")
    beliefs_doc = json.loads((store.beliefs_path).read_text(encoding="utf-8"))
    assert beliefs_doc["schema_version"] == SCHEMA_VERSION


def test_civilization_enriched_ingest(tmp_path):
    from cabs.belief_extractor import ingest_civilization

    run_dir = tmp_path / "run_test"
    run_dir.mkdir()
    (run_dir / "civilization.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "trait_insights": [
                    {
                        "trait": "memory",
                        "value": "failure_based",
                        "mean_fitness_delta": 0.05,
                        "generations_observed": [1, 2],
                        "confidence": 0.8,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    beliefs = ingest_civilization(run_dir)
    assert len(beliefs) == 1
    assert beliefs[0].metadata.get("mean_fitness_delta") == 0.05


def test_approved_techniques_contract(tmp_path):
    path = tmp_path / "approved_techniques.json"
    payload = {
        "schema_version": "1.0",
        "approved_techniques": [
            {
                "technique": "stratified_memory",
                "implementation_hint": "Gate memory by difficulty",
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == SCHEMA_VERSION
    assert data["approved_techniques"][0]["technique"] == "stratified_memory"


def test_topic_mapping_table():
    assert topic_to_dna_field("planning") == "planning_style"
    assert topic_to_dna_field("error_handling") == "retry_policy"
