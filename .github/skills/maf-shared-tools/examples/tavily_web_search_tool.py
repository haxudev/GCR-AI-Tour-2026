#!/usr/bin/env python3
"""Tavily web search tool (optional, skill example).

Dependency (optional):
- pip install tavily-python

Env:
- TAVILY_API_KEY
"""

from __future__ import annotations

import os
from typing import Any


def _lazy_import_tavily_client():
    try:
        from tavily import TavilyClient  # type: ignore

        return TavilyClient
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Tavily client not available. Install `tavily-python`.") from exc


def tavily_web_search(
    query: str,
    max_results: int = 5,
    include_answer: bool = False,
    include_raw_content: bool = False,
    search_depth: str = "basic",
    api_key: str | None = None,
) -> dict[str, Any]:
    key = api_key or os.getenv("TAVILY_API_KEY")
    if not key:
        return {"ok": False, "error": "Missing TAVILY_API_KEY. Set it in env/.env or pass api_key.", "query": query}

    TavilyClient = _lazy_import_tavily_client()
    client = TavilyClient(api_key=key)

    try:
        resp = client.search(
            query=query,
            max_results=int(max_results),
            include_answer=bool(include_answer),
            include_raw_content=bool(include_raw_content),
            search_depth=str(search_depth),
        )
        return {"ok": True, "query": query, "response": resp}
    except Exception as exc:
        return {"ok": False, "query": query, "error": str(exc)}


def register_tools(registry: object) -> None:
    register = getattr(registry, "register_tool", None)
    if not callable(register):
        return

    register("web.tavily_search", tavily_web_search)
