# Offline case study — Condition D mechanism chain

**Status:** offline dry-run evidence (synthetic GPQA fixture; additive latent DNA fitness). Does **not** satisfy live PRIMARY. Supports MECHANISM case-study criterion.

**Run:** `runs/run_1900`

## Chain

1. **Tie / disagreement:** population agents hold opposing DNA-linked beliefs.
2. **Contradiction:** topic `tool_use` — 'Agent 0: tool_strategy=selective achieved fitness 0.2567 (population mean 0.2267)' vs 'Agent 1: tool_strategy=aggressive achieved fitness 0.2191 (population mean 0.2267)' (priority=0.85).
3. **Fitness-weighted bias:** field `tool_strategy` ordered `['selective', 'minimal', 'aggressive']` (prefer `selective`).
4. **DNA skew (post-steering):** preferred share by gen = gen1=0.25, gen2=0.5, gen3=0.75, gen4=1.0, gen5=1.0, gen6=0.75. Delay-all keeps gen1→gen2 fair; first steered generation is gen3 (steered share **0.75** at gen3; pre-steer/gen2 share 0.5).
5. **Fitness lift:** preferred@gen3 mean − loser@gen1 mean = **+0.0436** (pop mean 0.226725 → 0.24957500000000002).

DNA fitness transferability check: `True` (same DNA ⇒ same score across agent_id/gen).

## Offline B vs D summary (synthetic; not PRIMARY)

```json
{
  "n_pairs": 5,
  "d_wins_gens25": 0,
  "b_wins_gens25": 0,
  "d_wins_gens30": 4,
  "b_wins_gens30": 0,
  "d_wins_cost25": 0,
  "b_wins_cost25": 0,
  "d_wins_cost30": 4,
  "b_wins_cost30": 0,
  "d_wins_final": 5,
  "b_wins_final": 0,
  "mean_final_b": 0.2526,
  "mean_final_d": 0.3141,
  "mean_final_gap": 0.0615,
  "primary_gens25_pass": false,
  "primary_gens30_pass": true,
  "primary_cost25_pass": false,
  "primary_cost30_pass": true,
  "primary_final_pass": true
}
```

## Raw case payload

```json
{
  "run_dir": "runs/run_1900",
  "field": "tool_strategy",
  "preferred_value": "selective",
  "bias_order": [
    "selective",
    "minimal",
    "aggressive"
  ],
  "first_steered_gen": 3,
  "steered_gen": 3,
  "contradiction": {
    "topic": "tool_use",
    "belief_a": "Agent 0: tool_strategy=selective achieved fitness 0.2567 (population mean 0.2267)",
    "belief_b": "Agent 1: tool_strategy=aggressive achieved fitness 0.2191 (population mean 0.2267)",
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
      "fitness": 0.2567
    },
    {
      "agent_id": 1,
      "trait": "aggressive",
      "fitness": 0.2191
    },
    {
      "agent_id": 2,
      "trait": "minimal",
      "fitness": 0.2539
    },
    {
      "agent_id": 3,
      "trait": "minimal",
      "fitness": 0.1772
    }
  ],
  "gen2_traits": [
    {
      "agent_id": 0,
      "trait": "minimal",
      "fitness": 0.1949
    },
    {
      "agent_id": 1,
      "trait": "selective",
      "fitness": 0.2829
    },
    {
      "agent_id": 2,
      "trait": "selective",
      "fitness": 0.2393
    },
    {
      "agent_id": 3,
      "trait": "aggressive",
      "fitness": 0.2263
    }
  ],
  "steered_traits": [
    {
      "agent_id": 0,
      "trait": "selective",
      "fitness": 0.2494
    },
    {
      "agent_id": 1,
      "trait": "selective",
      "fitness": 0.2757
    },
    {
      "agent_id": 2,
      "trait": "minimal",
      "fitness": 0.2209
    },
    {
      "agent_id": 3,
      "trait": "selective",
      "fitness": 0.2523
    }
  ],
  "traits_by_gen": {
    "1": [
      {
        "agent_id": 0,
        "trait": "selective",
        "fitness": 0.2567
      },
      {
        "agent_id": 1,
        "trait": "aggressive",
        "fitness": 0.2191
      },
      {
        "agent_id": 2,
        "trait": "minimal",
        "fitness": 0.2539
      },
      {
        "agent_id": 3,
        "trait": "minimal",
        "fitness": 0.1772
      }
    ],
    "2": [
      {
        "agent_id": 0,
        "trait": "minimal",
        "fitness": 0.1949
      },
      {
        "agent_id": 1,
        "trait": "selective",
        "fitness": 0.2829
      },
      {
        "agent_id": 2,
        "trait": "selective",
        "fitness": 0.2393
      },
      {
        "agent_id": 3,
        "trait": "aggressive",
        "fitness": 0.2263
      }
    ],
    "3": [
      {
        "agent_id": 0,
        "trait": "selective",
        "fitness": 0.2494
      },
      {
        "agent_id": 1,
        "trait": "selective",
        "fitness": 0.2757
      },
      {
        "agent_id": 2,
        "trait": "minimal",
        "fitness": 0.2209
      },
      {
        "agent_id": 3,
        "trait": "selective",
        "fitness": 0.2523
      }
    ],
    "4": [
      {
        "agent_id": 0,
        "trait": "selective",
        "fitness": 0.2607
      },
      {
        "agent_id": 1,
        "trait": "selective",
        "fitness": 0.301
      },
      {
        "agent_id": 2,
        "trait": "selective",
        "fitness": 0.2673
      },
      {
        "agent_id": 3,
        "trait": "selective",
        "fitness": 0.292
      }
    ],
    "5": [
      {
        "agent_id": 0,
        "trait": "selective",
        "fitness": 0.2842
      },
      {
        "agent_id": 1,
        "trait": "selective",
        "fitness": 0.273
      },
      {
        "agent_id": 2,
        "trait": "selective",
        "fitness": 0.2539
      },
      {
        "agent_id": 3,
        "trait": "selective",
        "fitness": 0.23
      }
    ],
    "6": [
      {
        "agent_id": 0,
        "trait": "selective",
        "fitness": 0.3035
      },
      {
        "agent_id": 1,
        "trait": "selective",
        "fitness": 0.3017
      },
      {
        "agent_id": 2,
        "trait": "selective",
        "fitness": 0.2873
      },
      {
        "agent_id": 3,
        "trait": "minimal",
        "fitness": 0.2495
      }
    ]
  },
  "preferred_share_by_gen": {
    "1": 0.25,
    "2": 0.5,
    "3": 0.75,
    "4": 1.0,
    "5": 1.0,
    "6": 0.75
  },
  "gen1_preferred_mean_fitness": 0.2567,
  "gen1_loser_mean_fitness": 0.21555000000000002,
  "gen2_preferred_mean_fitness": 0.2611,
  "steered_preferred_mean_fitness": 0.2591333333333334,
  "gen1_pop_mean": 0.226725,
  "gen2_pop_mean": 0.23585,
  "steered_pop_mean": 0.24957500000000002,
  "fitness_lift": 0.04358333333333336,
  "gen2_preferred_share": 0.5,
  "pre_steer_preferred_share": 0.5,
  "steered_preferred_share": 0.75,
  "dna_fitness_transfers": true,
  "belief_count": 15,
  "agenda_prefers_first": "selective"
}
```
