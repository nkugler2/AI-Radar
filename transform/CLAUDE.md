# Transform agent context

## Your scope
You own `transform/` only. Do not modify files outside `transform/` or `contracts/`.

## Your job
1. `clean.py` — reads raw data from the `raw_repos` DuckDB table, cleans nulls,
   drops malformed records, and normalizes field types using Polars
2. `metrics.py` — computes derived analytical columns and writes the final clean
   dataset to the `repos` table

## Key details

### Input
- Read from `raw_repos` table only — schema is defined in `contracts/schema.py`
- Never touch the GitHub API or any external network resource
- Never read from the `repos` table (that is your output, not your input)

### Transforms to compute
- `momentum_score` — stars divided by age in days since repo creation. Higher means
  faster growth relative to how long the project has existed.
- `maintenance_score` — derived from recency of last push (65%) and ratio of open to
  total issues (35%). A repo with recent pushes and low open issue ratio scores higher.
  Weights are defined in `MAINTENANCE_WEIGHTS` in `contracts/schema.py`.
- `days_since_push` — integer days between `pushed_at` and the current date
- `category` — assigned from the `topics` array using the `TOPIC_TO_CATEGORY` mapping
  from `contracts/schema.py` — it is authoritative. Categories are: LLM, RAG, Agents,
  Computer Vision, NLP, ML Framework, Image Generation, Data/ML Ops, Other.
  If multiple tags match, use the first match.

### Output
- Write to `repos` table only — schema is defined in `contracts/schema.py`
- The `repos` table is the single source of truth for the dashboard layer
- Always overwrite cleanly — do not append duplicate rows on re-runs

### Libraries
- Use Polars for all DataFrame operations — not Pandas
- Use DuckDB Python client for reading and writing
- Load DB path from `contracts/schema.py` — never hardcode it
