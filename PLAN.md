---
id: PLAN
aliases: []
tags: []
---

# AI Radar — Next-Phase Implementation Plan

Written 2026-06-04. Covers the next 5 phases of work. Each phase is independently shippable: you can stop after any phase and the project still works end-to-end.

## Why this order

1. **Momentum must be absolute before snapshots are meaningful.** Today's score is rank-normalized — the same repo gets a different score every run depending on the cohort. Snapshotting that produces noise, not signal. Fix the formula first.
2. **Snapshots unblock trend charts.** Once they exist and accumulate, the dashboard rebuild has data to show.
3. **Dashboard rebuild is the user-facing payoff.** Includes the 06-01 cleanup (kill the pie chart, % labels, dropdown).
4. **Observability is small but high-value.** Easy to layer in after the big work is done.
5. **Category mapping fix is isolated.** Can ship anytime, but parking it last keeps earlier phases focused.

---

## Phase 1 — Make momentum scoring absolute

**Why:** `transform/metrics.py:162-166` uses `pl.col(...).rank("ordinal") / pl.col(...).count()`. The same repo will get a different score across runs because the rank depends on what else was ingested. Trend tracking is meaningless until this is fixed.

### Build

1. In `contracts/schema.py`, add normalization constants near `MOMENTUM_WEIGHTS`:
   ```python
   # Caps used to normalize raw signals into [0, 1] without ranking.
   # Tune these by spot-checking the top-20 — values here are calibrated
   # so the established giants land near 1.0 on each component.
   MOMENTUM_NORM = {
       "stars_per_day_cap": 100.0,    # log10-scaled; 100 sp/d → ~1.0
       "fork_ratio_cap": 0.5,         # forks/stars ≥ 0.5 → 1.0
       "open_issues_cap": 1000,       # log10-scaled
   }
   ```

2. In `transform/metrics.py:159-177`, replace the rank-based components with absolute formulas:
   - `spd_norm`: `min(log10(stars_per_day + 1) / log10(STARS_PER_DAY_CAP + 1), 1.0)`
   - `push_bonus`: keep as-is (already absolute)
   - `fr_norm`: `min(fork_to_star_ratio / FORK_RATIO_CAP, 1.0)`
   - `ia_norm`: `min(log10(open_issues + 1) / log10(OPEN_ISSUES_CAP + 1), 1.0)`
3. Add a short comment block explaining why log-scaling: star-velocity is heavy-tailed (autogpt vs an obscure repo can differ by 1000×), and linear normalization makes 99% of repos score near 0.

### Verify

- [ ] Run `uv run python main.py --mode deep_only` against the current DB.
- [ ] Spot-check the top 20 by `momentum_score` — should be qualitatively similar to today's ranking (a few shifts are expected and desired).
- [ ] Run transform twice in a row **with no new ingestion**. Diff the `momentum_score` column — it should be byte-identical the second time. (Today, because of rank ties' nondeterminism, it might shift slightly. After the fix, it must not.)
- [ ] Write a quick scratch test (or just compute by hand in a Python REPL) that confirms: given fixed inputs, `compute_metrics` produces the same score regardless of how many other rows are in the DataFrame.

**Definition of done:** Same raw inputs → same `momentum_score`, run-to-run, cohort-independent.

---

## Phase 2 — Daily snapshots into `repo_snapshots`

**Why:** The schema is already there (`contracts/schema.py:321-332`). Writing to it is the unlock for every trend feature. Starts fresh from today — no backfill.

### Build

1. In `transform/metrics.py`, add a `write_snapshot()` function:
   ```python
   def write_snapshot(df: pl.DataFrame) -> int:
       """Write today's row to repo_snapshots for every repo in df.
       Idempotent: re-running the same day overwrites that day's row."""
   ```
   - Take the columns `id`, `stars`, `forks`, `open_issues`, `momentum_score`, `maintenance_score`.
   - Add `snapshot_date = today UTC` (date, not datetime).
   - `INSERT OR REPLACE INTO repo_snapshots` keyed on `(repo_id, snapshot_date)`. Multiple runs same day → last write wins.
2. Call `write_snapshot(scored)` from `run()` in `transform/metrics.py` after `write_repos(scored, ...)`. Return both counts.
3. In `main.py`, log the snapshot row count separately from the transform row count.
4. In `main.py` Step 3 (Parquet export), also export `repo_snapshots` to `data/snapshots.parquet`. Add `SNAPSHOTS_PARQUET_PATH` to `contracts/schema.py`.
5. Confirm `.gitignore` already tracks `data/*.parquet` (it should — README says it does).
6. No workflow changes needed — both `daily-rising.yml` and `weekly-deep.yml` will pick up snapshot writes automatically through `main.py`.

### Verify

- [ ] Run `uv run python main.py --mode deep_only` locally. Confirm `repo_snapshots` has one row per repo with today's date.
- [ ] Run it again the same day. Confirm row count in `repo_snapshots` did not double — the same (repo_id, today) keys were replaced.
- [ ] Confirm `data/snapshots.parquet` was written.
- [ ] In DuckDB CLI: `SELECT snapshot_date, COUNT(*) FROM repo_snapshots GROUP BY snapshot_date;` — should show only today's date with the expected repo count.
- [ ] Commit, push, watch the next scheduled daily-rising run on GitHub Actions complete and commit a `snapshots.parquet` update.

**Definition of done:** Every pipeline run produces a snapshot row per repo per day. Same-day reruns are idempotent. Parquet is exported for Streamlit Cloud.

---

## Phase 3 — Dashboard rebuild for trends + 06-01 cleanup

**Why:** This is where snapshots become visible to the user. Bundle the 06-01 cleanup items (kill pie chart, % labels, slider→dropdown) into the same pass so the dashboard ships as one coherent change.

Note: snapshots accumulate one row per repo per day. The first time you ship this, **the trend tabs will look almost flat** — you need a few days of accumulation before they're useful. Ship anyway; the data builds up.

### Build

#### 3a. Load snapshots

1. In `dashboard/app.py`, add `load_snapshots()` (cached, `ttl=300`) following the dual-mode pattern of `load_repos()` at `dashboard/app.py:30-56`. Reads from `repo_snapshots` table locally or `snapshots.parquet` on Cloud.
2. Join in `full_name`, `category`, `language` from `df` (loaded repos) so trend charts can filter and color by those without re-querying.

#### 3b. Cleanup the existing tabs

3. **Category Breakdown tab** (`dashboard/app.py:209-308`):
   - Delete the Bar/Pie radio control and the pie branch (`dashboard/app.py:240-255`).
   - On the remaining bar chart, add text labels showing each bar's % of the total. Use `text_auto` or compute a `percent` column and pass it to `px.bar(..., text="percent")`.
4. **Rising Stars tab** (`dashboard/app.py:376-444`):
   - Replace the `st.slider` for age (`dashboard/app.py:383-389`) with `st.selectbox` showing presets: "Last 30 days", "Last 90 days", "Last 180 days", "Last year", "All time". Map each to an int days value.

#### 3c. Add two new tabs

5. **Category Trends tab.** New tab between "Category Breakdown" and "Leaderboard":
   - Multi-select categories (default: all).
   - Date range selectbox: "Last 30/90/180 days, All time".
   - Plotly line chart: x = `snapshot_date`, y = count of repos per category that day, color = category.
   - Below the chart: a table of week-over-week % change per category, sortable.
6. **Repo Trends tab.** New tab after "Rising Stars":
   - Search input + multi-select for repos (limit 10 selected at a time to keep the chart readable).
   - Metric selector: stars / momentum_score / maintenance_score / open_issues.
   - Plotly line chart: one line per selected repo, x = `snapshot_date`, y = chosen metric.
   - Persist selection in `st.session_state` so switching metrics doesn't lose the repo list.

#### 3d. Final tab order

`Category Breakdown | Category Trends | Leaderboard | Rising Stars | Repo Trends | Repo Detail`

### Verify

- [ ] Local: launch dashboard with `uv run streamlit run dashboard/app.py`. Confirm pie chart toggle is gone, bar chart shows %, Rising Stars uses a dropdown.
- [ ] Both new trend tabs render without error even on day-1 (single snapshot date) — they should show single-point "lines" gracefully, not crash.
- [ ] After 3+ days of snapshots, confirm trend lines actually have shape.
- [ ] Multi-select 3 repos in Repo Trends, switch the metric dropdown, confirm the selection persists.
- [ ] On Streamlit Cloud after the next push, confirm both new tabs load from `snapshots.parquet`.

**Definition of done:** Dashboard has both trend tabs, pie chart is gone, slider is gone, bars show %, and everything works on Cloud.

---

## Phase 4 — Pipeline observability

**Why:** You flagged the "how long did each run take" gap on 06-01. Pairs naturally with a "data last updated" banner so users know if the Cloud data is fresh.

### Build

1. In `contracts/schema.py`, add a new table:
   ```python
   PIPELINE_RUNS_TABLE = "pipeline_runs"
   PIPELINE_RUNS_SCHEMA = f"""
   CREATE TABLE IF NOT EXISTS {PIPELINE_RUNS_TABLE} (
       id              VARCHAR PRIMARY KEY,           -- uuid
       mode            VARCHAR NOT NULL,              -- full/rising_only/deep_only
       started_at      TIMESTAMP NOT NULL,
       ended_at        TIMESTAMP NOT NULL,
       duration_sec    INTEGER NOT NULL,
       ingestion_count INTEGER,
       transform_count INTEGER,
       snapshot_count  INTEGER,
       status          VARCHAR NOT NULL               -- 'success' | 'failure'
   );
   """
   ```
   Add to `ALL_SCHEMAS`.
2. In `main.py`, wrap the pipeline in a try/except and timing block. Insert one row at the end (success) or on failure.
3. Export `pipeline_runs` to `data/pipeline_runs.parquet` alongside the other parquets.
4. In `dashboard/app.py`, add a small banner at the very top (under `st.title`):
   ```
   Last updated: 2026-06-04 06:00 UTC · deep_only · 1,234 repos · 12m 30s
   ```
   Loaded from the most recent successful row in `pipeline_runs`.
5. (Optional, low-effort add) In the same banner, show a 🟢/🟡/🔴 indicator based on age:
   - 🟢 < 36h since last run
   - 🟡 36h–72h
   - 🔴 > 72h

### Verify

- [ ] Run `uv run python main.py --mode rising_only` locally. Confirm one row appears in `pipeline_runs` with a sensible `duration_sec`.
- [ ] Force a failure (e.g. temporarily break a query) and confirm a `status='failure'` row is written.
- [ ] Banner renders on dashboard with correct values.
- [ ] After the next scheduled GH Action, confirm Cloud picks up the freshness banner.

**Definition of done:** Every run logs timing. Dashboard banner shows freshness with a status indicator.

---

## Phase 5 — Smarter category mapping

**Why:** `transform/metrics.py:48-52` does "first match wins" against a flat dict. A repo tagged `[chatgpt, rag]` becomes LLM (less specific) instead of RAG (more specific). Same problem for any repo with both a framework tag and a use-case tag.

### Build

1. In `contracts/schema.py`, restructure `TOPIC_TO_CATEGORY`. Two options — pick one based on which you prefer:

   **Option A — Specificity-ranked (recommended, simpler):**
   ```python
   # (category, specificity) — higher specificity wins when multiple topics match.
   # Use-case categories (RAG, AGENTS, IMAGE_GEN) are more specific than
   # ecosystem categories (LLM, ML_FRAMEWORK) — they describe what the repo
   # does, not just what stack it uses.
   TOPIC_TO_CATEGORY: dict[str, tuple[AICategory, int]] = {
       "rag": (AICategory.RAG, 3),
       "retrieval-augmented-generation": (AICategory.RAG, 3),
       "agents": (AICategory.AGENTS, 3),
       "ai-agents": (AICategory.AGENTS, 3),
       "stable-diffusion": (AICategory.IMAGE_GEN, 3),
       "text-to-image": (AICategory.IMAGE_GEN, 3),
       "llm": (AICategory.LLM, 2),
       "gpt": (AICategory.LLM, 2),
       "chatgpt": (AICategory.LLM, 2),
       "computer-vision": (AICategory.COMPUTER_VISION, 2),
       "nlp": (AICategory.NLP, 2),
       # ... ecosystem-level fallbacks at specificity 1
       "machine-learning": (AICategory.ML_FRAMEWORK, 1),
       "pytorch": (AICategory.ML_FRAMEWORK, 1),
       # ...
   }
   ```

   **Option B — Multi-label (heavier, future-proof):** add a `secondary_category` column to the repos schema. Skip if you don't want a schema migration right now.

2. In `transform/metrics.py:34-52`, update `_assign_category` to iterate topics, collect all matches, pick the one with the highest specificity. Tie-break alphabetically for determinism.
3. Run transform; eyeball the category distribution before/after.

### Verify

- [ ] Pick 5 known multi-tagged repos (e.g. a langchain+rag repo, a chatgpt+agents repo) and confirm they land in the more-specific category.
- [ ] Aggregate count of each category before vs after — expect counts to shift from LLM/ML_FRAMEWORK toward RAG/AGENTS.
- [ ] Run twice; confirm category assignments are deterministic (tie-break by name works).

**Definition of done:** Multi-tagged repos route to their most specific category. Distribution shifts in the expected direction.

---

## Out of scope for this plan (parked for later)

These were considered and explicitly deferred:

- **Contributor + release ingestion.** Schemas exist; transforms already wait for them. Worth doing, but it adds API budget cost and the trend work is higher value.
- **Alerting for fast-trending repos.** Needs snapshots to exist *and* a chosen destination (email / GitHub issue / dashboard banner). Revisit after Phase 3 is live and snapshots have accumulated.
- **PyPI download trend integration.** A second ingestion source — sensible after the trend infrastructure is solid for GitHub data alone.
- **Prefect / orchestration migration.** GitHub Actions is working. Don't migrate until it breaks.
- **Schema migrations tooling.** `SCHEMA_VERSION` exists but no migration runner. Worth doing once you've shipped 2-3 column additions and feel the pain.

---

## Phase order recap

| Phase | What | Verifies trend integrity? | User-visible? |
|-------|------|--------------------------|---------------|
| 1 | Fix momentum to absolute formula | Yes (blocks 2) | No |
| 2 | Write daily snapshots | Yes (blocks 3) | No |
| 3 | Dashboard rebuild + 06-01 cleanup | — | Yes (big) |
| 4 | Pipeline timing + freshness banner | — | Yes (small) |
| 5 | Smarter category mapping | — | Yes (distribution shift) |
