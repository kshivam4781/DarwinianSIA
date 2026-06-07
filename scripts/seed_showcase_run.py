"""Create runs/run_showcase — a 3-generation CABS story for hackathon demos (no API)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "runs" / "run_showcase"


GENERATIONS = [
    (
        1,
        """# Generation 1 improvements

- Memory helps on hard legal reasoning because context carries citations.
- Planning depth improves move selection on complex chess positions.
- Added conversation history buffer for multi-step tasks.
""",
        {"accuracy": 0.31, "correct": 15, "total": 50},
        "memory = True\nreflection = False\nplanning_depth = 3\n",
    ),
    (
        2,
        """# Generation 2 improvements

- Memory helps on hard examples; added reflection for error recovery.
- Planning depth of 5 improved accuracy on the hardest subset.
- Tool use via search helped when memory alone was insufficient.
""",
        {"accuracy": 0.38, "correct": 19, "total": 50},
        "memory = True\nreflection = True\nplanning_depth = 5\nuse_tools = True\n",
    ),
    (
        3,
        """# Generation 3 improvements

- Memory hurts on easy examples and reflection added latency/timeouts.
- Planning depth above 5 caused timeouts on long chain-of-thought paths.
- Disabling memory on easy slice may recover the regression we observed.
""",
        {"accuracy": 0.35, "correct": 17, "total": 50},
        "memory = True\nreflection = True\nplanning_depth = 7\nuse_tools = True\n",
    ),
]


def seed(force: bool = False) -> Path:
    if SHOWCASE.exists():
        if not force:
            return SHOWCASE
        shutil.rmtree(SHOWCASE)

    SHOWCASE.mkdir(parents=True)
    (SHOWCASE / "context.md").write_text(
        "# Showcase run\n\nSynthetic 3-generation story for hackathon presentation. No API keys required.\n",
        encoding="utf-8",
    )

    for gen, improvement, results, code in GENERATIONS:
        gen_dir = SHOWCASE / f"gen_{gen}"
        gen_dir.mkdir(parents=True)
        (gen_dir / "improvement.md").write_text(improvement, encoding="utf-8")
        (gen_dir / "target_agent.py").write_text(code, encoding="utf-8")
        (gen_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    return SHOWCASE


def main() -> None:
    path = seed(force="--force" in __import__("sys").argv)
    print(f"Showcase run ready: {path}")


if __name__ == "__main__":
    main()
