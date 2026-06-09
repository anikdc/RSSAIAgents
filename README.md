# AI News Trend Agent

AI News Trend Agent is a news briefing pipeline. It polls RSS feeds, scores source credibility, clusters related stories with embeddings, scrapes article text, and generates a synthesized briefing with Google Gemini.

The original Streamlit UI still works. A MERN migration is now being built beside it: React for the dashboard, Express for the frontend-facing API, MongoDB for durable persistence, and FastAPI as a thin Python worker around the existing AI pipeline.

## Flowchart

<img width="816" height="834" alt="AI News Trend Agent flowchart" src="https://github.com/user-attachments/assets/fd93ed40-3cd1-4bdb-9a12-35690d18d8b9" />

## Prerequisites

- Python 3.14 or compatible Python 3.10+
- uv
- Node.js 18+ for the MERN services
- MongoDB, optional while JSON fallback is enabled
- Google Gemini API key

## Setup

1. Clone the repository.

2. Install dependencies.

   ```bash
   uv sync
   npm install
   ```

3. Create a local environment file.

   ```bash
   cp .env.example .env
   ```

4. Edit `.env` and set `GEMINI_API_KEY`.

5. After the SentenceTransformer verifier model has been downloaded once, keep local-only mode enabled to prevent Hugging Face model re-downloads.

   ```env
   SENTENCE_TRANSFORMERS_LOCAL_ONLY=true
   HF_HUB_OFFLINE=1
   ```

## Usage

Run the Python worker API:

```bash
uv run uvicorn src.api:app --host 127.0.0.1 --port 8000
```

Run the Express API in another terminal:

```bash
npm run dev:api
```

Run the React dashboard in another terminal:

```bash
npm run dev:web
```

Run the Streamlit UI:

```bash
uv run streamlit run app.py
```

Run the Streamlit UI in a headless environment:

```bash
uv run streamlit run app.py --server.headless true
```

Run the briefing pipeline manually:

```bash
uv run python src/orchestrator.py
```

Run the briefing pipeline while forcing cached SentenceTransformer files only:

```bash
HF_HUB_OFFLINE=1 SENTENCE_TRANSFORMERS_LOCAL_ONLY=true uv run python src/orchestrator.py
```

## Configuration

The project reads configuration from `.env`.

- `LLM_PROVIDER`: `gemini` by default. `groq` is optional.
- `GEMINI_API_KEY`: Required for Gemini synthesis and embeddings.
- `GEMINI_MODEL`: Gemini model used for briefing synthesis.
- `GEMINI_EMBEDDING_MODEL`: Gemini embedding model used for clustering. `gemini-embedding-001` is the tested batch embedding model for this pipeline.
- `SENTENCE_TRANSFORMERS_LOCAL_ONLY`: Set to `true` after the verifier model is cached locally.
- `HF_HUB_OFFLINE`: Set to `1` to prevent Hugging Face network checks.
- `GROQ_API_KEY`: Required only when `LLM_PROVIDER=groq`.
- `GROQ_MODEL`: Groq model used when the optional Groq provider is enabled.
- `PYTHON_WORKER_PORT`: Port for the FastAPI worker. Default: `8000`.
- `PYTHON_WORKER_MAX_JOBS`: Maximum concurrent Python worker jobs. Default: `2`.
- `EXPRESS_PORT`: Port for the Express API. Default: `4000`.
- `PYTHON_WORKER_URL`: URL Express uses to call FastAPI. Default: `http://127.0.0.1:8000`.
- `FRONTEND_ORIGIN`: Allowed frontend origin for Express CORS. Default: `http://127.0.0.1:5173`.
- `VITE_API_BASE`: Express API base URL used by React. Default: `http://127.0.0.1:4000`.
- `MONGODB_URI`: MongoDB connection string. Leave empty to use local JSON fallback.
- `MONGODB_DB`: MongoDB database name. Default: `rssaiagents`.

To install the optional Groq dependency:

```bash
uv sync --extra groq
```

## Project Files

- `app.py`: Streamlit interface for the briefing and feed controls.
- `frontend/`: React dashboard for the MERN migration.
- `backend/`: Express API gateway for the MERN migration.
- `feeds_default.json`: Default RSS feed list.
- `feeds_db.json`: Searchable feed database used by the search agent.
- `pyproject.toml`: Project metadata and uv dependency declarations.
- `uv.lock`: Locked dependency graph for reproducible installs.
- `src/orchestrator.py`: Coordinates polling, verification, clustering, scraping, synthesis, and output writing.
- `src/api.py`: FastAPI worker API for asynchronous pipeline jobs.
- `src/persistence.py`: MongoDB persistence adapter with JSON fallback.
- `src/rss_poller.py`: Fetches and parses RSS feeds.
- `src/verification_agent.py`: Scores articles and handles SentenceTransformer-based corroboration.
- `src/trend_detector.py`: Generates Gemini embeddings and clusters articles with DBSCAN, HDBSCAN, or KMeans.
- `src/scraper_agent.py`: Fetches article page text.
- `src/synthesis_agent.py`: Generates synthesized briefings.
- `src/search_agent.py`: Parses user search queries and selects relevant feeds.

## Runtime Outputs

These files are generated locally and are not committed:

- `.env`
- `.venv/`
- `agent.log`
- `briefing_data.json`
- `active_feeds.json`
- `.runtime/`
- `node_modules/`
- `frontend/dist/`

## Roadmap

- Keep Streamlit available until the React dashboard reaches feature parity.
- Expand MongoDB persistence and cache reuse for verification, scraped text, embeddings, and search intent.
- Add production-grade job cancellation, retries, and authentication.
- Retire Streamlit after the MERN stack is the primary workflow.
