"""Cross-repo merge contract tests (Section 19)."""

import json
from dataclasses import asdict

from sia.evolution.civilization import CivilizationMemory
from sia.evolution.dna import AgentDNA


def test_civilization_schema_version(tmp_path):
    civ_path = tmp_path / "civilization.json"
    mem = CivilizationMemory(str(civ_path), population_size=2, elite_count=1, mutation_rate=0.25)
    mem.record_generation(
        1,
        [
            {
                "agent_id": 0,
                "fitness": 0.2,
                "dna": asdict(AgentDNA(memory="failure_based")),
            },
            {
                "agent_id": 1,
                "fitness": 0.1,
                "dna": asdict(AgentDNA(memory="full_history")),
            },
        ],
        elite_ids=[0],
    )
    mem.save()
    data = json.loads(civ_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert isinstance(data["trait_insights"], list)
    traits = {item["trait"] for item in data["trait_insights"]}
    assert "memory" in traits
    assert "trait_insights_ranked" in data


def test_agent_dna_technique_seeds_roundtrip(tmp_path):
    dna = AgentDNA(technique_seeds=["stratified_memory"])
    path = tmp_path / "agent_dna.json"
    dna.save(str(path))
    loaded = AgentDNA.load(str(path))
    assert loaded.technique_seeds == ["stratified_memory"]
