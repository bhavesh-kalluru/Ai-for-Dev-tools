
import logging
from functools import lru_cache
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

from config import get_openai_client
from utils.text_utils import truncate_text, extract_domain
from web_search import web_search

logger = logging.getLogger(__name__)


@lru_cache(maxsize=32)
def fetch_url_content(url: str, max_chars: int = 6000) -> str:
    """
    Download the URL and extract readable text using BeautifulSoup.
    We keep it simple: collect <p> tags and join their text.
    """
    try:
        resp = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "DevToolScope/1.0 (+for educational portfolio use)"},
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to fetch url %s: %s", url, exc)
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    paragraphs = soup.find_all("p")
    text_chunks: List[str] = []

    for p in paragraphs:
        t = p.get_text(separator=" ", strip=True)
        if t:
            text_chunks.append(t)
        if sum(len(x) for x in text_chunks) > max_chars:
            break

    joined = "\n\n".join(text_chunks)
    return truncate_text(joined, max_chars=max_chars)


def build_context_from_sources(sources: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    For each source, fetch content and build a unified context string plus
    sidebar-friendly source metadata.
    """
    context_blocks: List[str] = []
    sidebar_sources: List[Dict[str, str]] = []

    for idx, src in enumerate(sources, start=1):
        url = src.get("url")
        if not url:
            continue

        title = src.get("title") or f"Source {idx}"
        snippet = src.get("snippet") or ""
        text = fetch_url_content(url)
        if not text:
            text = snippet or ""

        text = truncate_text(text, max_chars=2000)

        label = f"S{idx}"
        block = (
            f"[{label}] {title}\nURL: {url}\n\n"
            f"{text}\n"
            "------------------------"
        )
        context_blocks.append(block)

        sidebar_sources.append(
            {
                "title": title,
                "url": url,
                "snippet": truncate_text(snippet or text, max_chars=260),
                "meta": extract_domain(url),
            }
        )

    combined_context = "\n\n".join(context_blocks)
    context_preview = truncate_text(combined_context, max_chars=4000)

    return {
        "context": combined_context,
        "context_preview": context_preview,
        "sidebar_sources": sidebar_sources,
    }


def _build_openai_system_prompt(depth: str, focus: str) -> str:
    depth_text = (
        "Provide a concise but actionable briefing, focusing on the most impactful tools."
        if depth == "Concise"
        else "Provide a deep, structured briefing with nuanced analysis, trade-offs, and adoption tips."
    )

    focus_text = ""
    if focus != "Any":
        focus_text = (
            f" Prioritize tools and practices related to {focus} when they appear in the context."
        )

    return (
        "You are DevToolScope, a senior engineer and dev productivity expert. "
        "You answer based ONLY on the provided web context, labeled as [S1], [S2], etc. "
        "If something is not supported by the context, say that it is not clearly covered. "
        f"{depth_text}"
        f"{focus_text} "
        "Structure your answer with the following sections:\n"
        "1. Summary\n"
        "2. Recommended tools & platforms\n"
        "3. How to adopt them (step-by-step)\n"
        "4. Trade-offs & caveats\n"
        "5. Confidence & limitations\n\n"
        "When you mention a specific tool, reference supporting sources in brackets like [S1], [S2]."
    )


def generate_tooling_briefing(
    query: str,
    mode: str,
    recency: str,
    focus: str,
    depth: str,
    stack: str,
) -> Dict[str, Any]:
    """
    Main entry point used by app.py.

    1. Call Perplexity web search to obtain sources about dev tools.
    2. Fetch and build context from those sources.
    3. Call OpenAI with a tailored system prompt and the context.
    """
    # Step 1: Web search via Perplexity (Web-RAG retrieval step)
    if mode == "Discover tools for a problem":
        search_query = f"Developer productivity tools to help with: {query}"
    elif mode == "Compare tools in a category":
        search_query = f"Compare popular developer tools in this category: {query}"
    else:  # "Deep dive on a specific tool"
        search_query = f"Deep dive on developer tool: {query} (use cases, pros/cons, ecosystem)"

    if stack.strip():
        search_query += f" for a stack that includes: {stack.strip()}"

    research = web_search(search_query, recency=recency)
    sources = research.get("sources", [])
    search_summary = research.get("summary", "")

    if not sources:
        raise RuntimeError("No web sources were returned by the search layer.")

    # Step 2: Build context from fetched pages
    context_info = build_context_from_sources(sources)
    context = context_info["context"]
    context_preview = context_info["context_preview"]
    sidebar_sources = context_info["sidebar_sources"]

    # Step 3: Call OpenAI to synthesize the final briefing
    client: OpenAI = get_openai_client()

    system_prompt = _build_openai_system_prompt(depth=depth, focus=focus)

    stack_suffix = ""
    if stack.strip():
        stack_suffix = (
            "\n\nThe user also described their tech stack as:\n"
            f"{stack.strip()}\n"
            "Tailor recommendations and caveats to this stack where relevant."
        )

    user_message = (
        "User question:\n"
        f"{query}\n\n"
        "Web research context:\n"
        f"{context}\n"
        f"{stack_suffix}"
    )

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=0.15,
        max_tokens=1400,
    )

    answer = completion.choices[0].message.content

    # Expose sources list to the Streamlit app via session_state
    import streamlit as st  # local import to avoid hard dependency in non-UI contexts

    st.session_state["last_sources"] = sidebar_sources

    return {
        "answer": answer,
        "search_summary": search_summary,
        "context_preview": context_preview,
    }
