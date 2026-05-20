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

# readme_content is in RAW_REPOS_SCHEMA but not in RAW_REPOS_COLUMNS (list used for inserts).
# Extend locally so we can write the field without touching contracts/schema.py.
_INSERT_COLUMNS = RAW_REPOS_COLUMNS + ["readme_content"]

# Insert or replace repo data -> called an "upsert" (update + insert)
# means if row already exist, delete and remake with new data. if doesn't exist, insert
# means we can run this multiple times without things breaking
INSERT_SQL = f"""
    INSERT OR REPLACE INTO {RAW_REPOS_TABLE} (
        {', '.join(_INSERT_COLUMNS)}
    ) VALUES (
        {', '.join('?' for _ in _INSERT_COLUMNS)}
    )
"""

# Convert out repo dicitonary to a tuple
def _row_tuple(repo: dict) -> tuple:
    """Convert a parsed repo dict into an ordered tuple for INSERT.

    Explanation: SQL needs values in a specific order (matching the RAW_REPOS_COLUMNS list). Our repo data is in a dictionary (unordered by nature). This function extracts values from the dictionary in the right order and returns them as a tuple.

      `tuple(repo[col] for col in RAW_REPOS_COLUMNS)` is a generator expression — it loops through each column name and pulls the corresponding value from the repo dictionary, then wraps everything in a tuple.

      Example: if repo = {"id": 123, "full_name": "user/repo", ...}, this returns (123, "user/repo", ...).

    """
    return tuple(repo[col] for col in RAW_REPOS_COLUMNS) + (repo.get("readme_content", ""),)


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

    log.info("Fetching README content for %d repos...", len(repos))
    repos = fetch_readmes(repos)

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
