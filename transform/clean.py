"""transform/clean.py — Read raw_repos, clean nulls and bad data using Polars."""

from __future__ import annotations

import logging

import polars as pl

from contracts.schema import (
    RAW_REPOS_TABLE,
    get_connection,
)
from contracts.scrub import scrub_readme

log = logging.getLogger(__name__)

# connect to the DB, select the data, and put it into a polars Dataframe
def read_raw_repos() -> pl.DataFrame:
    """Read the raw_repos table into a Polars DataFrame."""
    con = get_connection()
    try:
        return con.execute(f"SELECT * FROM {RAW_REPOS_TABLE}").pl()
    finally:
        con.close()

def _scrub_secrets(df: pl.DataFrame) -> pl.DataFrame:
    """Scan readme_content for secrets, log findings, replace matches with redaction markers."""
    all_findings: list[dict] = []
    scrubbed_readmes: list[str] = []

    for row in df.iter_rows(named=True):
        readme = row.get("readme_content") or ""
        scrubbed, findings = scrub_readme(readme)
        scrubbed_readmes.append(scrubbed)
        for f in findings:
            all_findings.append({"full_name": row["full_name"], **f})

    if all_findings:
        affected_repos = len({f["full_name"] for f in all_findings})
        log.warning(
            "SECRET SCAN: %d pattern(s) found across %d repo(s) — redacted before writing",
            len(all_findings),
            affected_repos,
        )
        for f in all_findings:
            note = " (likely placeholder)" if f["is_likely_placeholder"] else " *** REVIEW NEEDED ***"
            log.warning(
                "  %-50s | %-20s | severity=%-8s | sample: %s%s",
                f["full_name"],
                f["pattern_name"],
                f["severity"],
                f["sample"],
                note,
            )

    return df.with_columns(pl.Series("readme_content", scrubbed_readmes))


# data cleaning
def clean(df: pl.DataFrame) -> pl.DataFrame:
    """Clean nulls, drop bad rows, normalize types.

    - Drops forks (repos table has no is_fork column).
    - Keeps archived repos (flagged via is_archived).
    - Drops rows missing essential fields.
    - Fills null numerics with 0 and null text with empty string.
    - Deduplicates by id, keeping the most recent fetch.
    """
    # Drop forks — the repos table doesn't carry is_fork
    # the noqa comment is because of polars and doing == False rather than is False
    df = df.filter(pl.col("is_fork") == False)  # noqa: E712

    # Drop rows missing essential fields
    df = df.filter(
        pl.col("id").is_not_null()
        & pl.col("full_name").is_not_null()
        & pl.col("created_at").is_not_null()
    )

    # Fill null numerics
    df = df.with_columns(
        pl.col("stars").fill_null(0),
        pl.col("forks").fill_null(0),
        pl.col("open_issues").fill_null(0),
        pl.col("watchers").fill_null(0),
        pl.col("size_kb").fill_null(0),
    )

    # Fill null text
    df = df.with_columns(
        pl.col("description").fill_null(""),
        pl.col("readme_content").fill_null(""),
    )

    # Scrub secrets from README content before it reaches the parquet / repos table
    df = _scrub_secrets(df)

    # Ensure topics is an empty list when null
    df = df.with_columns(
        pl.when(pl.col("topics").is_null())
        .then(pl.lit([], dtype=pl.List(pl.Utf8)))
        .otherwise(pl.col("topics"))
        .alias("topics")
    )

    # Deduplicate by id, keeping the most recently fetched row
    # for each record, only keep the most recent version
    df = df.sort("fetched_at", descending=True).unique(subset=["id"], keep="first")

    # return our cleaned dataframe
    return df


def run() -> pl.DataFrame:
    """Entry point: read raw_repos → clean → return Polars DataFrame."""
    raw = read_raw_repos()
    return clean(raw)
