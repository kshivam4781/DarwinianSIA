#!/usr/bin/env python3
"""Compare baseline SIA runs vs darwinian evolution runs for submission."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sia.evolution.operators import extract_fitness


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _run_label(run_dir: Path) -> str:
    return run_dir.name


def _baseline_row(run_dir: Path) -> dict:
    results_path = run_dir / "gen_1" / "results.json"
    results = _load_json(results_path)
    fitness = extract_fitness(results)
    notes_parts = []
    if results:
        if "eval_subset" in results:
            notes_parts.append(f"subset {results['eval_subset']}")
        if "n_correct" in results and "n_total" in results:
            notes_parts.append(f"{results['n_correct']}/{results['n_total']} correct")
    if not results_path.is_file():
        notes_parts.append("results.json missing")
    return {
        "run": _run_label(run_dir),
        "mode": "baseline",
        "best_fitness": fitness,
        "mean_fitness": fitness,
        "notes": ", ".join(notes_parts) if notes_parts else "standard SIA",
    }


def _darwinian_rows(run_dir: Path) -> list[dict]:
    civ_path = run_dir / "civilization.json"
    civ = _load_json(civ_path)
    if not civ:
        return [{
            "run": _run_label(run_dir),
            "mode": "darwinian",
            "best_fitness": 0.0,
            "mean_fitness": 0.0,
            "notes": "civilization.json missing",
        }]

    all_agents = [
        a for g in civ.get("generations", []) for a in g.get("agents", [])
    ]
    dry = bool(all_agents) and all(a.get("duration", 0) == 0.0 for a in all_agents)
    pop = civ.get("population_size", "?")
    rows = []
    for gen in civ.get("generations", []):
        elite_ids = gen.get("elite_ids", [])
        insights = civ.get("trait_insights", {})
        top_traits = []
        for trait, ranked in list(insights.items())[:2]:
            if ranked:
                top_traits.append(f"{trait}={ranked[0][0]}")
        notes_parts = [
            f"gen {gen.get('gen', '?')}",
            f"pop {pop}",
            f"elites {elite_ids}",
        ]
        if top_traits:
            notes_parts.append("; ".join(top_traits))
        if dry:
            notes_parts.append("dry-run")
        rows.append({
            "run": _run_label(run_dir),
            "mode": "darwinian",
            "best_fitness": gen.get("best_fitness", 0.0),
            "mean_fitness": gen.get("mean_fitness", 0.0),
            "notes": ", ".join(notes_parts),
        })
    return rows or [{
        "run": _run_label(run_dir),
        "mode": "darwinian",
        "best_fitness": 0.0,
        "mean_fitness": 0.0,
        "notes": "no generations recorded",
    }]


def _format_table(rows: list[dict]) -> str:
    header = "| Run | Mode | Best fitness | Mean fitness | Notes |"
    sep = "|-----|------|--------------|--------------|-------|"
    lines = [header, sep]
    for row in rows:
        best = f"{row['best_fitness']:.3f}"
        mean = f"{row['mean_fitness']:.3f}"
        lines.append(
            f"| {row['run']} | {row['mode']} | {best} | {mean} | {row['notes']} |"
        )
    return "\n".join(lines)


def _format_trait_insights(run_dir: Path) -> str:
    civ = _load_json(run_dir / "civilization.json")
    if not civ:
        return ""
    insights = civ.get("trait_insights")
    ranked = civ.get("trait_insights_ranked")
    if not insights and not ranked:
        return ""

    lines = ["", "### Trait insights", ""]

    if isinstance(insights, list):
        for item in insights[:8]:
            trait = item.get("trait", "?")
            value = item.get("value", "?")
            delta = item.get("mean_fitness_delta")
            delta_s = f" Δ={delta:+.3f}" if isinstance(delta, (int, float)) else ""
            lines.append(f"- **{trait}**={value}{delta_s}")
    elif isinstance(insights, dict):
        for trait, values in insights.items():
            if values:
                top = ", ".join(f"{val} ({count})" for val, count in values[:3])
                lines.append(f"- **{trait}**: {top}")

    if isinstance(ranked, dict) and not isinstance(insights, dict):
        lines.append("")
        lines.append("#### Elite win counts")
        for trait, values in ranked.items():
            if values:
                top = ", ".join(f"{val} ({count})" for val, count in values[:3])
                lines.append(f"- **{trait}**: {top}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare baseline vs darwinian SIA runs")
    parser.add_argument("--baseline", required=True, help="Baseline run directory (e.g. runs/run_201)")
    parser.add_argument("--darwinian", required=True, help="Darwinian run directory (e.g. runs/run_300)")
    parser.add_argument("--out", help="Write markdown table to this file")
    args = parser.parse_args()

    baseline_dir = Path(args.baseline)
    darwinian_dir = Path(args.darwinian)

    if not baseline_dir.is_dir():
        print(f"Error: baseline directory not found: {baseline_dir}", file=sys.stderr)
        return 1
    if not darwinian_dir.is_dir():
        print(f"Error: darwinian directory not found: {darwinian_dir}", file=sys.stderr)
        return 1

    rows = [_baseline_row(baseline_dir)] + _darwinian_rows(darwinian_dir)
    table = _format_table(rows)
    insights = _format_trait_insights(darwinian_dir)
    output = table + insights

    print(output)
    if args.out:
        Path(args.out).write_text(output + "\n", encoding="utf-8")
        print(f"\nWrote {args.out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
