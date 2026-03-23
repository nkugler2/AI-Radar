# Ingestion agent context

## Your scope
You own ingestion/ only. Do not modify files outside ingestion/ or contracts/.

## Your job
1. github_client.py — search GitHub for repos, fetch metadata per repo
2. runner.py — orchestrate ingestion, write raw rows to DuckDB raw_repos table

## Key details
- Load GITHUB_TOKEN from .env using python-dotenv
- Use requests for all API calls
- Rate limit: 5000 req/hour authenticated. Use retry/sleep on 403 or 429.
- Write to raw_repos table only — schema is in contracts/schema.py
- The ingestion function signature should accept a query parameter so
  language filters can be changed without modifying logic
