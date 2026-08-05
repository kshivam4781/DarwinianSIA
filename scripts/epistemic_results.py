#!/usr/bin/env python3
"""Compute ICML epistemic metrics (H2 / H5 / PRIMARY helpers) from run directories.

Usage:
  python scripts/epistemic_results.py --run-dir runs/run_1301
  python scripts/epistemic_results.py --b-runs runs/run_1201 --d-runs runs/run_1301 --write-docs

Does not call paid APIs. Safe for dry-run and live GPQA artifacts.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def load_epistemic_series(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "belief_store" / "epistemic_value.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and "generation" in row:
            rows.append(row)
    rows.sort(key=lambda r: int(r["generation"]))
    return rows


def load_gen_fitness(run_dir: Path) -> dict[int, dict[str, float]]:
    """Map generation → {best, mean} from civilization.json (fallback: agent results)."""
    out: dict[int, dict[str, float]] = {}
    civ = _load_json(run_dir / "civilization.json")
    if civ:
        for gen in civ.get("generations", []):
            try:
                g = int(gen.get("gen") or gen.get("generation"))
            except (TypeError, ValueError):
                continue
            out[g] = {
                "best": float(gen.get("best_fitness", 0.0) or 0.0),
                "mean": float(gen.get("mean_fitness", 0.0) or 0.0),
            }
        if out:
            return out

    for gen_dir in sorted(run_dir.glob("gen_*")):
        try:
            g = int(gen_dir.name.split("_", 1)[1])
        except ValueError:
            continue
        fits: list[float] = []
        for results_path in gen_dir.glob("agent_*/results.json"):
            data = _load_json(results_path)
            if not data:
                continue
            acc = data.get("accuracy")
            if isinstance(acc, (int, float)):
                fits.append(float(acc))
        if fits:
            out[g] = {"best": max(fits), "mean": sum(fits) / len(fits)}
    return out


def spearman_rho(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation; None if undefined (n<2 or zero variance)."""
    n = len(xs)
    if n != len(ys) or n < 2:
        return None
    try:
        from scipy.stats import spearmanr

        corr = spearmanr(xs, ys)
        val = float(corr.statistic if hasattr(corr, "statistic") else corr[0])
        return None if math.isnan(val) else val
    except Exception:
        # Pure-Python fallback
        def ranks(vals: list[float]) -> list[float]:
            order = sorted(range(len(vals)), key=lambda i: vals[i])
            r = [0.0] * len(vals)
            i = 0
            while i < len(vals):
                j = i
                while j + 1 < len(vals) and vals[order[j + 1]] == vals[order[i]]:
                    j += 1
                avg = (i + j) / 2.0 + 1.0
                for k in range(i, j + 1):
                    r[order[k]] = avg
                i = j + 1
            return r

        rx, ry = ranks(xs), ranks(ys)
        mean_x = sum(rx) / n
        mean_y = sum(ry) / n
        num = sum((rx[i] - mean_x) * (ry[i] - mean_y) for i in range(n))
        den_x = math.sqrt(sum((rx[i] - mean_x) ** 2 for i in range(n)))
        den_y = math.sqrt(sum((ry[i] - mean_y) ** 2 for i in range(n)))
        if den_x == 0.0 or den_y == 0.0:
            return None
        return num / (den_x * den_y)


def compute_h5(
    run_dir: Path,
    fitness_key: str = "mean",
    *,
    min_generation: int = 2,
) -> dict[str, Any]:
    """H5: Spearman ρ(epistemic_value_t, Δfitness_t+1).

    Default ``fitness_key="mean"``: population-mean Δfitness matches
    contradiction-scoped steering (which reshapes the population, not only the
    elite). Elite ``best`` is still available for sensitivity checks.

    Default ``min_generation=2`` excludes gen1→gen2 pairs. Under Condition D
    delay-all DNA steering, breeding into gen2 is intentionally fair (no CABS
    mutation/crossover bias yet), so gen1 epistemic stock cannot be expected to
    predict that Δfitness. H5 therefore measures predictive validity once
    contradiction-scoped steering is active (gen≥2 → gen≥3).
    """
    epi = load_epistemic_series(run_dir)
    fitness = load_gen_fitness(run_dir)
    pairs_x: list[float] = []
    pairs_y: list[float] = []
    detail: list[dict[str, Any]] = []
    for row in epi:
        g = int(row["generation"])
        if g < int(min_generation):
            continue
        if g not in fitness or (g + 1) not in fitness:
            continue
        ev = float(row.get("epistemic_value", 0.0) or 0.0)
        delta = float(fitness[g + 1][fitness_key]) - float(fitness[g][fitness_key])
        pairs_x.append(ev)
        pairs_y.append(delta)
        detail.append({"generation": g, "epistemic_value": ev, "delta_fitness": delta})
    rho = spearman_rho(pairs_x, pairs_y)
    return {
        "n_pairs": len(pairs_x),
        "spearman_rho": rho,
        "pass": bool(rho is not None and rho > 0.3),
        "pairs": detail,
        "fitness_key": fitness_key,
        "min_generation": int(min_generation),
    }


def collect_dna_traits(run_dir: Path, field: str = "memory") -> Counter:
    counts: Counter = Counter()
    for dna_path in run_dir.glob("gen_*/agent_*/agent_dna.json"):
        data = _load_json(dna_path)
        if not data:
            continue
        val = data.get(field)
        if val is not None:
            counts[str(val)] += 1
    return counts


def compute_h2(
    run_dir: Path,
    field: str = "memory",
    bias_values: list[str] | None = None,
) -> dict[str, Any]:
    """H2 helper: fraction of DNA trait values that fall in contradiction bias pool."""
    counts = collect_dna_traits(run_dir, field)
    total = sum(counts.values())
    bias = list(bias_values or [])
    if not bias:
        # Infer from belief_store mutation-bias-like signals if present
        from contextlib import suppress

        with suppress(Exception):
            sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "SIA"))
            from sia.evolution.cabs_bridge import load_mutation_bias

            bias_map = load_mutation_bias(str(run_dir))
            bias = list(bias_map.get(field, []))
    in_bias = sum(counts[v] for v in counts if v in bias) if bias else 0
    share = (in_bias / total) if total else None
    return {
        "field": field,
        "counts": dict(counts),
        "total": total,
        "bias_values": bias,
        "in_bias_count": in_bias,
        "in_bias_share": share,
    }


def gens_to_threshold(run_dir: Path, threshold: float = 0.25, fitness_key: str = "best") -> int | None:
    fitness = load_gen_fitness(run_dir)
    for g in sorted(fitness):
        if fitness[g][fitness_key] >= threshold:
            return g
    return None


def summarize_run(run_dir: Path) -> dict[str, Any]:
    fitness = load_gen_fitness(run_dir)
    gens = sorted(fitness)
    final = fitness[gens[-1]] if gens else {"best": 0.0, "mean": 0.0}
    h5 = compute_h5(run_dir)
    h2 = compute_h2(run_dir, field="memory")
    return {
        "run_dir": str(run_dir),
        "n_generations": len(gens),
        "final_best": final["best"],
        "final_mean": final["mean"],
        "gens_to_25": gens_to_threshold(run_dir, 0.25),
        "gens_to_30": gens_to_threshold(run_dir, 0.30),
        "h5": h5,
        "h2_memory": h2,
        "learning_curve": {str(g): fitness[g] for g in gens},
    }


def _gens_win(d_g: int | None, b_g: int | None) -> str | None:
    """Return 'D', 'B', or None (tie) for gens-to-threshold comparison.

    Reaching the threshold when the other never does counts as a win.
    """
    if d_g is None and b_g is None:
        return None
    if d_g is not None and b_g is None:
        return "D"
    if b_g is not None and d_g is None:
        return "B"
    if d_g is not None and b_g is not None:
        if d_g < b_g:
            return "D"
        if b_g < d_g:
            return "B"
    return None


def compare_b_vs_d(b_runs: list[Path], d_runs: list[Path]) -> dict[str, Any]:
    rows = []
    b_wins = {"gens25": 0, "gens30": 0, "final": 0}
    d_wins = {"gens25": 0, "gens30": 0, "final": 0}
    n = min(len(b_runs), len(d_runs))
    for i in range(n):
        b = summarize_run(b_runs[i])
        d = summarize_run(d_runs[i])
        for key, bucket in (("gens_to_25", "gens25"), ("gens_to_30", "gens30")):
            winner = _gens_win(d.get(key), b.get(key))
            if winner == "D":
                d_wins[bucket] += 1
            elif winner == "B":
                b_wins[bucket] += 1
        if d["final_best"] > b["final_best"] + 0.01:
            d_wins["final"] += 1
        elif b["final_best"] > d["final_best"] + 0.01:
            b_wins["final"] += 1
        rows.append({"seed_idx": i, "B": b, "D": d})
    return {
        "n_pairs": n,
        "d_wins_gens25": d_wins["gens25"],
        "b_wins_gens25": b_wins["gens25"],
        "d_wins_gens30": d_wins["gens30"],
        "b_wins_gens30": b_wins["gens30"],
        "d_wins_final": d_wins["final"],
        "b_wins_final": b_wins["final"],
        "primary_gens25_pass": d_wins["gens25"] >= 3 and n >= 5,
        "primary_gens30_pass": d_wins["gens30"] >= 3 and n >= 5,
        "rows": rows,
    }


def _maybe_write_figures(summary: dict[str, Any], out_dir: Path) -> list[str]:
    written: list[str] = []
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return written

    out_dir.mkdir(parents=True, exist_ok=True)
    curve = summary.get("learning_curve") or {}
    if curve:
        gens = sorted(int(g) for g in curve)
        bests = [curve[str(g)]["best"] for g in gens]
        means = [curve[str(g)]["mean"] for g in gens]
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot(gens, bests, marker="o", label="best")
        ax.plot(gens, means, marker="s", label="mean")
        ax.set_xlabel("generation")
        ax.set_ylabel("fitness")
        ax.set_title("Learning curve")
        ax.legend()
        ax.grid(True, alpha=0.3)
        path = out_dir / "fig1_learning_curves.png"
        fig.tight_layout()
        fig.savefig(path, dpi=120)
        plt.close(fig)
        written.append(str(path))

    h2 = summary.get("h2_memory") or {}
    counts = h2.get("counts") or {}
    if counts:
        fig, ax = plt.subplots(figsize=(6, 4))
        labels = list(counts.keys())
        vals = [counts[k] for k in labels]
        ax.bar(labels, vals)
        ax.set_title(f"H2 DNA trait histogram ({h2.get('field', 'memory')})")
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
    p.add_argument("--run-dir", type=Path, help="Single run directory to summarize")
    p.add_argument("--b-runs", nargs="*", type=Path, default=[], help="Condition B run dirs")
    p.add_argument("--d-runs", nargs="*", type=Path, default=[], help="Condition D run dirs")
    p.add_argument("--json-out", type=Path, help="Write full JSON summary here")
    p.add_argument("--write-docs", action="store_true", help="Refresh docs/paper_artifacts metrics block")
    p.add_argument("--figures-dir", type=Path, default=Path("docs/figures"))
    args = p.parse_args(argv)

    payload: dict[str, Any] = {}
    if args.run_dir:
        summary = summarize_run(args.run_dir)
        payload["single"] = summary
        figs = _maybe_write_figures(summary, args.figures_dir)
        payload["figures"] = figs
        print(json.dumps(summary, indent=2))
        h5 = summary["h5"]
        print(
            f"\nH5 Spearman ρ={h5['spearman_rho']} (n={h5['n_pairs']}) "
            f"pass={h5['pass']} (need > 0.3)"
        )

    if args.b_runs and args.d_runs:
        cmp_ = compare_b_vs_d(list(args.b_runs), list(args.d_runs))
        payload["compare"] = {
            k: v for k, v in cmp_.items() if k != "rows"
        }
        payload["compare_rows"] = cmp_["rows"]
        print(json.dumps(payload.get("compare", cmp_), indent=2))

    if not args.run_dir and not (args.b_runs and args.d_runs):
        p.error("Provide --run-dir and/or both --b-runs and --d-runs")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {args.json_out}")

    if args.write_docs and payload:
        docs = Path("docs/paper_artifacts.md")
        if docs.is_file():
            block = (
                "\n\n## Auto metrics (scripts/epistemic_results.py)\n\n"
                "```json\n"
                + json.dumps(payload.get("single") or payload.get("compare"), indent=2)
                + "\n```\n"
            )
            text = docs.read_text(encoding="utf-8")
            marker = "## Auto metrics (scripts/epistemic_results.py)"
            if marker in text:
                text = text.split(marker)[0].rstrip() + block
            else:
                text = text.rstrip() + block
            docs.write_text(text, encoding="utf-8")
            print(f"Updated {docs}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
