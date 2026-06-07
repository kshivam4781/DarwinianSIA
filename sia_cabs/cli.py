"""CLI for SIA-CABS."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cabs.belief_engine import BeliefEngine
from cabs.prompt_injection import agenda_snapshot
from cabs.committee.gate import run_committee_reviews
from cabs.tavily_grounding import ground_open_questions


def _cmd_analyze(args: argparse.Namespace) -> None:
    engine = BeliefEngine.for_run(args.run_dir)
    results = engine.process_run(args.run_dir, max_generation=args.max_gen)
    payload = {
        "run_dir": str(args.run_dir),
        "generations_processed": len(results),
        "results": [
            {
                "generation": r.generation,
                "beliefs_added": r.beliefs_added,
                "contradictions_added": r.contradictions_added,
                "research_questions_added": r.research_questions_added,
                "knowledge_gain_score": r.knowledge_gain_score,
            }
            for r in results
        ],
        "agenda": agenda_snapshot(str(Path(args.run_dir) / "belief_store")),
    }
    print(json.dumps(payload, indent=2))


def _cmd_agenda(args: argparse.Namespace) -> None:
    store_root = Path(args.run_dir) / "belief_store"
    print(json.dumps(agenda_snapshot(str(store_root)), indent=2))


def _cmd_committee(args: argparse.Namespace) -> None:
    from sia_cabs.env_loader import load_project_dotenv

    load_project_dotenv()
    store_root = Path(args.run_dir) / "belief_store"
    summary = run_committee_reviews(
        str(store_root),
        generation=args.generation,
        max_reviews=args.max_reviews,
        task_hint=args.task_hint,
        use_llm=not args.offline,
    )
    print(json.dumps(summary, indent=2))


def _cmd_ground(args: argparse.Namespace) -> None:
    from sia_cabs.env_loader import load_project_dotenv

    load_project_dotenv()
    store_root = Path(args.run_dir) / "belief_store"
    summary = ground_open_questions(
        str(store_root),
        generation=args.generation,
        max_calls=args.max_calls,
        task_hint=args.task_hint,
    )
    print(json.dumps(summary, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sia-cabs",
        description="SIA with Contradiction-Aware Belief System (CABS)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    analyze_parser = sub.add_parser("analyze", help="Run CABS on an existing SIA run directory")
    analyze_parser.add_argument("--run-dir", required=True, help="Path to runs/run_<id>")
    analyze_parser.add_argument("--max-gen", type=int, default=None, help="Only process up to this generation")
    analyze_parser.set_defaults(func=_cmd_analyze)

    agenda_parser = sub.add_parser("agenda", help="Print current CABS research agenda for a run")
    agenda_parser.add_argument("--run-dir", required=True, help="Path to runs/run_<id>")
    agenda_parser.set_defaults(func=_cmd_agenda)

    ground_parser = sub.add_parser("ground", help="Ground open research questions with Tavily")
    ground_parser.add_argument("--run-dir", required=True, help="Path to runs/run_<id>")
    ground_parser.add_argument("--generation", type=int, default=0, help="Generation label for evidence")
    ground_parser.add_argument("--max-calls", type=int, default=10, help="Max Tavily calls for this run")
    ground_parser.add_argument("--task-hint", default="", help="Task name appended to search queries")
    ground_parser.set_defaults(func=_cmd_ground)

    committee_parser = sub.add_parser("committee", help="Run committee review on Tavily evidence")
    committee_parser.add_argument("--run-dir", required=True, help="Path to runs/run_<id>")
    committee_parser.add_argument("--generation", type=int, default=0)
    committee_parser.add_argument("--max-reviews", type=int, default=5)
    committee_parser.add_argument("--task-hint", default="")
    committee_parser.add_argument("--offline", action="store_true", help="Heuristic votes only (no Haiku)")
    committee_parser.set_defaults(func=_cmd_committee)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
