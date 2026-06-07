"""Persist committee approvals and rejections."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cabs.belief_store import SCHEMA_VERSION, Belief, BeliefStore


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CommitteeStore:
    def __init__(self, belief_store_root: str | Path):
        self.root = Path(belief_store_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.approved_path = self.root / "approved_techniques.json"
        self.rejected_path = self.root / "rejected_techniques.json"
        self.usage_path = self.root / "committee_usage.json"
        self._ensure_files()

    def _ensure_files(self) -> None:
        for path, key, empty in (
            (self.approved_path, "approved_techniques", []),
            (self.rejected_path, "rejected_techniques", []),
            (self.usage_path, "reviewed", []),
        ):
            if not path.exists():
                path.write_text(
                    json.dumps({"schema_version": SCHEMA_VERSION, key: empty, "updated_at": _utc_now()}, indent=2),
                    encoding="utf-8",
                )

    def _read(self, path: Path, key: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items = data.get(key) or []
            return items if isinstance(items, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _write(self, path: Path, key: str, items: list[dict[str, Any]]) -> None:
        path.write_text(
            json.dumps({"schema_version": SCHEMA_VERSION, key: items, "updated_at": _utc_now()}, indent=2),
            encoding="utf-8",
        )

    def load_approved(self) -> list[dict[str, Any]]:
        return self._read(self.approved_path, "approved_techniques")

    def load_rejected(self) -> list[dict[str, Any]]:
        return self._read(self.rejected_path, "rejected_techniques")

    def already_reviewed(self, technique: str, research_question_id: str | None) -> bool:
        reviewed = self._read(self.usage_path, "reviewed")
        for entry in reviewed:
            if entry.get("technique") == technique and entry.get("research_question_id") == research_question_id:
                return True
        return False

    def record_review(self, technique: str, research_question_id: str | None, status: str) -> None:
        reviewed = self._read(self.usage_path, "reviewed")
        reviewed.append(
            {
                "technique": technique,
                "research_question_id": research_question_id,
                "status": status,
                "timestamp": _utc_now(),
            }
        )
        self._write(self.usage_path, "reviewed", reviewed)

    def append_approved(self, record: dict[str, Any]) -> None:
        items = self.load_approved()
        items.append(record)
        self._write(self.approved_path, "approved_techniques", items)

    def append_rejected(self, record: dict[str, Any]) -> None:
        items = self.load_rejected()
        items.append(record)
        self._write(self.rejected_path, "rejected_techniques", items)

    def promote_to_beliefs(self, belief_store: BeliefStore, record: dict[str, Any], generation: int) -> None:
        """Add approved technique as a belief for prompt injection."""
        belief_text = record.get("belief") or record.get("belief_text") or ""
        if not belief_text:
            return
        topic = record.get("topic") or "prompting"
        belief_store.append_beliefs(
            [
                Belief(
                    belief=belief_text,
                    topic=topic,
                    polarity="positive",
                    confidence=float(record.get("confidence", 0.75)),
                    generation=generation,
                    evidence=[f"committee:{record.get('technique')}"],
                    metadata={
                        "source": "committee",
                        "technique": record.get("technique"),
                        "implementation_hint": record.get("implementation_hint"),
                        "committee_vote": record.get("committee_vote"),
                    },
                )
            ]
        )
