---
id: MYNOTES
aliases: []
tags: []
---

# My Changelog/Notes -> Claude Squad AI attempt

This note will act as a Changelog and a notes repository to understand what my agents are doing, when, and why

## 06-09-2026 - Secret scrubbing + Rising Stars dashboard fix

### Steps taken today

1. Added a secret-scrubbing layer (`contracts/scrub.py`) with 8 regex patterns covering the most common leaked credential types: GitHub tokens, AWS access keys, OpenAI/Anthropic API keys, PEM private key headers, Slack tokens, Stripe live keys, and Google API keys
2. Ingestion now logs a WARNING block after each README fetch showing which repos had matches, what pattern fired, and a redacted sample — so you can audit what would have been scrubbed without touching the data
3. Transform (`clean.py`) applies the actual scrub before writing to the `repos` table and parquet — replacements use the format `[AI-Radar: {pattern_name} redacted]`. Raw DuckDB data is intentionally left untouched (it's local-only and not published)
4. Fixed a silent inconsistency in the Rising Stars tab: the dataframe showed the top 20 repos by momentum but the chart showed the top 50, so repos that appeared in the visualization were missing from the table. Replaced both hardcoded limits with a single slider (default 20, range 5–100) so the two views are always in sync

### Why this matters

README files from GitHub repos can contain real secrets that their authors accidentally committed. Since this project fetches and publishes those READMEs to a public parquet file, scrubbing before export is a necessary safety measure.

## 06-08-2026 - Parallelization fix for the weekly deep run

### Steps taken today

1. The weekly deep GitHub Action was consistently timing out at the 1-hour mark because fetching READMEs for hundreds of repos sequentially was too slow. Fixed by adding parallelization to the ingestion layer and adding a TTL-based cache so READMEs already fetched recently are not re-downloaded
2. Added `README_CACHE_TTL_HOURS` constant to `contracts/schema.py` to control the cache window
3. The GitHub Action for the deep search still hit the GitHub rate limit and failed on this run specifically. Ran the deep and rising-star modes locally instead — the README cache meant most files were already on disk, so the local run completed quickly and the parquet file was repopulated manually

## 06-04-2026 - Bug: daily run was wiping all repos from the parquet file

### Steps taken today

1. Discovered that the daily rising-stars run was overwriting the entire `repos` table with only the ~150 repos it fetched — deleting all the repos from the deeper weekly run
2. The bug was in `transform/metrics.py` (full table overwrite on every run) and `main.py` (no distinction between run modes when writing output)
3. Fixed both files so a `rising` mode run merges results into the existing table rather than replacing it
4. Had to manually trigger the weekly runner again after this fix to repopulate the data that was lost

## 06-03-2026 - Timeout fix, CLAUDE.md overhaul

### Steps taken today

1. Fixed the `daily-rising` GitHub Action timeout: it was set to 15 minutes, which was too short for the run. Increased to 60 minutes
2. Cleaned up `CLAUDE.md` — removed the multi-agent workflow instructions that were left over from the original project setup and replaced with guidance that leans the model toward teaching and explaining decisions as it helps build the project
3. Updated README to more accurately reflect the actual development process (iterating with AI agents) rather than describing it as a purely manual build

## 06-02-2026 - Multi Language branch committed - fixes need to be made to the daily runner

The branch has been fully merged (committed, pushed, pr created, pr merged). Tried to run the daily GitHub action and it failed due to taking too long. Changing that to 60 minutes and it should be fine.

### Things I want to add

**Add more languages** — add values to the `Language` enum in `contracts/schema.py` (the value must match GitHub's `language:` qualifier; multi-word names are quoted automatically). The ingestion agent reads `DEFAULT_LANGUAGES` dynamically, and the dashboard's language filter is populated from the data, so no transform or dashboard changes are needed.

**Add a second data source** — implement a new ingestion module (e.g. `ingestion/pypi_client.py`) that writes to the same `raw_repos` schema. The transform and dashboard layers are unaffected.

**Add trend tracking** — modify `raw_repos` to store multiple snapshots per repo over time (add a `fetched_at` index). The transform layer can then compute week-over-week star growth.

- [x] Multi-language support (JavaScript/TypeScript, C++, Rust, Go, Jupyter Notebook, C#, Java)
- [ ] Contributor data ingestion and scoring
- [ ] Release cadence tracking
- [ ] Time-series snapshots for trend tracking (check the prompt in 06-01-2026)
- [ ] PyPI download trend integration
- [ ] Scheduled ingestion with Prefect
- [ ] Week-over-week momentum tracking
- [ ] Alerting for fast-trending repos

## 06-01-2026 - Remote claude attempt at multi language - Failed so far due to hitting rate limits on GitHub

Made a new branch of the pipeline remotely on my phone. It seemed to have all worked, but when I ran the pipeline locally on my computer, it failed due to rate limiting. Pulled it locally to my computer, am able to switch between the main branch and this new branch. I need to figure out rate limiting for pulling from multiple languages.

### Notes for a later prompt on main

```md
I would like to add the ability to track repos accross time. Right now, every time my DB updates, it gets a fresh pull of the repos, but there is no historical tracking. I
would like to save data for each run, and then be able to show analysis of trends over time for different repos or differnt cateoriges, or in the future differnet languages.
How should I implement this?

Some of the things that I want are:

0. additions to the dashboard: I would like to have two options for the buttons in the category breakdown with better names. One button for the bar graph of the categories
   and add in the percent of the total onto each bar graph. I want the percentage on the bar graph to replace the pie graph, and I need you to delete that too. Then I want to
   add a new button that is for the line graph that shows the trend of these categories. You can also click into a category to see that catgegory alone over time, or can get a
   line graph of the top x amount of repos for that catgegory. I would also like to be able to select any number of repos and be able to show the trend line of different
   metrics for those repos.
1. any needed changes to the pipeline: i assume chaneges to the database will need to be made for this, as well as possibly changes to the github runner. I don't know, i am
   just assuming.

Make a plan for completing this
```

### Other things that I want

1. To say how much time each run of the pipeline took. Now that I have multiple ways to run it, I want to know how long each takes

## 05-30-2026 - Changed ingestion to surface newer repos

### Steps taken today

1. Noticed that the Rising Stars view was never showing repos younger than ~60 days. The root cause: ingestion only fetched the top 150 repos by stars, and no recently-created project ever ranks that high
2. Added a second ingestion pass in `runner.py` (`_fetch_recent_rising`) that specifically queries GitHub for repos created in the past 90 days, sorted by stars ascending — this surfaces new projects that are growing fast but haven't yet accumulated the total stars to appear in the main search
3. `github_client.py` got a small update to support the additional query parameters

### Why this matters

The whole point of Rising Stars is to find new, fast-growing projects before they become obvious. If ingestion only ever pulls the top repos by total stars, that view just becomes a second leaderboard. This change is what makes the Rising Stars tab actually useful.

## 05-21-2026 - On GitHub, with a GitHub Action, in a Streamlit Cloud hosted Dashboard

### Steps taken today

This is the culmination of many of the changes I made 2 days ago. It includes:

1. Making sure that README files are actually seen in the dashboard, which requried a breif database migration
2. Fixed a bug with the README files where HTML was not rendering correctly
3. Made changes to files for the move to streamlit cloud, github, and github actions, the changes are listed below

| File                                | Action                                                       |
| ----------------------------------- | ------------------------------------------------------------ |
| `.python-version`                   | Change 4.14 → 3.12 (Streamlit Cloud max)                     |
| `pyproject.toml`                    | Change `requires-python = ">=4.14"` → `>=3.12`               |
| `uv.lock`                           | Regenerate with `uv lock` after pyproject change             |
| `contracts/schema.py`               | Add `PARQUET_PATH` constant after `DB_PATH`                  |
| `main.py`                           | Add Step 4: export repos table to Parquet via DuckDB COPY    |
| `.gitignore`                        | Replace `data/` with `data/*.duckdb` (so Parquet is tracked) |
| `dashboard/app.py`                  | Dual-mode `load_repos()` + guarded `load_contributors()`     |
| `requirements.txt`                  | Create for Streamlit Cloud (`uv export --no-hashes`)         |
| `.github/workflows/update-data.yml` | Create: daily cron + manual trigger                          |

4. We also set up and tested the github actions
5. The dashboard is not hosted on streamlit, at https://ai-radar-dashboard.streamlit.app/

### Next Steps

Small changes:

1. Change slider for dates to some sort of drop down, just some easier way to do it

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

## 05-12-2026 - Major dashboard overhaul

### Steps taken today

1. Used the requirements I wrote in the 05-08 notes as a prompt and applied a large set of changes to `dashboard/app.py` (~150 lines changed)
2. Category Breakdown: bar chart is now clickable to filter repos, multi-select is supported, filtered repos appear in a dataframe below the chart, and you can select multiple repos from that dataframe to compare them side by side
3. Leaderboard: replaced the sidebar category dropdown with a checkbox grid (select all / clear all buttons) — much easier to use when filtering by multiple categories
4. Rising Stars: added the age slider so you can look back N days and only see repos created within that window, which ensures the view actually surfaces new projects rather than duplicating the leaderboard
5. Repo Detail: kept as a searchable tab, but detail is now surfaced inline from any tab rather than requiring a separate navigation step

## 05-11-2026 - First manual revision to the dashboard

### Steps taken today

1. Made the first pass of manual edits to `dashboard/app.py` after seeing the initial agent output running in the browser
2. Updated MYNOTES and README to capture the state of the project at this point

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

## 04-01-2026 - Merged all three worktree branches into master

### Steps taken today

1. Merged all three feature branches into master: `feature/ingestion-start`, `feature/transform`, `feature/dashboard-start`
2. Ran the full pipeline for the first time end-to-end: ingestion → transform → dashboard
3. Fixed a type error in the transform script that only surfaced after merging (types between the clean and metrics steps were mismatched)
4. Fixed a Streamlit deprecation warning in `dashboard/app.py`: replaced `use_container_width=True` with `width='stretch'`. Useful to know: `width='content'` is the equivalent of `use_container_width=False` if you ever need it

### Lesson learned

When running agent-generated code from separate worktrees together for the first time, expect type mismatches at the seams — each agent writes to contract types independently, but small assumptions can differ (e.g. what a nullable column looks like coming out of a Polars query). The fix is usually small, but you have to actually run the pipeline to find it.

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
