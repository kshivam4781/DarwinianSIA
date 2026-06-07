"""Tests for Darwinian evolution operators and DNA."""

import json
import random

from sia.evolution.civilization import CivilizationMemory
from sia.evolution.dna import AgentDNA
from sia.evolution.operators import (
    breed_offspring,
    crossover,
    extract_fitness,
    mutate,
    select_elites,
    tournament_rank,
)


class TestAgentDNA:
    def test_random_produces_valid_dna(self):
        rng = random.Random(42)
        dna = AgentDNA.random(rng=rng)
        assert dna.planning_style in ("stepwise", "direct", "hierarchical")
        assert 0.0 <= dna.confidence_threshold <= 1.0

    def test_save_and_load(self, tmp_path):
        dna = AgentDNA(planning_style="direct", reflection=False)
        path = tmp_path / "agent_dna.json"
        dna.save(str(path))
        loaded = AgentDNA.load(str(path))
        assert loaded.planning_style == "direct"
        assert loaded.reflection is False

    def test_invalid_trait_defaults(self):
        dna = AgentDNA(planning_style="invalid")
        assert dna.planning_style == "stepwise"


class TestOperators:
    def test_extract_fitness_accuracy(self):
        assert extract_fitness({"accuracy": 0.85}) == 0.85

    def test_extract_fitness_missing(self):
        assert extract_fitness(None) == 0.0
        assert extract_fitness({}) == 0.0

    def test_tournament_rank(self):
        scored = [(2, 0.3), (0, 0.9), (1, 0.5)]
        ranked = tournament_rank(scored)
        assert ranked[0] == (0, 0.9)
        assert ranked[-1] == (2, 0.3)

    def test_select_elites(self):
        scored = [(0, 0.9), (1, 0.5), (2, 0.3), (3, 0.1)]
        elites = select_elites(scored, elite_count=2)
        assert elites == [0, 1]

    def test_crossover_inherits_from_both_parents(self):
        rng = random.Random(0)
        a = AgentDNA(planning_style="stepwise", tool_strategy="aggressive")
        b = AgentDNA(planning_style="direct", tool_strategy="minimal")
        child = crossover(a, b, rng=rng)
        assert child.planning_style in ("stepwise", "direct")
        assert child.tool_strategy in ("aggressive", "minimal")

    def test_mutate_changes_with_high_rate(self):
        rng = random.Random(1)
        dna = AgentDNA()
        mutated = mutate(dna, mutation_rate=1.0, rng=rng)
        assert isinstance(mutated, AgentDNA)

    def test_breed_offspring(self):
        rng = random.Random(99)
        a = AgentDNA(planning_style="stepwise")
        b = AgentDNA(planning_style="direct")
        child = breed_offspring(a, b, mutation_rate=0.5, rng=rng)
        assert isinstance(child, AgentDNA)


class TestCivilizationMemory:
    def test_record_and_save(self, tmp_path):
        path = tmp_path / "civilization.json"
        mem = CivilizationMemory(str(path), population_size=4, elite_count=2, mutation_rate=0.25)
        agents = [
            {"agent_id": 0, "dna": {"planning_style": "stepwise", "reflection": True, "tool_strategy": "selective",
             "retry_policy": "generic", "memory": "short_summary", "confidence_threshold": 0.75,
             "prompt_structure": "detailed"}, "fitness": 0.9},
            {"agent_id": 1, "dna": {"planning_style": "direct", "reflection": False, "tool_strategy": "minimal",
             "retry_policy": "none", "memory": "none", "confidence_threshold": 0.6,
             "prompt_structure": "minimal"}, "fitness": 0.3},
        ]
        mem.record_generation(1, agents, elite_ids=[0])
        mem.save()
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["mode"] == "darwinian"
        assert len(data["generations"]) == 1
        assert data["generations"][0]["best_fitness"] == 0.9

    def test_summary_markdown(self):
        mem = CivilizationMemory("/tmp/test.json", 8, 2, 0.25)
        summary = mem.summary_markdown()
        assert "Darwinian Civilization Memory" in summary
