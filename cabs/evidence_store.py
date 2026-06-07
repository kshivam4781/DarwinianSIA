"""Persist Tavily evidence snippets under belief_store/evidence/."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cabs.belief_store import SCHEMA_VERSION


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidenceStore:
    def __init__(self, belief_store_root: str | Path):
        self.root = Path(belief_store_root)
        self.evidence_dir = self.root / "evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.usage_path = self.root / "tavily_usage.json"

    def load_usage(self) -> dict[str, Any]:
        if not self.usage_path.exists():
            return {"schema_version": SCHEMA_VERSION, "calls": 0, "history": []}
        try:
            return json.loads(self.usage_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"schema_version": SCHEMA_VERSION, "calls": 0, "history": []}

    def record_call(self, research_question_id: str, query: str, generation: int) -> int:
        usage = self.load_usage()
        usage["calls"] = int(usage.get("calls", 0)) + 1
        history = usage.setdefault("history", [])
        history.append(
            {
                "research_question_id": research_question_id,
                "query": query,
                "generation": generation,
                "timestamp": _utc_now(),
            }
        )
        usage["updated_at"] = _utc_now()
        self.usage_path.write_text(json.dumps(usage, indent=2), encoding="utf-8")
        return int(usage["calls"])

    def calls_used(self) -> int:
        return int(self.load_usage().get("calls", 0))

    def has_evidence(self, research_question_id: str) -> bool:
        return (self.evidence_dir / f"{research_question_id}.json").exists()

    def save_evidence(
        self,
        research_question_id: str,
        *,
        query: str,
        generation: int,
        answer: str | None,
        results: list[dict[str, Any]],
    ) -> Path:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "research_question_id": research_question_id,
            "query": query,
            "generation": generation,
            "answer": answer,
            "results": results,
            "fetched_at": _utc_now(),
        }
        path = self.evidence_dir / f"{research_question_id}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def load_all(self) -> list[dict[str, Any]]:
        items = []
        for path in sorted(self.evidence_dir.glob("*.json")):
            try:
                items.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return items

    def load_for_question(self, research_question_id: str) -> dict[str, Any] | None:
        path = self.evidence_dir / f"{research_question_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
