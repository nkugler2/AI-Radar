---
id: CLAUDE
aliases: []
tags: []
---

# AI Radar Project Context

This project has one goals:

1. Build a working application that tracks new AI projects on GitHub (across multiple languages, e.g. Python, JavaScript/TypeScript, and more)

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

- ingestion/ — GitHub API client and runner
- transform/ — cleaning and metrics logic
- dashboard/ — Streamlit app (read-only)
- contracts/ — shared schema (do not modify without team agreement)
- data/ — DuckDB file (gitignored)
- .github/workflows/ - Github action files

## Pedagogy

This project's goal is to ship something cool with AI. I want all answers to my prompts to work towards shipping. However, building this project is also a learning experience. It is learning how to build software, how to think about products and who uses them, and also how to work effectively with AI. In that vane, I would like you to explain things to me in a way that helps me learn. Your answers to my prompts should be primarily centered around and focused on shipping, but they can be framed in the way a teacher would, explaining concepts, why they are important, and how they impact the decisions we are making as we are building and running production.
