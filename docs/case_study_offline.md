# Offline case study — Condition D mechanism chain

**Status:** offline dry-run evidence (synthetic GPQA fixture; additive latent DNA fitness). Does **not** satisfy live PRIMARY. Supports MECHANISM case-study criterion.

**Run:** `/workspace/runs/run_1620`

## Chain

1. **Tie / disagreement:** population agents hold opposing DNA-linked beliefs.
2. **Contradiction:** topic `tool_use` — 'Agent 0: tool_strategy=selective achieved fitness 0.2863 (population mean 0.2525)' vs 'Agent 1: tool_strategy=aggressive achieved fitness 0.2439 (population mean 0.2525)' (priority=0.85).
3. **Fitness-weighted bias:** field `tool_strategy` ordered `['selective', 'aggressive']` (prefer `selective`).
4. **DNA skew:** gen2 share of preferred trait = 0.5.
5. **Fitness lift:** preferred@gen2 mean − loser@gen1 mean = **+0.0473** (pop mean 0.252525 → 0.2628).

DNA fitness transferability check: `True` (same DNA ⇒ same score across agent_id/gen).

## Offline B vs D summary (synthetic; not PRIMARY)

```json
{
  "n_pairs": 5,
  "d_wins_gens25": 0,
  "b_wins_gens25": 0,
  "d_wins_gens30": 0,
  "b_wins_gens30": 1,
  "d_wins_final": 4,
  "b_wins_final": 1,
  "primary_gens25_pass": false,
  "primary_gens30_pass": false
}
```

## Raw case payload

```json
{
  "run_dir": "/workspace/runs/run_1620",
  "field": "tool_strategy",
  "preferred_value": "selective",
  "bias_order": [
    "selective",
    "aggressive"
  ],
  "contradiction": {
    "topic": "tool_use",
    "belief_a": "Agent 0: tool_strategy=selective achieved fitness 0.2863 (population mean 0.2525)",
    "belief_b": "Agent 1: tool_strategy=aggressive achieved fitness 0.2439 (population mean 0.2525)",
    "priority": 0.85,
    "agents": [
      0,
      1
    ]
  },
  "gen1_traits": [
    {
      "agent_id": 0,
      "trait": "selective",
      "fitness": 0.2863
    },
    {
      "agent_id": 1,
      "trait": "aggressive",
      "fitness": 0.2439
    },
    {
      "agent_id": 2,
      "trait": "minimal",
      "fitness": 0.2831
    },
    {
      "agent_id": 3,
      "trait": "minimal",
      "fitness": 0.1968
    }
  ],
  "gen2_traits": [
    {
      "agent_id": 0,
      "trait": "minimal",
      "fitness": 0.2167
    },
    {
      "agent_id": 1,
      "trait": "selective",
      "fitness": 0.3157
    },
    {
      "agent_id": 2,
      "trait": "selective",
      "fitness": 0.2667
    },
    {
      "agent_id": 3,
      "trait": "aggressive",
      "fitness": 0.2521
    }
  ],
  "gen1_preferred_mean_fitness": 0.2863,
  "gen1_loser_mean_fitness": 0.2439,
  "gen2_preferred_mean_fitness": 0.2912,
  "gen1_pop_mean": 0.252525,
  "gen2_pop_mean": 0.2628,
  "fitness_lift": 0.04730000000000001,
  "gen2_preferred_share": 0.5,
  "dna_fitness_transfers": true,
  "belief_count": 15,
  "agenda_prefers_first": "selective"
}
```
