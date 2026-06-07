"""Parse structured beliefs.json written by the feedback agent."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from cabs.belief_nlp import detect_polarity, detect_topic
from cabs.belief_store import Belief

VALID_TOPICS = {
    "memory",
    "reflection",
    "planning",
    "tool_use",
    "prompting",
    "error_handling",
    "model_choice",
    "data_quality",
    "benchmark_score",
}


def _normalize_topic(raw: str) -> str:
    topic = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if topic in VALID_TOPICS:
        return topic
    detected = detect_topic(topic)
    return detected or topic or "prompting"


def _normalize_polarity(raw: str, belief_text: str) -> str:
    p = (raw or "").strip().lower()
    if p in ("positive", "negative"):
        return p
    return detect_polarity(belief_text)


def parse_beliefs_file(path: Path, generation: int) -> list[Belief]:
    """Load beliefs from feedback agent's beliefs.json."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    items = data.get("beliefs") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []

    beliefs: list[Belief] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("belief", "")).strip()
        if len(text) < 10:
            continue
        topic = _normalize_topic(str(item.get("topic", "")))
        polarity = _normalize_polarity(str(item.get("polarity", "")), text)
        if polarity == "neutral":
            continue
        try:
            confidence = float(item.get("confidence", 0.75))
        except (TypeError, ValueError):
            confidence = 0.75
        beliefs.append(
            Belief(
                belief=text,
                topic=topic,
                polarity=polarity,
                confidence=min(max(confidence, 0.0), 1.0),
                generation=generation,
                evidence=[f"gen_{generation}"],
                metadata={"source": "beliefs.json"},
            )
        )
    return beliefs


def find_beliefs_json(gen_dir: Path) -> Path | None:
    """Return beliefs.json path if present in a generation directory."""
    direct = gen_dir / "beliefs.json"
    if direct.exists():
        return direct
    return None
