"""
ingestion/runner.py

Orchestrates the ingestion pipeline: fetches repos from GitHub,
creates the basicConfig for logging, and writes raw rows into
DuckDB using the raw_repos schema.
"""

# -- Imports ------------------------------------------------

# Allows for modern type annotation syntax in Python
# ex/ str | int
from __future__ import annotations

import logging
import sys

# Values from the contracts/schema file, should not be hardcorded here
from contracts.schema import (
    RAW_REPOS_TABLE,
    RAW_REPOS_COLUMNS,
    RAW_REPOS_SCHEMA,
    init_db,
    get_connection,
)
from ingestion.github_client import fetch_all_topics, fetch_readmes

# basicConfig sets up logging for the entire program:
#    - level=logging.INFO — show INFO messages and above (INFO, WARNING, ERROR). DEBUG messages are hidden.
#    - format=... — controls what each log line looks like. %(asctime)s = timestamp, %(levelname)s = INFO/WARNING/etc., %(name)s = which module, %(message)s = the actual message.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
log = logging.getLogger(__name__)

INSERT_SQL = f"""
    INSERT OR REPLACE INTO {RAW_REPOS_TABLE} (
        {', '.join(RAW_REPOS_COLUMNS)}
    ) VALUES (
        {', '.join('?' for _ in RAW_REPOS_COLUMNS)}
    )
"""


def _row_tuple(repo: dict) -> tuple:
    return tuple(repo.get(col) for col in RAW_REPOS_COLUMNS)


def _load_cached_readmes(con, repo_ids: list[int]) -> dict[int, str]:
    """Return {repo_id: readme_content} for repos fetched within the last 24 hours."""
    if not repo_ids:
        return {}
    rows = con.execute("""
        SELECT id, readme_content
        FROM raw_repos
        WHERE id = ANY(?)
          AND readme_content IS NOT NULL
          AND fetched_at >= NOW() - INTERVAL '24 hours'
    """, [repo_ids]).fetchall()
    return {row[0]: row[1] for row in rows}


# Run the actual ingestion
def run_ingestion(language: str = "python", limit: int | None = None) -> int:
    """Run a full ingestion cycle.

    1. Ensure the DB and tables exist.
    2. Fetch repos from GitHub for all configured topics.
    3. Upsert rows into raw_repos.

    Returns the number of rows written as an integer.
    """
    # Fetch the number of repos allowed. If not provide, use the setting defined in the contracts/schema.py file
    from contracts.schema import DEFAULT_REPO_LIMIT

    limit = limit or DEFAULT_REPO_LIMIT

    # log db creation
    log.info("Initializing database...")
    # create the db
    init_db()

    # log the grabbing of repos
    log.info("Fetching repos from GitHub (language=%s, limit=%d per topic)...", language, limit)
    # the actual fetching of repos
    repos = fetch_all_topics(language=language, limit=limit)

    # log warning if nothing was fetched from github. It's not an error case, as the topics may be updated over time.
    if not repos:
        log.warning("No repos fetched — nothing to write.")
        return 0

    # Load cached READMEs from the last 24 hours so we skip those API calls
    con = get_connection()
    cached = _load_cached_readmes(con, [r["id"] for r in repos])
    con.close()

    for repo in repos:
        if repo["id"] in cached:
            repo["readme_content"] = cached[repo["id"]]

    uncached = [r for r in repos if "readme_content" not in r]
    log.info("README cache: %d cached, %d to fetch", len(cached), len(uncached))

    if uncached:
        uncached = fetch_readmes(uncached)
        fetched_map = {r["id"]: r for r in uncached}
        repos = [fetched_map.get(r["id"], r) for r in repos]

    # log the writing of data into duckdb
    log.info("Writing %d repos to %s...", len(repos), RAW_REPOS_TABLE)

    # Where we write to the database
    con = get_connection()
    # use try/finally to ensure con.close() runs even on error
    try:
        # Ensure table exists (idempotent) - just in case it wasn't created, it is ok to be here
        con.execute(RAW_REPOS_SCHEMA)

        # uses our _row_tuple function to convert repo dictionaries to our tuples
        rows = [_row_tuple(r) for r in repos]
        # runs our actual insert
        con.executemany(INSERT_SQL, rows)
        # the number of items in the list rows. The length is the total inserted/replace
        log.info("Successfully wrote %d rows.", len(rows))
        return len(rows)
    finally:
        con.close()


# make sure this is a runable script and something that can be imported
if __name__ == "__main__":
    count = run_ingestion()
    log.info("Ingestion complete — %d repos ingested.", count)
    # tell the operating system that we are done
    sys.exit(0)
