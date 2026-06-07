"""Offline demo: show CABS contradiction detection without API keys."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from cabs.belief_engine import BeliefEngine
from cabs.prompt_injection import format_cabs_context


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "run_demo"
        generations = [
            (
                1,
                "- Memory helps on hard legal reasoning because context carries citations.\n",
                {"accuracy": 0.31},
            ),
            (
                2,
                "- Memory helps on hard examples; added reflection for error recovery.\n",
                {"accuracy": 0.38},
            ),
            (
                3,
                "- Memory hurts on easy examples and reflection added latency/timeouts.\n",
                {"accuracy": 0.35},
            ),
        ]

        for gen, improvement, results in generations:
            gen_dir = run_dir / f"gen_{gen}"
            gen_dir.mkdir(parents=True)
            (gen_dir / "improvement.md").write_text(improvement, encoding="utf-8")
            (gen_dir / "target_agent.py").write_text(
                "memory = True\nreflection = True\nplanning_depth = 5\n",
                encoding="utf-8",
            )
            (gen_dir / "results.json").write_text(json.dumps(results), encoding="utf-8")

        engine = BeliefEngine.for_run(run_dir)
        for gen, _, _ in generations:
            engine.process_generation(run_dir, gen)

        agenda = engine.process_generation(run_dir, 3).agenda
        print("=== SIA-CABS Demo ===\n")
        print(format_cabs_context(agenda))
        print("\n=== Belief Store Snapshot ===\n")
        print(json.dumps(engine.store.snapshot(), indent=2))


if __name__ == "__main__":
    main()
