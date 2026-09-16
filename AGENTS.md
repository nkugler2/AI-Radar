---
id: AGENTS
aliases: []
tags:
  - ai-radar
  - context
---

# AI Radar

## What this is

A daily-updating dashboard that surfaces rising AI repos on GitHub, ranked by
momentum and maintenance health. A pipeline ingests repo metadata from the
GitHub API across many languages (Python, JS/TS, C++, Rust, Go, Java, C#,
Jupyter), computes momentum/maintenance scores and categories, and a Streamlit
app reads the result. Solo project, ship-focused, and also a deliberate
learning vehicle.

## Critical rule — the schema is the contract

**Always read `contracts/schema.py` before writing any code that touches the
database.** It is the single source of truth for table names, field names,
types, the DB path, and tuning constants (momentum/maintenance weights, the
category map). Never hardcode a table or field name anywhere else. All three
layers code against this contract independently, so a change here ripples
everywhere — change it deliberately.

`contracts/scrub.py` is the companion contract: secret-detection patterns
applied to README text **before** anything is exported to the committed parquet.
Add a new secret type by adding one entry to `SECRET_PATTERNS` (see README).
Never bypass the scrub — third-party READMEs can contain real credentials.

## Stack

- **Python**, managed with **uv** (`uv sync`, `uv run …`).
- **DuckDB** — local analytical storage (`data/ai_radar.duckdb`, gitignored).
- **Polars** — transforms (no Pandas).
- **Streamlit + Plotly** — dashboard (read-only).
- `requests` + `python-dotenv` — GitHub API client; token from `.env`.
- ⚠️ **Python version:** local is 3.14, but **Streamlit Cloud caps at 3.12** —
  `pyproject.toml` pins `requires-python = ">=3.12"`. Don't use 3.13+-only
  syntax or the deploy breaks.

## Layout

| Path | What |
| --- | --- |
| `contracts/` | `schema.py` (source of truth) + `scrub.py` (secret patterns). Everything depends on this; change deliberately |
| `ingestion/` | `github_client.py` (API client, search, rate-limit retry, README fetch + TTL cache) + `runner.py` (orchestrates, writes `raw_repos`) |
| `transform/` | `clean.py` (Polars cleaning + scrub) + `metrics.py` (momentum/maintenance scores, category, writes `repos`) |
| `dashboard/` | `app.py` (Streamlit, **read-only**; dual-mode: DuckDB locally / parquet on Cloud) |
| `main.py` | Pipeline runner: ingestion → transform → parquet export. Modes: `full` / `rising_only` / `deep_only` |
| `data/` | `*.duckdb` gitignored; **`*.parquet` is committed** (it's what Streamlit Cloud reads) |
| `.github/workflows/` | `daily-rising` + `weekly-deep` cron Actions that run the pipeline and commit updated parquet |
| `notes/` | Project vault — [home](notes/HOME.md). Active plan: [plan-next-phases.md](notes/plans/plan-next-phases.md) (phases 1–5; 1 ✅, 2 ✅, phase 3 next) |

## Commands

```sh
uv sync                                  # install
uv run python main.py                    # full pipeline
uv run python main.py --mode rising_only # partial run (also: deep_only)
uv run streamlit run dashboard/app.py    # dashboard
```

Requires `.env` with `GITHUB_TOKEN=…` (classic PAT, `public_repo` scope).
Never commit `.env`.

## Gotchas (learned the hard way — see [notes/DEVLOG.md](notes/DEVLOG.md))

- **GitHub rate limits** bite on deep runs; READMEs are cached with a TTL so
  reruns reuse them. The deep GH Action can fail on limits — running locally
  with a warm cache is the fallback.
- **Parquet is the published artifact.** A transform that overwrites instead of
  merging can wipe repos from other run modes (a past bug); `rising_only` and
  `deep_only` runs must merge, not replace. `full` deliberately keeps
  full-refresh semantics — it's the intentional clean-slate rebuild.
- **Determinism matters:** scores must be reproducible run-to-run for trend
  tracking — avoid rank-based / cohort-dependent formulas.

## Learning mode: OFF

<!-- ON | OFF - set this line; leave the rest of the section as written.

When ON, the agent applies the five-rung learning ladder (`/learn`)
AUTOMATICALLY, without being asked, in three contexts:

  1. breaking down a question Noah asks,
  2. teaching a concept while Noah is deciding what to build,
  3. pushing back on an idea.

Discretion governs DEPTH, never whether: a small question gets the compressed
form, a subsystem gets the full ladder.

It never fires at the end of a phase, or after a batch of edits, at any flag
setting. Phases end at the devlog entry and the /phase-complete report; Noah
runs /learn himself when he wants a phase's work explained.

Foundational explanations (architecture, whole subsystems) are written to
notes/explanations/<kebab-topic>.md and linked in that folder's MOC;
day-to-day answers stay in the terminal.

When OFF, none of the above happens unprompted - `/learn` still works on
demand. Operational spec: ~/Developer/ai/claude/skills/learn/SKILL.md. -->
