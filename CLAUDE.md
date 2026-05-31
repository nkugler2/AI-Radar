# AI Radar Project Context

This project has two goals:

1. Learn about using multiple claude code agents using Claude-Squad
2. Build a working application that tracks new AI projects on GitHub (across multiple languages, e.g. Python, JavaScript/TypeScript, and more)

Ensure that you provide useful insight not just to the goal of completing the project, but also what kinds of coding tasks are ideal to give multiple agents working at the same time in different git worktrees.

## What this project is
A data pipeline and dashboard tracking popular AI repositories on GitHub across multiple languages.

## Critical rule
Always read `contracts/schema.py` before writing any code that touches the database.
This is the single source of truth for all table names, field names, and the DB path.
Never hardcode table names or field types anywhere else.

## Stack
- Python, managed with uv
- DuckDB for storage
- Polars for transforms
- Streamlit + Plotly for the dashboard

## Project structure
- ingestion/   — GitHub API client and runner
- transform/   — cleaning and metrics logic
- dashboard/   — Streamlit app (read-only)
- contracts/   — shared schema (do not modify without team agreement)
- data/        — DuckDB file (gitignored)
