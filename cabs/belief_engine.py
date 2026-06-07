"""Orchestrate the CABS pipeline after each SIA generation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cabs.belief_extractor import (
    extract_beliefs_from_generation,
    ingest_civilization,
    is_population_layout,
    load_generation_context,
)
from cabs.belief_store import Belief, BeliefStore
from cabs.contradiction_detector import detect_contradictions, detect_population_contradictions
from cabs.feedback_beliefs import parse_beliefs_file
from cabs.research_agent import build_research_agenda
from cabs.research_question_generator import generate_research_questions
from cabs.resolution_tracker import check_resolutions
from cabs.committee.gate import run_committee_reviews
from cabs.tavily_grounding import ground_open_questions


@dataclass
class CabsEngineConfig:
    enable_tavily: bool = False
    tavily_max_calls: int = 10
    enable_committee: bool = False
    committee_max_reviews: int = 5
    committee_use_llm: bool = True
    task_hint: str = ""


@dataclass
class GenerationCabsResult:
    generation: int
    beliefs_added: int
    contradictions_added: int
    research_questions_added: int
    resolutions: int
    knowledge_gain_score: float
    agenda: dict[str, Any]
    tavily: dict[str, Any] = field(default_factory=dict)
    committee: dict[str, Any] = field(default_factory=dict)


class BeliefEngine:
    """Run belief extraction, contradiction detection, and research planning."""

    def __init__(self, belief_store_root: str | Path, config: CabsEngineConfig | None = None):
        self.store = BeliefStore(belief_store_root)
        self.config = config or CabsEngineConfig()

    @classmethod
    def for_run(
        cls,
        run_dir: str | Path,
        *,
        enable_tavily: bool = False,
        tavily_max_calls: int = 10,
        enable_committee: bool = False,
        committee_max_reviews: int = 5,
        committee_use_llm: bool = True,
        task_hint: str = "",
    ) -> "BeliefEngine":
        return cls(
            Path(run_dir) / "belief_store",
            CabsEngineConfig(
                enable_tavily=enable_tavily,
                tavily_max_calls=tavily_max_calls,
                enable_committee=enable_committee,
                committee_max_reviews=committee_max_reviews,
                committee_use_llm=committee_use_llm,
                task_hint=task_hint,
            ),
        )

    def process_generation(self, run_dir: str | Path, generation: int) -> GenerationCabsResult:
        run_path = Path(run_dir)
        ctx = load_generation_context(run_path, generation)

        improvement_text = ctx.improvement_text
        if ctx.is_population and ctx.agents:
            improvement_text = "\n".join(
                a.improvement_text for a in ctx.agents if a.improvement_text
            )

        resolutions = self._apply_resolution_tracking(improvement_text, generation)

        new_beliefs = extract_beliefs_from_generation(ctx)

        if generation == 1 and (run_path / "civilization.json").exists():
            civ_beliefs = ingest_civilization(run_path)
            if civ_beliefs:
                seen_civ = {(b.topic, b.polarity) for b in new_beliefs}
                for belief in civ_beliefs:
                    key = (belief.topic, belief.polarity)
                    if key not in seen_civ:
                        new_beliefs.append(belief)
                        seen_civ.add(key)

        self.store.append_beliefs(new_beliefs)

        all_beliefs = self.store.load_beliefs()
        existing_contradictions = self.store.load_contradictions()
        new_contradictions = detect_contradictions(all_beliefs, generation, existing_contradictions)

        if ctx.is_population:
            pop_contradictions = detect_population_contradictions(
                all_beliefs, generation, existing_contradictions + [c.to_dict() for c in new_contradictions]
            )
            new_contradictions.extend(pop_contradictions)

        self.store.append_contradictions(new_contradictions)

        existing_questions = self.store.load_research_questions()
        new_questions = generate_research_questions(
            [c.to_dict() for c in new_contradictions],
            existing_questions,
        )
        self.store.append_research_questions(new_questions)

        tavily_summary = self._maybe_ground_with_tavily(generation)
        committee_summary = self._maybe_run_committee(generation, after_tavily=tavily_summary)

        agenda = build_research_agenda(
            self.store.load_contradictions(),
            self.store.load_research_questions(),
            belief_store_root=self.store.root,
        )
        self._write_generation_report(
            ctx.gen_dir,
            generation,
            agenda,
            new_beliefs,
            new_contradictions,
            new_questions,
            resolutions,
            tavily_summary=tavily_summary,
            committee_summary=committee_summary,
        )

        knowledge_gain = self._knowledge_gain_score(
            new_beliefs, new_contradictions, new_questions, resolutions, tavily_summary, committee_summary
        )
        return GenerationCabsResult(
            generation=generation,
            beliefs_added=len(new_beliefs),
            contradictions_added=len(new_contradictions),
            research_questions_added=len(new_questions),
            resolutions=resolutions,
            knowledge_gain_score=knowledge_gain,
            agenda=agenda,
            tavily=tavily_summary,
            committee=committee_summary,
        )

    def ingest_feedback_beliefs(
        self,
        run_dir: str | Path,
        artifact_dir: str | Path,
        source_generation: int,
    ) -> GenerationCabsResult:
        """After feedback agent completes, ingest beliefs.json from next gen dir."""
        artifact_path = Path(artifact_dir)
        beliefs_path = artifact_path / "beliefs.json"
        new_beliefs = parse_beliefs_file(beliefs_path, source_generation)
        if not new_beliefs:
            return GenerationCabsResult(
                generation=source_generation,
                beliefs_added=0,
                contradictions_added=0,
                research_questions_added=0,
                resolutions=0,
                knowledge_gain_score=0.0,
                agenda=build_research_agenda(
                    self.store.load_contradictions(),
                    self.store.load_research_questions(),
                    belief_store_root=self.store.root,
                ),
            )

        self.store.append_beliefs(new_beliefs)
        all_beliefs = self.store.load_beliefs()
        existing_contradictions = self.store.load_contradictions()
        new_contradictions = detect_contradictions(all_beliefs, source_generation, existing_contradictions)
        self.store.append_contradictions(new_contradictions)

        existing_questions = self.store.load_research_questions()
        new_questions = generate_research_questions(
            [c.to_dict() for c in new_contradictions],
            existing_questions,
        )
        self.store.append_research_questions(new_questions)

        tavily_summary = self._maybe_ground_with_tavily(source_generation)
        committee_summary = self._maybe_run_committee(source_generation, after_tavily=tavily_summary)

        agenda = build_research_agenda(
            self.store.load_contradictions(),
            self.store.load_research_questions(),
            belief_store_root=self.store.root,
        )
        gen_dir = Path(run_dir) / f"gen_{source_generation}"
        self._write_generation_report(
            gen_dir,
            source_generation,
            agenda,
            new_beliefs,
            new_contradictions,
            new_questions,
            0,
            source="feedback_ingest",
            tavily_summary=tavily_summary,
            committee_summary=committee_summary,
        )
        knowledge_gain = self._knowledge_gain_score(
            new_beliefs, new_contradictions, new_questions, 0, tavily_summary, committee_summary
        )
        return GenerationCabsResult(
            generation=source_generation,
            beliefs_added=len(new_beliefs),
            contradictions_added=len(new_contradictions),
            research_questions_added=len(new_questions),
            resolutions=0,
            knowledge_gain_score=knowledge_gain,
            agenda=agenda,
            tavily=tavily_summary,
            committee=committee_summary,
        )

    def run_committee(self, generation: int = 0) -> dict[str, Any]:
        """Retroactively run committee reviews (CLI use)."""
        self.config.enable_committee = True
        return self._maybe_run_committee(generation, after_tavily={"enabled": True})

    def ground_existing_questions(self, generation: int = 0) -> dict[str, Any]:
        """Retroactively ground open questions (CLI / offline use)."""
        if not self.config.enable_tavily:
            self.config.enable_tavily = True
        return self._maybe_ground_with_tavily(generation)

    def process_run(self, run_dir: str | Path, max_generation: int | None = None) -> list[GenerationCabsResult]:
        run_path = Path(run_dir)
        gen_dirs = sorted(
            [p for p in run_path.glob("gen_*") if p.is_dir()],
            key=lambda p: int(p.name.split("_")[1]),
        )
        if max_generation is not None:
            gen_dirs = [p for p in gen_dirs if int(p.name.split("_")[1]) <= max_generation]

        results = []
        for gen_dir in gen_dirs:
            generation = int(gen_dir.name.split("_")[1])
            results.append(self.process_generation(run_path, generation))
        return results

    def _maybe_ground_with_tavily(self, generation: int) -> dict[str, Any]:
        if not self.config.enable_tavily:
            return {"enabled": False, "reason": "tavily disabled"}
        return ground_open_questions(
            str(self.store.root),
            generation=generation,
            max_calls=self.config.tavily_max_calls,
            task_hint=self.config.task_hint,
        )

    def _maybe_run_committee(self, generation: int, after_tavily: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.config.enable_committee:
            return {"enabled": False, "reason": "committee disabled"}
        after_tavily = after_tavily or {}
        if self.config.enable_tavily and not after_tavily.get("grounded") and after_tavily.get("enabled"):
            pass  # Tavily ran but found nothing new — still review existing evidence
        return run_committee_reviews(
            str(self.store.root),
            generation=generation,
            max_reviews=self.config.committee_max_reviews,
            task_hint=self.config.task_hint,
            use_llm=self.config.committee_use_llm,
        )

    def _apply_resolution_tracking(self, improvement_text: str, generation: int) -> int:
        questions = self.store.load_research_questions()
        contradictions = self.store.load_contradictions()
        open_before = sum(1 for q in questions if q.get("status") == "open")

        updated_questions, updated_contradictions = check_resolutions(
            improvement_text,
            questions,
            contradictions,
            generation,
        )
        self.store.save_research_questions(updated_questions)
        self.store.save_contradictions(updated_contradictions)

        open_after = sum(1 for q in updated_questions if q.get("status") == "open")
        return max(0, open_before - open_after)

    def _write_generation_report(
        self,
        gen_dir: Path,
        generation: int,
        agenda: dict[str, Any],
        beliefs: list,
        contradictions: list,
        questions: list,
        resolutions: int,
        source: str = "pipeline",
        tavily_summary: dict[str, Any] | None = None,
        committee_summary: dict[str, Any] | None = None,
    ) -> None:
        tavily_summary = tavily_summary or {}
        committee_summary = committee_summary or {}
        knowledge_gain = self._knowledge_gain_score(
            beliefs, contradictions, questions, resolutions, tavily_summary, committee_summary
        )
        report = {
            "generation": generation,
            "source": source,
            "beliefs_added": [b.to_dict() if isinstance(b, Belief) else b for b in beliefs],
            "contradictions_added": [c.to_dict() for c in contradictions],
            "research_questions_added": [q.to_dict() for q in questions],
            "resolutions": resolutions,
            "knowledge_gain_score": knowledge_gain,
            "cabs_injected": "prepend",
            "tavily": tavily_summary,
            "committee": committee_summary,
            "agenda": agenda,
        }
        gen_dir.mkdir(parents=True, exist_ok=True)
        with (gen_dir / "cabs_report.json").open("w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)

    def _knowledge_gain_score(
        self,
        beliefs: list,
        contradictions: list,
        questions: list,
        resolutions: int = 0,
        tavily_summary: dict[str, Any] | None = None,
        committee_summary: dict[str, Any] | None = None,
    ) -> float:
        """Reward uncertainty reduction, not only benchmark gains."""
        score = 0.0
        score += len(beliefs) * 0.05
        score += len(contradictions) * 0.25
        score += len(questions) * 0.35
        score += resolutions * 0.15
        if contradictions:
            score += sum(float(c.priority) for c in contradictions) / len(contradictions) * 0.2
        tavily_summary = tavily_summary or {}
        grounded = tavily_summary.get("grounded") or []
        score += len(grounded) * 0.1
        committee_summary = committee_summary or {}
        approved = committee_summary.get("approved") or []
        score += len(approved) * 0.12
        return round(min(score, 1.0), 4)
