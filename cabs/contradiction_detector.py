"""Detect contradictions in the evolving belief graph."""

from __future__ import annotations

from cabs.belief_store import Contradiction


def _belief_priority(belief_a: dict, belief_b: dict) -> float:
    conf_a = float(belief_a.get("confidence", 0.5))
    conf_b = float(belief_b.get("confidence", 0.5))
    return min(1.0, (conf_a + conf_b) / 2 + abs(conf_a - conf_b) * 0.25)


def detect_contradictions(
    beliefs: list[dict],
    generation: int,
    existing: list[dict] | None = None,
) -> list[Contradiction]:
    """Find opposing beliefs on the same topic."""
    existing = existing or []
    existing_pairs = {
        tuple(sorted((c["belief_a_id"], c["belief_b_id"])))
        for c in existing
        if c.get("status") == "open"
    }

    active = [b for b in beliefs if b.get("status", "active") == "active"]
    by_topic: dict[str, list[dict]] = {}
    for belief in active:
        topic = belief.get("topic")
        if not topic or topic == "benchmark_score":
            continue
        by_topic.setdefault(topic, []).append(belief)

    contradictions: list[Contradiction] = []
    for topic, topic_beliefs in by_topic.items():
        positives = [b for b in topic_beliefs if b.get("polarity") == "positive"]
        negatives = [b for b in topic_beliefs if b.get("polarity") == "negative"]
        if not positives or not negatives:
            continue

        positive = max(positives, key=lambda b: float(b.get("confidence", 0)))
        negative = max(negatives, key=lambda b: float(b.get("confidence", 0)))
        pair_key = tuple(sorted((positive["id"], negative["id"])))
        if pair_key in existing_pairs:
            continue

        metadata = _population_metadata(positive, negative)
        contradictions.append(
            Contradiction(
                topic=topic,
                belief_a_id=positive["id"],
                belief_b_id=negative["id"],
                belief_a=positive["belief"],
                belief_b=negative["belief"],
                detected_at_gen=generation,
                confidence_delta=abs(
                    float(positive.get("confidence", 0)) - float(negative.get("confidence", 0))
                ),
                priority=_belief_priority(positive, negative),
                metadata=metadata,
            )
        )
    return contradictions


def _population_metadata(belief_a: dict, belief_b: dict) -> dict:
    """Attach agent IDs when contradiction spans population members (Section 19.4)."""
    meta_a = belief_a.get("metadata") or {}
    meta_b = belief_b.get("metadata") or {}
    agents = []
    for meta in (meta_a, meta_b):
        aid = meta.get("agent_id")
        if aid is not None and aid not in agents:
            agents.append(aid)
    if len(agents) >= 2:
        return {"agents": agents, "cross_agent": True}
    if agents:
        return {"agents": agents}
    return {}


def detect_population_contradictions(
    beliefs: list[dict],
    generation: int,
    existing: list[dict] | None = None,
) -> list[Contradiction]:
    """Find cross-agent contradictions: opposing beliefs on same topic from different agents."""
    existing = existing or []
    existing_pairs = {
        tuple(sorted((c["belief_a_id"], c["belief_b_id"])))
        for c in existing
        if c.get("status") == "open"
    }

    active = [b for b in beliefs if b.get("status", "active") == "active"]
    by_topic_agent: dict[str, dict[int, list[dict]]] = {}
    for belief in active:
        topic = belief.get("topic")
        if not topic or topic == "benchmark_score":
            continue
        meta = belief.get("metadata") or {}
        agent_id = meta.get("agent_id")
        if agent_id is None:
            continue
        by_topic_agent.setdefault(topic, {}).setdefault(agent_id, []).append(belief)

    contradictions: list[Contradiction] = []
    for topic, agent_beliefs in by_topic_agent.items():
        if len(agent_beliefs) < 2:
            continue

        positives: list[dict] = []
        negatives: list[dict] = []
        for agent_id, blist in agent_beliefs.items():
            for b in blist:
                if b.get("polarity") == "positive":
                    positives.append(b)
                elif b.get("polarity") == "negative":
                    negatives.append(b)

        if not positives or not negatives:
            continue

        positive = max(positives, key=lambda b: float(b.get("confidence", 0)))
        negative = max(negatives, key=lambda b: float(b.get("confidence", 0)))
        pos_agent = (positive.get("metadata") or {}).get("agent_id")
        neg_agent = (negative.get("metadata") or {}).get("agent_id")
        if pos_agent == neg_agent:
            continue

        pair_key = tuple(sorted((positive["id"], negative["id"])))
        if pair_key in existing_pairs:
            continue

        contradictions.append(
            Contradiction(
                topic=topic,
                belief_a_id=positive["id"],
                belief_b_id=negative["id"],
                belief_a=positive["belief"],
                belief_b=negative["belief"],
                detected_at_gen=generation,
                confidence_delta=abs(
                    float(positive.get("confidence", 0)) - float(negative.get("confidence", 0))
                ),
                priority=min(1.0, _belief_priority(positive, negative) + 0.1),
                metadata={"agents": [pos_agent, neg_agent], "cross_agent": True},
            )
        )
    return contradictions
