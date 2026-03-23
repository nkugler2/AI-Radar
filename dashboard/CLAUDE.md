# Dashboard agent context

## Your scope
You own `dashboard/` only. Do not modify files outside `dashboard/` or `contracts/`.

## Your job
Build `dashboard/app.py` as a Streamlit application that reads from the `repos`
DuckDB table and presents the data through four views.

## Key details

### Hard rules
- Read only — never write to, update, or delete from any DuckDB table
- Never call the GitHub API or any external network resource
- Never import from `ingestion/` or `transform/` — only from `contracts/` and
  standard libraries
- Load DB path from `contracts/schema.py` — never hardcode it

### The four views to build

**1. Leaderboard** — sortable table of all repos. Default sort by stars descending.
Allow the user to re-sort by momentum_score or maintenance_score. Show columns:
repo name, category, stars, forks, momentum score, maintenance score, days since push.

**2. Category breakdown** — Plotly bar or pie chart showing how many repos fall
into each category. Let the user use this as a filter that updates the leaderboard.

**3. Rising stars** — top 20 repos sorted by momentum_score descending. Emphasis
on projects that are newer but growing fast, not just the highest absolute star counts.

**4. Repo detail** — when a repo is selected from the leaderboard or rising stars
view, show a detail panel with all available fields: description, homepage link,
topics, license, open issues, forks, days since push, and both computed scores.

### Libraries
- Streamlit for the app shell, layout, and controls
- Plotly for all charts — use plotly.express for straightforward charts
- DuckDB Python client for queries
- Do not use Pandas — read query results directly into Polars or native Python
  structures if transformation is needed before rendering
