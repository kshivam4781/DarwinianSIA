"""Map CABS belief topics to Darwinian DNA field names (Section 19 / 20.1)."""

from __future__ import annotations

# CABS topic → Darwinian AgentDNA field
TOPIC_TO_DNA_FIELD: dict[str, str] = {
    "memory": "memory",
    "reflection": "reflection",
    "planning": "planning_style",
    "tool_use": "tool_strategy",
    "prompting": "prompt_structure",
    "error_handling": "retry_policy",
    "model_choice": "confidence_threshold",
    "data_quality": "planning_style",
    "benchmark_score": "planning_style",
}

# Darwinian DNA field → CABS topic (for civilization ingest)
DNA_FIELD_TO_TOPIC: dict[str, str] = {
    "memory": "memory",
    "reflection": "reflection",
    "planning_style": "planning",
    "tool_strategy": "tool_use",
    "prompt_structure": "prompting",
    "retry_policy": "error_handling",
    "confidence_threshold": "model_choice",
}

DEFAULT_DNA_FIELD = "planning_style"
DEFAULT_TOPIC = "planning"


def topic_to_dna_field(topic: str) -> str:
    return TOPIC_TO_DNA_FIELD.get(topic, DEFAULT_DNA_FIELD)


def dna_field_to_topic(dna_field: str) -> str:
    return DNA_FIELD_TO_TOPIC.get(dna_field, DEFAULT_TOPIC)


# DNA trait keys present in agent_dna.json
DNA_TRAIT_FIELDS: tuple[str, ...] = (
    "planning_style",
    "reflection",
    "tool_strategy",
    "retry_policy",
    "memory",
    "confidence_threshold",
    "prompt_structure",
)
