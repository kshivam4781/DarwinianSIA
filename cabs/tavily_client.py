"""Minimal Tavily Search API client (stdlib only)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
DEFAULT_MAX_RESULTS = 3
DEFAULT_SEARCH_DEPTH = "basic"


@dataclass
class TavilySearchResult:
    query: str
    answer: str | None
    results: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


class TavilyClient:
    """Thin wrapper around POST https://api.tavily.com/search."""

    def __init__(self, api_key: str | None = None):
        self.api_key = (api_key or os.getenv("TAVILY_API_KEY", "")).strip()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def search(
        self,
        query: str,
        *,
        max_results: int = DEFAULT_MAX_RESULTS,
        search_depth: str = DEFAULT_SEARCH_DEPTH,
        include_answer: bool = True,
    ) -> TavilySearchResult:
        if not self.configured:
            raise RuntimeError("TAVILY_API_KEY is not set")

        payload = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_answer": include_answer,
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            TAVILY_SEARCH_URL,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Tavily HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Tavily request failed: {exc}") from exc

        snippets = []
        for item in raw.get("results") or []:
            if not isinstance(item, dict):
                continue
            snippets.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": (item.get("content") or "")[:800],
                    "score": item.get("score"),
                }
            )

        return TavilySearchResult(
            query=query,
            answer=raw.get("answer"),
            results=snippets,
            raw=raw,
        )
