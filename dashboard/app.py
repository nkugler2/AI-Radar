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
# Shared detail panel — rendered wherever a repo is selected
# ---------------------------------------------------------------------------
def show_repo_detail(repo_row: dict) -> None:
    """Render all available fields for a single repo."""
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


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="AI Radar", page_icon="📡", layout="wide")
st.title("AI Radar")
st.caption("Tracking popular AI Python repositories on GitHub")

df = load_repos()

if df.is_empty():
    st.warning("No data yet — run the ingestion and transform pipelines first.")
    st.stop()

# Session state: tracks which repo was last clicked in any table
if "selected_repo" not in st.session_state:
    st.session_state.selected_repo = None

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_leader, tab_category, tab_rising, tab_detail = st.tabs(
    ["Leaderboard", "Category Breakdown", "Rising Stars", "Repo Detail"]
)

# ---- 1. Leaderboard -------------------------------------------------------
with tab_leader:
    st.subheader("Leaderboard")
    st.caption("Click any column header to sort. Click a row to see full details.")

    # Inline category filter (replaces sidebar)
    categories = sorted(df["category"].drop_nulls().unique().to_list())
    selected_categories = st.multiselect(
        "Filter by category",
        options=categories,
        default=categories,
        placeholder="Filter by category…",
    )
    filtered_df = (
        df.filter(pl.col("category").is_in(selected_categories))
        if selected_categories
        else df
    )

    leaderboard_cols = [
        "full_name", "category", "stars", "forks",
        "momentum_score", "maintenance_score", "days_since_push",
    ]
    leaderboard_cols = [c for c in leaderboard_cols if c in filtered_df.columns]

    leaderboard = filtered_df.select(leaderboard_cols).sort(
        "stars", descending=True, nulls_last=True
    )

    leader_event = st.dataframe(
        leaderboard,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    if leader_event.selection.rows:
        row_idx = leader_event.selection.rows[0]
        repo_name = leaderboard.row(row_idx, named=True)["full_name"]
        st.session_state.selected_repo = repo_name
        repo_row = df.filter(pl.col("full_name") == repo_name).row(0, named=True)
        with st.expander(f"Detail — {repo_name}", expanded=True):
            show_repo_detail(repo_row)

# ---- 2. Category breakdown ------------------------------------------------
with tab_category:
    st.subheader("Category Breakdown")
    st.caption("Click a bar or slice to see all repos in that category.")

    cat_counts = (
        df
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

    chart_event = st.plotly_chart(fig, width="stretch", on_select="rerun")

    # Determine which category was clicked
    clicked_category = None
    if chart_event and chart_event.selection:
        points = chart_event.selection.get("points", [])
        if points:
            clicked_category = (
                points[0].get("x") if chart_type == "Bar" else points[0].get("label")
            )

    if clicked_category:
        st.subheader(f"Repos — {clicked_category}")
        st.caption("Click a row to see full details.")

        cat_cols = [
            "full_name", "stars", "forks",
            "momentum_score", "maintenance_score", "days_since_push",
        ]
        cat_cols = [c for c in cat_cols if c in df.columns]

        cat_repos = (
            df
            .filter(pl.col("category") == clicked_category)
            .select(cat_cols)
            .sort("stars", descending=True, nulls_last=True)
        )

        cat_event = st.dataframe(
            cat_repos,
            width="stretch",
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
        )

        if cat_event.selection.rows:
            row_idx = cat_event.selection.rows[0]
            repo_name = cat_repos.row(row_idx, named=True)["full_name"]
            st.session_state.selected_repo = repo_name
            repo_row = df.filter(pl.col("full_name") == repo_name).row(0, named=True)
            with st.expander(f"Detail — {repo_name}", expanded=True):
                show_repo_detail(repo_row)

# ---- 3. Rising Stars -------------------------------------------------------
with tab_rising:
    st.subheader("Rising Stars")
    st.caption(
        "Top 20 repos by momentum score — newer projects growing fast. "
        "Click a row to see full details."
    )

    rising_cols = [
        "full_name", "category", "stars",
        "momentum_score", "repo_age_days", "stars_per_day", "days_since_push",
    ]
    rising_cols = [c for c in rising_cols if c in df.columns]

    rising = (
        df
        .select(rising_cols)
        .sort("momentum_score", descending=True, nulls_last=True)
        .head(20)
    )

    rising_event = st.dataframe(
        rising,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    if rising_event.selection.rows:
        row_idx = rising_event.selection.rows[0]
        repo_name = rising.row(row_idx, named=True)["full_name"]
        st.session_state.selected_repo = repo_name
        repo_row = df.filter(pl.col("full_name") == repo_name).row(0, named=True)
        with st.expander(f"Detail — {repo_name}", expanded=True):
            show_repo_detail(repo_row)

    # Momentum scatter
    if "stars" in df.columns and "momentum_score" in df.columns:
        scatter_df = (
            df
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
            st.plotly_chart(fig_scatter, width="stretch")

# ---- 4. Repo Detail -------------------------------------------------------
with tab_detail:
    st.subheader("Repo Detail")

    # Text search — replaces the dropdown
    search_term = st.text_input(
        "Search repositories",
        placeholder="Type a repo name or owner…",
        value="",
    )

    all_repos_sorted = df.sort("stars", descending=True)["full_name"].to_list()

    if search_term:
        matches = [r for r in all_repos_sorted if search_term.lower() in r.lower()]
    else:
        matches = all_repos_sorted

    if not matches:
        st.info("No repositories match your search.")
    else:
        # Pre-select the repo that was last clicked in another tab
        default_idx = 0
        if st.session_state.selected_repo and st.session_state.selected_repo in matches:
            default_idx = matches.index(st.session_state.selected_repo)

        selected_repo = st.selectbox(
            "Matching repositories",
            options=matches,
            index=default_idx,
            label_visibility="collapsed",
        )

        repo_row = df.filter(pl.col("full_name") == selected_repo).row(0, named=True)
        st.divider()
        show_repo_detail(repo_row)
