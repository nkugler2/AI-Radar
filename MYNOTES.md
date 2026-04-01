---
id: MYNOTES
aliases: []
tags: []
---

# My Changelog/Notes -> Claude Squad AI attempt

This note will act as a Changelog and a notes repository to understand what my agents are doing, when, and why

## 03-30-2026 - Inital commit and merge of changes

I reviewed the work of the three agents, made changes where I thought needed, and am now ready to merge them all into main.

## 03-23-2026 - Initial Run

This was from setting up the repo, the agent workflow, and starting the first run for each agent

**What Needs to be Checked**

- [x] Verify ingestion - github_client
- [x] Verify ingestion - runner
- [x] Verify transform - clean
- [x] Verify transform - metrics
- [ ] Verify dashboard - app.py - didn't actuall check this, but will check after running if there are issues.

### Ingestion

⏺ Both files import cleanly. Here's what was built:

ingestion/github_client.py

- search_repos(topic, language, limit) — searches GitHub's search API for repos by topic+language, with pagination
- parse_repo(raw) — maps GitHub API response fields to the raw_repos schema columns exactly
- fetch_all_topics(language, limit) — iterates all SearchTopic values, deduplicates by repo ID, returns parsed rows
- \_request_with_retry() — handles 403/429 rate limiting with exponential backoff, respects Retry-After header
- All config (API_CALL_DELAY, API_MAX_RETRIES, DEFAULT_REPO_LIMIT, SearchTopic, Language) is read from contracts/schema.py

ingestion/runner.py

- run_ingestion(language, limit) — full pipeline: init_db() → fetch_all_topics() → INSERT OR REPLACE into raw_repos
- Uses get_connection() and init_db() from contracts
- Runnable directly: uv run python -m ingestion.runner

To run it you'll need a .env file with GITHUB*TOKEN=ghp*... in the project root.

### Transform

⏺ Everything works. Here's what was built:

transform/clean.py

- read_raw_repos() — reads the raw_repos DuckDB table into a Polars DataFrame using get_connection() from the schema contract
- clean(df) — drops forks, removes rows missing id/full_name/created_at, fills null numerics with 0, ensures topics is never null, and deduplicates by id keeping
  the most recent fetch
- run() — entry point that chains read → clean

transform/metrics.py

- compute_metrics(df) — joins contributor/release data from raw tables, then computes:
  - repo_age_days, days_since_push, stars_per_day, fork_to_star_ratio
  - contributor_count, release_count, latest_release_date, days_since_release
  - momentum_score — weighted sum (using MOMENTUM_WEIGHTS) of rank-normalized stars/day, push recency, fork ratio, and issue activity
  - maintenance_score — weighted sum (using MAINTENANCE_WEIGHTS) of push recency, recent-release bonus, and an open-issues proxy for issue close ratio
  - category — first-match from TOPIC_TO_CATEGORY, defaults to AICategory.OTHER
- write_repos(df) — creates the repos table if needed, deletes all existing rows, and inserts the scored DataFrame (clean overwrite on re-runs)
- run() — full pipeline: clean → metrics → write, returns row count

All table names, column names, DB path, weights, and category mappings come from contracts/schema.py — nothing is hardcoded.

### Dashboard

⏺ Syntax is clean. Here's what was built in dashboard/app.py:

Four views, all read-only:

1. Leaderboard — sortable table (stars / momentum_score / maintenance_score) showing repo name, category, stars, forks, both scores, and days since push.
   Filtered by sidebar category selector.
2. Category Breakdown — Plotly bar or pie chart (user-togglable) of repo counts per category, using unfiltered data. Sidebar multiselect filters the other
   views.
3. Rising Stars — top 20 by momentum_score, plus a scatter plot of stars vs momentum for the top 50. Filtered by category.
4. Repo Detail — select any repo to see all fields: description, homepage, license, topics, stars, forks, open issues, days since push, both computed scores,
   stars/day, age, fork-to-star ratio, contributor count, release info, and archive status.

Key design decisions:

- All table/path constants come from contracts.schema — nothing hardcoded
- DB opened with read_only=True via get_connection()
- Data cached with @st.cache_data(ttl=300) for 5-minute refresh
- No Pandas — Polars for data handling, .to_dict(as_series=False) for Plotly, Polars DataFrames directly to st.dataframe()
- Defensive column checks so the app won't crash if the transform agent hasn't populated all fields yet

Run with: streamlit run dashboard/app.py
