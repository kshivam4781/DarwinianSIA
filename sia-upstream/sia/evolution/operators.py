"""Evolutionary operators: selection, crossover, and mutation."""

from __future__ import annotations

import random
from dataclasses import asdict

from sia.evolution.dna import (
    MEMORY_MODES,
    PLANNING_STYLES,
    PROMPT_STRUCTURES,
    RETRY_POLICIES,
    TOOL_STRATEGIES,
    AgentDNA,
)


def extract_fitness(results: dict | None) -> float:
    """Extract primary fitness from evaluation results.json content."""
    if not results:
        return 0.0
    for key in ("accuracy", "score", "f1", "reward", "success_rate"):
        if key in results and isinstance(results[key], (int, float)):
            return float(results[key])
    return 0.0


def tournament_rank(scored_agents: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Sort agents by fitness descending. Each item is (agent_id, fitness)."""
    return sorted(scored_agents, key=lambda x: x[1], reverse=True)


def select_elites(
    scored_agents: list[tuple[int, float]],
    elite_count: int,
) -> list[int]:
    """Return agent IDs of the top elite_count performers."""
    ranked = tournament_rank(scored_agents)
    return [agent_id for agent_id, _ in ranked[:elite_count]]


def _merge_technique_seeds(parent_a: AgentDNA, parent_b: AgentDNA) -> list[str]:
    return list(dict.fromkeys([*(parent_a.technique_seeds or []), *(parent_b.technique_seeds or [])]))


def crossover(parent_a: AgentDNA, parent_b: AgentDNA, rng: random.Random | None = None) -> AgentDNA:
    """Combine two parent DNAs by randomly inheriting each trait."""
    r = rng or random.Random()
    a = parent_a
    b = parent_b
    return AgentDNA(
        planning_style=a.planning_style if r.random() < 0.5 else b.planning_style,
        reflection=a.reflection if r.random() < 0.5 else b.reflection,
        tool_strategy=a.tool_strategy if r.random() < 0.5 else b.tool_strategy,
        retry_policy=a.retry_policy if r.random() < 0.5 else b.retry_policy,
        memory=a.memory if r.random() < 0.5 else b.memory,
        confidence_threshold=round((a.confidence_threshold + b.confidence_threshold) / 2, 2),
        prompt_structure=a.prompt_structure if r.random() < 0.5 else b.prompt_structure,
        technique_seeds=_merge_technique_seeds(a, b),
    )


def _biased_choice(
    r: random.Random,
    field: str,
    default_choices: tuple[str, ...],
    bias: dict[str, list[str]] | None,
) -> str:
    """Pick trait value; weight toward CABS-suggested values when bias present.

    Bias lists from ``load_mutation_bias`` are ordered highest-fitness-first.
    Earlier candidates get linearly higher weight so Condition D exploits the
    winning side of a contradiction while still exploring the disputed pool.
    """
    suggested = (bias or {}).get(field)
    if suggested:
        pool = [v for v in suggested if v in default_choices]
        if pool:
            n = len(pool)
            # Rank weights: first=n, second=n-1, ... last=1
            weights = [float(n - i) for i in range(n)]
            return r.choices(pool, weights=weights, k=1)[0]
    return r.choice(default_choices)


def mutate(
    dna: AgentDNA,
    mutation_rate: float,
    rng: random.Random | None = None,
    bias: dict[str, list[str]] | None = None,
) -> AgentDNA:
    """Randomly mutate traits with given probability per trait."""
    r = rng or random.Random()
    data = asdict(dna)

    if r.random() < mutation_rate:
        data["planning_style"] = _biased_choice(r, "planning_style", PLANNING_STYLES, bias)
    if r.random() < mutation_rate:
        data["reflection"] = not data["reflection"]
    if r.random() < mutation_rate:
        data["tool_strategy"] = _biased_choice(r, "tool_strategy", TOOL_STRATEGIES, bias)
    if r.random() < mutation_rate:
        data["retry_policy"] = _biased_choice(r, "retry_policy", RETRY_POLICIES, bias)
    if r.random() < mutation_rate:
        data["memory"] = _biased_choice(r, "memory", MEMORY_MODES, bias)
    if r.random() < mutation_rate:
        data["prompt_structure"] = _biased_choice(r, "prompt_structure", PROMPT_STRUCTURES, bias)
    if r.random() < mutation_rate:
        data["confidence_threshold"] = round(
            max(0.0, min(1.0, data["confidence_threshold"] + r.uniform(-0.15, 0.15))),
            2,
        )

    child = AgentDNA.from_dict(data)
    child.technique_seeds = list(dna.technique_seeds or [])
    return child


def inject_technique_seeds(dna: AgentDNA, seeds: list[str]) -> AgentDNA:
    """Attach committee-approved technique names to offspring DNA."""
    if not seeds:
        return dna
    return dna.with_technique_seeds(seeds)


def breed_offspring(
    parent_a: AgentDNA,
    parent_b: AgentDNA,
    mutation_rate: float,
    rng: random.Random | None = None,
    bias: dict[str, list[str]] | None = None,
    technique_seeds: list[str] | None = None,
) -> AgentDNA:
    """Crossover two parents then apply mutation."""
    child = crossover(parent_a, parent_b, rng=rng)
    child = mutate(child, mutation_rate, rng=rng, bias=bias)
    return inject_technique_seeds(child, technique_seeds or [])
