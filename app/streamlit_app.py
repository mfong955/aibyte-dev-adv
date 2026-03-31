"""Streamlit demo UI for the Airbyte Issue Analyst."""

from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

from agent.analyst import AnalystAgent

DB_PATH = Path(__file__).parent.parent / "data" / "community.db"

EXAMPLE_QUESTIONS = [
    "What documentation gaps come up most often?",
    "Which issues represent the best developer advocate opportunities?",
    "What features are developers requesting most?",
    "Give me 3 specific advocate actions based on these issues",
    "What connectors or integrations are mentioned most?",
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
    col1.metric("Total issues analyzed", summary["total_issues"])
    col2.metric(
        "Advocate opportunities",
        f"{summary['advocate_count']} ({summary['advocate_pct']:.0f}%)",
    )
    col3.metric("Top category", summary["top_category"])
    col4.metric("Top sentiment", summary["top_sentiment"])

    st.bar_chart(
        summary["category_counts"].set_index("category")["count"],
        use_container_width=True,
    )

except Exception as exc:
    st.warning(f"Could not load summary dashboard: {exc}")

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
            st.dataframe(pd.DataFrame(result["results"]), use_container_width=True)

elif analyze_clicked:
    st.warning("Please enter a question.")
