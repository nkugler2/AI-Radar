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

# Session state initialization
if "selected_repo" not in st.session_state:
    st.session_state.selected_repo = None

# ---------------------------------------------------------------------------
# Tabs — Category Breakdown first, then Leaderboard, Rising Stars, Repo Detail
# ---------------------------------------------------------------------------
tab_category, tab_leader, tab_rising, tab_detail = st.tabs(
    ["Category Breakdown", "Leaderboard", "Rising Stars", "Repo Detail"]
)

# ---- 1. Category Breakdown ------------------------------------------------
with tab_category:
    st.subheader("Category Breakdown")
    st.caption("Click bars to filter repos by category. Multi-select supported.")

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
        chart_event = st.plotly_chart(fig, on_select="rerun", selection_mode="points")

        selected_cats: list[str] = []
        if chart_event and chart_event.selection:
            points = chart_event.selection.get("points", [])
            for p in points:
                cat = p.get("x")
                if cat and cat not in selected_cats:
                    selected_cats.append(cat)
    else:
        fig = px.pie(
            cat_counts.to_dict(as_series=False),
            names="category",
            values="count",
            title="Repos per Category",
        )
        chart_event = st.plotly_chart(fig, on_select="rerun")

        selected_cats = []
        if chart_event and chart_event.selection:
            points = chart_event.selection.get("points", [])
            for p in points:
                cat = p.get("label")
                if cat and cat not in selected_cats:
                    selected_cats.append(cat)

    cat_cols = [
        "full_name", "category", "stars", "forks",
        "momentum_score", "maintenance_score", "days_since_push",
    ]
    cat_cols = [c for c in cat_cols if c in df.columns]

    if selected_cats:
        st.markdown(f"**Showing:** {', '.join(selected_cats)}")
        cat_repos = (
            df
            .filter(pl.col("category").is_in(selected_cats))
            .select(cat_cols)
            .sort("stars", descending=True, nulls_last=True)
        )
    else:
        cat_repos = (
            df
            .select(cat_cols)
            .sort("stars", descending=True, nulls_last=True)
        )

    cat_event = st.dataframe(
        cat_repos,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="multi-row",
    )

    selected_repo_names: list[str] = []
    if cat_event.selection.rows:
        selected_repo_names = [
            cat_repos.row(i, named=True)["full_name"]
            for i in cat_event.selection.rows
        ]

    if selected_repo_names:
        n_cols = min(len(selected_repo_names), 4)
        cols = st.columns(n_cols)
        for i, repo_name in enumerate(selected_repo_names[:4]):
            repo_row = df.filter(pl.col("full_name") == repo_name).row(0, named=True)
            with cols[i]:
                st.markdown(f"#### {repo_row['full_name']}")
                st.markdown(f"**Category:** {repo_row.get('category') or 'N/A'}")
                st.metric("Stars", f"{repo_row.get('stars', 0):,}")
                momentum = repo_row.get("momentum_score")
                st.metric("Momentum Score", f"{momentum:.3f}" if momentum is not None else "N/A")
                desc = repo_row.get("description") or ""
                if len(desc) > 200:
                    desc = desc[:200] + "…"
                st.markdown(f"**Description:** {desc or 'N/A'}")

# ---- 2. Leaderboard -------------------------------------------------------
with tab_leader:
    st.subheader("Leaderboard")
    st.caption("Click any column header to sort. Click a row to see full details.")

    categories = sorted(df["category"].drop_nulls().unique().to_list())

    # Initialize per-category checkbox states (all checked by default)
    for cat in categories:
        key = f"leader_cat_{cat}"
        if key not in st.session_state:
            st.session_state[key] = True

    btn_col1, btn_col2, _ = st.columns([1, 1, 8])
    with btn_col1:
        if st.button("Select All"):
            for cat in categories:
                st.session_state[f"leader_cat_{cat}"] = True
    with btn_col2:
        if st.button("Clear All"):
            for cat in categories:
                st.session_state[f"leader_cat_{cat}"] = False

    # Render checkboxes in a grid, 4 per row
    cols_per_row = 4
    cat_rows = [categories[i:i + cols_per_row] for i in range(0, len(categories), cols_per_row)]
    for cat_row in cat_rows:
        check_cols = st.columns(cols_per_row)
        for j, cat in enumerate(cat_row):
            with check_cols[j]:
                st.checkbox(cat, key=f"leader_cat_{cat}")

    selected_categories = [cat for cat in categories if st.session_state.get(f"leader_cat_{cat}", True)]
    filtered_df = (
        df.filter(pl.col("category").is_in(selected_categories))
        if selected_categories
        else df.head(0)
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

# ---- 3. Rising Stars -------------------------------------------------------
with tab_rising:
    st.subheader("Rising Stars")
    st.caption(
        "Top repos by momentum score — newer projects growing fast. "
        "Click a row to see full details."
    )

    age_limit = st.slider(
        "Show repos created within the last N days",
        min_value=7,
        max_value=365,
        value=90,
        step=7,
    )

    rising_df = (
        df.filter(pl.col("repo_age_days") <= age_limit)
        if "repo_age_days" in df.columns
        else df
    )

    rising_cols = [
        "full_name", "category", "stars",
        "momentum_score", "repo_age_days", "stars_per_day", "days_since_push",
    ]
    rising_cols = [c for c in rising_cols if c in rising_df.columns]

    rising = (
        rising_df
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

    # Momentum scatter — scoped to the age-filtered DataFrame
    if "stars" in rising_df.columns and "momentum_score" in rising_df.columns:
        scatter_df = (
            rising_df
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
