"""DNA-aware prompt sections for darwinian evolution."""

from __future__ import annotations

import json

from sia.evolution.dna import AgentDNA


def _gpqa_harness_constraints() -> str:
    """Benchmark-specific guardrails so evolved agents remain scorable."""
    return """
## CRITICAL: GPQA Evaluation Requirements

Fitness = `accuracy` in `results.json` (fraction of questions answered A–D correctly).

**Preserve from the reference `target_agent.py`:**
1. Nebius OpenAI client calling `moonshotai/Kimi-K2.6` with `NEBIUS_API_KEY`.
2. User prompt ending with: `Respond with ONLY a JSON object: {"answer": "A"}` (A, B, C, or D).
3. Robust answer parsing (JSON regex + letter fallback) — never leave `model_answer` empty if the API returned text.
4. Async batch inference with `tqdm`; write `results/submission.json`.

**DO NOT:**
- Withhold or skip answers when confidence is below the DNA threshold (log confidence only).
- Use unsupported structured-output / pydantic response modes that return empty content.
- Replace the API call pipeline with planning-only stubs that never call the model.

Implement DNA traits as *lightweight* control-flow differences (retry loops, reflection logs,
small memory dicts) on top of the working reference inference pipeline.
"""


def dna_architecture_section(dna: AgentDNA) -> str:
    """Prompt block instructing the meta/feedback agent to implement this DNA."""
    return f"""
## AGENT DNA (Architectural Genotype)

You MUST implement a target agent whose architecture reflects this DNA genotype.
The DNA describes *how* the agent solves tasks, not just prompt wording.

```json
{json.dumps(dna.__dict__, indent=2)}
```

### DNA Implementation Guide

**Planning style: {dna.planning_style}**
- `stepwise`: Break the task into explicit sequential steps before acting.
- `direct`: Solve in one pass with minimal intermediate planning.
- `hierarchical`: Decompose into sub-goals, solve each, then synthesize.

**Self-reflection: {'ON' if dna.reflection else 'OFF'}**
- If ON: After each major action, critique the result and adjust before continuing.
- If OFF: Execute without self-critique loops.

**Tool strategy: {dna.tool_strategy}**
- `aggressive`: Use tools liberally; prefer tool calls over pure reasoning.
- `selective`: Use tools only when clearly beneficial.
- `minimal`: Avoid tools unless absolutely necessary.

**Retry policy: {dna.retry_policy}**
- `none`: Fail fast on errors.
- `generic`: Retry once on any error.
- `error_specific`: Retry with different strategies based on error type.

**Memory mode: {dna.memory}**
- `none`: No cross-sample memory.
- `short_summary`: Keep a brief running summary of progress.
- `failure_based`: Remember and avoid repeated failure patterns.
- `full_history`: Retain complete conversation history.

**Confidence threshold: {dna.confidence_threshold}**
- Log confidence scores; optionally retry once if below threshold.
- Always submit the best available A–D answer after retries (never block scoring).

**Prompt structure: {dna.prompt_structure}**
- `minimal`: Short system prompt, concise instructions.
- `detailed`: Rich instructions with examples and edge cases.
- `chain_of_thought`: Explicit reasoning traces before each action.
{_technique_seeds_section(dna)}

Implement these traits as structural code patterns (control flow, retry loops,
memory buffers, tool selection logic) — not just prompt text changes.
"""


def _technique_seeds_section(dna: AgentDNA) -> str:
    if not dna.technique_seeds:
        return ""
    seeds = ", ".join(f"`{s}`" for s in dna.technique_seeds)
    return f"""
**Technique seeds (committee-approved): {seeds}**
- Feedback MUST implement each seed as concrete code in `target_agent.py`.
- Seeds are mandatory architectural changes, not optional prompt tweaks.
"""


def darwinian_meta_addon(dna: AgentDNA, agent_id: int, population_size: int) -> str:
    """Additional context for meta-agent when creating a population member."""
    return f"""
## Darwinian Population Context

You are creating agent {agent_id + 1} of {population_size} in generation 1.
Each agent has unique DNA encoding different architectural strategies.
Your agent will compete against others on the benchmark; only the fittest survive.

{_gpqa_harness_constraints()}
{dna_architecture_section(dna)}
"""


def cabs_feedback_addon(cabs_agenda: str) -> str:
    """Prepend CABS research agenda to Darwinian feedback prompts (Phase 7 / Section 20.3)."""
    if not cabs_agenda.strip():
        return ""
    return cabs_agenda


def darwinian_feedback_addon(
    dna: AgentDNA,
    parent_dnas: list[AgentDNA],
    parent_fitnesses: list[float],
    agent_id: int,
    population_size: int,
    civilization_insights: str = "",
) -> str:
    """Additional context for feedback-agent when breeding offspring."""
    parent_summary = "\n".join(
        f"- Parent {i + 1}: fitness={fit:.4f}, DNA={json.dumps(asdict_safe(p))}"
        for i, (p, fit) in enumerate(zip(parent_dnas, parent_fitnesses, strict=False))
    )
    civ_section = f"\n### Civilization Memory\n{civilization_insights}\n" if civilization_insights else ""
    return f"""
## Darwinian Evolution Context

You are creating offspring agent {agent_id + 1} of {population_size} for the next generation.
This agent inherits traits from the fittest parents via crossover and mutation.

### Parent Lineage
{parent_summary}

{_gpqa_harness_constraints()}
{dna_architecture_section(dna)}
{civ_section}
Adapt the parent agent's code to fully implement the offspring DNA above.
Preserve what worked in the parent code while restructuring to match the new genotype.
If parent fitness was 0, simplify toward the reference agent's working API + JSON answer pattern first.
"""


def asdict_safe(dna: AgentDNA) -> dict:
    return {
        "planning_style": dna.planning_style,
        "reflection": dna.reflection,
        "tool_strategy": dna.tool_strategy,
        "retry_policy": dna.retry_policy,
        "memory": dna.memory,
        "confidence_threshold": dna.confidence_threshold,
        "prompt_structure": dna.prompt_structure,
        "technique_seeds": list(dna.technique_seeds or []),
    }
