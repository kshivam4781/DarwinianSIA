"""Extra prompt sections injected into SIA meta/feedback agents by sia-cabs."""

from __future__ import annotations

FEEDBACK_BELIEFS_INSTRUCTION = """
## CABS REQUIRED OUTPUT: beliefs.json

In addition to improvement.md and target_agent.py, you MUST write a structured belief file:

**Path:** `{next_gen_dir}/beliefs.json`

**Schema:**
```json
{{
  "schema_version": "1.0",
  "generation_learned_from": {current_gen},
  "beliefs": [
    {{
      "belief": "One sentence hypothesis about what helps or hurts",
      "topic": "memory|reflection|planning|tool_use|prompting|error_handling|model_choice",
      "polarity": "positive|negative",
      "confidence": 0.0
    }}
  ]
}}
```

Rules:
- Include 2-5 beliefs based on evaluation results and execution logs.
- Each belief must state what helped OR what hurt (polarity required).
- Topics must match the schema enum values above.
- Do not repeat generic scaffold observations; cite observed behavior from this generation.
"""


def feedback_beliefs_instruction(current_gen: int, next_gen_dir: str) -> str:
    return FEEDBACK_BELIEFS_INSTRUCTION.format(
        current_gen=current_gen,
        next_gen_dir=next_gen_dir,
    )


LONGCOT_CHESS_META_HINT = """
## CABS CRITICAL: longcot-chess output format

When writing target_agent.py for longcot-chess, ensure the evaluator can parse answers:

1. **responses.json** must be written to the generation working directory.
2. Each answer must appear in model output as a final line: `solution = ["move1", "move2", "move3"]` or `solution = <integer>`.
3. **Thinking/reasoning models:** if using Qwen Thinking or similar, read the FULL completion —
   content may be in `message.content` OR a reasoning field. Never save empty `model_response` when tokens were consumed.
4. Reserve completion tokens for the final `solution = ...` line (e.g. cap chain-of-thought, append answer at end).
5. Prefer a model variant that returns visible `content`, or parse provider-specific reasoning fields.
6. Test extraction with regex: `solution\\s*=\\s*(.+)`
"""


def meta_task_hints(task_name: str) -> str:
    if task_name and "chess" in task_name.lower():
        return LONGCOT_CHESS_META_HINT
    return ""
