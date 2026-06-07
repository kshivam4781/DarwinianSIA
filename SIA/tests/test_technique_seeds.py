"""Tests for CABS technique_seeds on AgentDNA (Section 20.5)."""

import json
import random

from sia.evolution.cabs_bridge import load_approved_technique_names
from sia.evolution.dna import AgentDNA
from sia.evolution.evolution_prompts import dna_architecture_section
from sia.evolution.operators import breed_offspring, crossover, inject_technique_seeds


def test_crossover_merges_technique_seeds():
    a = AgentDNA(technique_seeds=["self_consistency"])
    b = AgentDNA(technique_seeds=["stratified_memory"])
    child = crossover(a, b, rng=random.Random(0))
    assert "self_consistency" in child.technique_seeds
    assert "stratified_memory" in child.technique_seeds


def test_breed_offspring_injects_cabs_seeds():
    a = AgentDNA(planning_style="stepwise")
    b = AgentDNA(planning_style="direct")
    child = breed_offspring(
        a,
        b,
        mutation_rate=0.0,
        rng=random.Random(1),
        technique_seeds=["stratified_memory"],
    )
    assert "stratified_memory" in child.technique_seeds


def test_dna_architecture_section_lists_seeds():
    dna = AgentDNA(technique_seeds=["stratified_memory"])
    section = dna_architecture_section(dna)
    assert "stratified_memory" in section
    assert "MUST implement" in section


def test_load_approved_technique_names(tmp_path):
    store = tmp_path / "belief_store"
    store.mkdir()
    (store / "approved_techniques.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "approved_techniques": [
                    {"technique": "stratified_memory", "implementation_hint": "gate by difficulty"}
                ],
            }
        ),
        encoding="utf-8",
    )
    names = load_approved_technique_names(str(tmp_path))
    assert names == ["stratified_memory"]


def test_inject_technique_seeds_dedupes():
    dna = AgentDNA(technique_seeds=["a"])
    updated = inject_technique_seeds(dna, ["a", "b"])
    assert updated.technique_seeds == ["a", "b"]
