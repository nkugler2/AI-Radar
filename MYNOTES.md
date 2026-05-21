---
id: MYNOTES
aliases: []
tags: []
---

# My Changelog/Notes -> Claude Squad AI attempt

This note will act as a Changelog and a notes repository to understand what my agents are doing, when, and why

## 05-19-2026 - Running the 4 agent loop

### Steps taken today

I was making signifianct changes to the app today, recomended of course by AI. Here is a summary of the agents

Let me see if I can grab what was done for A and B as well

- couldn't find, but could find C and D

**Agent C**
ingestion/github_client.py

- Added import base64
- Added fetch_readme(full_name) — calls GET /repos/{full_name}/readme, base64-decodes the content field, truncates to 50,000 chars, returns "" on any error (404, network,
  etc.), always sleeps API_CALL_DELAY in the finally block
- Added fetch_readmes(repos) — loops through the repo list, calls fetch_readme per repo, prints "Fetching READMEs: N/total" progress, injects readme_content into each dict

ingestion/runner.py

- Imported fetch_readmes
- Added \_INSERT_COLUMNS = RAW_REPOS_COLUMNS + ["readme_content"] — necessary because RAW_REPOS_COLUMNS in schema.py doesn't include readme_content even though the SQL DDL
  does; this extends it locally without touching contracts/schema.py
- Updated INSERT_SQL to use \_INSERT_COLUMNS
- Updated \_row_tuple to append repo.get("readme_content", "") at the end (matching the column order in the schema)
- Added repos = fetch_readmes(repos) call in run_ingestion between fetch_all_topics and the DB write step

**Agent D**

1. Import — added RAW_CONTRIBUTORS_TABLE to the contracts.schema import (line 20).
2. load_contributors(repo_id) (lines 42–59) — @st.cache_data(ttl=300) function that queries raw_contributors for a given repo_id, ordered by contributions descending, limited
   to 10, returning a Polars DataFrame with login and contributions columns.
3. show_repo_detail() updates:
   - GitHub link (line 68) — st.link_button at the very top using full_name.
   - Topic badges (lines 82–83) — replaced ', '.join(topics) with backtick-wrapped inline code pills.
   - Top Contributors (lines 114–119) — subheader + load_contributors(repo_row['id']) call; falls back to "No contributor data." if empty.
   - README expander (lines 121–126) — st.expander("README", expanded=True) with st.markdown(readme_content) or a caption fallback.

There was a bug in this implemntation, specifically when trying to write the README.md files to the database. The agent never changed the schema.py, since it was told not to do that, but that meant there was a column that should have been there but wasn't.

I changed that, and I also implemnted a very basic cache system, where it does not download any README.md files if that repo was last read from in the last 24 hours. This way, I can do multiple runs in a day all using the same README.md.

### Next Steps

There are a couple of things that I need to test:

0. Restart the pipeline (it failed last time but I think I fixed it)
1. Test that the pipeline works, and that it completes even after the changes I made to implement readme.md files being downloaded.
2. test how the dashboard looks and functions with the readme changes and other dashboard changes

## 05-08-2026 - Changes to the dashboard

### Steps taken today

1. Used my "Next Steps" from 05-04-2026 as a prompt to make changes to the dashboard
2. changes were solid, but new changes need to be made based on the actual functionality that I want

### Next Steps

The functionality that I actually want is:

1. The Category Breakdown: This should show a bar graph with the count of each category, and each bar should show the percentage of the total repos. Selecting one bar shows a dataframe with those repos underneath, and selecting multiple bars makes a dataframe with those selected bars and a title to show what categories are selected. You should then be able to select **multiple** repos and have each one appear below the dataframe. right now you can select one and only it appears. being able to select multiple repos would allow someone to compare repos within one cateogry, or accross several categories.

2. The Leaderboard: A way to see the top repo's for any selection of categories. the current way of filtering is bad, maybe a check box system where you can select all or select none would be better. This is just a way to see what is at the top at any one moment that you can filter by things like stars, momentum, etc. Right now I have Leaderboard and Category breakdown, but htye both kind of do the same thing. The Category Breakdown Should be first, as it is a way to see the distribution of repos across categories. The Leaderboard should then show the top repos for the selected categories.

3. Rising stars: right now, rising stars is being judged by momentum score. that isnt working, because things like Autogpt are taking the lead there, which just makes it the same view as the leaderboard or the category breakdown. in addition, autogpt is over 1000 days old, and is thus not a good representation of the rising stars. the rising stars is arguabblly the most important view - it is what allows me to track new and interesting projects that are worth my attention. so things that are new, maybe I can have a slider or drop down to say how long ago i want to look back, and it can show me repos created within that past time that have high momentum scores. then I can really have soemthing that tracks new repos I should look into.

4. Repo detail: the current repo detail tab is useless, there is nothing useful there. But on the topic of repo details, my current implementation shows me the names and basic descriptions, but I cant get a vibe of what the repos actually are. Can i pull the readme.md files and display them, or at least the markdown output? Is there other useful info I can put for when you select a certain repository that would help me understand them?

I should put all of this back into ai and get some feedback on what my goals are and what will actually be useful.

## 05-04-2026 - Changing to using main.py

### Steps Taken Today

0. Commited MYNOTES and MYREADME changes (minor)
1. Changed the running of the pipeline to only use main.py - `uv run python main.py`

## 03-30-2026 - Inital commit and merge of changes

I reviewed the work of the three agents, made changes where I thought needed, and am now ready to merge them all into main.

### Steps Taken Today

1. Committed each worktree using lazygit within that specific worktree
2. Went back to master and then merged the three worktrees. Kept the worktrees since I knew there would be bugs I needed to fix.
3. Ran scripts for ingestion -> transformation -> Dashboard
4. Fixed a type error in the transformation script
5. Got Dashboard working
6. Fixed Dashboard warning that came up in the terminal about a deprecated setting

### Next Steps

1. Improve Dashboard experience: - Add more interactive elements (e.g., filters, drill-downs). I should be able to click on something like AI Agents in the Category Breakdown and see a dataframe of just that topic. The leaderboard should have more sort by options, or just rely on the native dataframe sorting with the headings. Should not have a drop down in the Repo Detail tab. Should either have a search, or a way of getting to it from any of the dataframes.
2. Major Dashboard Fix: The side bar on the left is ugly, awful, and possibly useless. Need to do something completely different

## 03-23-2026 - Initial Run

This was from setting up the repo, the agent workflow, and starting the first run for each agent

**What Needs to be Checked**

- [x] Verify ingestion - github_client
- [x] Verify ingestion - runner
- [x] Verify transform - clean
- [x] Verify transform - metrics
- [x] Verify dashboard - app.py - didn't actuall check this, but will check after running if there are issues.

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
