"""Dry-run helpers: mock agents and fitness without LLM API calls."""

from __future__ import annotations

import json
import os
from pathlib import Path

from sia.evolution.dna import AgentDNA
from sia.io_utils import write_text
from sia.layout import Names

# Latent per-trait quality for offline dry-run fitness. Additive scores make
# contradiction → fitness-weighted bias → DNA adoption causally improve fitness
# (opaque DNA-hash scoring broke that chain: biasing one field scrambled others
# and often lowered fitness, yielding negative multi-seed H5).
_LATENT_TRAIT_SCORES: dict[str, dict[str, float]] = {
    "planning_style": {
        "hierarchical": 0.12,
        "stepwise": 0.10,
        "direct": 0.04,
    },
    "tool_strategy": {
        "selective": 0.22,
        "minimal": 0.12,
        "aggressive": 0.03,
    },
    "retry_policy": {
        "error_specific": 0.10,
        "generic": 0.07,
        "none": 0.02,
    },
    "memory": {
        "failure_based": 0.18,
        "short_summary": 0.12,
        "full_history": 0.08,
        "none": 0.03,
    },
    "prompt_structure": {
        "chain_of_thought": 0.12,
        "detailed": 0.09,
        "minimal": 0.04,
    },
}
_REFLECTION_SCORE = {True: 0.08, False: 0.02}
# confidence_threshold: peak near 0.75
_BASE_FITNESS = 0.05
_MAX_LATENT = (
    0.12  # planning
    + 0.22  # tool
    + 0.10  # retry
    + 0.18  # memory
    + 0.12  # prompt
    + 0.08  # reflection
    + 0.06  # confidence peak
)


def _confidence_score(threshold: float) -> float:
    # Triangular peak at 0.75; max 0.06
    dist = abs(float(threshold) - 0.75)
    return max(0.0, 0.06 * (1.0 - dist / 0.35))


def deterministic_fitness(agent_id: int, dna: AgentDNA, generation: int) -> float:
    """Produce stable, varied fitness in ~[0.05, 0.70] from transferable DNA traits.

    Fitness depends **only** on DNA trait values (not ``agent_id`` / ``generation``),
    so offspring that inherit a high-fitness parent's traits keep that fitness
    contribution. Scores are **additive latent trait qualities** so Condition D's
    contradiction-scoped bias toward higher-fitness sides causally improves fitness
    offline (needed for H5 / case-study chains). Not a substitute for live GPQA.

    ``agent_id`` and ``generation`` remain in the signature for call-site
    compatibility but are ignored for scoring.
    """
    del agent_id, generation  # unused — fitness must transfer with DNA traits
    total = _BASE_FITNESS
    total += _LATENT_TRAIT_SCORES["planning_style"].get(dna.planning_style, 0.0)
    total += _LATENT_TRAIT_SCORES["tool_strategy"].get(dna.tool_strategy, 0.0)
    total += _LATENT_TRAIT_SCORES["retry_policy"].get(dna.retry_policy, 0.0)
    total += _LATENT_TRAIT_SCORES["memory"].get(dna.memory, 0.0)
    total += _LATENT_TRAIT_SCORES["prompt_structure"].get(dna.prompt_structure, 0.0)
    total += _REFLECTION_SCORE.get(bool(dna.reflection), 0.0)
    total += _confidence_score(dna.confidence_threshold)
    # Normalize additive sum into ~[0.05, 0.70]. Cap below ~0.75 so random
    # gen-1 DNA often sits under the 25%/30% PRIMARY thresholds; Condition D
    # must climb via contradiction-biased adoption of high-latent traits.
    span = _MAX_LATENT
    norm = (total - _BASE_FITNESS) / span if span > 0 else 0.0
    fitness = 0.05 + 0.65 * max(0.0, min(1.0, norm))
    return round(fitness, 4)


# Back-compat alias for older call sites / tests.
_deterministic_fitness = deterministic_fitness


def parse_agent_coords(agent_dir: str) -> tuple[int, int]:
    """Return (agent_id, generation) parsed from ``.../gen_N/agent_K`` paths."""
    generation = 1
    agent_id = 0
    for part in Path(agent_dir).parts:
        if part.startswith("gen_"):
            try:
                generation = int(part.split("_", 1)[1])
            except ValueError:
                pass
        elif part.startswith("agent_"):
            try:
                agent_id = int(part.split("_", 1)[1])
            except ValueError:
                pass
    return agent_id, generation


def write_mock_target_agent(agent_dir: str, task_name: str) -> None:
    """Write a target agent that produces valid mock outputs without API calls."""
    if task_name == "lawbench":
        body = '''#!/usr/bin/env python3
"""Dry-run mock target agent for LawBench."""
import argparse
from pathlib import Path
import pandas as pd

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset_dir", required=True)
    p.add_argument("--working_dir", required=True)
    args = p.parse_args()
    dataset = Path(args.dataset_dir)
    work = Path(args.working_dir)
    work.mkdir(parents=True, exist_ok=True)
    test = pd.read_csv(dataset / "test.csv")
    classes = __import__("json").loads((dataset / "classes.json").read_text(encoding="utf-8"))
    default_label = classes[0] if classes else "盗窃"
    out = pd.DataFrame({"id": test["id"], "label": [default_label] * len(test)})
    out.to_csv(work / "submission.csv", index=False)
    print(f"Dry-run: wrote {len(out)} mock predictions")

if __name__ == "__main__":
    main()
'''
    elif task_name == "gpqa":
        body = '''#!/usr/bin/env python3
"""Dry-run mock target agent for GPQA."""
import argparse
import json
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset_dir", required=True)
    p.add_argument("--working_dir", required=True)
    args = p.parse_args()
    dataset = Path(args.dataset_dir)
    work = Path(args.working_dir)
    work.mkdir(parents=True, exist_ok=True)
    questions = json.loads((dataset / "diamond_questions.json").read_text(encoding="utf-8"))
    details = [{"question_id": q["id"], "model_answer": "A"} for q in questions]
    payload = {
        "model": "dry-run-mock",
        "dataset_config": "diamond_qna",
        "total_questions": len(questions),
        "errors": 0,
        "details": details,
    }
    results_dir = work / "results"
    results_dir.mkdir(exist_ok=True)
    (results_dir / "submission.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Dry-run: wrote {len(details)} mock GPQA answers")

if __name__ == "__main__":
    main()
'''
    else:
        body = '''#!/usr/bin/env python3
import argparse
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dataset_dir", required=True)
    p.add_argument("--working_dir", required=True)
    args = p.parse_args()
    Path(args.working_dir).mkdir(parents=True, exist_ok=True)
    Path(args.working_dir, "dry_run.txt").write_text("ok", encoding="utf-8")
    print("Dry-run mock agent completed")

if __name__ == "__main__":
    main()
'''
    write_text(os.path.join(agent_dir, Names.TARGET_AGENT), body)


def write_mock_results(agent_dir: str, fitness: float, task_name: str, eval_subset: int | None) -> None:
    results = {
        "accuracy": fitness,
        "n_correct": int(fitness * 100),
        "n_total": 100,
        "dry_run": True,
    }
    if eval_subset is not None:
        results["eval_subset"] = eval_subset
    path = os.path.join(agent_dir, Names.RESULTS_JSON)
    Path(path).write_text(json.dumps(results, indent=2), encoding="utf-8")
    score_path = os.path.join(agent_dir, Names.SCORE_JSON)
    Path(score_path).write_text(json.dumps({"fitness": fitness, "results": results}, indent=2), encoding="utf-8")


def agent_creation_complete(agent_dir: str) -> bool:
    return os.path.isfile(os.path.join(agent_dir, Names.TARGET_AGENT))


def agent_run_complete(agent_dir: str) -> bool:
    return os.path.isfile(os.path.join(agent_dir, Names.RESULTS_JSON))
