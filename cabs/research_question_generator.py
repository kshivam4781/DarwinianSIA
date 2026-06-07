"""Turn contradictions into prioritized research questions."""

from __future__ import annotations

from cabs.belief_store import ResearchQuestion
from cabs.dna_mapping import topic_to_dna_field

TOPIC_QUESTIONS: dict[str, str] = {
    "memory": "When does memory help versus hurt task performance?",
    "reflection": "When does reflection improve outcomes versus add overhead?",
    "planning": "When does planning depth help versus cause timeouts or errors?",
    "tool_use": "When does tool use improve accuracy versus introduce failure modes?",
    "prompting": "Which prompt structures generalize versus overfit this benchmark?",
    "error_handling": "Which error-handling strategies recover failures versus mask root causes?",
    "model_choice": "Which model settings trade off accuracy, cost, and stability?",
    "data_quality": "When does data preprocessing help versus remove useful signal?",
}

TOPIC_HIDDEN_VARIABLES: dict[str, list[str]] = {
    "memory": ["task_complexity", "context_length", "example_difficulty"],
    "reflection": ["task_complexity", "latency_budget", "failure_rate"],
    "planning": ["task_complexity", "planning_depth", "timeout_risk"],
    "tool_use": ["tool_reliability", "query_difficulty", "search_depth"],
    "prompting": ["task_type", "prompt_length", "instruction_specificity"],
    "error_handling": ["failure_type", "retry_budget", "error_frequency"],
    "model_choice": ["model_size", "temperature", "task_difficulty"],
    "data_quality": ["noise_level", "dataset_size", "label_quality"],
}


def generate_research_questions(
    contradictions: list[dict],
    existing: list[dict] | None = None,
) -> list[ResearchQuestion]:
    existing = existing or []
    existing_contradiction_ids = {q.get("contradiction_id") for q in existing if q.get("status") == "open"}

    questions: list[ResearchQuestion] = []
    for contradiction in contradictions:
        if contradiction["id"] in existing_contradiction_ids:
            continue
        topic = contradiction.get("topic", "unknown")
        template = TOPIC_QUESTIONS.get(topic, f"When does {topic} help versus hurt performance?")
        question_text = (
            f"{template} Contradiction: '{contradiction['belief_a']}' vs '{contradiction['belief_b']}'."
        )
        questions.append(
            ResearchQuestion(
                question=question_text,
                contradiction_id=contradiction["id"],
                priority=float(contradiction.get("priority", 0.5)),
                topic=topic,
                dna_field=topic_to_dna_field(topic),
                hidden_variables=TOPIC_HIDDEN_VARIABLES.get(topic, ["task_complexity"]),
            )
        )
    return questions
