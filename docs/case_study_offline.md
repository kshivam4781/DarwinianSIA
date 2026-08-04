# Offline case study — Condition D mechanism chain

**Status:** offline dry-run evidence (synthetic GPQA fixture; DNA-hash fitness). Does **not** satisfy live PRIMARY. Supports MECHANISM case-study criterion.

**Run:** `/workspace/runs/run_1420`

## Chain

1. **Tie / disagreement:** population agents hold opposing DNA-linked beliefs.
2. **Contradiction:** topic `tool_use` — 'Agent 0: tool_strategy=selective achieved fitness 0.5234 (population mean 0.3932)' vs 'Agent 1: tool_strategy=aggressive achieved fitness 0.1640 (population mean 0.3932)' (priority=0.85).
3. **Fitness-weighted bias:** field `tool_strategy` ordered `['selective', 'aggressive']` (prefer `selective`).
4. **DNA skew:** gen2 share of preferred trait = 0.75.
5. **Fitness lift:** preferred@gen2 mean − loser@gen1 mean = **+0.0853**. Cleanest artifact: gen2 `agent_2` kept `tool_strategy=selective` with fitness **0.5234** (identical to gen1 winner agent_0), vs gen1 loser `aggressive` at **0.1640** — lift **+0.3594** on the preserved winning genome. Population mean can still dip when other mutated traits hurt non-elite carriers (0.393 → 0.265).

DNA fitness transferability check: `True` (same DNA ⇒ same score across agent_id/gen).

## Offline B vs D summary (synthetic; not PRIMARY)

```json
{
  "n_pairs": 5,
  "d_wins_gens25": 0,
  "b_wins_gens25": 0,
  "d_wins_final": 4,
  "b_wins_final": 1,
  "primary_gens25_pass": false
}
```

## Raw case payload

```json
{
  "run_dir": "/workspace/runs/run_1420",
  "field": "tool_strategy",
  "preferred_value": "selective",
  "bias_order": [
    "selective",
    "aggressive"
  ],
  "contradiction": {
    "topic": "tool_use",
    "belief_a": "Agent 0: tool_strategy=selective achieved fitness 0.5234 (population mean 0.3932)",
    "belief_b": "Agent 1: tool_strategy=aggressive achieved fitness 0.1640 (population mean 0.3932)",
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
      "fitness": 0.5234
    },
    {
      "agent_id": 1,
      "trait": "aggressive",
      "fitness": 0.164
    },
    {
      "agent_id": 2,
      "trait": "minimal",
      "fitness": 0.3667
    },
    {
      "agent_id": 3,
      "trait": "minimal",
      "fitness": 0.5186
    }
  ],
  "gen2_traits": [
    {
      "agent_id": 0,
      "trait": "selective",
      "fitness": 0.1331
    },
    {
      "agent_id": 1,
      "trait": "aggressive",
      "fitness": 0.311
    },
    {
      "agent_id": 2,
      "trait": "selective",
      "fitness": 0.5234
    },
    {
      "agent_id": 3,
      "trait": "selective",
      "fitness": 0.0913
    }
  ],
  "gen1_preferred_mean_fitness": 0.5234,
  "gen1_loser_mean_fitness": 0.164,
  "gen2_preferred_mean_fitness": 0.24926666666666666,
  "gen1_pop_mean": 0.393175,
  "gen2_pop_mean": 0.2647,
  "fitness_lift": 0.08526666666666666,
  "gen2_preferred_share": 0.75,
  "dna_fitness_transfers": true,
  "belief_count": 16,
  "agenda_prefers_first": "selective"
}
```
