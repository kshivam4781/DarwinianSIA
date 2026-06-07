"""Agent DNA: genotype encoding architectural traits for target agents."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from typing import Any

PLANNING_STYLES = ("stepwise", "direct", "hierarchical")
TOOL_STRATEGIES = ("aggressive", "selective", "minimal")
RETRY_POLICIES = ("none", "generic", "error_specific")
MEMORY_MODES = ("none", "short_summary", "failure_based", "full_history")
PROMPT_STRUCTURES = ("minimal", "detailed", "chain_of_thought")


@dataclass
class AgentDNA:
    """Genotype describing how a target agent should be architected."""

    planning_style: str = "stepwise"
    reflection: bool = True
    tool_strategy: str = "selective"
    retry_policy: str = "generic"
    memory: str = "short_summary"
    confidence_threshold: float = 0.75
    prompt_structure: str = "detailed"
    technique_seeds: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.planning_style = _validate_choice(self.planning_style, PLANNING_STYLES)
        self.tool_strategy = _validate_choice(self.tool_strategy, TOOL_STRATEGIES)
        self.retry_policy = _validate_choice(self.retry_policy, RETRY_POLICIES)
        self.memory = _validate_choice(self.memory, MEMORY_MODES)
        self.prompt_structure = _validate_choice(self.prompt_structure, PROMPT_STRUCTURES)
        self.confidence_threshold = max(0.0, min(1.0, float(self.confidence_threshold)))
        if self.technique_seeds is None:
            self.technique_seeds = []
        self.technique_seeds = [str(s) for s in self.technique_seeds if s]

    @classmethod
    def random(cls, rng: random.Random | None = None) -> AgentDNA:
        """Create a randomly initialized DNA for generation-0 diversity."""
        r = rng or random.Random()
        return cls(
            planning_style=r.choice(PLANNING_STYLES),
            reflection=r.choice([True, False]),
            tool_strategy=r.choice(TOOL_STRATEGIES),
            retry_policy=r.choice(RETRY_POLICIES),
            memory=r.choice(MEMORY_MODES),
            confidence_threshold=round(r.uniform(0.5, 0.95), 2),
            prompt_structure=r.choice(PROMPT_STRUCTURES),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentDNA:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def load(cls, path: str) -> AgentDNA:
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    def trait_items(self) -> list[tuple[str, Any]]:
        return list(asdict(self).items())

    def describe(self) -> str:
        """Human-readable summary for prompts."""
        lines = [
            f"- Planning style: {self.planning_style}",
            f"- Self-reflection: {'enabled' if self.reflection else 'disabled'}",
            f"- Tool strategy: {self.tool_strategy}",
            f"- Retry policy: {self.retry_policy}",
            f"- Memory mode: {self.memory}",
            f"- Confidence threshold: {self.confidence_threshold}",
            f"- Prompt structure: {self.prompt_structure}",
        ]
        if self.technique_seeds:
            lines.append(f"- Technique seeds (committee-approved): {', '.join(self.technique_seeds)}")
        return "\n".join(lines)

    def with_technique_seeds(self, seeds: list[str]) -> AgentDNA:
        """Return copy with merged technique seeds (deduplicated, order preserved)."""
        merged = list(dict.fromkeys([*self.technique_seeds, *[s for s in seeds if s]]))
        data = asdict(self)
        data["technique_seeds"] = merged
        return AgentDNA.from_dict(data)


def _validate_choice(value: str, choices: tuple[str, ...]) -> str:
    if value in choices:
        return value
    return choices[0]
