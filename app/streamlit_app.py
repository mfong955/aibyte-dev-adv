"""Streamlit demo UI for the Airbyte Issue Analyst."""

from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

from agent.analyst import AnalystAgent

DB_PATH = Path(__file__).parent.parent / "data" / "community.db"

EXAMPLE_QUESTIONS = [
    "What documentation gaps come up most often?",
    "Which issues represent the best developer advocate opportunities?",
    "What features are developers requesting most?",
    "Give me 3 specific advocate actions I can take based on the Airbyte community issues",
    "What connectors or integrations are mentioned most?",
    "What category has the most issues? Please list the ones where the community is frustrated and list them according to the number of comments, descending. Include the title, url, comments, pain points, unmet needs, advocate actions, community sentiment, and issue category.",
]


@st.cache_resource
def get_agent() -> AnalystAgent:
    """Instantiate and cache the AnalystAgent for the session."""
    return AnalystAgent()


@st.cache_data
def load_summary() -> dict:
    """Load summary metrics from DuckDB for the dashboard.

    Returns:
        Dict with keys: total_issues, advocate_count, advocate_pct,
        top_category, top_sentiment, category_counts.
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)

    total_issues = con.execute(
        "SELECT COUNT(*) FROM issues i JOIN enrichment e ON i.issue_number = e.issue_number"
    ).fetchone()[0]

    advocate_count = con.execute(
        "SELECT COUNT(*) FROM enrichment WHERE advocate_opportunity = true"
    ).fetchone()[0]

    advocate_pct = (advocate_count / total_issues * 100) if total_issues else 0.0

    top_category = con.execute(
        "SELECT category FROM enrichment GROUP BY category ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()
    top_category = top_category[0] if top_category else "N/A"

    top_sentiment = con.execute(
        "SELECT community_sentiment FROM enrichment GROUP BY community_sentiment ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()
    top_sentiment = top_sentiment[0] if top_sentiment else "N/A"

    category_df = con.execute(
        "SELECT category, COUNT(*) as count FROM enrichment GROUP BY category ORDER BY count DESC"
    ).df()

    con.close()

    return {
        "total_issues": total_issues,
        "advocate_count": advocate_count,
        "advocate_pct": advocate_pct,
        "top_category": top_category,
        "top_sentiment": top_sentiment,
        "category_counts": category_df,
    }


# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Airbyte Issue Analyst",
    page_icon="🔭",
    layout="wide",
)

# ── Header ───────────────────────────────────────────────────────────────────

st.title("Airbyte Issue Analyst")
st.caption(
    "Surfacing developer advocacy opportunities from airbytehq/airbyte GitHub issues "
    "— powered by PyAirbyte + Claude"
)

# ── Session state ─────────────────────────────────────────────────────────────

if "question_input" not in st.session_state:
    st.session_state["question_input"] = ""

# ── Sidebar — example questions ───────────────────────────────────────────────

with st.sidebar:
    st.header("Example questions")
    for q in EXAMPLE_QUESTIONS:
        if st.button(q, use_container_width=True):
            st.session_state["question_input"] = q
            st.rerun()

# ── Summary dashboard ─────────────────────────────────────────────────────────

try:
    summary = load_summary()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Total issues analyzed",
        summary["total_issues"],
        help=(
            "Count of GitHub issues from airbytehq/airbyte that have been both ingested "
            "and enriched. Ingestion pulls up to 1,000 of the most recent open issues via "
            "the GitHub REST API, excluding pull requests. Enrichment runs Claude on each "
            "issue to extract structured signal. This number reflects how many issues "
            "successfully completed both steps."
        ),
    )
    col2.metric(
        "Advocate opportunities",
        f"{summary['advocate_count']} ({summary['advocate_pct']:.0f}%)",
        help=(
            "Issues where Claude judged there is a concrete action a Developer Advocate "
            "could take — for example: writing a tutorial to address a documentation gap, "
            "creating a FAQ for a recurring question, aggregating feature demand for the "
            "product team, or proactively communicating a workaround for a confusing bug. "
            "This is Claude's judgment call based on the issue title, labels, and body — "
            "no hard-coded rules."
        ),
    )
    col3.metric(
        "Top category",
        summary["top_category"],
        help=(
            "The most common category assigned by Claude across all enriched issues. "
            "Categories: documentation-gap (missing or unclear docs), "
            "feature-request (new functionality asked for), "
            "question (user is confused and seeking help), "
            "bug-with-advocacy-angle (a bug that also reveals UX confusion a DA could address), "
            "integration-request (request for a new connector or integration), "
            "other (catch-all). These categories map directly to DA content and outreach opportunities."
        ),
    )
    col4.metric(
        "Top sentiment",
        summary["top_sentiment"],
        help=(
            "The most common community sentiment detected by Claude across all enriched issues. "
            "Sentiments: frustrated (user is blocked or angry), confused (user doesn't understand "
            "how something works), hopeful (user is optimistic about a feature or fix), "
            "neutral (matter-of-fact report with no strong emotion). "
            "Sentiment helps prioritize which issues need the most urgent advocacy attention."
        ),
    )

    all_categories = [
        "documentation-gap", "feature-request", "question",
        "bug-with-advocacy-angle", "integration-request", "other",
    ]
    cat_df = (
        pd.DataFrame({"category": all_categories})
        .merge(summary["category_counts"], on="category", how="left")
        .fillna(0)
        .assign(count=lambda d: d["count"].astype(int))
    )
    total_cat = cat_df["count"].sum()
    cat_df["pct"] = (cat_df["count"] / total_cat * 100).round(1) if total_cat else 0.0

    selection = alt.selection_point(fields=["category"], on="click", clear="dblclick")
    chart = (
        alt.Chart(cat_df)
        .mark_bar()
        .encode(
            x=alt.X("count:Q", title="Issue count"),
            y=alt.Y("category:N", sort="-x", title=None),
            opacity=alt.condition(selection, alt.value(1.0), alt.value(0.4)),
            tooltip=[
                alt.Tooltip("category:N", title="Category"),
                alt.Tooltip("count:Q", title="Issues"),
                alt.Tooltip("pct:Q", title="% of total", format=".1f"),
            ],
        )
        .properties(height=220)
        .add_params(selection)
    )
    chart_state = st.altair_chart(chart, use_container_width=True, on_select="rerun")
    st.caption(
        "Issue breakdown by category — assigned by Claude based on issue title, labels, and body. "
        "Each category maps to a distinct type of developer advocacy action. "
        "Hover to see count and percentage. Click a bar to drill into its issues; double-click to clear."
    )

except Exception as exc:
    st.warning(f"Could not load summary dashboard: {exc}")
    chart_state = None

if chart_state is not None:
    selected_points = chart_state.selection.get("param_1") or []
    selected_cat = selected_points[0].get("category") if selected_points else None
    if selected_cat:
        st.subheader(f"Issues: {selected_cat}")
        con = duckdb.connect(str(DB_PATH), read_only=True)
        drill_df = con.execute("""
            SELECT i.issue_number, i.title, i.html_url, i.state,
                   e.pain_point, e.community_sentiment, e.advocate_opportunity, e.advocate_action
            FROM issues i
            JOIN enrichment e ON i.issue_number = e.issue_number
            WHERE e.category = ?
            ORDER BY i.created_at DESC
        """, [selected_cat]).df()
        con.close()
        st.dataframe(
            drill_df,
            column_config={"html_url": st.column_config.LinkColumn("url")},
            use_container_width=True,
        )

st.divider()

# ── Issue list ────────────────────────────────────────────────────────────────

with st.expander("View all issues in dataset"):
    try:
        con = duckdb.connect(str(DB_PATH), read_only=True)
        issues_df = con.execute(
            "SELECT issue_number, title, labels, state, html_url FROM issues ORDER BY issue_number DESC"
        ).df()
        con.close()
        st.dataframe(
            issues_df,
            column_config={"html_url": st.column_config.LinkColumn("url")},
            use_container_width=True,
        )
    except Exception as exc:
        st.warning(f"Could not load issues: {exc}")

st.divider()

# ── Q&A interface ─────────────────────────────────────────────────────────────

question = st.text_input(
    "Ask a question about Airbyte's GitHub issues...",
    value=st.session_state["question_input"],
    key="question_input",
)

analyze_clicked = st.button("Analyze", type="primary")

if analyze_clicked and question.strip():
    agent = get_agent()

    with st.spinner("Thinking..."):
        result = agent.ask(question.strip())

    if result["error"]:
        st.error(result["error"])
    else:
        with st.expander("Generated SQL", expanded=False):
            st.code(result["sql"], language="sql")

        st.markdown(result["interpretation"])

        if result["results"]:
            df = pd.DataFrame(result["results"])
            col_config = {}
            if "html_url" in df.columns:
                col_config["html_url"] = st.column_config.LinkColumn("url")
            st.dataframe(df, column_config=col_config, use_container_width=True)

elif analyze_clicked:
    st.warning("Please enter a question.")
