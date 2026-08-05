# Offline case study — Condition D mechanism chain

**Status:** offline dry-run evidence (synthetic GPQA fixture; additive latent DNA fitness). Does **not** satisfy live PRIMARY. Supports MECHANISM case-study criterion.

**Run:** `runs/run_1743`

## Chain

1. **Tie / disagreement:** population agents hold opposing DNA-linked beliefs.
2. **Contradiction:** topic `planning` — 'Agent 1: planning_style=stepwise achieved fitness 0.2199 (population mean 0.2083)' vs 'Agent 0: planning_style=direct achieved fitness 0.1725 (population mean 0.2083)' (priority=0.85).
3. **Fitness-weighted bias:** field `planning_style` ordered `['stepwise', 'direct']` (prefer `stepwise`).
4. **DNA skew:** gen2 share of preferred trait = 0.25.
5. **Fitness lift:** preferred@gen2 mean − loser@gen1 mean = **+0.0869** (pop mean 0.20834999999999998 → 0.26385000000000003).

DNA fitness transferability check: `True` (same DNA ⇒ same score across agent_id/gen).

## Offline B vs D summary (synthetic; not PRIMARY)

```json
{
  "n_pairs": 5,
  "d_wins_gens25": 0,
  "b_wins_gens25": 0,
  "d_wins_gens30": 3,
  "b_wins_gens30": 0,
  "d_wins_final": 5,
  "b_wins_final": 0,
  "primary_gens25_pass": false,
  "primary_gens30_pass": true
}
```

## Raw case payload

```json
{
  "run_dir": "runs/run_1743",
  "field": "planning_style",
  "preferred_value": "stepwise",
  "bias_order": [
    "stepwise",
    "direct"
  ],
  "contradiction": {
    "topic": "planning",
    "belief_a": "Agent 1: planning_style=stepwise achieved fitness 0.2199 (population mean 0.2083)",
    "belief_b": "Agent 0: planning_style=direct achieved fitness 0.1725 (population mean 0.2083)",
    "priority": 0.85,
    "agents": [
      1,
      0
    ]
  },
  "gen1_traits": [
    {
      "agent_id": 0,
      "trait": "direct",
      "fitness": 0.1725
    },
    {
      "agent_id": 1,
      "trait": "stepwise",
      "fitness": 0.2199
    },
    {
      "agent_id": 2,
      "trait": "hierarchical",
      "fitness": 0.2653
    },
    {
      "agent_id": 3,
      "trait": "direct",
      "fitness": 0.1757
    }
  ],
  "gen2_traits": [
    {
      "agent_id": 0,
      "trait": "direct",
      "fitness": 0.3016
    },
    {
      "agent_id": 1,
      "trait": "hierarchical",
      "fitness": 0.3063
    },
    {
      "agent_id": 2,
      "trait": "hierarchical",
      "fitness": 0.1865
    },
    {
      "agent_id": 3,
      "trait": "stepwise",
      "fitness": 0.261
    }
  ],
  "gen1_preferred_mean_fitness": 0.2199,
  "gen1_loser_mean_fitness": 0.17409999999999998,
  "gen2_preferred_mean_fitness": 0.261,
  "gen1_pop_mean": 0.20834999999999998,
  "gen2_pop_mean": 0.26385000000000003,
  "fitness_lift": 0.08690000000000003,
  "gen2_preferred_share": 0.25,
  "dna_fitness_transfers": true,
  "belief_count": 15,
  "agenda_prefers_first": "stepwise"
}
```
