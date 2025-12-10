# DevToolScope — AI Dev Productivity Radar 🧰

**Tagline:** A Web-RAG Streamlit app that scouts dev tools, AI assistants, and platforms to boost developer productivity — using Python, Perplexity, and OpenAI.

---

## Overview

DevToolScope is a **developer productivity radar**. You describe a problem, category, or specific tool, and the app:

1. Uses the **Perplexity API** to run a web-grounded search over docs, blogs, and comparison posts.
2. Fetches those pages, extracts readable text, and treats them as context chunks.
3. Uses **OpenAI** to generate a structured briefing with:
   - Summary  
   - Recommended tools & platforms  
   - How to adopt them  
   - Trade-offs & caveats  
   - Confidence & limitations  

This is **Web-RAG**, not local-file RAG. There is no static `data/` folder: the knowledge comes from live web content.

It’s designed as a portfolio-ready project to show end-to-end **GenAI / AI Engineering** skills.

---

## Features

- **Dev productivity focus**
  - Discover tools to solve a specific pain point.
  - Compare tools in a category (e.g., feature flags, error tracking, observability).
  - Deep dive on a single tool (use cases, pros/cons, ecosystem).

- **Web-RAG pipeline**
  - Perplexity Chat Completions API with `search_mode="web"` for retrieval.
  - `requests + BeautifulSoup` to turn URLs into plain text context.
  - OpenAI (`gpt-4o-mini`) to synthesize a structured dev-tool briefing.

- **Modern Streamlit UI**
  - Sidebar controls for analysis mode, recency, focus area, and answer depth.
  - Main card for the AI-generated tooling briefing.
  - Sources panel showing URLs and snippets used.
  - Simple per-session history of past analyses.

---

## Project Structure

```text
devtool-rag-app/
│
├─ app.py               # Streamlit UI + orchestration
├─ rag_pipeline.py      # Web-RAG pipeline (fetch, context, OpenAI)
├─ web_search.py        # Perplexity web search wrapper
├─ config.py            # Env config and client helpers
│
├─ requirements.txt     # Python dependencies
├─ Dockerfile           # Container build for Streamlit app
├─ README.md            # This file
├─ .gitignore           # Ensures .env and other cruft are ignored
├─ .env.example         # Sample env variables (no secrets)
│
└─ utils/
   ├─ __init__.py
   └─ text_utils.py     # Helpers (truncate, domain extraction)
```

---

## Local Setup (macOS / PyCharm)

1. **Unzip the project** and `cd` into it:

   ```bash
   cd devtool-rag-app
   ```

2. **Create & activate a virtual environment**:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Create your `.env` file** from the example:

   ```bash
   cp .env .env
   ```

   Edit `.env` and add:

   ```bash
   OPENAI_API_KEY=your_openai_api_key_here
   PERPLEXITY_API_KEY=your_perplexity_api_key_here
   ```

5. **Run the app**:

   ```bash
   streamlit run app.py
   ```

   Open `http://localhost:8501` in your browser.

---

## Docker Usage

Build the image:

```bash
docker build -t devtool-rag-app .
```

Run the container (using your local `.env` for API keys):

```bash
docker run -p 8501:8501 --env-file .env devtool-rag-app
```

Visit `http://localhost:8501` to use the app.

---

## Git & Deployment Notes

- `.env` and `.env.*` are ignored by `.gitignore` and **must not** be committed.
- Basic Git flow:

  ```bash
  git init
  git add .
  git commit -m "Initial commit: DevToolScope Web-RAG dev productivity app"
  git branch -M main
  git remote add origin REPO_URL_HERE
  git push -u origin main
  ```

- On Render or another cloud provider:
  - Use `pip install -r requirements.txt` as the build command.
  - Use `streamlit run app.py --server.port $PORT --server.address 0.0.0.0` as the start command.
  - Set `OPENAI_API_KEY` and `PERPLEXITY_API_KEY` as environment variables in the dashboard.

---

## Why This Project Matters

This project shows:

- **Real Web-RAG** over live dev-tool content (docs, blogs, comparisons).
- **Multi-model orchestration**: Perplexity for retrieval, OpenAI for reasoning.
- Clean separation of:
  - UI (Streamlit)
  - Retrieval (Perplexity + HTTP)
  - RAG pipeline (context building + LLM call)
- Containerization and deployment readiness (Docker, Render-compatible commands).

It’s a good code sample for **GenAI / AI Engineer** interviews, especially around developer productivity, AI tooling, and MLOps ecosystems.

---

## About the Author

Hi, I’m **Bhavesh Kalluru**, a developer with **5 years of experience**, focusing on **GenAI / AI Engineering**.

- I’m actively looking for **full-time GenAI / AI Engineer roles**, preferably in the US.  
- I enjoy building practical GenAI systems around RAG, evaluation, and tooling for developers.

**Links:**

- GitHub: https://github.com/bhavesh-kalluru
- LinkedIn: https://www.linkedin.com/in/bhaveshkalluru/
- Portfolio: https://kbhavesh.com
- This project repo: REPO_URL_HERE
