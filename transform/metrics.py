"""transform/metrics.py — Compute derived metrics and write to the repos table.

This is the main logic file that deterines scoring and metrics for all of the projects pulled.

"""

from __future__ import annotations

import datetime

import polars as pl

from contracts.schema import (
    AICategory,
    MAINTENANCE_WEIGHTS,
    MOMENTUM_WEIGHTS,
    RAW_CONTRIBUTORS_TABLE,
    RAW_RELEASES_TABLE,
    REPOS_SCHEMA,
    REPOS_TABLE,
    TOPIC_TO_CATEGORY,
    get_connection,
)
# import from our transform/clean.py file
from transform.clean import run as clean_run


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# map topics made by repo author to my list of topics for sorting
# ex/ chatgpt, gpt, and llm are all now AICategory.LLM
def _assign_category(topics: list[str] | None) -> str:
    """Return the first matching AICategory value for *topics*, else OTHER.

        `topics` - a list of topics someone can add to their repo for discoverability, with each topic being a string
            - `topics` are not required

        We:
            1. Account for if `topics` is an empty list using truthy/falsy `if topics:` , i.e. topics were not entered by the repo author
            2. If there are topics, loop through them
            3. If one of those topics (as a string) matches one from my `TOPIC_TO_CATEGORY` dictionary, then we will use my new value
                ex/ "llm", "gpt", and "chatgpt" would all be changed to `AICategory.LLM`
            4. If there is no topic, or if there is no matching topic, we will use `AICategory.Other`

    """
    if topics:                                          # account for if topics is an empty list
        for topic in topics:                            # loop through each tag topic in the list
            if topic in TOPIC_TO_CATEGORY:              # if topic is one of my categories
                return TOPIC_TO_CATEGORY[topic].value   # use my corresponding word
    return AICategory.OTHER.value                       # else categorize as Other


def _get_contributor_counts() -> pl.DataFrame:
    """Aggregate contributor count per repo from raw_contributors."""
    # connect to the database
    con = get_connection()
    # try finally loop to make sure it closes
    try:
        return con.execute(
            # call repo_id id, then count distinct contribuotrs
            f"SELECT repo_id AS id, COUNT(*) AS contributor_count "
            # group contributor table by repo_id - one row per repo with a count
            f"FROM {RAW_CONTRIBUTORS_TABLE} GROUP BY repo_id"
        ).pl()
    finally:
        con.close()


# similar logic to get contributor, but also grab MAX published_at date
def _get_release_info() -> pl.DataFrame:
    """Aggregate release count and latest release date per repo."""
    con = get_connection()
    try:
        return con.execute(
            f"SELECT repo_id AS id, COUNT(*) AS release_count, "
            f"MAX(published_at) AS latest_release_date "
            f"FROM {RAW_RELEASES_TABLE} GROUP BY repo_id"
        ).pl()
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def compute_metrics(df: pl.DataFrame) -> pl.DataFrame:
    """Add all derived columns and scores to the cleaned DataFrame."""
    # grab the current time
    now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)

    # --- Join contributor / release data (graceful if tables are empty) ------
    # if raw_contributors doesn't exist yet, this would crash, so we put a try/except
    # we just catch the error and add a none value
    try:
        contributors = _get_contributor_counts()
        # left join: for every row in df, look for matching id in contributors
        # we keep every row from df even if there is no match (left join)
        df = df.join(contributors, on="id", how="left")
    except Exception:
        # creates literal None value, casts as correct thing for polars
        # NOTE ON with_columns: is immutable, creates a new Dataframe
        df = df.with_columns(pl.lit(None).cast(pl.Int64).alias("contributor_count"))

    # -- Release Data
    try:
        releases = _get_release_info()
        # another left join
        df = df.join(releases, on="id", how="left")
    except Exception:
        # None casted values as seen in contributors logic
        df = df.with_columns(
            pl.lit(None).cast(pl.Int64).alias("release_count"),
            pl.lit(None).cast(pl.Datetime).alias("latest_release_date"),
        )

    # column cleanup
    df = df.with_columns(
        pl.col("contributor_count").fill_null(0),
        pl.col("release_count").fill_null(0),
    )

    # --- Time-based columns --------------------------------------------------
    df = df.with_columns(
        # now compared to when repo was created to calculate repo age
        (pl.lit(now) - pl.col("created_at")).dt.total_days().alias("repo_age_days"),
        # now compared to latest pushed_at to see calculate days since pushed
        (pl.lit(now) - pl.col("pushed_at")).dt.total_days().alias("days_since_push"),
    )
    # column cleanup
    df = df.with_columns(
        # repo less then a day old is 1 day old
        pl.col("repo_age_days").fill_null(1).clip(lower_bound=1),
        # when there is no data since pushed, mark it as a very long time ago, makes sense for scoring
        pl.col("days_since_push").fill_null(9999),
    )

    # --- Ratio columns -------------------------------------------------------
    # Stars per day, fork-to-star ratio
    df = df.with_columns(
        (pl.col("stars").cast(pl.Float64) / pl.col("repo_age_days")).alias("stars_per_day"),
        pl.when(pl.col("stars") > 0)
        .then(pl.col("forks").cast(pl.Float64) / pl.col("stars"))
        .otherwise(0.0)
        .alias("fork_to_star_ratio"),
    )

    # --- Days since release --------------------------------------------------
    df = df.with_columns(
        pl.when(pl.col("latest_release_date").is_not_null())
        .then((pl.lit(now) - pl.col("latest_release_date")).dt.total_days())
        .otherwise(None)
        .cast(pl.Int32)
        .alias("days_since_release"),
    )

    # --- Momentum score ------------------------------------------------------
    # Each component is normalised to roughly [0, 1] before weighting.
    spd_norm = pl.col("stars_per_day").rank("ordinal") / pl.col("stars_per_day").count()
    push_bonus = 1.0 - pl.col("days_since_push").cast(pl.Float64).clip(0, 365) / 365.0
    fr_norm = pl.col("fork_to_star_ratio").rank("ordinal") / pl.col("fork_to_star_ratio").count()
    ia_norm = pl.col("open_issues").cast(pl.Float64).rank("ordinal") / pl.col("open_issues").count()

    df = df.with_columns(
        (
            MOMENTUM_WEIGHTS["stars_per_day"] * spd_norm
            + MOMENTUM_WEIGHTS["recent_push_bonus"] * push_bonus
            + MOMENTUM_WEIGHTS["fork_ratio"] * fr_norm
            + MOMENTUM_WEIGHTS["issue_activity"] * ia_norm
        )
        .round(4)
        .alias("momentum_score"),
    )

    # --- Maintenance score ---------------------------------------------------
    # variables defined first, used to record score second using weights from schema.py
    push_maint = 1.0 - pl.col("days_since_push").cast(pl.Float64).clip(0, 365) / 365.0
    release_bonus = pl.when(
        pl.col("days_since_release").is_not_null() & (pl.col("days_since_release") < 90)
    ).then(1.0).otherwise(0.0)
    # Proxy for issue_close_ratio: lower open-to-star ratio ≈ better maintained
    issue_proxy = pl.when(pl.col("stars") > 0).then(
        1.0 - (pl.col("open_issues").cast(pl.Float64) / pl.col("stars")).clip(0.0, 1.0)
    ).otherwise(0.5)

    df = df.with_columns(
        (
            MAINTENANCE_WEIGHTS["days_since_push"] * push_maint
            + MAINTENANCE_WEIGHTS["has_recent_release"] * release_bonus
            + MAINTENANCE_WEIGHTS["issue_close_ratio"] * issue_proxy
        )
        .round(4)
        .alias("maintenance_score"),
    )

    # --- Category Assignment ---------------------------------------------------
    # Why map_elements instead of a pure Polars expression? The TOPIC_TO_CATEGORY lookup with
    # "first match wins" logic is inherently row-by-row and involves iterating a variable-length list.
    # It's hard to express this purely in Polars expressions. map_elements is slower than native Polars
    # (it drops into Python for each row), but for this use case the simplicity is worth it,
    # category assignment isn't computationally intensive.

    df = df.with_columns(
        pl.col("topics")
        # take topic column value, pass to our function, return a string for polars
        .map_elements(_assign_category, return_dtype=pl.Utf8)
        .alias("category"),
    )

    return df


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def write_repos(df: pl.DataFrame) -> int:
    """Overwrite the repos table with the scored DataFrame. Returns row count."""
    con = get_connection()
    try:
        # Ensure the table exists before we do anything else.
        con.execute(REPOS_SCHEMA)

        # --- Derive column list from the database at runtime ---
        # WHY: We used to keep a hand-written _REPOS_COLUMNS list here, but that
        # duplicated the column definitions already in REPOS_SCHEMA (contracts/schema.py).
        # If someone added a column to the schema, they'd also have to remember to update
        # _REPOS_COLUMNS — easy to forget and a violation of the single-source-of-truth rule.
        #
        # Instead we ask DuckDB itself: "what columns does this table have, in order?"
        # information_schema.columns is a standard SQL metadata view that every database
        # provides. ordinal_position gives us columns in the same order as the CREATE TABLE.
        cols = [
            row[0]
            for row in con.execute(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{REPOS_TABLE}' "
                f"ORDER BY ordinal_position"
            ).fetchall()
        ]

        # Only select columns that actually exist in our DataFrame.
        # This guards against schema columns the transform hasn't computed yet
        # (e.g. a new column was added to the schema but the transform logic
        # hasn't been updated to produce it — the INSERT will use DuckDB defaults).
        # -- can ingnore warning, out is used, just in a sql statement not python code --
        out = df.select([c for c in cols if c in df.columns])

        # makes sure we wipe the table before inserting for a fresh snapshot
        con.execute(f"DELETE FROM {REPOS_TABLE}")
        # the actual insertion (duckdb can read directly from polars)
        con.execute(f"INSERT INTO {REPOS_TABLE} SELECT * FROM out")
        # runs a count for rows in the table, fetchone()[0] returns just the int count, not a tuple
        count: int = con.execute(f"SELECT COUNT(*) FROM {REPOS_TABLE}").fetchone()[0]
        return count
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run() -> int:
    """Clean → score → write. Returns the number of repos written."""
    cleaned = clean_run()
    scored = compute_metrics(cleaned)
    return write_repos(scored)


if __name__ == "__main__":
    n = run()
    print(f"Transform complete: {n} repos written to '{REPOS_TABLE}'.")
