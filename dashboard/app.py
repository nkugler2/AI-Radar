"""
dashboard/app.py

AI Radar — Streamlit dashboard (read-only).
Run with:  streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is importable so `contracts` resolves
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import polars as pl
import plotly.express as px
import streamlit as st

from contracts.schema import DB_PATH, REPOS_TABLE, get_connection


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def load_repos() -> pl.DataFrame:
    """Fetch every row from the repos table into a Polars DataFrame."""
    con = get_connection(read_only=True)
    try:
        result = con.execute(f"SELECT * FROM {REPOS_TABLE}").fetchall()
        columns = [desc[0] for desc in con.description]
    finally:
        con.close()

    if not result:
        return pl.DataFrame()

    return pl.DataFrame(dict(zip(columns, zip(*result))))


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="AI Radar", page_icon="📡", layout="wide")
st.title("AI Radar")
st.caption("Tracking popular AI Python repositories on GitHub")

# Load data (cached)
df = load_repos()

if df.is_empty():
    st.warning("No data yet — run the ingestion and transform pipelines first.")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar — category filter (driven by the category breakdown)
# ---------------------------------------------------------------------------
categories = sorted(df["category"].drop_nulls().unique().to_list())
selected_categories = st.sidebar.multiselect(
    "Filter by category",
    options=categories,
    default=categories,
)

filtered_df = df.filter(pl.col("category").is_in(selected_categories))

# ---------------------------------------------------------------------------
# Tabs for the four views
# ---------------------------------------------------------------------------
tab_leader, tab_category, tab_rising, tab_detail = st.tabs(
    ["Leaderboard", "Category Breakdown", "Rising Stars", "Repo Detail"]
)

# ---- 1. Leaderboard -------------------------------------------------------
with tab_leader:
    st.subheader("Leaderboard")

    sort_col = st.selectbox(
        "Sort by",
        options=["stars", "momentum_score", "maintenance_score"],
        index=0,
    )

    leaderboard_cols = [
        "full_name",
        "category",
        "stars",
        "forks",
        "momentum_score",
        "maintenance_score",
        "days_since_push",
    ]
    # Only include columns that exist in the dataframe
    leaderboard_cols = [c for c in leaderboard_cols if c in filtered_df.columns]

    leaderboard = (
        filtered_df
        .select(leaderboard_cols)
        .sort(sort_col, descending=True, nulls_last=True)
    )

    st.dataframe(leaderboard, use_container_width=True, hide_index=True)

# ---- 2. Category breakdown ------------------------------------------------
with tab_category:
    st.subheader("Category Breakdown")

    cat_counts = (
        df  # use unfiltered data so the chart shows all categories
        .filter(pl.col("category").is_not_null())
        .group_by("category")
        .agg(pl.len().alias("count"))
        .sort("count", descending=True)
    )

    chart_type = st.radio("Chart type", ["Bar", "Pie"], horizontal=True)

    if chart_type == "Bar":
        fig = px.bar(
            cat_counts.to_dict(as_series=False),
            x="category",
            y="count",
            color="category",
            title="Repos per Category",
        )
    else:
        fig = px.pie(
            cat_counts.to_dict(as_series=False),
            names="category",
            values="count",
            title="Repos per Category",
        )

    st.plotly_chart(fig, use_container_width=True)

    st.info("Use the sidebar category filter to update the Leaderboard and Rising Stars views.")

# ---- 3. Rising Stars -------------------------------------------------------
with tab_rising:
    st.subheader("Rising Stars")
    st.caption("Top 20 repos by momentum score — newer projects growing fast.")

    rising_cols = [
        "full_name",
        "category",
        "stars",
        "momentum_score",
        "repo_age_days",
        "stars_per_day",
        "days_since_push",
    ]
    rising_cols = [c for c in rising_cols if c in filtered_df.columns]

    rising = (
        filtered_df
        .select(rising_cols)
        .sort("momentum_score", descending=True, nulls_last=True)
        .head(20)
    )

    st.dataframe(rising, use_container_width=True, hide_index=True)

    # Momentum scatter
    if "stars" in filtered_df.columns and "momentum_score" in filtered_df.columns:
        scatter_df = (
            filtered_df
            .filter(pl.col("momentum_score").is_not_null())
            .sort("momentum_score", descending=True)
            .head(50)
        )
        if not scatter_df.is_empty():
            fig_scatter = px.scatter(
                scatter_df.to_dict(as_series=False),
                x="stars",
                y="momentum_score",
                hover_name="full_name",
                color="category",
                title="Stars vs Momentum (top 50)",
                size="stars_per_day" if "stars_per_day" in scatter_df.columns else None,
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

# ---- 4. Repo Detail -------------------------------------------------------
with tab_detail:
    st.subheader("Repo Detail")

    repo_names = filtered_df.sort("stars", descending=True)["full_name"].to_list()

    if not repo_names:
        st.info("No repos match the current filters.")
    else:
        selected_repo = st.selectbox("Select a repository", options=repo_names)

        repo_row = df.filter(pl.col("full_name") == selected_repo).row(0, named=True)

        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"### {repo_row['full_name']}")
            st.markdown(f"**Description:** {repo_row.get('description') or 'N/A'}")
            homepage = repo_row.get("homepage")
            if homepage:
                st.markdown(f"**Homepage:** {homepage}")
            st.markdown(f"**License:** {repo_row.get('license') or 'N/A'}")
            st.markdown(f"**Category:** {repo_row.get('category') or 'N/A'}")

            topics = repo_row.get("topics")
            if topics:
                st.markdown(f"**Topics:** {', '.join(topics)}")

        with col2:
            st.metric("Stars", f"{repo_row.get('stars', 0):,}")
            st.metric("Forks", f"{repo_row.get('forks', 0):,}")
            st.metric("Open Issues", f"{repo_row.get('open_issues', 0):,}")
            st.metric("Days Since Push", repo_row.get("days_since_push", "N/A"))

        st.divider()

        score_col1, score_col2, score_col3 = st.columns(3)
        with score_col1:
            momentum = repo_row.get("momentum_score")
            st.metric("Momentum Score", f"{momentum:.3f}" if momentum is not None else "N/A")
        with score_col2:
            maintenance = repo_row.get("maintenance_score")
            st.metric("Maintenance Score", f"{maintenance:.3f}" if maintenance is not None else "N/A")
        with score_col3:
            spd = repo_row.get("stars_per_day")
            st.metric("Stars / Day", f"{spd:.2f}" if spd is not None else "N/A")

        st.divider()
        detail_col1, detail_col2 = st.columns(2)
        with detail_col1:
            st.markdown(f"**Repo Age:** {repo_row.get('repo_age_days', 'N/A')} days")
            st.markdown(f"**Fork-to-Star Ratio:** {repo_row.get('fork_to_star_ratio', 'N/A')}")
            st.markdown(f"**Contributors:** {repo_row.get('contributor_count', 'N/A')}")
        with detail_col2:
            st.markdown(f"**Releases:** {repo_row.get('release_count', 'N/A')}")
            st.markdown(f"**Days Since Release:** {repo_row.get('days_since_release', 'N/A')}")
            st.markdown(f"**Archived:** {'Yes' if repo_row.get('is_archived') else 'No'}")
