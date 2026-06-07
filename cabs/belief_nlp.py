"""Shared topic and polarity detection for belief extraction."""

from __future__ import annotations

import re

TOPIC_PATTERNS: dict[str, list[str]] = {
    "memory": [r"\bmemory\b", r"\bcontext window\b", r"\bretain\b"],
    "reflection": [r"\breflect(?:ion)?\b", r"\bself[- ]critique\b"],
    "planning": [r"\bplan(?:ning)?\b", r"\bplanning[_ ]depth\b", r"\bchain of thought\b", r"\bcot\b"],
    "tool_use": [r"\btool(?:s)?\b", r"\bfunction call\b", r"\bsearch\b", r"\bretrieval\b"],
    "prompting": [r"\bprompt\b", r"\binstruction\b", r"\bsystem message\b"],
    "error_handling": [r"\berror handling\b", r"\brobust(?:ness)?\b", r"\bretry\b", r"\bfallback\b"],
    "model_choice": [r"\bmodel\b", r"\btemperature\b", r"\bsampling\b"],
    "data_quality": [r"\bdata quality\b", r"\bpreprocess\b", r"\bcleaning\b"],
}

POSITIVE_MARKERS = [
    "improve", "helps", "helped", "increase", "increased", "boost", "better", "gain", "effective", "works", "success",
]
NEGATIVE_MARKERS = [
    "hurt", "harm", "degrade", "decreased", "worse", "failed", "failure", "timeout", "regression",
    "ineffective", "does not help", "doesn't help",
]


def detect_topic(text: str) -> str | None:
    lowered = text.lower()
    for topic, patterns in TOPIC_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, lowered):
                return topic
    return None


def detect_polarity(text: str) -> str:
    lowered = text.lower()
    pos = sum(1 for marker in POSITIVE_MARKERS if marker in lowered)
    neg = sum(1 for marker in NEGATIVE_MARKERS if marker in lowered)
    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"
