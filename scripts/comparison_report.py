"""Compare baseline vs CABS runs for hackathon evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_accuracy(gen_dir: Path) -> float | None:
    results_path = gen_dir / "results.json"
    if not results_path.exists():
        return None
    try:
        data = json.loads(results_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if "summary" in data and isinstance(data["summary"], dict):
        acc = data["summary"].get("accuracy")
        if isinstance(acc, (int, float)):
            return float(acc)
    if "accuracy" in data and isinstance(data["accuracy"], (int, float)):
        return float(data["accuracy"])
    return None


def _generation_scores(run_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for gen_dir in sorted(run_dir.glob("gen_*"), key=lambda p: int(p.name.split("_")[1])):
        gen = int(gen_dir.name.split("_")[1])
        acc = _load_accuracy(gen_dir)
        cabs_path = gen_dir / "cabs_report.json"
        kg = None
        if cabs_path.exists():
            try:
                report = json.loads(cabs_path.read_text(encoding="utf-8"))
                kg = report.get("knowledge_gain_score")
            except (json.JSONDecodeError, OSError):
                pass
        rows.append({"generation": gen, "accuracy": acc, "knowledge_gain": kg})
    return rows


def _belief_summary(run_dir: Path) -> dict[str, int]:
    store = run_dir / "belief_store"
    counts = {
        "beliefs": 0,
        "contradictions": 0,
        "contradictions_open": 0,
        "contradictions_resolved": 0,
        "research_questions": 0,
        "research_questions_open": 0,
        "research_questions_resolved": 0,
    }
    mapping = {
        "beliefs": store / "beliefs.json",
        "contradictions": store / "contradictions.json",
        "research_questions": store / "research_questions.json",
    }
    for key, path in mapping.items():
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items = data.get(key) or data.get("contradictions") or data.get("research_questions") or []
            if isinstance(items, list):
                counts[key] = len(items)
                if key == "contradictions":
                    counts["contradictions_open"] = sum(1 for i in items if i.get("status") == "open")
                    counts["contradictions_resolved"] = sum(1 for i in items if i.get("status") == "resolved")
                if key == "research_questions":
                    counts["research_questions_open"] = sum(1 for i in items if i.get("status") == "open")
                    counts["research_questions_resolved"] = sum(1 for i in items if i.get("status") == "resolved")
        except (json.JSONDecodeError, OSError):
            pass
    return counts


def _cabs_timeline(cabs_dir: Path) -> list[dict[str, Any]]:
    events = []
    for gen_dir in sorted(cabs_dir.glob("gen_*"), key=lambda p: int(p.name.split("_")[1])):
        gen = int(gen_dir.name.split("_")[1])
        report_path = gen_dir / "cabs_report.json"
        if not report_path.exists():
            continue
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for c in report.get("contradictions_added") or []:
            events.append(
                {
                    "generation": gen,
                    "type": "contradiction",
                    "topic": c.get("topic"),
                    "summary": f"{c.get('belief_a', '')[:40]} vs {c.get('belief_b', '')[:40]}",
                }
            )
        for q in report.get("research_questions_added") or []:
            events.append(
                {
                    "generation": gen,
                    "type": "research_question",
                    "topic": q.get("topic"),
                    "summary": (q.get("question") or "")[:80],
                }
            )
        if report.get("resolutions"):
            events.append(
                {
                    "generation": gen,
                    "type": "resolution",
                    "topic": "",
                    "summary": f"{report['resolutions']} research question(s) resolved",
                }
            )
    return events


def build_report(baseline_dir: Path, cabs_dir: Path) -> dict[str, Any]:
    return {
        "baseline": {
            "run_dir": str(baseline_dir),
            "generations": _generation_scores(baseline_dir),
        },
        "cabs": {
            "run_dir": str(cabs_dir),
            "generations": _generation_scores(cabs_dir),
            "belief_store": _belief_summary(cabs_dir),
            "timeline": _cabs_timeline(cabs_dir),
        },
    }


def format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SIA vs SIA-CABS Comparison",
        "",
        "## Benchmark accuracy by generation",
        "",
        "| Generation | Baseline accuracy | CABS accuracy | CABS knowledge gain |",
        "|------------|-------------------|---------------|---------------------|",
    ]

    baseline_by_gen = {r["generation"]: r for r in report["baseline"]["generations"]}
    cabs_by_gen = {r["generation"]: r for r in report["cabs"]["generations"]}
    all_gens = sorted(set(baseline_by_gen) | set(cabs_by_gen))

    for gen in all_gens:
        b = baseline_by_gen.get(gen, {})
        c = cabs_by_gen.get(gen, {})
        b_acc = "—" if b.get("accuracy") is None else f"{b['accuracy']:.1%}"
        c_acc = "—" if c.get("accuracy") is None else f"{c['accuracy']:.1%}"
        kg = c.get("knowledge_gain")
        kg_str = "—" if kg is None else f"{kg:.2f}"
        lines.append(f"| {gen} | {b_acc} | {c_acc} | {kg_str} |")

    store = report["cabs"]["belief_store"]
    lines.extend(
        [
            "",
            "## CABS knowledge gain curve",
            "",
            "| Generation | Knowledge gain |",
            "|------------|----------------|",
        ]
    )
    for row in report["cabs"]["generations"]:
        kg = row.get("knowledge_gain")
        kg_str = "-" if kg is None else f"{kg:.2f}"
        lines.append(f"| {row['generation']} | {kg_str} |")

    lines.extend(
        [
            "",
            "## CABS belief store (cumulative)",
            "",
            f"- Beliefs: **{store['beliefs']}**",
            f"- Contradictions: **{store['contradictions']}** (open: {store['contradictions_open']}, resolved: {store['contradictions_resolved']})",
            f"- Research questions: **{store['research_questions']}** (open: {store['research_questions_open']}, resolved: {store['research_questions_resolved']})",
            "",
            "## CABS event timeline",
            "",
        ]
    )
    timeline = report["cabs"].get("timeline") or []
    if timeline:
        lines.append("| Gen | Event | Topic | Summary |")
        lines.append("|-----|-------|-------|---------|")
        for event in timeline:
            lines.append(
                f"| {event['generation']} | {event['type']} | {event.get('topic') or '-'} | {event.get('summary', '')} |"
            )
    else:
        lines.append(
            "_No CABS timeline events yet. Run a multi-generation CABS job or "
            f"`{Path(sys.executable).name} scripts/present_hackathon.py`._"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Standard SIA optimizes *score*. SIA-CABS also tracks *what the system learned* — "
            "especially when beliefs contradict (e.g. memory helps on hard cases but hurts on easy ones).",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare baseline SIA run vs SIA-CABS run")
    parser.add_argument("--baseline", required=True, help="Path to baseline run dir (e.g. runs/run_901)")
    parser.add_argument("--cabs", required=True, help="Path to CABS run dir (e.g. runs/run_902)")
    parser.add_argument("--markdown", action="store_true", help="Print markdown table for slides/docs")
    parser.add_argument("--out", type=Path, default=None, help="Write markdown report to file")
    args = parser.parse_args()

    report = build_report(Path(args.baseline), Path(args.cabs))
    md = format_markdown(report)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md, encoding="utf-8")
        print(f"Wrote {args.out}")

    if args.markdown or not args.out:
        print(md)

    if not args.markdown and not args.out:
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
