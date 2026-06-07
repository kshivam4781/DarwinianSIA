"""Design experiments that resolve open research questions."""

from __future__ import annotations

from typing import Any


def plan_experiments(question: dict) -> list[dict[str, Any]]:
    """Create a small factorial experiment plan for a research question."""
    topic = _topic_from_question(question.get("question", ""))
    hidden_vars = question.get("hidden_variables") or ["task_complexity"]
    experiments: list[dict[str, Any]] = []

    if topic in {"memory", "reflection", "planning", "tool_use"}:
        experiments.extend(
            [
                {
                    "name": f"{topic}_on_easy_tasks",
                    "variable": topic,
                    "setting": "enabled",
                    "slice": "easy",
                    "metric": "accuracy_delta",
                },
                {
                    "name": f"{topic}_off_easy_tasks",
                    "variable": topic,
                    "setting": "disabled",
                    "slice": "easy",
                    "metric": "accuracy_delta",
                },
                {
                    "name": f"{topic}_on_hard_tasks",
                    "variable": topic,
                    "setting": "enabled",
                    "slice": "hard",
                    "metric": "accuracy_delta",
                },
                {
                    "name": f"{topic}_off_hard_tasks",
                    "variable": topic,
                    "setting": "disabled",
                    "slice": "hard",
                    "metric": "accuracy_delta",
                },
            ]
        )
    else:
        experiments.extend(
            [
                {
                    "name": f"{topic}_variant_a",
                    "variable": topic,
                    "setting": "baseline",
                    "slice": "all",
                    "metric": "primary_score",
                },
                {
                    "name": f"{topic}_variant_b",
                    "variable": topic,
                    "setting": "alternative",
                    "slice": "all",
                    "metric": "primary_score",
                },
            ]
        )

    for hidden in hidden_vars[:2]:
        experiments.append(
            {
                "name": f"control_for_{hidden}",
                "variable": hidden,
                "setting": "stratified",
                "slice": "all",
                "metric": "uncertainty_reduction",
            }
        )
    return experiments


def _topic_from_question(question: str) -> str:
    lowered = question.lower()
    for topic in ("memory", "reflection", "planning", "tool_use", "prompting", "error_handling"):
        if topic.replace("_", " ") in lowered or topic in lowered:
            return topic
    return "architecture"
