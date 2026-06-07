"""Civilization memory: track trait performance across generations."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import asdict
from typing import Any

from sia.evolution.dna import AgentDNA


class CivilizationMemory:
    """Persistent record of evolutionary history and trait statistics."""

    def __init__(
        self,
        path: str,
        population_size: int,
        elite_count: int,
        mutation_rate: float,
    ) -> None:
        self.path = path
        self.population_size = population_size
        self.elite_count = elite_count
        self.mutation_rate = mutation_rate
        self.generations: list[dict[str, Any]] = []
        self.trait_wins: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.trait_failures: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    @classmethod
    def load(cls, path: str) -> CivilizationMemory:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        mem = cls(
            path=path,
            population_size=data.get("population_size", 8),
            elite_count=data.get("elite_count", 2),
            mutation_rate=data.get("mutation_rate", 0.25),
        )
        mem.generations = data.get("generations", [])
        mem.trait_wins = defaultdict(lambda: defaultdict(int), data.get("trait_wins", {}))
        mem.trait_failures = defaultdict(lambda: defaultdict(int), data.get("trait_failures", {}))
        return mem

    def record_generation(
        self,
        gen: int,
        agents: list[dict[str, Any]],
        elite_ids: list[int],
    ) -> None:
        """Record one generation's results and update trait statistics."""
        gen_record = {
            "gen": gen,
            "agents": agents,
            "elite_ids": elite_ids,
            "best_fitness": max((a["fitness"] for a in agents), default=0.0),
            "mean_fitness": sum(a["fitness"] for a in agents) / len(agents) if agents else 0.0,
        }
        self.generations.append(gen_record)

        elite_set = set(elite_ids)
        for agent in agents:
            dna = AgentDNA.from_dict(agent["dna"])
            is_elite = agent["agent_id"] in elite_set
            for trait, value in dna.trait_items():
                if trait == "technique_seeds":
                    continue
                key = str(value)
                if is_elite:
                    self.trait_wins[trait][key] += 1
                elif agent["fitness"] <= 0.0:
                    self.trait_failures[trait][key] += 1

    def trait_insights(self) -> dict[str, list[tuple[str, int]]]:
        """Return top-performing trait values per dimension (win counts)."""
        insights: dict[str, list[tuple[str, int]]] = {}
        for trait, counts in self.trait_wins.items():
            ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
            insights[trait] = ranked[:3]
        return insights

    def trait_insights_enriched(self) -> list[dict[str, Any]]:
        """Section 19.2 export: trait value vs population mean fitness delta."""
        from collections import defaultdict

        value_records: dict[tuple[str, str], list[tuple[float, int]]] = defaultdict(list)
        for gen_record in self.generations:
            gen = int(gen_record["gen"])
            for agent in gen_record.get("agents", []):
                if agent.get("agent_id") not in set(gen_record.get("elite_ids", [])):
                    continue
                dna = AgentDNA.from_dict(agent.get("dna", {}))
                fit = float(agent.get("fitness", 0.0))
                for trait, value in dna.trait_items():
                    if trait == "technique_seeds":
                        continue
                    value_records[(trait, str(value))].append((fit, gen))

        if not self.generations:
            return []

        overall_mean = sum(g["mean_fitness"] for g in self.generations) / len(self.generations)
        enriched: list[dict[str, Any]] = []
        for (trait, value), records in value_records.items():
            avg_fit = sum(r[0] for r in records) / len(records)
            gens = sorted({r[1] for r in records})
            enriched.append(
                {
                    "trait": trait,
                    "value": value,
                    "mean_fitness_delta": round(avg_fit - overall_mean, 4),
                    "generations_observed": gens,
                    "confidence": min(0.95, 0.5 + len(records) * 0.1),
                }
            )
        return sorted(enriched, key=lambda x: -float(x["mean_fitness_delta"]))

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        data = {
            "schema_version": "1.0",
            "mode": "darwinian",
            "population_size": self.population_size,
            "elite_count": self.elite_count,
            "mutation_rate": self.mutation_rate,
            "generations": self.generations,
            "trait_wins": {k: dict(v) for k, v in self.trait_wins.items()},
            "trait_failures": {k: dict(v) for k, v in self.trait_failures.items()},
            "trait_insights": self.trait_insights_enriched(),
            "trait_insights_ranked": self.trait_insights(),
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def summary_markdown(self) -> str:
        """Generate a markdown summary for context.md."""
        lines = [
            "## Darwinian Civilization Memory",
            "",
            f"- Population size: {self.population_size}",
            f"- Elite count: {self.elite_count}",
            f"- Mutation rate: {self.mutation_rate}",
            "",
        ]
        if self.generations:
            best_gen = max(self.generations, key=lambda g: g["best_fitness"])
            lines.append(f"- Best generation: gen_{best_gen['gen']} (fitness={best_gen['best_fitness']:.4f})")
            lines.append(f"- Latest mean fitness: {self.generations[-1]['mean_fitness']:.4f}")
            lines.append("")

        insights = self.trait_insights()
        if insights:
            lines.append("### Top-performing traits")
            for trait, values in insights.items():
                top = ", ".join(f"{v} ({c}x)" for v, c in values)
                lines.append(f"- **{trait}**: {top}")
        return "\n".join(lines)
