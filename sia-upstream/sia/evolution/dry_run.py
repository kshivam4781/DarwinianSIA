"""Dry-run helpers: mock agents and fitness without LLM API calls."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from sia.evolution.dna import AgentDNA
from sia.io_utils import write_text
from sia.layout import Names


def _deterministic_fitness(agent_id: int, dna: AgentDNA, generation: int) -> float:
    """Produce stable, varied fitness in [0.05, 0.95] from DNA + ids."""
    payload = json.dumps({"agent_id": agent_id, "gen": generation, "dna": dna.__dict__}, sort_keys=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    raw = int(digest[:8], 16) / 0xFFFFFFFF
    return round(0.05 + 0.9 * raw, 4)


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
