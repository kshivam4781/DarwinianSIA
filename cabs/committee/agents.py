"""Committee roles: proponent, skeptic, replicator."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class CommitteeVote:
    role: str
    vote: str  # approve | reject | abstain
    rationale: str


@dataclass
class CommitteeDecision:
    technique: str
    status: str  # approved | rejected
    votes: list[CommitteeVote]
    implementation_hint: str
    task: str
    research_question_id: str | None = None
    belief_text: str = ""


def _extract_json_object(text: str) -> dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def _heuristic_votes(candidate: dict[str, Any]) -> list[CommitteeVote]:
    """Offline committee when Anthropic is unavailable."""
    hint = candidate.get("implementation_hint") or ""
    confidence = float(candidate.get("confidence", 0.5))
    concrete = len(hint) > 40 and any(
        kw in hint.lower() for kw in ("disable", "enable", "limit", "sample", "slice", "cap")
    )

    proponent = CommitteeVote(
        role="proponent",
        vote="approve" if confidence >= 0.55 else "abstain",
        rationale="External evidence supports trying this technique on the target task.",
    )
    skeptic = CommitteeVote(
        role="skeptic",
        vote="reject" if not concrete and confidence < 0.65 else "approve",
        rationale="Reject vague techniques without a concrete harness change."
        if not concrete
        else "Implementation hint is concrete enough to test safely.",
    )
    replicator = CommitteeVote(
        role="replicator",
        vote="approve" if concrete else "abstain",
        rationale="Technique is reproducible in target_agent.py scaffold."
        if concrete
        else "Need clearer steps before coding this into the harness.",
    )
    return [proponent, skeptic, replicator]


def _llm_committee_votes(candidate: dict[str, Any], task_hint: str) -> list[CommitteeVote]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return _heuristic_votes(candidate)

    try:
        import anthropic
    except ImportError:
        return _heuristic_votes(candidate)

    prompt = f"""You are simulating a 3-agent committee that gates whether an external AI technique enters a self-improving agent harness.

Task context: {task_hint or "benchmark agent optimization"}
Technique candidate: {json.dumps(candidate, indent=2)}

Return ONLY JSON:
{{
  "proponent": {{"vote": "approve|reject|abstain", "rationale": "..."}},
  "skeptic": {{"vote": "approve|reject|abstain", "rationale": "..."}},
  "replicator": {{"vote": "approve|reject|abstain", "rationale": "..."}}
}}

Rules:
- Proponent argues for experimentation value.
- Skeptic flags risk, cost, or weak evidence.
- Replicator judges if the technique can be implemented in Python target_agent.py.
- Approve only if evidence is relevant and implementation_hint is actionable.
"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = ""
        for block in message.content:
            if hasattr(block, "text"):
                raw += block.text
        data = _extract_json_object(raw)
    except Exception:
        return _heuristic_votes(candidate)

    votes: list[CommitteeVote] = []
    for role in ("proponent", "skeptic", "replicator"):
        entry = data.get(role) or {}
        vote = str(entry.get("vote", "abstain")).lower()
        if vote not in ("approve", "reject", "abstain"):
            vote = "abstain"
        votes.append(
            CommitteeVote(
                role=role,
                vote=vote,
                rationale=str(entry.get("rationale", ""))[:500],
            )
        )
    return votes


def deliberate(
    candidate: dict[str, Any],
    *,
    task_hint: str = "",
    use_llm: bool = True,
) -> CommitteeDecision:
    """Run proponent/skeptic/replicator and return gate decision."""
    votes = _llm_committee_votes(candidate, task_hint) if use_llm else _heuristic_votes(candidate)

    approve = sum(1 for v in votes if v.vote == "approve")
    reject = sum(1 for v in votes if v.vote == "reject")

    if reject >= 2:
        status = "rejected"
    elif approve >= 2:
        status = "approved"
    else:
        status = "rejected"

    technique = candidate.get("technique") or "unknown"
    task = candidate.get("task") or task_hint or "general"
    title = candidate.get("title") or technique
    belief_text = (
        f"Technique '{title}' may help on {task} (committee-approved external idea)."
        if status == "approved"
        else ""
    )

    return CommitteeDecision(
        technique=technique,
        status=status,
        votes=votes,
        implementation_hint=candidate.get("implementation_hint") or "",
        task=task,
        research_question_id=candidate.get("research_question_id"),
        belief_text=belief_text,
    )
