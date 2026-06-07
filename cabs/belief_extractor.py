"""Extract structured beliefs from SIA generation artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cabs.belief_nlp import detect_polarity, detect_topic
from cabs.belief_store import Belief
from cabs.dna_mapping import DNA_TRAIT_FIELDS, dna_field_to_topic
from cabs.feedback_beliefs import find_beliefs_json, parse_beliefs_file
from cabs.llm_belief_extractor import maybe_supplement_beliefs


@dataclass
class AgentContext:
    agent_id: int
    generation: int
    run_dir: Path
    agent_dir: Path
    improvement_text: str = ""
    results: dict[str, Any] | None = None
    agent_code: str = ""
    stdout_tail: str = ""
    agent_dna: dict[str, Any] | None = None
    fitness: float | None = None


@dataclass
class GenerationContext:
    generation: int
    run_dir: Path
    gen_dir: Path
    improvement_text: str = ""
    results: dict[str, Any] | None = None
    agent_code: str = ""
    stdout_tail: str = ""
    agents: list[AgentContext] = field(default_factory=list)
    is_population: bool = False


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _load_results(agent_dir: Path) -> dict[str, Any] | None:
    for name in ("results.json", "score.json"):
        data = _load_json(agent_dir / name)
        if data is None:
            continue
        if name == "score.json" and "results" in data:
            return data["results"]
        return data
    return None


def _extract_fitness(results: dict[str, Any] | None, score_path: Path | None = None) -> float | None:
    if results:
        for key in ("accuracy", "score", "f1", "macro_f1", "primary_metric", "fitness"):
            if key in results and isinstance(results[key], (int, float)):
                return float(results[key])
    if score_path and score_path.exists():
        data = _load_json(score_path)
        if data and "fitness" in data:
            return float(data["fitness"])
    return None


def iter_agent_dirs(gen_dir: Path) -> list[Path]:
    """Return sorted agent_* subdirs, or empty if flat standard-SIA layout."""
    agents = sorted(
        [p for p in gen_dir.glob("agent_*") if p.is_dir()],
        key=lambda p: int(p.name.split("_")[1]),
    )
    return agents


def is_population_layout(gen_dir: Path) -> bool:
    return bool(iter_agent_dirs(gen_dir))


def load_agent_context(run_dir: Path, generation: int, agent_id: int) -> AgentContext:
    gen_dir = run_dir / f"gen_{generation}"
    agent_dir = gen_dir / f"agent_{agent_id}"
    results = _load_results(agent_dir)
    return AgentContext(
        agent_id=agent_id,
        generation=generation,
        run_dir=run_dir,
        agent_dir=agent_dir,
        improvement_text=_read_text(agent_dir / "improvement.md"),
        results=results,
        agent_code=_read_text(agent_dir / "target_agent.py"),
        stdout_tail=_read_text(agent_dir / "target_agent_stdout.log")[-4000:],
        agent_dna=_load_json(agent_dir / "agent_dna.json"),
        fitness=_extract_fitness(results, agent_dir / "score.json"),
    )


def load_generation_context(run_dir: str | Path, generation: int) -> GenerationContext:
    run_path = Path(run_dir)
    gen_dir = run_path / f"gen_{generation}"
    agent_dirs = iter_agent_dirs(gen_dir)

    if agent_dirs:
        agents = [
            load_agent_context(run_path, generation, int(p.name.split("_")[1]))
            for p in agent_dirs
        ]
        return GenerationContext(
            generation=generation,
            run_dir=run_path,
            gen_dir=gen_dir,
            agents=agents,
            is_population=True,
        )

    return GenerationContext(
        generation=generation,
        run_dir=run_path,
        gen_dir=gen_dir,
        improvement_text=_read_text(gen_dir / "improvement.md"),
        results=_load_results(gen_dir),
        agent_code=_read_text(gen_dir / "target_agent.py"),
        stdout_tail=_read_text(gen_dir / "target_agent_stdout.log")[-4000:],
        is_population=False,
    )


def _confidence_from_evidence(text: str, results: dict[str, Any] | None) -> float:
    base = 0.55
    if results:
        base += 0.15
    if any(marker in text.lower() for marker in ("because", "evidence", "observed", "metric")):
        base += 0.1
    if len(text) > 120:
        base += 0.05
    return min(base, 0.95)


def _candidate_sentences(text: str) -> list[str]:
    if not text.strip():
        return []
    chunks = re.split(r"(?<=[.!?])\s+|\n+", text)
    candidates = []
    for chunk in chunks:
        cleaned = chunk.strip(" -*#")
        if len(cleaned) < 20:
            continue
        if not any(
            keyword in cleaned.lower()
            for keyword in ("memory", "plan", "tool", "reflect", "prompt", "search", "retry", "error", "model")
        ):
            continue
        candidates.append(cleaned)
    return candidates[:12]


def beliefs_from_sentence(sentence: str, generation: int, agent_id: int | None = None) -> Belief | None:
    topic = detect_topic(sentence)
    polarity = detect_polarity(sentence)
    if topic is None or polarity == "neutral":
        return None
    metadata: dict[str, Any] = {}
    if agent_id is not None:
        metadata["agent_id"] = agent_id
    return Belief(
        belief=sentence,
        topic=topic,
        polarity=polarity,
        confidence=_confidence_from_evidence(sentence, None),
        generation=generation,
        evidence=[f"gen_{generation}"],
        metadata=metadata,
    )


def _primary_score(results: dict[str, Any]) -> float | None:
    for key in ("accuracy", "score", "f1", "macro_f1", "primary_metric"):
        if key in results and isinstance(results[key], (int, float)):
            return float(results[key])
    for value in results.values():
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _extract_architecture_beliefs(
    agent_code: str,
    generation: int,
    agent_id: int | None = None,
) -> list[Belief]:
    code = agent_code.lower()
    beliefs: list[Belief] = []
    metadata_base: dict[str, Any] = {"source": "target_agent.py"}
    if agent_id is not None:
        metadata_base["agent_id"] = agent_id

    checks = [
        ("memory", r"\b(memory|history|conversation)\b", "Agent scaffold uses memory/history mechanisms"),
        ("reflection", r"\b(reflect|critique|review)\b", "Agent scaffold includes reflection/critique"),
        ("planning", r"\b(plan|step[- ]by[- ]step|decompose)\b", "Agent scaffold includes explicit planning"),
        ("tool_use", r"\b(tool|search|retriev|function)\b", "Agent scaffold uses tools or retrieval"),
    ]
    for topic, pattern, statement in checks:
        if re.search(pattern, code):
            beliefs.append(
                Belief(
                    belief=statement,
                    topic=topic,
                    polarity="positive",
                    confidence=0.72,
                    generation=generation,
                    evidence=[f"gen_{generation}"],
                    metadata=dict(metadata_base),
                )
            )
    return beliefs


def beliefs_from_agent_dna(
    agent_ctx: AgentContext,
    population_mean_fitness: float,
) -> list[Belief]:
    """Emit per-trait beliefs from DNA + fitness for cross-agent contradiction detection."""
    if not agent_ctx.agent_dna:
        return []

    beliefs: list[Belief] = []
    fitness = agent_ctx.fitness if agent_ctx.fitness is not None else 0.0

    for trait in DNA_TRAIT_FIELDS:
        if trait not in agent_ctx.agent_dna:
            continue
        value = agent_ctx.agent_dna[trait]
        topic = dna_field_to_topic(trait)
        if fitness > population_mean_fitness:
            polarity = "positive"
        elif fitness < population_mean_fitness:
            polarity = "negative"
        else:
            polarity = "positive" if agent_ctx.agent_id % 2 == 0 else "negative"

        beliefs.append(
            Belief(
                belief=(
                    f"Agent {agent_ctx.agent_id}: {trait}={value} "
                    f"achieved fitness {fitness:.4f} (population mean {population_mean_fitness:.4f})"
                ),
                topic=topic,
                polarity=polarity,
                confidence=0.85,
                generation=agent_ctx.generation,
                evidence=[f"gen_{agent_ctx.generation}/agent_{agent_ctx.agent_id}"],
                metadata={
                    "agent_id": agent_ctx.agent_id,
                    "trait": trait,
                    "value": value,
                    "fitness": fitness,
                    "source": "agent_dna.json",
                },
            )
        )
    return beliefs


def extract_beliefs_from_agent(agent_ctx: AgentContext, population_mean_fitness: float) -> list[Belief]:
    """Extract beliefs from a single darwinian population member."""
    beliefs: list[Belief] = []
    seen: set[tuple[str, str, int | None]] = set()
    gen = agent_ctx.generation
    aid = agent_ctx.agent_id

    beliefs_path = find_beliefs_json(agent_ctx.agent_dir)
    if beliefs_path:
        for belief in parse_beliefs_file(beliefs_path, gen):
            belief.metadata.setdefault("agent_id", aid)
            key = (belief.topic, belief.polarity, aid)
            if key in seen:
                continue
            seen.add(key)
            beliefs.append(belief)

    sources = [agent_ctx.improvement_text, agent_ctx.stdout_tail]
    if agent_ctx.results:
        sources.append(json.dumps(agent_ctx.results))

    for source in sources:
        for sentence in _candidate_sentences(source):
            belief = beliefs_from_sentence(sentence, gen, agent_id=aid)
            if belief is None:
                continue
            key = (belief.topic, belief.polarity, aid)
            if key in seen:
                continue
            seen.add(key)
            beliefs.append(belief)

    if agent_ctx.results:
        score = _primary_score(agent_ctx.results)
        if score is not None:
            beliefs.append(
                Belief(
                    belief=f"Agent {aid} generation {gen} achieved benchmark score {score:.4f}",
                    topic="benchmark_score",
                    polarity="positive" if score >= 0.5 else "negative",
                    confidence=0.9,
                    generation=gen,
                    evidence=[f"gen_{gen}/agent_{aid}"],
                    metadata={"agent_id": aid, "score": score},
                )
            )

    if not agent_ctx.agent_dna:
        for belief in _extract_architecture_beliefs(agent_ctx.agent_code, gen, agent_id=aid):
            key = (belief.topic, belief.polarity, aid)
            if key in seen:
                continue
            seen.add(key)
            beliefs.append(belief)

    for belief in beliefs_from_agent_dna(agent_ctx, population_mean_fitness):
        key = (belief.topic, belief.polarity, aid)
        if key in seen:
            continue
        seen.add(key)
        beliefs.append(belief)

    return beliefs


def extract_beliefs_from_generation(ctx: GenerationContext) -> list[Belief]:
    """Extract beliefs from generation artifacts (flat or darwinian population layout)."""
    if ctx.is_population and ctx.agents:
        fitnesses = [a.fitness or 0.0 for a in ctx.agents]
        mean_fitness = sum(fitnesses) / len(fitnesses) if fitnesses else 0.0
        all_beliefs: list[Belief] = []
        seen: set[tuple[str, str, int | None]] = set()
        for agent_ctx in ctx.agents:
            for belief in extract_beliefs_from_agent(agent_ctx, mean_fitness):
                aid = belief.metadata.get("agent_id")
                key = (belief.topic, belief.polarity, aid)
                if key in seen:
                    continue
                seen.add(key)
                all_beliefs.append(belief)
        return all_beliefs

    beliefs: list[Belief] = []
    seen: set[tuple[str, str, int | None]] = set()

    beliefs_path = find_beliefs_json(ctx.gen_dir)
    if beliefs_path:
        for belief in parse_beliefs_file(beliefs_path, ctx.generation):
            key = (belief.topic, belief.polarity, None)
            if key in seen:
                continue
            seen.add(key)
            beliefs.append(belief)

    sources = [ctx.improvement_text, ctx.stdout_tail]
    if ctx.results:
        sources.append(json.dumps(ctx.results))

    for source in sources:
        for sentence in _candidate_sentences(source):
            belief = beliefs_from_sentence(sentence, ctx.generation)
            if belief is None:
                continue
            key = (belief.topic, belief.polarity, None)
            if key in seen:
                continue
            seen.add(key)
            beliefs.append(belief)

    if ctx.results:
        score = _primary_score(ctx.results)
        if score is not None:
            beliefs.append(
                Belief(
                    belief=f"Generation {ctx.generation} achieved benchmark score {score:.4f}",
                    topic="benchmark_score",
                    polarity="positive" if score >= 0.5 else "negative",
                    confidence=0.9,
                    generation=ctx.generation,
                    evidence=[f"gen_{ctx.generation}"],
                    metadata={"score": score},
                )
            )

    for belief in _extract_architecture_beliefs(ctx.agent_code, ctx.generation):
        key = (belief.topic, belief.polarity, None)
        if key in seen:
            continue
        seen.add(key)
        beliefs.append(belief)

    beliefs = maybe_supplement_beliefs(beliefs, ctx.improvement_text, ctx.generation)
    deduped: list[Belief] = []
    seen = set()
    for belief in beliefs:
        aid = belief.metadata.get("agent_id")
        key = (belief.topic, belief.polarity, aid)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(belief)
    return deduped


def ingest_civilization(run_dir: str | Path) -> list[Belief]:
    """Convert civilization.json trait_insights into CABS beliefs (Section 19.2)."""
    run_path = Path(run_dir)
    civ_path = run_path / "civilization.json"
    if not civ_path.exists():
        return []

    try:
        with civ_path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return []

    beliefs: list[Belief] = []
    trait_insights = data.get("trait_insights")

    if isinstance(trait_insights, list):
        for insight in trait_insights:
            trait = insight.get("trait", "")
            value = insight.get("value", "")
            delta = insight.get("mean_fitness_delta")
            gens = insight.get("generations_observed", [])
            conf = float(insight.get("confidence", 0.7))
            topic = dna_field_to_topic(trait)
            delta_str = f"+{delta:.3f}" if delta is not None and delta >= 0 else (
                f"{delta:.3f}" if delta is not None else "unknown delta"
            )
            beliefs.append(
                Belief(
                    belief=f"{trait}={value} correlates with {delta_str} fitness on benchmark",
                    topic=topic,
                    polarity="positive" if (delta is None or delta >= 0) else "negative",
                    confidence=conf,
                    generation=max(gens) if gens else 0,
                    evidence=[f"civilization.json"],
                    metadata={
                        "source": "civilization.json",
                        "trait": trait,
                        "value": value,
                        "mean_fitness_delta": delta,
                        "generations_observed": gens,
                    },
                )
            )
    elif isinstance(trait_insights, dict):
        for trait, ranked in trait_insights.items():
            if not ranked:
                continue
            top = ranked[0]
            if isinstance(top, (list, tuple)) and len(top) >= 2:
                value, count = top[0], top[1]
            else:
                continue
            topic = dna_field_to_topic(trait)
            beliefs.append(
                Belief(
                    belief=f"{trait}={value} appeared in {count} elite(s) across generations",
                    topic=topic,
                    polarity="positive",
                    confidence=min(0.95, 0.6 + count * 0.1),
                    generation=0,
                    evidence=["civilization.json"],
                    metadata={
                        "source": "civilization.json",
                        "trait": trait,
                        "value": value,
                        "elite_count": count,
                    },
                )
            )

    return beliefs
