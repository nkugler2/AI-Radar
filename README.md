# README.md

A data pipeline and dashboard for tracking the health and momentum of popular AI projects on GitHub across many languages (Python, JavaScript/TypeScript, C++, Rust, Go, and more). AI Radar ingests repository metadata from the GitHub API, runs analytial transforms, and surfaces insights through an interactive Streamlit dashboard — showing which projects are gaining traction, which are well-maintained, and how the AI open source ecosystem is evolving.

Built as a learning project for multi-agent agentic coding using [Claude Squad](https://github.com/smtg-ai/claude-squad), where three Claude Code instances work in parallel across isolated git worktrees.

---

## What it does

- Searches GitHub for AI-related repositories across many languages (Python, JavaScript/TypeScript, C++, Rust, Go, Jupyter Notebook, C#, Java) using topic tags like `llm`, `rag`, `agents`, and `computer-vision`
- Fetches metadata per repo: stars, forks, open issues, and last push date
- Computes derived metrics: momentum score (stars relative to project age), maintenance score (push recency and issue closure rate), and days since last push
- Categorizes repos by their GitHub topic tags
- Presents everything in a Streamlit dashboard with a sortable leaderboard, rising stars view, category breakdown, and per-repo detail page

Designed to be extended: adding JavaScript/TypeScript repos, additional data sources like PyPI download trends, or a scheduled pipeline via Prefect requires minimal changes to the existing architecture.

---

## Architecture

The project is split into three layers with a shared contract that each layer codes against independently.

```
├── contracts/
│   └── schema.py          # Single source of truth — table names, field types, DB path
├── ingestion/
│   ├── github_client.py   # GitHub API client, search, and repo metadata fetching
│   └── runner.py          # Orchestrates ingestion and writes to DuckDB
├── transform/
│   ├── clean.py           # Reads raw data, cleans nulls and bad records using Polars
│   └── metrics.py         # Computes momentum score, maintenance score, categories
├── dashboard/
│   └── app.py             # Streamlit app — reads only from clean analytical tables
├── data/
│   └── ai_radar.duckdb    # Local DuckDB file (gitignored)
└── main.py                # Pipeline runner: ingestion → transform → launch instructions
```

### The shared contract

`contracts/schema.py` is the most important file in the project. It defines all DuckDB table names, field names, and types. No agent writes code that assumes anything about the database that isn't declared here. This is what makes the three layers independently buildable and the project safely extensible.

### Three-agent breakdown

| Agent               | Branch              | Owns         | Reads from        | Writes to           |
| ------------------- | ------------------- | ------------ | ----------------- | ------------------- |
| Agent 1 — Ingestion | `feature/ingestion` | `ingestion/` | GitHub API        | `raw_repos` table   |
| Agent 2 — Transform | `feature/transform` | `transform/` | `raw_repos` table | `repos` table       |
| Agent 3 — Dashboard | `feature/dashboard` | `dashboard/` | `repos` table     | Nothing (read-only) |

Agents 1 and 3 have zero code overlap. The only shared boundary is `contracts/schema.py`, which is written and committed to `main` before any agent starts. This is what enables genuine parallel development — each agent works in its own worktree against a stable interface.

---

## Tech stack

| Layer     | Library         | Purpose                                |
| --------- | --------------- | -------------------------------------- |
| Ingestion | `requests`      | GitHub REST API client                 |
| Ingestion | `python-dotenv` | Load GitHub token from `.env`          |
| Transform | `polars`        | Fast DataFrame transforms and cleaning |
| Storage   | `duckdb`        | Local analytical database              |
| Dashboard | `streamlit`     | Interactive web dashboard              |
| Dashboard | `plotly`        | Charts and visualizations              |

---

## Data source

Repository data is sourced from the [GitHub REST API](https://docs.github.com/en/rest). Specifically:

- **Search endpoint**: [`GET /search/repositories`](https://docs.github.com/en/rest/search/search#search-repositories) — used to find repos matching a topic and language query (e.g. `topic:llm language:python`)
- **Repo endpoint**: [`GET /repos/{owner}/{repo}`](https://docs.github.com/en/rest/repos/repos#get-a-repository) — used to fetch detailed metadata per repo

Authentication uses a GitHub personal access token (classic) with `public_repo` read scope. Unauthenticated requests are limited to 60/hour; authenticated requests allow 5,000/hour.

---

## Setup

### Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) for dependency management
- A GitHub personal access token (classic) with `public_repo` scope — generate one at [github.com/settings/tokens](https://github.com/settings/tokens)

### Install dependencies

```bash
uv sync
```

### Configure environment

Create a `.env` file in the project root:

```
GITHUB_TOKEN=your_token_here
```

### Run the pipeline

```bash
uv run python main.py
```

### Launch the dashboard

```bash
uv run streamlit run dashboard/app.py
```

---

## Multi-agent development with Claude Squad

This project was built using [Claude Squad](https://github.com/smtg-ai/claude-squad), a tool that orchestrates multiple Claude Code instances simultaneously in the terminal using git worktrees. Each agent gets its own branch and working directory, enabling genuine parallel development.

### Why this project suits multi-agent coding

The three layers — ingestion, transform, and dashboard — have clean boundaries and almost no code overlap once the schema contract is defined. This makes it an ideal candidate for parallel agentic work:

- Each agent receives a scoped brief pointing it to `contracts/schema.py` and its own directory
- Agents never need to coordinate mid-task because the interface is pre-agreed
- Merging is straightforward because branches touch different files

### Default Agent Prompt Per Agent

**Agent 1 — Ingestion** (`feature/ingestion`):

> "You are building the ingestion layer for a project called AI Radar. Read `contracts/schema.py` first — this is the only source of truth for table names, field names, and the DB path. Your job:

**Agent 2 — Transform** (`feature/transform`):

> "You are building the transform layer for a project called AI Radar. Read `contracts/schema.py` first — this is the only source of truth for table names, field names, and the DB path. Your job:

**Agent 3 — Dashboard** (`feature/dashboard`):

> "You are building the Streamlit dashboard for a project called AI Radar. Read `contracts/schema.py` first — this is the only source of truth for table names and the DB path. Your job:

### Agent prompts used to start this project

**Agent 1 — Ingestion** (`feature/ingestion`):

> "You are building the ingestion layer for a project called AI Radar. Read `contracts/schema.py` first — this is the only source of truth for table names, field names, and the DB path. Your job: build `ingestion/github_client.py` (a GitHub API client that searches for repos and fetches metadata) and `ingestion/runner.py` (a script that runs the ingestion and writes raw rows into DuckDB using the `raw_repos` schema). Load the GitHub token from `.env` using python-dotenv. Use `requests` for API calls. Handle rate limiting with a simple retry/sleep. Do not touch any files outside the `ingestion/` folder and `contracts/`."

**Agent 2 — Transform** (`feature/transform`):

> "You are building the transform layer for a project called AI Radar. Read `contracts/schema.py` first — this is the only source of truth for table names, field names, and the DB path. Your job: build `transform/clean.py` (reads from the `raw_repos` DuckDB table, cleans nulls and bad data using Polars) and `transform/metrics.py` (computes `momentum_score` from stars/age_in_days plus push recency and fork ratio, `maintenance_score` from days since push and issue close ratio, `days_since_push`, and assigns a `category` from the topics array using the `TOPIC_TO_CATEGORY` mapping). Write results to the `repos` table. Do not touch any files outside the `transform/` folder and `contracts/`."

**Agent 3 — Dashboard** (`feature/dashboard`):

> "You are building the Streamlit dashboard for a project called AI Radar. Read `contracts/schema.py` first — this is the only source of truth for table names and the DB path. Your job: build `dashboard/app.py` as a Streamlit app that reads from the `repos` DuckDB table and renders: (1) a sortable leaderboard by stars and momentum score, (2) a category breakdown chart using Plotly, (3) a rising stars view sorted by momentum_score, (4) a detail view when a repo is selected. Read only — never write to the database. Do not touch files outside the `dashboard/` folder and `contracts/`."

---

## Extending the project

The architecture is designed to grow without touching existing layers.

**Add more languages** — add values to the `Language` enum in `contracts/schema.py` (the value must match GitHub's `language:` qualifier; multi-word names are quoted automatically). The ingestion agent reads `DEFAULT_LANGUAGES` dynamically, and the dashboard's language filter is populated from the data, so no transform or dashboard changes are needed.

**Add a second data source** — implement a new ingestion module (e.g. `ingestion/pypi_client.py`) that writes to the same `raw_repos` schema. The transform and dashboard layers are unaffected.

**Add scheduled runs** — wrap `main.py` with Prefect or a cron job. The pipeline is already structured as discrete steps.

**Add trend tracking** — modify `raw_repos` to store multiple snapshots per repo over time (add a `fetched_at` index). The transform layer can then compute week-over-week star growth.

---

## Roadmap

- [x] Multi-language support (JavaScript/TypeScript, C++, Rust, Go, Jupyter Notebook, C#, Java)
- [ ] Contributor data ingestion and scoring
- [ ] Release cadence tracking
- [ ] Time-series snapshots for trend tracking
- [ ] PyPI download trend integration
- [ ] Scheduled ingestion with Prefect
- [ ] Week-over-week momentum tracking
- [ ] Alerting for fast-trending repos
