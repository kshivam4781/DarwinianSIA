"""Tests for Tavily grounding (mocked HTTP)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from cabs.belief_store import BeliefStore
from cabs.evidence_store import EvidenceStore
from cabs.tavily_client import TavilyClient, TavilySearchResult
from cabs.tavily_grounding import build_search_query, ground_open_questions


def test_build_search_query_strips_contradiction_clause():
    q = {
        "question": "When does memory help? Contradiction: 'a' vs 'b'.",
        "topic": "memory",
    }
    assert "Contradiction" not in build_search_query(q)


def test_tavily_client_parses_response():
    fake_response = json.dumps(
        {
            "answer": "Memory can help on hard tasks.",
            "results": [
                {"title": "Paper", "url": "https://example.com", "content": "snippet", "score": 0.9}
            ],
        }
    ).encode("utf-8")

    mock_http = MagicMock()
    mock_http.read.return_value = fake_response
    mock_http.__enter__.return_value = mock_http

    with patch("cabs.tavily_client.urllib.request.urlopen", return_value=mock_http):
        result = TavilyClient(api_key="tvly-test").search("memory in AI agents")

    assert result.answer == "Memory can help on hard tasks."
    assert len(result.results) == 1


def test_ground_open_questions_saves_evidence(tmp_path):
    store_root = tmp_path / "belief_store"
    store = BeliefStore(store_root)
    store.append_research_questions(
        [
            {
                "id": "rq_test",
                "question": "When does memory help versus hurt?",
                "topic": "memory",
                "contradiction_id": "c1",
                "status": "open",
                "priority": 0.8,
            }
        ]
    )
    store.append_beliefs(
        [
            {
                "id": "b1",
                "belief": "Memory helps",
                "topic": "memory",
                "polarity": "positive",
                "confidence": 0.7,
                "generation": 1,
                "status": "active",
            }
        ]
    )

    mock_client = MagicMock(spec=TavilyClient)
    mock_client.configured = True
    mock_client.search.return_value = TavilySearchResult(
        query="q",
        answer="External summary",
        results=[{"title": "T", "url": "u", "content": "c", "score": 0.5}],
    )

    summary = ground_open_questions(
        str(store_root),
        generation=2,
        max_calls=5,
        client=mock_client,
    )

    assert summary["enabled"] is True
    assert len(summary["grounded"]) == 1
    evidence = EvidenceStore(store_root).load_for_question("rq_test")
    assert evidence is not None
    assert evidence["answer"] == "External summary"
    beliefs = store.load_beliefs()
    assert float(beliefs[0]["confidence"]) > 0.7


def test_ground_respects_max_calls(tmp_path):
    store_root = tmp_path / "belief_store"
    store = BeliefStore(store_root)
    for i in range(3):
        store.append_research_questions(
            [
                {
                    "id": f"rq_{i}",
                    "question": f"When does memory help case {i}?",
                    "topic": "memory",
                    "contradiction_id": f"c{i}",
                    "status": "open",
                    "priority": 0.5,
                }
            ]
        )

    mock_client = MagicMock(spec=TavilyClient)
    mock_client.configured = True
    mock_client.search.return_value = TavilySearchResult(query="q", answer="a", results=[])

    summary = ground_open_questions(
        str(store_root),
        generation=1,
        max_calls=2,
        client=mock_client,
    )

    assert summary["calls_total"] <= 2
    assert mock_client.search.call_count <= 2
