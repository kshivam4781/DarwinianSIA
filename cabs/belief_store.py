"""Persistent belief graph storage for SIA-CABS."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class Belief:
    belief: str
    topic: str
    polarity: str
    confidence: float
    generation: int
    id: str = field(default_factory=lambda: _new_id("belief"))
    evidence: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)
    status: str = "active"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Contradiction:
    topic: str
    belief_a_id: str
    belief_b_id: str
    belief_a: str
    belief_b: str
    detected_at_gen: int
    id: str = field(default_factory=lambda: _new_id("contradiction"))
    confidence_delta: float = 0.0
    priority: float = 0.5
    status: str = "open"
    created_at: str = field(default_factory=_utc_now)
    resolved_at: str | None = None
    resolved_at_gen: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchQuestion:
    question: str
    contradiction_id: str
    id: str = field(default_factory=lambda: _new_id("rq"))
    priority: float = 0.5
    status: str = "open"
    topic: str = ""
    dna_field: str = ""
    hidden_variables: list[str] = field(default_factory=list)
    experiments: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=_utc_now)
    resolved_at: str | None = None
    resolution: str | None = None
    resolved_at_gen: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BeliefStore:
    """Read/write beliefs, contradictions, and research questions."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.beliefs_path = self.root / "beliefs.json"
        self.contradictions_path = self.root / "contradictions.json"
        self.research_questions_path = self.root / "research_questions.json"
        self._ensure_files()

    def _ensure_files(self) -> None:
        defaults = {
            self.beliefs_path: {"schema_version": SCHEMA_VERSION, "beliefs": [], "updated_at": _utc_now()},
            self.contradictions_path: {"schema_version": SCHEMA_VERSION, "contradictions": [], "updated_at": _utc_now()},
            self.research_questions_path: {
                "schema_version": SCHEMA_VERSION,
                "research_questions": [],
                "updated_at": _utc_now(),
            },
        }
        for path, payload in defaults.items():
            if not path.exists():
                self._write_json(path, payload)

    def _read_json(self, path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        payload["updated_at"] = _utc_now()
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

    def load_beliefs(self) -> list[dict[str, Any]]:
        return self._read_json(self.beliefs_path).get("beliefs", [])

    def load_contradictions(self) -> list[dict[str, Any]]:
        return self._read_json(self.contradictions_path).get("contradictions", [])

    def load_research_questions(self) -> list[dict[str, Any]]:
        return self._read_json(self.research_questions_path).get("research_questions", [])

    def save_beliefs(self, beliefs: list[dict[str, Any]]) -> None:
        self._write_json(self.beliefs_path, {"schema_version": SCHEMA_VERSION, "beliefs": beliefs})

    def save_contradictions(self, contradictions: list[dict[str, Any]]) -> None:
        self._write_json(
            self.contradictions_path,
            {"schema_version": SCHEMA_VERSION, "contradictions": contradictions},
        )

    def save_research_questions(self, questions: list[dict[str, Any]]) -> None:
        self._write_json(
            self.research_questions_path,
            {"schema_version": SCHEMA_VERSION, "research_questions": questions},
        )

    def append_beliefs(self, new_beliefs: list[Belief | dict[str, Any]]) -> list[dict[str, Any]]:
        beliefs = self.load_beliefs()
        for item in new_beliefs:
            payload = item.to_dict() if isinstance(item, Belief) else item
            if self._is_duplicate_belief(beliefs, payload):
                continue
            beliefs.append(payload)
        self.save_beliefs(beliefs)
        return beliefs

    def _is_duplicate_belief(self, existing: list[dict[str, Any]], candidate: dict[str, Any]) -> bool:
        """Skip beliefs with same topic + polarity already in the store."""
        topic = candidate.get("topic")
        polarity = candidate.get("polarity")
        for belief in existing:
            if belief.get("topic") == topic and belief.get("polarity") == polarity:
                return True
        return False

    def append_contradictions(self, new_items: list[Contradiction | dict[str, Any]]) -> list[dict[str, Any]]:
        contradictions = self.load_contradictions()
        for item in new_items:
            contradictions.append(item.to_dict() if isinstance(item, Contradiction) else item)
        self.save_contradictions(contradictions)
        return contradictions

    def append_research_questions(self, new_items: list[ResearchQuestion | dict[str, Any]]) -> list[dict[str, Any]]:
        questions = self.load_research_questions()
        for item in new_items:
            questions.append(item.to_dict() if isinstance(item, ResearchQuestion) else item)
        self.save_research_questions(questions)
        return questions

    def get_open_contradictions(self) -> list[dict[str, Any]]:
        return [c for c in self.load_contradictions() if c.get("status") == "open"]

    def get_open_research_questions(self) -> list[dict[str, Any]]:
        return [q for q in self.load_research_questions() if q.get("status") == "open"]

    def snapshot(self) -> dict[str, Any]:
        return {
            "beliefs": self.load_beliefs(),
            "contradictions": self.load_contradictions(),
            "research_questions": self.load_research_questions(),
        }
