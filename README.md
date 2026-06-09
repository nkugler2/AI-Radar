# README.md

A data pipeline and dashboard for tracking the health and momentum of popular AI projects on GitHub across many languages (Python, JavaScript/TypeScript, C++, Rust, Go, and more). AI Radar ingests repository metadata from the GitHub API, runs analytial transforms, and surfaces insights through an interactive Streamlit dashboard — showing which projects are gaining traction, which are well-maintained, and how the AI open source ecosystem is evolving.

Built originally as a learning project for multi-agent agentic coding using [Claude Squad](https://github.com/smtg-ai/claude-squad), where three Claude Code instances work in parallel across isolated git worktrees.

---

## What it does

- Searches GitHub for AI-related repositories across many languages (Python, JavaScript/TypeScript, C++, Rust, Go, Jupyter Notebook, C#, Java) using topic tags like `llm`, `rag`, `agents`, and `computer-vision`
- Fetches metadata per repo: stars, forks, open issues, and last push date
- Computes derived metrics: momentum score (stars relative to project age), maintenance score (push recency and issue closure rate), and days since last push
- Categorizes repos by their GitHub topic tags
- Presents everything in a Streamlit dashboard with a sortable leaderboard, rising stars view, category breakdown, and per-repo detail page

---

## Architecture

The project is split into three layers with a shared contract that each layer codes against independently.

```
├── contracts/
│   ├── schema.py          # Single source of truth — table names, field types, DB path
│   └── scrub.py           # Secret detection and redaction patterns (shared by all layers)
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

### Secret scrubbing

Some third-party READMEs contain credential-shaped strings (real or example). Before any data reaches the parquet file that gets committed to git, `contracts/scrub.py` scans and redacts them.

- **Ingestion** (`runner.py`) — after READMEs are fetched, scans each one and prints a WARNING log block listing every repo, what pattern was hit, the severity, and a sample. This is read-only: `raw_repos` in DuckDB is left unchanged.
- **Transform** (`clean.py`) — during cleaning, replaces every match with `[AI-Radar: {pattern_name} redacted]` before writing to the `repos` table and exporting to parquet.

**To add a new secret type**, add one entry to `SECRET_PATTERNS` in `contracts/scrub.py`:

```python
"my_new_key": {
    "pattern": r"my-regex-here",
    "severity": "high",   # critical / high / medium / low
},
```

That's it — both the ingestion log and the transform scrub pick it up automatically.

### The shared contract

`contracts/schema.py` is the most important file in the project. It defines all DuckDB table names, field names, and types. No agent writes code that assumes anything about the database that isn't declared here. This is what makes the three layers independently buildable and the project safely extensible.

### Three-agent breakdown

This project originally was made for me to test using multiple agents, Specifically with claude-squad and a fork of claude-squad called Agent Factory (af). I stopped using them for multiple reasons:

1. Both were generally buggy in a way I found disruptive to my workflow
2. Did not provide significant advantages over using one agent working across the three main areas (ingestion, transform, dashboard)
3. claude-code now has multi agents built in (late development)
4. A small project with a few main features does not benefit from the workflow like a project with dozens of different features that exist across multiple surfaces (front end, back end, database, auth, hosting, etc.)

The multi agent workflow was great for:

1. Starting the project from a shared `contracts/schema.py`: Since I started the project with a set definition of how data worked, the agents were able to work independently of each other without compromising the code
2. Small bug fixes: When ingestion and dashboard both had separate bugs, it was great to spin up two agents and manage them independently

| Agent               | Branch              | Owns         | Reads from        | Writes to           |
| ------------------- | ------------------- | ------------ | ----------------- | ------------------- |
| Agent 1 — Ingestion | `feature/ingestion` | `ingestion/` | GitHub API        | `raw_repos` table   |
| Agent 2 — Transform | `feature/transform` | `transform/` | `raw_repos` table | `repos` table       |
| Agent 3 — Dashboard | `feature/dashboard` | `dashboard/` | `repos` table     | Nothing (read-only) |

Agents 1 and 3 have zero code overlap. The only shared boundary is `contracts/schema.py`, which is written and committed to `main` before any agent starts. This is what enables genuine parallel development — each agent works in its own worktree against a stable interface.

#### Default Agent Prompt Per Agent

**Agent 1 — Ingestion** (`feature/ingestion`):

> "You are building the ingestion layer for a project called AI Radar. Read `contracts/schema.py` first — this is the only source of truth for table names, field names, and the DB path. Your job:

**Agent 2 — Transform** (`feature/transform`):

> "You are building the transform layer for a project called AI Radar. Read `contracts/schema.py` first — this is the only source of truth for table names, field names, and the DB path. Your job:

**Agent 3 — Dashboard** (`feature/dashboard`):

> "You are building the Streamlit dashboard for a project called AI Radar. Read `contracts/schema.py` first — this is the only source of truth for table names and the DB path. Your job:

#### Agent prompts used to start this project

**Agent 1 — Ingestion** (`feature/ingestion`):

> "You are building the ingestion layer for a project called AI Radar. Read `contracts/schema.py` first — this is the only source of truth for table names, field names, and the DB path. Your job: build `ingestion/github_client.py` (a GitHub API client that searches for repos and fetches metadata) and `ingestion/runner.py` (a script that runs the ingestion and writes raw rows into DuckDB using the `raw_repos` schema). Load the GitHub token from `.env` using python-dotenv. Use `requests` for API calls. Handle rate limiting with a simple retry/sleep. Do not touch any files outside the `ingestion/` folder and `contracts/`."

**Agent 2 — Transform** (`feature/transform`):

> "You are building the transform layer for a project called AI Radar. Read `contracts/schema.py` first — this is the only source of truth for table names, field names, and the DB path. Your job: build `transform/clean.py` (reads from the `raw_repos` DuckDB table, cleans nulls and bad data using Polars) and `transform/metrics.py` (computes `momentum_score` from stars/age_in_days plus push recency and fork ratio, `maintenance_score` from days since push and issue close ratio, `days_since_push`, and assigns a `category` from the topics array using the `TOPIC_TO_CATEGORY` mapping). Write results to the `repos` table. Do not touch any files outside the `transform/` folder and `contracts/`."

**Agent 3 — Dashboard** (`feature/dashboard`):

> "You are building the Streamlit dashboard for a project called AI Radar. Read `contracts/schema.py` first — this is the only source of truth for table names and the DB path. Your job: build `dashboard/app.py` as a Streamlit app that reads from the `repos` DuckDB table and renders: (1) a sortable leaderboard by stars and momentum score, (2) a category breakdown chart using Plotly, (3) a rising stars view sorted by momentum_score, (4) a detail view when a repo is selected. Read only — never write to the database. Do not touch files outside the `dashboard/` folder and `contracts/`."

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

## Extending the project

The architecture is designed to grow without touching existing layers.

**Add a second data source** — implement a new ingestion module (e.g. `ingestion/pypi_client.py`) that writes to the same `raw_repos` schema. The transform and dashboard layers are unaffected.

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
