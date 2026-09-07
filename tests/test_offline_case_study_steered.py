"""Case-study extractor must score H2 DNA skew after delay-all steering (gen≥3)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "SIA"))

from icml_env_checks import icml_g3g4_live_shape  # noqa: E402
from offline_bvd_case_study import (  # noqa: E402
    FIRST_STEERED_GEN,
    args_match_live_shape,
    extract_case_study,
    main as offline_bvd_main,
    offline_bvd_live_shape_defaults,
    preferred_share,
)


def _write_agent(run_dir: Path, gen: int, agent_id: int, *, trait: str, fitness: float) -> None:
    agent = run_dir / f"gen_{gen}" / f"agent_{agent_id}"
    agent.mkdir(parents=True, exist_ok=True)
    (agent / "agent_dna.json").write_text(
        json.dumps(
            {
                "planning_style": trait,
                "reflection": True,
                "tool_strategy": "selective",
                "retry_policy": "generic",
                "memory": "short_summary",
                "confidence_threshold": 0.75,
                "prompt_structure": "detailed",
                "technique_seeds": [],
            }
        ),
        encoding="utf-8",
    )
    (agent / "results.json").write_text(
        json.dumps({"accuracy": fitness, "eval_subset": 3}),
        encoding="utf-8",
    )


def test_offline_fig2_uses_primary_h2_field_not_memory(tmp_path: Path, monkeypatch):
    """Tick 362: offline Fig 2 must plot primary H2 (tool_strategy), not h2_memory."""
    from offline_bvd_case_study import _maybe_figures

    d_run = tmp_path / "run_d"
    d_run.mkdir()
    # summarize_run returns conflicting primary vs memory histograms — fig2 must
    # follow primary ``h2`` (tool_strategy), not legacy ``h2_memory``.
    fake = {
        "learning_curve": {
            "1": {"best": 0.2, "mean": 0.18},
            "2": {"best": 0.25, "mean": 0.22},
            "3": {"best": 0.31, "mean": 0.28},
        },
        "h2": {
            "field": "tool_strategy",
            "counts": {"selective": 9, "aggressive": 3},
            "in_bias_share": 1.0,
            "preferred_value": "selective",
            "preferred_share": 0.75,
        },
        "h2_field": "tool_strategy",
        "h2_memory": {
            "field": "memory",
            "counts": {"short_summary": 8, "none": 4},
            "in_bias_share": 0.1,
            "preferred_value": "short_summary",
            "preferred_share": 0.1,
        },
    }
    monkeypatch.setattr("offline_bvd_case_study.summarize_run", lambda _p: fake)

    captured: dict[str, object] = {}

    class _Ax:
        def bar(self, labels, vals, color=None):  # noqa: ANN001
            captured["labels"] = list(labels)
            captured["vals"] = list(vals)
            captured["color"] = color

        def plot(self, *a, **k):  # noqa: ANN001, ARG002
            return None

        def set_xlabel(self, *a, **k):  # noqa: ANN001, ARG002
            return None

        def set_ylabel(self, *a, **k):  # noqa: ANN001, ARG002
            return None

        def set_title(self, title, *a, **k):  # noqa: ANN001, ARG002
            captured["title"] = title

        def tick_params(self, *a, **k):  # noqa: ANN001, ARG002
            return None

        def grid(self, *a, **k):  # noqa: ANN001, ARG002
            return None

        def legend(self, *a, **k):  # noqa: ANN001, ARG002
            return None

    class _Fig:
        def tight_layout(self):
            return None

        def savefig(self, *a, **k):  # noqa: ANN001, ARG002
            return None

    class _Plt:
        @staticmethod
        def subplots(*a, **k):  # noqa: ANN001, ARG002
            return _Fig(), _Ax()

        @staticmethod
        def close(*a, **k):  # noqa: ANN001, ARG002
            return None

    import types
    import sys

    fake_mpl = types.ModuleType("matplotlib")
    fake_mpl.use = lambda *a, **k: None  # noqa: ARG005
    fake_pyplot = _Plt()
    monkeypatch.setitem(sys.modules, "matplotlib", fake_mpl)
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", fake_pyplot)

    out = tmp_path / "figs"
    written = _maybe_figures([], [d_run], out)
    assert any("fig2_mechanism.png" in p for p in written)
    assert captured.get("labels") == ["selective", "aggressive"]
    assert "tool_strategy" in str(captured.get("title"))
    assert "memory" not in str(captured.get("title")).lower()
    # Tick 365: MECHANISM preferred allele annotated in title / bar colors.
    assert "prefer=selective" in str(captured.get("title"))
    assert "share=0.75" in str(captured.get("title"))
    colors = captured.get("color")
    assert colors is not None
    assert list(colors)[0] != list(colors)[1]


def test_offline_compare_brief_uses_preferred_share_not_in_bias():
    """Tick 365: D_h2_share is preferred_share (MECHANISM), not pool membership."""
    from offline_bvd_case_study import _brief_h2_fields

    # Mimic compare_rows_brief extraction without a full offline pilot.
    row = {
        "seed_idx": 0,
        "B": {"final_best": 0.2, "gens_to_25": 3, "gens_to_30": None, "cost_to_30": {}},
        "D": {
            "final_best": 0.3,
            "gens_to_25": 2,
            "gens_to_30": 3,
            "cost_to_30": {"cost": 40.0, "unit": "calls"},
            "h5": {"spearman_rho": 0.5, "pass": True, "fitness_key": "mean", "delta_horizon": 2},
            "h2": {
                "field": "tool_strategy",
                "preferred_value": "selective",
                "preferred_share": 0.25,
                "in_bias_share": 1.0,
            },
        },
    }
    brief = _brief_h2_fields(row["D"])
    assert brief["D_h2_share"] == 0.25
    assert brief["D_h2_in_bias_share"] == 1.0
    assert brief["D_h2_preferred"] == "selective"
    assert brief["D_h2_share"] != brief["D_h2_in_bias_share"]
    assert brief["D_h2_pass"] is False  # Tick 366: preferred < 0.5
    traits = [{"trait": "stepwise"}, {"trait": "direct"}, {"trait": "stepwise"}, {"trait": "hierarchical"}]
    assert preferred_share(traits, "stepwise") == 0.5
    assert preferred_share([], "stepwise") is None


def test_offline_compare_brief_emits_h2_pass():
    """Tick 366: D_h2_pass follows preferred_share ≥ 0.5 (not in_bias_share)."""
    from offline_bvd_case_study import _brief_h2_fields

    win = _brief_h2_fields(
        {
            "h2": {
                "field": "tool_strategy",
                "preferred_value": "selective",
                "preferred_share": 0.75,
                "in_bias_share": 1.0,
            }
        }
    )
    lose = _brief_h2_fields(
        {
            "h2": {
                "field": "tool_strategy",
                "preferred_value": "selective",
                "preferred_share": 0.29,
                "in_bias_share": 1.0,
            }
        }
    )
    assert win["D_h2_pass"] is True
    assert lose["D_h2_pass"] is False
    # Committed offline summary must advertise aggregate preferred-pass.
    summary = json.loads((REPO / "docs" / "offline_bvd_summary.json").read_text())
    cmp = summary["compare"]
    assert cmp.get("d_wins_h2") == 4
    assert cmp.get("h2_preferred_pass") is True
    passes = [bool(r.get("D_h2_pass")) for r in summary["compare_rows_brief"]]
    assert passes == [True, False, True, True, True]

def test_offline_bvd_defaults_match_live_shape():
    """Tick 304: CLI defaults must track icml_g3g4_live_shape(), not hardcoded ints."""
    expected = icml_g3g4_live_shape()
    defaults = offline_bvd_live_shape_defaults()
    assert defaults == {
        "eval_subset": int(expected["eval_subset"]),
        "population_size": int(expected["population_size"]),
        "elite_count": int(expected["elite_count"]),
        "max_gen": int(expected["max_gen"]),
    }
    ok, got, exp = args_match_live_shape(
        pop=defaults["population_size"],
        elite=defaults["elite_count"],
        max_gen=defaults["max_gen"],
        eval_subset=defaults["eval_subset"],
    )
    assert ok and got == exp == expected


def test_offline_bvd_refuses_divergent_shape_without_override(capsys):
    """Tick 304: refuse writing offline PRIMARY tables at non-live shape."""
    live = icml_g3g4_live_shape()
    bad_eval = int(live["eval_subset"]) + 1
    rc = offline_bvd_main(
        [
            "--seeds",
            "11",
            "--eval-subset",
            str(bad_eval),
            "--pop",
            str(live["population_size"]),
            "--elite",
            str(live["elite_count"]),
            "--max-gen",
            str(live["max_gen"]),
        ]
    )
    assert rc == 3
    err = capsys.readouterr().err
    assert "!= live" in err
    assert "--allow-shape-override" in err


def test_extract_case_study_measures_post_steering_skew(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run_1833"
    store = run_dir / "belief_store"
    store.mkdir(parents=True)

    # Gen1: contradiction sides present; gen2 fair (low preferred); gen3 steered (high preferred).
    _write_agent(run_dir, 1, 0, trait="direct", fitness=0.17)
    _write_agent(run_dir, 1, 1, trait="stepwise", fitness=0.22)
    _write_agent(run_dir, 1, 2, trait="hierarchical", fitness=0.26)
    _write_agent(run_dir, 1, 3, trait="direct", fitness=0.18)

    _write_agent(run_dir, 2, 0, trait="direct", fitness=0.20)
    _write_agent(run_dir, 2, 1, trait="hierarchical", fitness=0.27)
    _write_agent(run_dir, 2, 2, trait="hierarchical", fitness=0.25)
    _write_agent(run_dir, 2, 3, trait="stepwise", fitness=0.24)  # share 0.25

    _write_agent(run_dir, 3, 0, trait="stepwise", fitness=0.30)
    _write_agent(run_dir, 3, 1, trait="stepwise", fitness=0.31)
    _write_agent(run_dir, 3, 2, trait="stepwise", fitness=0.29)
    _write_agent(run_dir, 3, 3, trait="direct", fitness=0.21)  # share 0.75

    (store / "contradictions.json").write_text(
        json.dumps(
            {
                "contradictions": [
                    {
                        "topic": "planning",
                        "belief_a": "Agent 1: planning_style=stepwise achieved fitness 0.22",
                        "belief_b": "Agent 0: planning_style=direct achieved fitness 0.17",
                        "priority": 0.9,
                        "status": "open",
                        "metadata": {"agents": [1, 0]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (store / "beliefs.json").write_text(json.dumps({"beliefs": []}), encoding="utf-8")
    (store / "research_questions.json").write_text(
        json.dumps({"research_questions": []}), encoding="utf-8"
    )

    monkeypatch.setattr(
        "offline_bvd_case_study.load_mutation_bias",
        lambda _run: {"planning_style": ["stepwise", "direct"]},
    )

    case = extract_case_study(run_dir)
    assert case is not None
    assert case["first_steered_gen"] == FIRST_STEERED_GEN == 3
    assert case["steered_gen"] == 3
    assert case["gen2_preferred_share"] == 0.25
    assert case["steered_preferred_share"] == 0.75
    assert case["preferred_share_by_gen"]["2"] == 0.25
    assert case["preferred_share_by_gen"]["3"] == 0.75
    # Lift uses steered preferred mean vs gen1 loser mean.
    assert case["fitness_lift"] is not None
    assert case["fitness_lift"] > 0
