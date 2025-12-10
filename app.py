
import streamlit as st

from rag_pipeline import generate_tooling_briefing
from config import validate_config


def init_page():
    st.set_page_config(
        page_title="DevToolScope — AI Dev Productivity Radar",
        page_icon="🧰",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        """
        <style>
        .dts-header {
            font-size: 2.2rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
        }
        .dts-subtitle {
            font-size: 1rem;
            color: #555;
            margin-bottom: 1.5rem;
        }
        .dts-card {
            padding: 1.1rem 1.3rem;
            border-radius: 0.9rem;
            border: 1px solid #E0E0E0;
            background-color: #FAFAFA;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        }
        .source-card {
            padding: 0.7rem 0.75rem;
            border-radius: 0.6rem;
            border: 1px solid #E5E5E5;
            background-color: #FFFFFF;
            margin-bottom: 0.5rem;
        }
        .source-title {
            font-weight: 600;
            font-size: 0.95rem;
        }
        .source-meta {
            font-size: 0.8rem;
            color: #777;
            margin-bottom: 0.25rem;
        }
        .footer-note {
            font-size: 0.8rem;
            color: #999;
            margin-top: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar():
    st.sidebar.title("⚙️ Controls")

    mode = st.sidebar.selectbox(
        "Analysis mode",
        [
            "Discover tools for a problem",
            "Compare tools in a category",
            "Deep dive on a specific tool",
        ],
    )

    recency = st.sidebar.selectbox(
        "Web recency filter",
        ["day", "week", "month", "year"],
        index=1,
        help="How fresh the web results should be. This is passed to the web search layer.",
    )

    focus = st.sidebar.selectbox(
        "Dev focus area",
        ["Any", "Backend / APIs", "Frontend / UI", "MLOps / Data", "DevEx / Collaboration", "Testing / QA"],
        help="Used as a soft hint in the prompt.",
    )

    depth = st.sidebar.radio(
        "Answer depth",
        ["Concise", "Deep dive"],
        index=0,
        help="Controls how detailed the final answer should be.",
    )

    stack = st.sidebar.text_area(
        "Your tech stack (optional)",
        placeholder="e.g., Python, FastAPI, React, PostgreSQL, Docker, AWS, GitHub Actions…",
        height=80,
    )

    st.sidebar.markdown(
        """
        ---
        **About the app**

        • Uses live web data via Perplexity API  
        • Performs Web-RAG with OpenAI  
        • Designed as a portfolio-grade GenAI project focused on dev productivity
        """
    )

    return {
        "mode": mode,
        "recency": recency,
        "focus": focus,
        "depth": depth,
        "stack": stack,
    }


def main():
    init_page()
    config_ok, config_error = validate_config()

    st.markdown('<div class="dts-header">DevToolScope — AI Dev Productivity Radar</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="dts-subtitle">'
        "Ask about your workflow or stack and get a curated radar of tools, AI assistants, and platforms "
        "that can improve developer productivity — powered by Web-RAG over live docs and blog posts."
        "</div>",
        unsafe_allow_html=True,
    )

    controls = render_sidebar()

    if not config_ok:
        st.error(
            "Configuration error: " + config_error
            + "\\n\\nPlease create a `.env` file with valid `OPENAI_API_KEY` and `PERPLEXITY_API_KEY`."
        )
        return

    if "history" not in st.session_state:
        st.session_state["history"] = []

    col_main, col_side = st.columns([2.4, 1.0])

    with col_main:
        placeholder_map = {
            "Discover tools for a problem": "e.g., \"We spend too much time debugging production issues in our Python microservices\"",
            "Compare tools in a category": "e.g., \"Compare popular feature flag platforms for a mid-size SaaS\"",
            "Deep dive on a specific tool": "e.g., \"Deep dive on LangSmith for evaluating LLM applications\"",
        }
        prompt_placeholder = placeholder_map[controls["mode"]]

        user_query = st.text_area(
            "What dev productivity problem or tool are you exploring?",
            placeholder=prompt_placeholder,
            height=120,
        )

        run_clicked = st.button("🧰 Generate Tooling Briefing")

        if run_clicked and not user_query.strip():
            st.warning("Please enter a question or topic first.")
            run_clicked = False

        if run_clicked:
            with st.spinner("Researching tools and generating your briefing..."):
                try:
                    result = generate_tooling_briefing(
                        query=user_query,
                        mode=controls["mode"],
                        recency=controls["recency"],
                        focus=controls["focus"],
                        depth=controls["depth"],
                        stack=controls["stack"],
                    )

                    st.session_state["history"].append(
                        {"query": user_query, "summary": result.get("answer", "")[:280]}
                    )

                    st.markdown('<div class="dts-card">', unsafe_allow_html=True)
                    st.markdown("#### 🧠 AI Tooling Briefing")
                    st.markdown(result.get("answer", "No answer generated."))

                    st.markdown("---")

                    if result.get("search_summary"):
                        st.markdown("**Web research summary (pre-synthesis):**")
                        st.markdown(result["search_summary"])

                    with st.expander("Show raw context used (debug)"):
                        st.write(result.get("context_preview", ""))

                    st.markdown("</div>", unsafe_allow_html=True)

                except Exception as exc:  # noqa: BLE001
                    st.error("Something went wrong while generating the briefing.")
                    st.exception(exc)

        if st.session_state["history"]:
            with st.expander("Past analyses this session"):
                for idx, h in enumerate(reversed(st.session_state["history"]), start=1):
                    st.markdown(f"**{idx}.** {h['query']}")
                    st.markdown(
                        f"<span style='font-size:0.9rem;color:#777;'>{h['summary']}...</span>",
                        unsafe_allow_html=True,
                    )
                    st.markdown("---")

    with col_side:
        st.markdown("### 🔍 Sources used")

        if "last_sources" in st.session_state and st.session_state["last_sources"]:
            for s in st.session_state["last_sources"]:
                st.markdown('<div class="source-card">', unsafe_allow_html=True)
                title = s.get("title") or "[untitled]"
                url = s.get("url") or "#"
                meta = s.get("meta") or ""
                snippet = s.get("snippet") or ""

                st.markdown(
                    f"<div class='source-title'><a href='{url}' target='_blank'>{title}</a></div>",
                    unsafe_allow_html=True,
                )
                if meta:
                    st.markdown(f"<div class='source-meta'>{meta}</div>", unsafe_allow_html=True)
                if snippet:
                    st.markdown(snippet)
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.info("Run an analysis to see which sources were used.")

        st.markdown(
            "<div class='footer-note'>This tool is for high-level product discovery only "
            "and does not replace hands-on evaluation.</div>",
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
