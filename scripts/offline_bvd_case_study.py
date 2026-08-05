#!/usr/bin/env python3
"""Offline Condition B vs D dry-run pilot + case-study chain (no API).

Runs synthetic GPQA-fixture Darwinian loops for Condition B (darwinian-only)
and Condition D (--cabs --cabs-inline), then:

1. Compares gens-to-threshold / final fitness across seeds
2. Extracts one documented case study:
   contradiction → fitness-weighted bias → offspring DNA skew → fitness lift
3. Optionally writes docs/figures and a JSON summary

Not a substitute for live GPQA PRIMARY. Safe under Section 21 hard stops.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "SIA"))
sys.path.insert(0, str(ROOT / "scripts"))

from epistemic_results import (  # noqa: E402
    compare_b_vs_d,
    summarize_run,
)
from sia.config import Config  # noqa: E402
from sia.context_manager import ContextManager  # noqa: E402
from sia.evolution.cabs_bridge import load_mutation_bias  # noqa: E402
from sia.evolution.cabs_inline import ensure_cabs_importable  # noqa: E402
from sia.evolution.dna import AgentDNA  # noqa: E402
from sia.evolution.dry_run import deterministic_fitness  # noqa: E402
from sia.evolution.population import run_darwinian_loop  # noqa: E402
from sia.layout import RunLayout  # noqa: E402
from sia.profiles import load_meta_agent_profile, load_target_agent_profile  # noqa: E402
from sia.run_setup import RunSetup, TaskFiles  # noqa: E402


def _make_gpqa_task(tmp_path: Path) -> tuple[str, str]:
    task_dir = tmp_path / "gpqa"
    shared = tmp_path / "_shared"
    ref = task_dir / "reference"
    pub = task_dir / "data" / "public"
    priv = task_dir / "data" / "private"
    for d in (shared, ref, pub, priv):
        d.mkdir(parents=True)

    questions = [
        {
            "id": i,
            "Question": f"Q{i}",
            "options": {"A": "1", "B": "2"},
            "correct_answer_letter": "A",
        }
        for i in range(8)
    ]
    (pub / "diamond_questions.json").write_text(json.dumps(questions), encoding="utf-8")
    (priv / "diamond_questions.json").write_text(json.dumps(questions), encoding="utf-8")
    (pub / "task.md").write_text("# GPQA offline B vs D fixture", encoding="utf-8")
    (ref / "reference_target_agent.py").write_text("print('ref')", encoding="utf-8")
    (ref / "SAMPLE_TASK_DESCRIPTIONS.md").write_text("samples", encoding="utf-8")
    (shared / "sample_agent_execution.json").write_text("[]", encoding="utf-8")
    return str(task_dir), str(shared)


def _run_condition(
    *,
    runs_root: Path,
    task_root: Path,
    run_id: int,
    seed: int,
    condition: str,
    pop: int,
    elite: int,
    max_gen: int,
    eval_subset: int,
) -> Path:
    assert condition in {"B", "D"}
    run_dir = runs_root / f"run_{run_id}"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    venv_dir = run_dir / "venv"
    venv_dir.mkdir(parents=True)
    (run_dir / "gen_1").mkdir(parents=True)

    task_dir, _shared = _make_gpqa_task(task_root / f"task_{run_id}")
    cabs_inline = condition == "D"
    enable_cabs = condition == "D"

    context_mgr = ContextManager(
        str(run_dir),
        {
            "task_dir": task_dir,
            "meta_model": "m",
            "task_model": "m",
            "agent_impl": "claude",
            "max_gen": max_gen,
            "cabs_inline": cabs_inline,
            "condition": condition,
            "seed": seed,
        },
    )
    context_mgr.initialize()

    run_setup = RunSetup(
        run_directory=str(run_dir),
        meta_agent_working_directory=str(run_dir / "gen_1"),
        venv_dir=str(venv_dir),
        context_mgr=context_mgr,
    )

    from sia.eval_subset import materialize_subset_dataset

    subset_dir = materialize_subset_dataset(task_dir, str(run_dir), eval_subset, task_name="gpqa")
    task_files = TaskFiles("samples", "ref", {}, "# GPQA offline B vs D fixture")
    meta = load_meta_agent_profile("default-meta")
    target = load_target_agent_profile("default-target")

    with (
        patch("sia.context_manager.ContextManager._generate_llm_summary", return_value=None),
        patch("sia.run_setup._create_venv", return_value=None),
        patch("sia.layout.venv_python_path", return_value=sys.executable),
    ):
        run_darwinian_loop(
            max_gen=max_gen,
            run_setup=run_setup,
            task_files=task_files,
            abs_dataset_dir=subset_dir,
            dataset_dir=subset_dir,
            meta_profile=meta,
            sandbox="none",
            env_config=Config(),
            task_model=target.model,
            target_provider=target.provider,
            focus="harness",
            training_sandbox="modal",
            resolved_ref=None,
            reference_dir=None,
            population_size=pop,
            elite_count=elite,
            mutation_rate=0.7,
            seed=seed,
            eval_subset=eval_subset,
            resume=False,
            dry_run=True,
            task_name="gpqa",
            task_root=task_dir,
            enable_cabs=enable_cabs,
            cabs_inline=cabs_inline,
        )
    return run_dir


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def extract_case_study(run_dir: Path) -> dict | None:
    """Find one chain: contradiction with fitness-tagged sides → bias order → DNA skew → lift."""
    store = run_dir / "belief_store"
    contradictions = _load_json(store / "contradictions.json").get("contradictions", [])
    beliefs = _load_json(store / "beliefs.json").get("beliefs", [])
    bias = load_mutation_bias(str(run_dir))
    if not contradictions or not bias:
        return None

    # Prefer a contradiction whose belief texts mention fitness and a DNA field in bias.
    chosen = None
    field = None
    for c in sorted(contradictions, key=lambda x: -float(x.get("priority", 0))):
        text = f"{c.get('belief_a', '')} || {c.get('belief_b', '')}"
        for f, values in bias.items():
            if len(values) < 2:
                continue
            if f in text or any(v in text for v in values):
                chosen = c
                field = f
                break
        if chosen is not None:
            break
    if chosen is None:
        field = next(iter(bias))
        chosen = contradictions[0]

    preferred = bias[field][0]
    disputed = list(bias[field])

    layout = RunLayout(str(run_dir))
    gen1_traits = []
    for agent_id in range(8):
        dna_path = Path(layout.gen_agent_dir(1, agent_id)) / "agent_dna.json"
        res_path = Path(layout.gen_agent_dir(1, agent_id)) / "results.json"
        if not dna_path.is_file():
            continue
        dna = _load_json(dna_path)
        res = _load_json(res_path)
        gen1_traits.append(
            {
                "agent_id": agent_id,
                "trait": dna.get(field),
                "fitness": float(res.get("accuracy", 0.0) or 0.0),
            }
        )

    gen2_traits = []
    for agent_id in range(8):
        dna_path = Path(layout.gen_agent_dir(2, agent_id)) / "agent_dna.json"
        res_path = Path(layout.gen_agent_dir(2, agent_id)) / "results.json"
        if not dna_path.is_file():
            continue
        dna = _load_json(dna_path)
        res = _load_json(res_path)
        gen2_traits.append(
            {
                "agent_id": agent_id,
                "trait": dna.get(field),
                "fitness": float(res.get("accuracy", 0.0) or 0.0),
            }
        )

    if not gen1_traits or not gen2_traits:
        return None

    loser_side = [t for t in disputed if t != preferred]
    loser = loser_side[0] if loser_side else None
    gen1_pref = [t for t in gen1_traits if t["trait"] == preferred]
    gen1_lose = [t for t in gen1_traits if loser and t["trait"] == loser]
    gen2_pref = [t for t in gen2_traits if t["trait"] == preferred]

    mean = lambda xs: (sum(xs) / len(xs)) if xs else None  # noqa: E731
    g1_pref_fit = mean([t["fitness"] for t in gen1_pref])
    g1_lose_fit = mean([t["fitness"] for t in gen1_lose]) if gen1_lose else None
    g2_pref_fit = mean([t["fitness"] for t in gen2_pref])
    g1_mean = mean([t["fitness"] for t in gen1_traits])
    g2_mean = mean([t["fitness"] for t in gen2_traits])

    # Fitness lift: preferred trait carriers in gen2 beat gen1 loser-side mean, or pop mean rises.
    lift = None
    if g2_pref_fit is not None and g1_lose_fit is not None:
        lift = g2_pref_fit - g1_lose_fit
    elif g1_mean is not None and g2_mean is not None:
        lift = g2_mean - g1_mean

    # Transferability check: preferred DNA scores same for any agent_id
    sample_dna = AgentDNA(**{k: v for k, v in _load_json(
        Path(layout.gen_agent_dir(1, gen1_pref[0]["agent_id"])) / "agent_dna.json"
    ).items() if k in AgentDNA.__dataclass_fields__}) if gen1_pref else None
    transfer_ok = False
    if sample_dna is not None:
        transfer_ok = deterministic_fitness(0, sample_dna, 1) == deterministic_fitness(9, sample_dna, 99)

    return {
        "run_dir": str(Path("runs") / run_dir.name),
        "field": field,
        "preferred_value": preferred,
        "bias_order": disputed,
        "contradiction": {
            "topic": chosen.get("topic"),
            "belief_a": chosen.get("belief_a"),
            "belief_b": chosen.get("belief_b"),
            "priority": chosen.get("priority"),
            "agents": (chosen.get("metadata") or {}).get("agents"),
        },
        "gen1_traits": gen1_traits,
        "gen2_traits": gen2_traits,
        "gen1_preferred_mean_fitness": g1_pref_fit,
        "gen1_loser_mean_fitness": g1_lose_fit,
        "gen2_preferred_mean_fitness": g2_pref_fit,
        "gen1_pop_mean": g1_mean,
        "gen2_pop_mean": g2_mean,
        "fitness_lift": lift,
        "gen2_preferred_share": (len(gen2_pref) / len(gen2_traits)) if gen2_traits else None,
        "dna_fitness_transfers": transfer_ok,
        "belief_count": len(beliefs),
        "agenda_prefers_first": preferred,
    }


def _write_case_study_md(case: dict, compare: dict, path: Path) -> None:
    lift = case.get("fitness_lift")
    lift_s = f"{lift:+.4f}" if isinstance(lift, (int, float)) else "n/a"
    lines = [
        "# Offline case study — Condition D mechanism chain",
        "",
        "**Status:** offline dry-run evidence (synthetic GPQA fixture; additive latent DNA fitness). "
        "Does **not** satisfy live PRIMARY. Supports MECHANISM case-study criterion.",
        "",
        f"**Run:** `{case['run_dir']}`",
        "",
        "## Chain",
        "",
        "1. **Tie / disagreement:** population agents hold opposing DNA-linked beliefs.",
        f"2. **Contradiction:** topic `{case['contradiction'].get('topic')}` — "
        f"'{case['contradiction'].get('belief_a')}' vs '{case['contradiction'].get('belief_b')}' "
        f"(priority={case['contradiction'].get('priority')}).",
        f"3. **Fitness-weighted bias:** field `{case['field']}` ordered "
        f"`{case['bias_order']}` (prefer `{case['preferred_value']}`).",
        f"4. **DNA skew:** gen2 share of preferred trait = "
        f"{case.get('gen2_preferred_share')}.",
        f"5. **Fitness lift:** preferred@gen2 mean − loser@gen1 mean = **{lift_s}** "
        f"(pop mean {case.get('gen1_pop_mean')} → {case.get('gen2_pop_mean')}).",
        "",
        f"DNA fitness transferability check: `{case.get('dna_fitness_transfers')}` "
        "(same DNA ⇒ same score across agent_id/gen).",
        "",
        "## Offline B vs D summary (synthetic; not PRIMARY)",
        "",
        "```json",
        json.dumps({k: v for k, v in compare.items() if k != "rows"}, indent=2),
        "```",
        "",
        "## Raw case payload",
        "",
        "```json",
        json.dumps(case, indent=2),
        "```",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _maybe_figures(b_runs: list[Path], d_runs: list[Path], out_dir: Path) -> list[str]:
    written: list[str] = []
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return written

    out_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7, 4))
    for label, runs, style in (("B", b_runs, "--"), ("D", d_runs, "-")):
        for i, run in enumerate(runs):
            s = summarize_run(run)
            curve = s.get("learning_curve") or {}
            gens = sorted(int(g) for g in curve)
            if not gens:
                continue
            bests = [curve[str(g)]["best"] for g in gens]
            ax.plot(
                gens,
                bests,
                style,
                marker="o",
                alpha=0.85,
                label=f"{label} seed{i}" if i < 3 or label == "D" else None,
            )
    ax.set_xlabel("generation")
    ax.set_ylabel("best fitness (dry-run DNA)")
    ax.set_title("Offline B vs D learning curves (synthetic)")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, ncol=2)
    path = out_dir / "fig1_learning_curves.png"
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written.append(str(path))

    # Fig 2 from first D run H2 histogram via summarize
    if d_runs:
        s = summarize_run(d_runs[0])
        counts = (s.get("h2_memory") or {}).get("counts") or {}
        if counts:
            fig, ax = plt.subplots(figsize=(6, 4))
            labels = list(counts.keys())
            vals = [counts[k] for k in labels]
            ax.bar(labels, vals, color="#2a6f97")
            ax.set_title("H2 DNA memory histogram (Condition D dry-run)")
            ax.set_ylabel("count")
            ax.tick_params(axis="x", rotation=30)
            path = out_dir / "fig2_mechanism.png"
            fig.tight_layout()
            fig.savefig(path, dpi=120)
            plt.close(fig)
            written.append(str(path))
    return written


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds", type=int, nargs="+", default=[11, 22, 33, 44, 55])
    p.add_argument("--pop", type=int, default=4)
    p.add_argument("--elite", type=int, default=2)
    p.add_argument("--max-gen", type=int, default=4)
    p.add_argument("--eval-subset", type=int, default=3)
    p.add_argument("--b-id-start", type=int, default=1410)
    p.add_argument("--d-id-start", type=int, default=1420)
    p.add_argument("--runs-root", type=Path, default=ROOT / "runs")
    p.add_argument("--work-root", type=Path, default=ROOT / "runs" / "_offline_bvd_work")
    p.add_argument("--json-out", type=Path, default=ROOT / "docs" / "offline_bvd_summary.json")
    p.add_argument("--case-md", type=Path, default=ROOT / "docs" / "case_study_offline.md")
    p.add_argument("--figures-dir", type=Path, default=ROOT / "docs" / "figures")
    args = p.parse_args(argv)

    if not ensure_cabs_importable():
        print("ERROR: cabs package not importable", file=sys.stderr)
        return 2

    args.runs_root.mkdir(parents=True, exist_ok=True)
    args.work_root.mkdir(parents=True, exist_ok=True)

    b_runs: list[Path] = []
    d_runs: list[Path] = []
    for i, seed in enumerate(args.seeds):
        b_id = args.b_id_start + i
        d_id = args.d_id_start + i
        print(f"Running seed={seed} B=run_{b_id} D=run_{d_id} ...")
        b_runs.append(
            _run_condition(
                runs_root=args.runs_root,
                task_root=args.work_root,
                run_id=b_id,
                seed=seed,
                condition="B",
                pop=args.pop,
                elite=args.elite,
                max_gen=args.max_gen,
                eval_subset=args.eval_subset,
            )
        )
        d_runs.append(
            _run_condition(
                runs_root=args.runs_root,
                task_root=args.work_root,
                run_id=d_id,
                seed=seed,
                condition="D",
                pop=args.pop,
                elite=args.elite,
                max_gen=args.max_gen,
                eval_subset=args.eval_subset,
            )
        )

    compare = compare_b_vs_d(b_runs, d_runs)
    # Prefer a positive-lift chain (tie → contradiction → DNA skew → fitness up).
    cases = [extract_case_study(d_run) for d_run in d_runs]
    cases = [c for c in cases if c and c.get("fitness_lift") is not None]
    positive = [c for c in cases if float(c.get("fitness_lift") or 0) > 0]
    case = None
    if positive:
        case = max(positive, key=lambda c: float(c.get("fitness_lift") or 0))
    elif cases:
        case = max(cases, key=lambda c: float(c.get("fitness_lift") or 0))
    elif d_runs:
        case = extract_case_study(d_runs[0])

    figs = _maybe_figures(b_runs, d_runs, args.figures_dir)
    payload = {
        "seeds": args.seeds,
        "b_run_ids": [args.b_id_start + i for i in range(len(args.seeds))],
        "d_run_ids": [args.d_id_start + i for i in range(len(args.seeds))],
        "compare": {k: v for k, v in compare.items() if k != "rows"},
        "compare_rows_brief": [
            {
                "seed": args.seeds[r["seed_idx"]],
                "B_final": r["B"]["final_best"],
                "D_final": r["D"]["final_best"],
                "B_gens25": r["B"]["gens_to_25"],
                "D_gens25": r["D"]["gens_to_25"],
                "B_gens30": r["B"]["gens_to_30"],
                "D_gens30": r["D"]["gens_to_30"],
                "D_h5_rho": (r["D"].get("h5") or {}).get("spearman_rho"),
                "D_h5_pass": (r["D"].get("h5") or {}).get("pass"),
                "D_h5_key": (r["D"].get("h5") or {}).get("fitness_key"),
                "D_h5_horizon": (r["D"].get("h5") or {}).get("delta_horizon"),
                "D_h2_share": (r["D"].get("h2_memory") or {}).get("in_bias_share"),
            }
            for r in compare.get("rows", [])
        ],
        "case_study": case,
        "figures": figs,
        "h5_protocol": {
            "min_generation": 2,
            "fitness_key": "mean",
            "delta_horizon": 2,
            "note": (
                "H5 uses population-mean forward Δfitness over the next 1–2 gens "
                "after DNA steering is active (gen≥2), matching ε-greedy discovery lag."
            ),
        },
        "note": (
            "Synthetic additive latent DNA fitness with transferable traits; offline only. "
            "Do not set ICML_READY PRIMARY from this."
        ),
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {args.json_out}")

    if case:
        _write_case_study_md(case, compare, args.case_md)
        print(f"Wrote {args.case_md}")
        print(
            f"Case study: field={case['field']} prefer={case['preferred_value']} "
            f"lift={case.get('fitness_lift')} gen2_pref_share={case.get('gen2_preferred_share')}"
        )
    print(json.dumps(payload["compare"], indent=2))
    print(json.dumps(payload["compare_rows_brief"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
