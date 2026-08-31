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
    delta_horizon: int = 2,
) -> dict[str, Any]:
    """H5: Spearman ρ(epistemic_value_t, forward Δfitness).

    Default ``fitness_key="mean"``: population-mean Δfitness matches
    contradiction-scoped steering (which reshapes the population, not only the
    elite). Elite ``best`` is still available for sensitivity checks.

    Default ``min_generation=2`` excludes gen1→gen2 pairs. Under Condition D
    delay-all DNA steering, breeding into gen2 is intentionally fair (no CABS
    mutation/crossover bias yet), so gen1 epistemic stock cannot be expected to
    predict that Δfitness. H5 therefore measures predictive validity once
    contradiction-scoped steering is active (gen≥2 → gen≥3).

    Default ``delta_horizon=2`` (Tick 19): Y is
    ``mean(fitness[t+1..t+h]) - fitness[t]`` with whatever future gens exist
    (at least one). ε-greedy mutation + live bias harvest can realize
    contradiction-scoped gains over 1–2 generations (discover → adopt); single
    step Δfitness is noisy under that lag and can zero out Spearman ρ even when
    epi ranks remaining improvement pressure correctly.
    """
    epi = load_epistemic_series(run_dir)
    fitness = load_gen_fitness(run_dir)
    horizon = max(1, int(delta_horizon))
    pairs_x: list[float] = []
    pairs_y: list[float] = []
    detail: list[dict[str, Any]] = []
    for row in epi:
        g = int(row["generation"])
        if g < int(min_generation):
            continue
        if g not in fitness:
            continue
        future = [g + i for i in range(1, horizon + 1) if (g + i) in fitness]
        if not future:
            continue
        ev = float(row.get("epistemic_value", 0.0) or 0.0)
        fut_mean = sum(float(fitness[f][fitness_key]) for f in future) / len(future)
        delta = fut_mean - float(fitness[g][fitness_key])
        pairs_x.append(ev)
        pairs_y.append(delta)
        detail.append(
            {
                "generation": g,
                "epistemic_value": ev,
                "delta_fitness": delta,
                "future_gens": future,
            }
        )
    rho = spearman_rho(pairs_x, pairs_y)
    return {
        "n_pairs": len(pairs_x),
        "spearman_rho": rho,
        "pass": bool(rho is not None and rho > 0.3),
        "pairs": detail,
        "fitness_key": fitness_key,
        "min_generation": int(min_generation),
        "delta_horizon": horizon,
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


def _agent_eval_cost(results: dict[str, Any]) -> tuple[float, str]:
    """Return (cost_units, unit) for one agent results.json.

    Prefer real token/USD fields from live GPQA; fall back to eval calls
    (``eval_subset`` / ``n_total`` / ``total_questions``, default 1).
    """
    tokens = 0.0
    for key in ("total_input_tokens", "total_output_tokens", "total_reasoning_tokens"):
        val = results.get(key)
        if isinstance(val, (int, float)):
            tokens += float(val)
    if tokens <= 0.0:
        for detail in results.get("details") or []:
            if not isinstance(detail, dict):
                continue
            for key in ("input_tokens", "output_tokens", "reasoning_tokens"):
                val = detail.get(key)
                if isinstance(val, (int, float)):
                    tokens += float(val)
    if tokens > 0.0:
        return tokens, "tokens"

    usd = results.get("total_cost_usd")
    if isinstance(usd, (int, float)) and float(usd) > 0.0:
        return float(usd), "usd"

    for key in ("eval_subset", "n_total", "total_questions"):
        val = results.get(key)
        if isinstance(val, (int, float)) and float(val) > 0.0:
            return float(val), "calls"
    return 1.0, "calls"


def _load_agent_cost_payload(agent_dir: Path) -> dict[str, Any] | None:
    """Load metering-bearing payload for one agent (Tick 290).

    Prefer ``results.json`` (accuracy + merged tokens after Tick 290 eval).
    Fall back to ``results/submission.json`` when results.json is accuracy-only
    (pre-merge live artifacts).
    """
    primary = _load_json(agent_dir / "results.json")
    if isinstance(primary, dict):
        # Has real metering?
        tokens = 0.0
        for key in ("total_input_tokens", "total_output_tokens", "total_reasoning_tokens"):
            val = primary.get(key)
            if isinstance(val, (int, float)):
                tokens += float(val)
        usd = primary.get("total_cost_usd")
        has_usd = isinstance(usd, (int, float)) and float(usd) > 0.0
        if tokens > 0.0 or has_usd or primary.get("details"):
            return primary
    submission = _load_json(agent_dir / "results" / "submission.json")
    if isinstance(submission, dict):
        if primary and isinstance(primary, dict):
            merged = dict(primary)
            for key in (
                "total_input_tokens",
                "total_output_tokens",
                "total_reasoning_tokens",
                "total_cost_usd",
                "total_questions",
                "details",
            ):
                if key in submission and key not in merged:
                    merged[key] = submission[key]
                elif key in submission and key == "details" and not merged.get("details"):
                    merged[key] = submission[key]
            return merged
        return submission
    return primary if isinstance(primary, dict) else None


def load_gen_cost(run_dir: Path) -> dict[int, dict[str, Any]]:
    """Map generation → cumulative-friendly cost units from agent results.

    Live GPQA writes token/USD fields; dry-run writes ``eval_subset`` / accuracy
    only, so cost falls back to per-agent eval calls. Unit is homogeneous within
    a run (tokens preferred over usd over calls).

    Tick 290: also reads ``results/submission.json`` when ``results.json`` lacks
    metering (latent pre-merge eval drop).
    """
    out: dict[int, dict[str, Any]] = {}
    for gen_dir in sorted(run_dir.glob("gen_*")):
        try:
            g = int(gen_dir.name.split("_", 1)[1])
        except ValueError:
            continue
        total = 0.0
        unit = "calls"
        n_agents = 0
        for agent_dir in sorted(gen_dir.glob("agent_*")):
            if not agent_dir.is_dir():
                continue
            data = _load_agent_cost_payload(agent_dir)
            if not data:
                continue
            cost, u = _agent_eval_cost(data)
            # Prefer higher-fidelity units if any agent reports them.
            if u == "tokens" or (u == "usd" and unit == "calls"):
                if unit != u and n_agents:
                    # Restart accumulation in the richer unit.
                    total = 0.0
                    n_agents = 0
                unit = u
            if u != unit:
                continue
            total += cost
            n_agents += 1
        if n_agents:
            out[g] = {"cost": total, "unit": unit, "n_agents": n_agents}
    return out


def cost_to_threshold(
    run_dir: Path,
    threshold: float = 0.30,
    fitness_key: str = "best",
) -> dict[str, Any]:
    """Cumulative cost (tokens/usd/calls) until gens-to-threshold; None if never."""
    g_hit = gens_to_threshold(run_dir, threshold, fitness_key=fitness_key)
    costs = load_gen_cost(run_dir)
    if g_hit is None:
        return {
            "generation": None,
            "cost": None,
            "unit": next((costs[g]["unit"] for g in sorted(costs)), "calls"),
            "threshold": threshold,
        }
    unit = "calls"
    total = 0.0
    for g in sorted(costs):
        if g > g_hit:
            break
        unit = str(costs[g]["unit"])
        total += float(costs[g]["cost"])
    return {
        "generation": g_hit,
        "cost": total if costs else None,
        "unit": unit,
        "threshold": threshold,
    }


def summarize_run(run_dir: Path) -> dict[str, Any]:
    fitness = load_gen_fitness(run_dir)
    gens = sorted(fitness)
    final = fitness[gens[-1]] if gens else {"best": 0.0, "mean": 0.0}
    h5 = compute_h5(run_dir)
    h2 = compute_h2(run_dir, field="memory")
    cost25 = cost_to_threshold(run_dir, 0.25)
    cost30 = cost_to_threshold(run_dir, 0.30)
    return {
        "run_dir": str(run_dir),
        "n_generations": len(gens),
        "final_best": final["best"],
        "final_mean": final["mean"],
        "gens_to_25": gens_to_threshold(run_dir, 0.25),
        "gens_to_30": gens_to_threshold(run_dir, 0.30),
        "cost_to_25": cost25,
        "cost_to_30": cost30,
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


def _cost_win(
    d_cost: float | None,
    b_cost: float | None,
    *,
    savings_frac: float = 0.15,
) -> str | None:
    """PRIMARY (b): D wins if ≥``savings_frac`` fewer cost units at equal threshold.

    Reaching the threshold when the other never does counts as a D/B win
    (infinite relative savings). Same-unit comparison only; ties if either cost
    is missing when both reached the threshold.
    """
    if d_cost is None and b_cost is None:
        return None
    if d_cost is not None and b_cost is None:
        return "D"
    if b_cost is not None and d_cost is None:
        return "B"
    assert d_cost is not None and b_cost is not None
    if b_cost <= 0.0 and d_cost <= 0.0:
        return None
    if b_cost <= 0.0:
        return "B" if d_cost > 0.0 else None
    if d_cost <= b_cost * (1.0 - savings_frac):
        return "D"
    if d_cost >= b_cost * (1.0 + savings_frac):
        return "B"
    return None


def compare_b_vs_d(b_runs: list[Path], d_runs: list[Path]) -> dict[str, Any]:
    rows = []
    b_wins = {"gens25": 0, "gens30": 0, "final": 0, "cost25": 0, "cost30": 0}
    d_wins = {"gens25": 0, "gens30": 0, "final": 0, "cost25": 0, "cost30": 0}
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
        for key, bucket in (("cost_to_25", "cost25"), ("cost_to_30", "cost30")):
            d_c = (d.get(key) or {}).get("cost")
            b_c = (b.get(key) or {}).get("cost")
            winner = _cost_win(
                float(d_c) if d_c is not None else None,
                float(b_c) if b_c is not None else None,
            )
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
        "d_wins_cost25": d_wins["cost25"],
        "b_wins_cost25": b_wins["cost25"],
        "d_wins_cost30": d_wins["cost30"],
        "b_wins_cost30": b_wins["cost30"],
        "d_wins_final": d_wins["final"],
        "b_wins_final": b_wins["final"],
        "primary_gens25_pass": d_wins["gens25"] >= 3 and n >= 5,
        "primary_gens30_pass": d_wins["gens30"] >= 3 and n >= 5,
        "primary_cost25_pass": d_wins["cost25"] >= 3 and n >= 5,
        "primary_cost30_pass": d_wins["cost30"] >= 3 and n >= 5,
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
