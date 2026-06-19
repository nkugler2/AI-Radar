---
id: AGENTS
aliases: []
tags: [ai-radar, context]
---

# AGENTS.md — AI Radar

Canonical project context for any AI coding agent. `CLAUDE.md` points here. Keep this lean and always-true; day-to-day notes go in `DEVLOG.md`, the active plan in `PLAN.md`.

## What this is

A data pipeline + Streamlit dashboard that tracks new and popular AI repositories on GitHub across many languages (Python, JS/TS, C++, Rust, Go, Java, C#, Jupyter). It ingests repo metadata from the GitHub API, computes momentum/maintenance scores and categories, and surfaces them in an interactive dashboard. Solo project, ship-focused, and also a deliberate learning vehicle.

## Critical rule — the schema is the contract

**Always read `contracts/schema.py` before writing any code that touches the database.** It is the single source of truth for table names, field names, types, the DB path, and tuning constants (momentum/maintenance weights, the category map). Never hardcode a table or field name anywhere else. All three layers code against this contract independently, so a change here ripples everywhere — change it deliberately.

`contracts/scrub.py` is the companion contract: secret-detection patterns applied to README text **before** anything is exported to the committed parquet. Add a new secret type by adding one entry to `SECRET_PATTERNS` (see README). Never bypass the scrub — third-party READMEs can contain real credentials.

## Stack

- **Python**, managed with **uv** (`uv sync`, `uv run …`).
- **DuckDB** — local analytical storage (`data/ai_radar.duckdb`, gitignored).
- **Polars** — transforms (no Pandas).
- **Streamlit + Plotly** — dashboard (read-only).
- `requests` + `python-dotenv` — GitHub API client; token from `.env`.
- ⚠️ **Python version:** local is 3.14, but **Streamlit Cloud caps at 3.12** — `pyproject.toml` pins `requires-python = ">=3.12"`. Don't use 3.13+-only syntax or the deploy breaks.

## Layout

- `contracts/` — `schema.py` (source of truth) + `scrub.py` (secret patterns). Everything depends on this; change deliberately.
- `ingestion/` — `github_client.py` (API client, search, rate-limit retry, README fetch + TTL cache) + `runner.py` (orchestrates, writes `raw_repos`).
- `transform/` — `clean.py` (Polars cleaning + scrub) + `metrics.py` (momentum/maintenance scores, category, writes `repos`).
- `dashboard/` — `app.py` (Streamlit, **read-only**; dual-mode: DuckDB locally / parquet on Cloud).
- `main.py` — pipeline runner: ingestion → transform → parquet export. Modes: `full` / `rising_only` / `deep_only`.
- `data/` — `*.duckdb` gitignored; **`*.parquet` is committed** (it's what Streamlit Cloud reads).
- `.github/workflows/` — `daily-rising` + `weekly-deep` cron Actions that run the pipeline and commit updated parquet.

## Commands

- Install: `uv sync`
- Run pipeline: `uv run python main.py` (add `--mode rising_only|deep_only` for partial runs)
- Dashboard: `uv run streamlit run dashboard/app.py`
- Requires `.env` with `GITHUB_TOKEN=…` (classic PAT, `public_repo` scope). Never commit `.env`.

## How we work

- **Phases:** the active plan is `PLAN.md` (phases 1–5). Work one phase at a time ("complete phase X of @PLAN.md") and finish with the **phase-complete** report. Each phase is independently shippable and has a "Definition of done".
- **Commits:** Conventional Commits (`feat:` / `fix:` / `docs:` / `chore:` / `refactor:`). Hand Noah a copy-paste message; he runs the commit. Don't auto-commit.
- **Devlog:** day-by-day notes live in `DEVLOG.md` (newest on top). Use `/log-today`.
- **Determinism matters:** scores must be reproducible run-to-run for trend tracking — avoid rank-based / cohort-dependent formulas (this is exactly what PLAN Phase 1 fixes).
- **Teach as you go:** ship first, but frame non-obvious decisions so Noah learns — the concept, why it matters, the trade-off.

## Gotchas (learned the hard way — see `DEVLOG.md`)

- **GitHub rate limits** bite on deep runs; READMEs are cached with a TTL so reruns reuse them. The deep GH Action can fail on limits — running locally with a warm cache is the fallback.
- **Parquet is the published artifact.** A transform that overwrites instead of merging can wipe repos from other run modes (a past bug); `rising` runs must merge, not replace.
