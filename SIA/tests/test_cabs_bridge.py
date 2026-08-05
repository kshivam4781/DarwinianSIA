"""Tests for CABS bridge (JSON-only merge with SIA2)."""

import json
import random
from pathlib import Path

from sia.evolution.cabs_bridge import load_cabs_agenda, load_mutation_bias
from sia.evolution.dna import AgentDNA, MEMORY_MODES
from sia.evolution.evolution_prompts import cabs_feedback_addon
from sia.evolution.operators import breed_offspring, crossover, mutate


def test_load_cabs_agenda(tmp_path):
    store = tmp_path / "belief_store"
    store.mkdir()
    (store / "contradictions.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "contradictions": [
                    {
                        "id": "c1",
                        "topic": "memory",
                        "belief_a": "memory helps",
                        "belief_b": "memory hurts",
                        "priority": 0.9,
                        "status": "open",
                        "metadata": {"agents": [0, 1], "cross_agent": True},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (store / "approved_techniques.json").write_text(
        json.dumps(
            {
                "techniques": [
                    {
                        "technique": "stratified_memory",
                        "implementation_hint": "Gate memory by difficulty",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    agenda = load_cabs_agenda(str(tmp_path))
    assert "memory" in agenda
    assert "stratified_memory" in agenda
    assert "MUST implement" in agenda

    addon = cabs_feedback_addon(agenda)
    assert addon.startswith("\n## CABS")


def _write_memory_contradiction_store(tmp_path: Path) -> Path:
    """Shared fixture: open memory contradiction with two concrete DNA values."""
    store = tmp_path / "belief_store"
    store.mkdir()
    (store / "research_questions.json").write_text(
        json.dumps(
            {
                "research_questions": [
                    {
                        "id": "rq1",
                        "question": "When does memory help?",
                        "contradiction_id": "c1",
                        "dna_field": "memory",
                        "status": "open",
                        "priority": 0.8,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (store / "contradictions.json").write_text(
        json.dumps(
            {
                "contradictions": [
                    {
                        "id": "c1",
                        "topic": "memory",
                        "belief_a": "Agent 0: memory=full_history achieved fitness 0.13",
                        "belief_b": "Agent 1: memory=failure_based achieved fitness 0.20",
                        "status": "open",
                        "detected_at_gen": 2,
                        "priority": 0.9,
                        "metadata": {"agents": [0, 1], "cross_agent": True},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (store / "beliefs.json").write_text(
        json.dumps(
            {
                "beliefs": [
                    {
                        "id": "b1",
                        "belief": "Agent 0: memory=full_history achieved fitness 0.13",
                        "topic": "memory",
                        "status": "active",
                        "metadata": {
                            "agent_id": 0,
                            "trait": "memory",
                            "value": "full_history",
                            "fitness": 0.13,
                        },
                    },
                    {
                        "id": "b2",
                        "belief": "Agent 1: memory=failure_based achieved fitness 0.20",
                        "topic": "memory",
                        "status": "active",
                        "metadata": {
                            "agent_id": 1,
                            "trait": "memory",
                            "value": "failure_based",
                            "fitness": 0.20,
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return store


def test_mutation_bias_from_contradiction_not_full_enum(tmp_path):
    """Bias must be contradiction-scoped values, not the entire MEMORY_MODES enum."""
    _write_memory_contradiction_store(tmp_path)

    bias = load_mutation_bias(str(tmp_path))
    assert "memory" in bias
    assert set(bias["memory"]) == {"full_history", "failure_based"}
    assert set(bias["memory"]) != set(MEMORY_MODES)
    assert "short_summary" not in bias["memory"]
    # Higher-fitness side (failure_based @ 0.20) must be listed first
    assert bias["memory"][0] == "failure_based"


def test_mutation_bias_prefers_higher_fitness_side(tmp_path):
    """PRIMARY lever: bias order prefers higher-fitness contradiction side."""
    _write_memory_contradiction_store(tmp_path)
    bias = load_mutation_bias(str(tmp_path))
    assert bias["memory"] == ["failure_based", "full_history"]

    agenda = load_cabs_agenda(str(tmp_path))
    assert "prefer `failure_based`" in agenda


def test_cabs_agenda_includes_scoped_dna_feedback_targets(tmp_path):
    """Scoped feedback must list contradiction-scoped DNA candidates (not full enums)."""
    _write_memory_contradiction_store(tmp_path)

    agenda = load_cabs_agenda(str(tmp_path))
    assert "Scoped DNA Feedback Targets" in agenda
    assert "`memory`" in agenda
    assert "`full_history`" in agenda
    assert "`failure_based`" in agenda
    # Must not dump the rest of MEMORY_MODES into feedback targets
    assert "`short_summary`" not in agenda
    assert "`none`" not in agenda

    addon = cabs_feedback_addon(agenda)
    assert "Scoped DNA Feedback Targets" in addon
    assert "consistent with at least one listed candidate" in addon


def test_mutation_bias_rq_only_without_values_is_empty(tmp_path):
    """Open RQ with dna_field but no concrete values must NOT dump the full enum."""
    store = tmp_path / "belief_store"
    store.mkdir()
    (store / "research_questions.json").write_text(
        json.dumps(
            {
                "research_questions": [
                    {
                        "id": "rq1",
                        "question": "When does memory help?",
                        "dna_field": "memory",
                        "status": "open",
                        "priority": 0.8,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    bias = load_mutation_bias(str(tmp_path))
    assert bias == {}


def test_mutation_bias_reads_agent_dna_files(tmp_path):
    store = tmp_path / "belief_store"
    store.mkdir()
    (store / "research_questions.json").write_text(
        json.dumps(
            {
                "research_questions": [
                    {
                        "id": "rq1",
                        "question": "Tool strategy disagreement",
                        "contradiction_id": "c1",
                        "dna_field": "tool_strategy",
                        "status": "open",
                        "priority": 0.7,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (store / "contradictions.json").write_text(
        json.dumps(
            {
                "contradictions": [
                    {
                        "id": "c1",
                        "topic": "tool_use",
                        "belief_a": "tools help",
                        "belief_b": "tools hurt",
                        "status": "open",
                        "detected_at_gen": 1,
                        "metadata": {"agents": [0, 1], "cross_agent": True},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "gen_1" / "agent_0").mkdir(parents=True)
    (tmp_path / "gen_1" / "agent_1").mkdir(parents=True)
    AgentDNA(tool_strategy="aggressive").save(str(tmp_path / "gen_1" / "agent_0" / "agent_dna.json"))
    AgentDNA(tool_strategy="minimal").save(str(tmp_path / "gen_1" / "agent_1" / "agent_dna.json"))

    bias = load_mutation_bias(str(tmp_path))
    assert set(bias["tool_strategy"]) == {"aggressive", "minimal"}


def test_mutation_bias_adopts_better_allele_from_latest_population(tmp_path):
    """Live population harvest: discovered selective can outrank frozen minimal."""
    store = tmp_path / "belief_store"
    store.mkdir()
    (store / "research_questions.json").write_text(
        json.dumps(
            {
                "research_questions": [
                    {
                        "id": "rq1",
                        "question": "Tool strategy disagreement",
                        "contradiction_id": "c1",
                        "dna_field": "tool_strategy",
                        "status": "open",
                        "priority": 0.7,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (store / "contradictions.json").write_text(
        json.dumps(
            {
                "contradictions": [
                    {
                        "id": "c1",
                        "topic": "tool_use",
                        "belief_a": "Agent 0: tool_strategy=minimal achieved fitness 0.24",
                        "belief_b": "Agent 1: tool_strategy=aggressive achieved fitness 0.18",
                        "status": "open",
                        "priority": 0.85,
                        "detected_at_gen": 1,
                        "metadata": {"agents": [0, 1], "cross_agent": True},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    # Frozen gen-1 contradiction pair.
    (tmp_path / "gen_1" / "agent_0").mkdir(parents=True)
    (tmp_path / "gen_1" / "agent_1").mkdir(parents=True)
    AgentDNA(tool_strategy="minimal").save(str(tmp_path / "gen_1" / "agent_0" / "agent_dna.json"))
    AgentDNA(tool_strategy="aggressive").save(str(tmp_path / "gen_1" / "agent_1" / "agent_dna.json"))
    (tmp_path / "gen_1" / "agent_0" / "results.json").write_text(
        json.dumps({"accuracy": 0.24}), encoding="utf-8"
    )
    (tmp_path / "gen_1" / "agent_1" / "results.json").write_text(
        json.dumps({"accuracy": 0.18}), encoding="utf-8"
    )
    # Later gen discovers selective via ε-greedy; higher fitness → preferred.
    (tmp_path / "gen_3" / "agent_0").mkdir(parents=True)
    (tmp_path / "gen_3" / "agent_1").mkdir(parents=True)
    AgentDNA(tool_strategy="selective").save(str(tmp_path / "gen_3" / "agent_0" / "agent_dna.json"))
    AgentDNA(tool_strategy="minimal").save(str(tmp_path / "gen_3" / "agent_1" / "agent_dna.json"))
    (tmp_path / "gen_3" / "agent_0" / "results.json").write_text(
        json.dumps({"accuracy": 0.31}), encoding="utf-8"
    )
    (tmp_path / "gen_3" / "agent_1" / "results.json").write_text(
        json.dumps({"accuracy": 0.25}), encoding="utf-8"
    )

    bias = load_mutation_bias(str(tmp_path))
    assert "tool_strategy" in bias
    assert bias["tool_strategy"][0] == "selective"
    assert "minimal" in bias["tool_strategy"]
    assert "aggressive" in bias["tool_strategy"]


def test_biased_mutate_skews_memory_vs_uniform():
    """H2 gate: contradiction bias must skew trait distribution vs unbiased mutation."""
    bias = {"memory": ["failure_based", "full_history"]}
    biased_counts = {m: 0 for m in MEMORY_MODES}
    uniform_counts = {m: 0 for m in MEMORY_MODES}
    n = 300
    for i in range(n):
        # Start on the disputed loser so skew is measured inside the pool
        # (outsiders are intentionally preserved under ε-greedy anchoring).
        dna = AgentDNA(memory="full_history")
        biased = mutate(dna, mutation_rate=1.0, rng=random.Random(1000 + i), bias=bias)
        uniform = mutate(dna, mutation_rate=1.0, rng=random.Random(1000 + i), bias=None)
        biased_counts[biased.memory] += 1
        uniform_counts[uniform.memory] += 1

    # Preferred dominates loser; preferred rate far above uniform baseline.
    assert biased_counts["failure_based"] > biased_counts["full_history"]
    assert biased_counts["failure_based"] > int(0.45 * n)
    assert biased_counts["failure_based"] > uniform_counts["failure_based"]

def test_biased_mutate_anchors_preferred_allele():
    """Preferred protect + outsider preserve + loser→preferred skew (ε-greedy)."""
    bias = {"memory": ["failure_based", "full_history"]}

    # Outside disputed pool → preserve outsider most of the time (not force
    # preferred); ε-greedy may explore. Never hard-collapse to preferred.
    outs = []
    for i in range(200):
        dna = AgentDNA(memory="short_summary")
        out = mutate(dna, mutation_rate=1.0, rng=random.Random(i), bias=bias)
        outs.append(out.memory)
    preserved = sum(1 for m in outs if m == "short_summary")
    pref = sum(1 for m in outs if m == "failure_based")
    assert preserved > int(0.50 * len(outs))
    assert pref < int(0.35 * len(outs))

    # Already preferred → stay preferred except ε exploration.
    kept = []
    for i in range(200):
        dna = AgentDNA(memory="failure_based")
        out = mutate(dna, mutation_rate=1.0, rng=random.Random(2000 + i), bias=bias)
        kept.append(out.memory)
    assert sum(1 for m in kept if m == "failure_based") > int(0.70 * len(kept))

    # Loser side → preferred should dominate (exponential weights); ε explores.
    from_loser = []
    for i in range(300):
        dna = AgentDNA(memory="full_history")
        out = mutate(dna, mutation_rate=1.0, rng=random.Random(3000 + i), bias=bias)
        from_loser.append(out.memory)
    pref = sum(1 for m in from_loser if m == "failure_based")
    lose = sum(1 for m in from_loser if m == "full_history")
    assert pref > lose
    assert pref > int(0.45 * len(from_loser))

def test_bias_aware_crossover_prefers_winner_allele():
    """Bias-aware crossover: soft-prefer preferred allele when one parent has it."""
    bias = {"memory": ["failure_based", "full_history"]}
    parent_pref = AgentDNA(memory="failure_based", tool_strategy="selective")
    parent_lose = AgentDNA(memory="full_history", tool_strategy="aggressive")

    # Preferred present in one parent → soft skew (not hard collapse).
    pref_counts = 0
    n = 200
    for i in range(n):
        child = crossover(parent_pref, parent_lose, rng=random.Random(i), bias=bias)
        if child.memory == "failure_based":
            pref_counts += 1
        child_rev = crossover(parent_lose, parent_pref, rng=random.Random(1000 + i), bias=bias)
        if child_rev.memory == "failure_based":
            pref_counts += 1
    # 2n trials; expect ~0.85 preferred → well above 0.5 and below hard-1.0.
    assert pref_counts > int(0.70 * 2 * n)
    assert pref_counts < 2 * n

    # Without bias → fair mix of parental alleles.
    mixed = []
    for i in range(80):
        child = crossover(parent_pref, parent_lose, rng=random.Random(2000 + i), bias=None)
        mixed.append(child.memory)
    assert "failure_based" in mixed and "full_history" in mixed

    # Breed path also forwards bias into crossover (mutation_rate=0 so only XO matters).
    breed_pref = 0
    for i in range(n):
        child = breed_offspring(
            parent_pref,
            parent_lose,
            mutation_rate=0.0,
            rng=random.Random(3000 + i),
            bias=bias,
        )
        if child.memory == "failure_based":
            breed_pref += 1
    assert breed_pref > int(0.70 * n)
    assert breed_pref < n


def test_breed_offspring_can_delay_crossover_bias():
    """Early gens: fair XO + mutation bias; later gens: bias-aware XO too."""
    bias = {"memory": ["failure_based", "full_history"]}
    parent_pref = AgentDNA(memory="failure_based", tool_strategy="selective")
    parent_lose = AgentDNA(memory="full_history", tool_strategy="aggressive")

    # mutation_rate=0 → only crossover decides; delayed XO bias ⇒ ~50/50 mix.
    delayed = []
    for i in range(120):
        child = breed_offspring(
            parent_pref,
            parent_lose,
            mutation_rate=0.0,
            rng=random.Random(4000 + i),
            bias=bias,
            apply_crossover_bias=False,
        )
        delayed.append(child.memory)
    assert "failure_based" in delayed and "full_history" in delayed
    delayed_pref = sum(1 for m in delayed if m == "failure_based")
    assert 0.35 * len(delayed) < delayed_pref < 0.65 * len(delayed)

    # With crossover bias enabled (default), soft preferred skew returns.
    steered = 0
    n = 120
    for i in range(n):
        child = breed_offspring(
            parent_pref,
            parent_lose,
            mutation_rate=0.0,
            rng=random.Random(5000 + i),
            bias=bias,
            apply_crossover_bias=True,
        )
        if child.memory == "failure_based":
            steered += 1
    assert steered > int(0.70 * n)
    assert steered < n


def test_breed_offspring_can_delay_all_mutation_bias():
    """Early gens can disable mutation bias entirely (uniform mutate)."""
    bias = {"memory": ["failure_based", "full_history"]}
    # Outsider parents: with mutation bias on, outsiders are preserved (ε may
    # explore). With mutation bias off (and fair XO), mutate is uniform.
    parent_a = AgentDNA(memory="short_summary", tool_strategy="selective")
    parent_b = AgentDNA(memory="none", tool_strategy="aggressive")

    delayed = []
    for i in range(120):
        child = breed_offspring(
            parent_a,
            parent_b,
            mutation_rate=1.0,
            rng=random.Random(11000 + i),
            bias=bias,
            apply_crossover_bias=False,
            apply_mutation_bias=False,
            apply_mutation_anchor=False,
        )
        delayed.append(child.memory)
    # Uniform mutate over MEMORY_MODES — preferred must not dominate.
    pref = sum(1 for m in delayed if m == "failure_based")
    assert pref < int(0.35 * len(delayed))
    assert len(set(delayed)) >= 3

    steered = []
    for i in range(120):
        child = breed_offspring(
            parent_a,
            parent_b,
            mutation_rate=1.0,
            rng=random.Random(12000 + i),
            bias=bias,
            apply_crossover_bias=True,
            apply_mutation_bias=True,
            apply_mutation_anchor=True,
        )
        steered.append(child.memory)
    # Outsider preserve dominates; ε-greedy still allows some preferred entry.
    preserved = sum(1 for m in steered if m in {"short_summary", "none"})
    pref = sum(1 for m in steered if m == "failure_based")
    assert preserved > int(0.40 * len(steered))
    assert pref < int(0.40 * len(steered))


def test_biased_mutate_can_soften_preferred_anchor():
    """Soft mutation bias: rank-weighted skew without hard preferred collapse."""
    bias = {"memory": ["failure_based", "full_history"]}

    # Outsiders under soft mode: preferred dominates but loser remains possible;
    # ε-greedy may also emit alleles outside the disputed pool.
    outs = []
    for i in range(300):
        dna = AgentDNA(memory="short_summary")
        out = mutate(
            dna,
            mutation_rate=1.0,
            rng=random.Random(i),
            bias=bias,
            anchor_preferred=False,
        )
        outs.append(out.memory)
    pref = sum(1 for m in outs if m == "failure_based")
    lose = sum(1 for m in outs if m == "full_history")
    assert pref > lose
    assert lose > 0
    assert pref + lose > int(0.70 * len(outs))

    # Already-preferred under soft mode can occasionally flip (no hard protect).
    flipped = 0
    for i in range(200):
        dna = AgentDNA(memory="failure_based")
        out = mutate(
            dna,
            mutation_rate=1.0,
            rng=random.Random(7000 + i),
            bias=bias,
            anchor_preferred=False,
        )
        if out.memory != "failure_based":
            flipped += 1
    assert flipped > 0

    # Breed path: early gens can disable mutation anchoring while keeping soft bias.
    parent_a = AgentDNA(memory="short_summary", tool_strategy="selective")
    parent_b = AgentDNA(memory="short_summary", tool_strategy="aggressive")
    soft_outs = []
    for i in range(160):
        child = breed_offspring(
            parent_a,
            parent_b,
            mutation_rate=1.0,
            rng=random.Random(8000 + i),
            bias=bias,
            apply_crossover_bias=False,
            apply_mutation_anchor=False,
        )
        soft_outs.append(child.memory)
    soft_pref = sum(1 for m in soft_outs if m == "failure_based")
    soft_lose = sum(1 for m in soft_outs if m == "full_history")
    # Soft mode samples disputed pool (plus ε full-enum exploration).
    assert soft_pref > soft_lose
    assert soft_lose > 0
    assert soft_pref + soft_lose > int(0.70 * len(soft_outs))

    # Anchoring restored → outsiders mostly preserved (ε may explore).
    hard = []
    for i in range(160):
        child = breed_offspring(
            parent_a,
            parent_b,
            mutation_rate=1.0,
            rng=random.Random(9000 + i),
            bias=bias,
            apply_crossover_bias=True,
            apply_mutation_anchor=True,
        )
        hard.append(child.memory)
    preserved = sum(1 for m in hard if m == "short_summary")
    assert preserved > int(0.50 * len(hard))


def test_biased_mutate_epsilon_explores_outside_disputed_pool():
    """ε-greedy mutation can discover alleles absent from the contradiction pair.

    Regression for suboptimal-pool traps: bias=[minimal, aggressive] must not
    permanently exclude selective (higher latent fitness offline / live escape).
    """
    bias = {"tool_strategy": ["minimal", "aggressive"]}
    seen = set()
    selective = 0
    n = 400
    for i in range(n):
        # Start from collapsed local winner (preferred).
        dna = AgentDNA(tool_strategy="minimal", memory="failure_based")
        out = mutate(dna, mutation_rate=1.0, rng=random.Random(15000 + i), bias=bias)
        seen.add(out.tool_strategy)
        if out.tool_strategy == "selective":
            selective += 1
    assert "selective" in seen
    assert selective > 0
    # Still mostly exploits preferred (protect + pool weights dominate ε).
    # Re-count preferred retention from preferred parents.
    pref_keep = 0
    for i in range(n):
        dna = AgentDNA(tool_strategy="minimal")
        out = mutate(dna, mutation_rate=1.0, rng=random.Random(16000 + i), bias=bias)
        if out.tool_strategy == "minimal":
            pref_keep += 1
    assert pref_keep > int(0.70 * n)


def test_mutation_bias_skips_singleton_candidates(tmp_path):
    """Same-allele contradictions must not create singleton bias pools."""
    store = tmp_path / "belief_store"
    store.mkdir()
    (store / "research_questions.json").write_text(
        json.dumps(
            {
                "research_questions": [
                    {
                        "id": "rq1",
                        "question": "Tool strategy?",
                        "contradiction_id": "c1",
                        "dna_field": "tool_strategy",
                        "status": "open",
                        "priority": 0.8,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (store / "contradictions.json").write_text(
        json.dumps(
            {
                "contradictions": [
                    {
                        "id": "c1",
                        "topic": "tool_use",
                        "belief_a": "Agent 0: tool_strategy=aggressive achieved fitness 0.28",
                        "belief_b": "Agent 1: tool_strategy=aggressive achieved fitness 0.20",
                        "status": "open",
                        "priority": 0.85,
                        "detected_at_gen": 1,
                        "metadata": {"agents": [0, 1], "cross_agent": True},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    bias = load_mutation_bias(str(tmp_path))
    assert "tool_strategy" not in bias

