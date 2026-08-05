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


# Probability of inheriting the preferred parental allele when exactly one
# parent carries it. Soft (<1) to avoid early diversity collapse that can
# hurt gens-to-threshold and H5 while still skewing toward the winner.
_BIAS_CROSSOVER_PREF_P = 0.85

# ε-greedy exploration outside the contradiction-scoped mutation pool.
# Without this, Condition D can trap the population in a suboptimal disputed
# pair (e.g. minimal vs aggressive) and never discover a better unexplored
# allele (selective) needed to cross accuracy thresholds.
_BIAS_MUTATE_EXPLORE_EPS = 0.18


def _crossover_pick(
    r: random.Random,
    field: str,
    value_a: str,
    value_b: str,
    bias: dict[str, list[str]] | None,
) -> str:
    """Pick a parental allele; prefer CABS-ranked values when bias is present.

    Bias-aware crossover (Condition D sample efficiency):
    - If exactly one parent carries the preferred (first) allele, take it
      with probability ``_BIAS_CROSSOVER_PREF_P`` (soft; keeps exploration).
    - If both carry preferred, keep preferred.
    - If neither carries preferred but both alleles are in the disputed pool,
      prefer the higher-ranked side (exponential rank weights).
    - Otherwise fall back to fair 50/50 between parents (Condition B path).
    """
    if value_a == value_b:
        return value_a
    suggested = (bias or {}).get(field) or []
    if suggested:
        preferred = suggested[0]
        if value_a == preferred and value_b != preferred:
            return value_a if r.random() < _BIAS_CROSSOVER_PREF_P else value_b
        if value_b == preferred and value_a != preferred:
            return value_b if r.random() < _BIAS_CROSSOVER_PREF_P else value_a
        if value_a == preferred and value_b == preferred:
            return preferred
        rank = {v: i for i, v in enumerate(suggested)}
        if value_a in rank and value_b in rank:
            # Lower rank index = higher fitness side from load_mutation_bias.
            wa = float(3 ** (len(suggested) - 1 - rank[value_a]))
            wb = float(3 ** (len(suggested) - 1 - rank[value_b]))
            return r.choices([value_a, value_b], weights=[wa, wb], k=1)[0]
        if value_a in rank and value_b not in rank:
            return value_a if r.random() < _BIAS_CROSSOVER_PREF_P else value_b
        if value_b in rank and value_a not in rank:
            return value_b if r.random() < _BIAS_CROSSOVER_PREF_P else value_a
    return value_a if r.random() < 0.5 else value_b


def crossover(
    parent_a: AgentDNA,
    parent_b: AgentDNA,
    rng: random.Random | None = None,
    bias: dict[str, list[str]] | None = None,
) -> AgentDNA:
    """Combine two parent DNAs; optionally bias disputed traits toward CABS winners."""
    r = rng or random.Random()
    a = parent_a
    b = parent_b
    return AgentDNA(
        planning_style=_crossover_pick(r, "planning_style", a.planning_style, b.planning_style, bias),
        reflection=a.reflection if r.random() < 0.5 else b.reflection,
        tool_strategy=_crossover_pick(r, "tool_strategy", a.tool_strategy, b.tool_strategy, bias),
        retry_policy=_crossover_pick(r, "retry_policy", a.retry_policy, b.retry_policy, bias),
        memory=_crossover_pick(r, "memory", a.memory, b.memory, bias),
        confidence_threshold=round((a.confidence_threshold + b.confidence_threshold) / 2, 2),
        prompt_structure=_crossover_pick(
            r, "prompt_structure", a.prompt_structure, b.prompt_structure, bias
        ),
        technique_seeds=_merge_technique_seeds(a, b),
    )


def _biased_choice(
    r: random.Random,
    field: str,
    default_choices: tuple[str, ...],
    bias: dict[str, list[str]] | None,
    current: str | None = None,
    anchor_preferred: bool = True,
) -> str:
    """Pick trait value; weight toward CABS-suggested values when bias present.

    Bias lists from ``load_mutation_bias`` are ordered highest-fitness-first.

    Preferred-allele anchoring (Condition D sample efficiency), when enabled:
    - If ``current`` is already the preferred (first) value, keep it.
    - If ``current`` is outside the disputed pool, **preserve** it (do not
      force preferred). Forcing outsiders onto the local winner trapped
      populations in suboptimal contradiction pairs and blocked better
      unexplored alleles from entering.
    - If ``current`` is a disputed non-preferred value, use exponential
      rank weights so the higher-fitness side dominates exploitation.

    ε-greedy exploration (``_BIAS_MUTATE_EXPLORE_EPS``): when the allele is
    already the local preferred winner, with small probability sample the
    full trait enum so alleles absent from the contradiction pair can still
    appear (escape suboptimal frozen pairs). Exploration is **not** applied
    on every mutate — only when stuck at preferred — so random mid-run
    fitness noise does not destroy H5 (epi_t vs Δfitness_t+1).

    Soft mode (``anchor_preferred=False``): skip preferred protect / outsider
    preserve; ε-explore from the preferred slot still applies when
    ``current == preferred``, otherwise sample the disputed pool with
    exponential rank weights.
    """
    suggested = (bias or {}).get(field)
    if suggested:
        pool = [v for v in suggested if v in default_choices]
        if pool:
            preferred = pool[0]
            if anchor_preferred and current == preferred:
                # Stuck at local winner: ε-escape to full enum, else protect.
                if default_choices and r.random() < _BIAS_MUTATE_EXPLORE_EPS:
                    return r.choice(default_choices)
                return preferred
            if (not anchor_preferred) and current == preferred:
                # Soft mode: still allow stuck-preferred escape.
                if default_choices and r.random() < _BIAS_MUTATE_EXPLORE_EPS:
                    return r.choice(default_choices)
            if anchor_preferred and current is not None and current not in pool:
                # Retain unexplored outsider alleles (selective, etc.).
                return current
            n = len(pool)
            # Exponential rank weights: first=3^(n-1), ..., last=1
            weights = [float(3 ** (n - 1 - i)) for i in range(n)]
            return r.choices(pool, weights=weights, k=1)[0]
    return r.choice(default_choices)


def mutate(
    dna: AgentDNA,
    mutation_rate: float,
    rng: random.Random | None = None,
    bias: dict[str, list[str]] | None = None,
    anchor_preferred: bool = True,
) -> AgentDNA:
    """Randomly mutate traits with given probability per trait."""
    r = rng or random.Random()
    data = asdict(dna)

    if r.random() < mutation_rate:
        data["planning_style"] = _biased_choice(
            r,
            "planning_style",
            PLANNING_STYLES,
            bias,
            current=data["planning_style"],
            anchor_preferred=anchor_preferred,
        )
    if r.random() < mutation_rate:
        data["reflection"] = not data["reflection"]
    if r.random() < mutation_rate:
        data["tool_strategy"] = _biased_choice(
            r,
            "tool_strategy",
            TOOL_STRATEGIES,
            bias,
            current=data["tool_strategy"],
            anchor_preferred=anchor_preferred,
        )
    if r.random() < mutation_rate:
        data["retry_policy"] = _biased_choice(
            r,
            "retry_policy",
            RETRY_POLICIES,
            bias,
            current=data["retry_policy"],
            anchor_preferred=anchor_preferred,
        )
    if r.random() < mutation_rate:
        data["memory"] = _biased_choice(
            r,
            "memory",
            MEMORY_MODES,
            bias,
            current=data["memory"],
            anchor_preferred=anchor_preferred,
        )
    if r.random() < mutation_rate:
        data["prompt_structure"] = _biased_choice(
            r,
            "prompt_structure",
            PROMPT_STRUCTURES,
            bias,
            current=data["prompt_structure"],
            anchor_preferred=anchor_preferred,
        )
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
    apply_crossover_bias: bool = True,
    apply_mutation_bias: bool = True,
    apply_mutation_anchor: bool = True,
) -> AgentDNA:
    """Crossover two parents then apply mutation.

    Crossover bias, mutation bias, and preferred-allele anchoring are each
    optional so early generations can stay fair (Condition-B-like breeding)
    while later gens apply full CABS steering (soft bias-aware XO + anchored
    mutate). When ``apply_mutation_bias`` is False, mutate is uniform even if
    ``bias`` is set.
    """
    xo_bias = bias if apply_crossover_bias else None
    mut_bias = bias if apply_mutation_bias else None
    child = crossover(parent_a, parent_b, rng=rng, bias=xo_bias)
    child = mutate(
        child,
        mutation_rate,
        rng=rng,
        bias=mut_bias,
        anchor_preferred=apply_mutation_anchor,
    )
    return inject_technique_seeds(child, technique_seeds or [])
