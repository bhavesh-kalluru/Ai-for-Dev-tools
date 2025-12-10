
import json
import logging
from typing import Any, Dict, List, Optional

import requests

from config import get_perplexity_api_key

logger = logging.getLogger(__name__)

PERPLEXITY_CHAT_URL = "https://api.perplexity.ai/chat/completions"


def _build_response_schema() -> Dict[str, Any]:
    """
    JSON schema for Perplexity structured output.

    We ask Perplexity to respond with:
    {
      "summary": "...",
      "sources": [
        {"title": "...", "url": "...", "snippet": "..."}
      ]
    }
    """
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                        "snippet": {"type": "string"},
                    },
                    "required": ["url"],
                },
            },
        },
        "required": ["sources"],
    }


def web_search(
    query: str,
    recency: str = "week",
    max_results: int = 6,
) -> Dict[str, Any]:
    """
    Call Perplexity Chat Completions API with web search turned on and request a
    structured JSON response describing sources.

    Returns a dict:
    {
      "summary": str,
      "sources": [ { "title": str, "url": str, "snippet": str }, ... ]
    }
    """
    api_key = get_perplexity_api_key()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    system_prompt = (
        "You are a dev tooling research assistant. Use web search to find "
        "high-quality, recent sources about developer tools, platforms, and AI assistants "
        "related to the user's question. "
        "Return a JSON object with a short 'summary' and a 'sources' array. "
        "Each source must include the URL and, if possible, a short snippet. "
        "Do NOT add commentary outside the JSON."
    )

    payload: Dict[str, Any] = {
        "model": "sonar-pro",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        "search_mode": "web",
        "search_recency_filter": recency,
        "temperature": 0.0,
        "max_tokens": 1024,
        "web_search_options": {"search_context_size": "high"},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "web_research_results",
                "schema": _build_response_schema(),
                "strict": True,
            },
        },
    }

    response = requests.post(
        PERPLEXITY_CHAT_URL,
        headers=headers,
        json=payload,
        timeout=80,
    )
    response.raise_for_status()
    data = response.json()

    raw_content = data["choices"][0]["message"]["content"]
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        logger.warning("Failed to parse Perplexity JSON; using fallback. Raw: %s", raw_content[:200])
        parsed = {"summary": raw_content, "sources": []}

    # Fallback: use search_results field if sources array is empty
    if not parsed.get("sources") and data.get("search_results"):
        fallback_sources: List[Dict[str, Optional[str]]] = []
        for item in data["search_results"][:max_results]:
            fallback_sources.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "snippet": "",
                }
            )
        parsed["sources"] = fallback_sources

    parsed["sources"] = parsed.get("sources", [])[:max_results]

    return parsed
