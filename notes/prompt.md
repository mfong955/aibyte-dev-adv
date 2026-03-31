I'm building an AI-powered GitHub issue analyst as an interview demo
for a Senior Developer Advocate role at Airbyte. Read CLAUDE.md in
full before writing any code. Do not deviate from it without flagging
the reason.

Important things confirmed during manual testing:
- source-github requires docker_image=True to work correctly
- The discussions stream is NOT available — use issues + comments
- Labels come back as a list of dicts, extract label["name"] from each
- User comes back as a dict, extract user["login"] as author
- We limit to 100 issues in DuckDB after sync to keep demo fast

Scaffold and build the full project in the steps below. Complete and
confirm each step before starting the next. If you're uncertain about
a PyAirbyte API detail, flag it rather than guess.

## Step 1 — Project setup

Create the full directory structure from CLAUDE.md.

Create requirements.txt with:
  airbyte, duckdb, anthropic, streamlit, python-dotenv, pandas

Create .env.example:
  ANTHROPIC_API_KEY=your_key_here
  GITHUB_TOKEN=your_github_pat_here

Create .gitignore excluding: .env, data/*.db, __pycache__, .venv,
.venv-source-github

## Step 2 — Ingest pipeline (pipeline/ingest.py)

Use PyAirbyte to configure source-github with docker_image=True:
  - repositories: ["airbytehq/airbyte"]
  - credentials: personal_access_token from GITHUB_TOKEN env var

Select only the "issues" stream.

Read into a local DuckDB cache at data/community.db.

After sync, query the DuckDB cache and write a clean `issues` table
with exactly these columns (transforming raw fields as noted):
  - issue_number: from "number" field
  - title: from "title"
  - body: first 1000 chars of "body" (truncate for enrichment cost)
  - author: from user["login"] — NOTE: in PyAirbyte DuckDB cache,
    nested fields may be stored as JSON strings, handle both cases
  - state: from "state"
  - labels: extract name from each label object, join with comma
    — handle both list-of-dicts and JSON string representations
  - comment_count: from "comments"
  - created_at: from "created_at"
  - updated_at: from "updated_at"
  - html_url: from "html_url"

IMPORTANT: After writing, immediately run:
  DELETE FROM issues WHERE issue_number NOT IN (
    SELECT issue_number FROM issues
    ORDER BY created_at DESC
    LIMIT 100
  )
This keeps the demo fast.

Also filter to only keep issues where labels contains at least one of:
documentation, question, enhancement, good first issue,
kind/feature, help wanted

Add CLI entrypoint: python -m pipeline.ingest
Print summary: total fetched, total after filtering, total in DB.

## Step 3 — Enrichment pipeline (pipeline/enrich.py)

Load all issues from DuckDB not yet in the enrichment table.

For each issue call Claude API (claude-sonnet-4-20250514):

System:
  You are a developer community analyst helping a Developer Advocate
  at Airbyte understand what developers need. Analyze GitHub issues
  from the airbytehq/airbyte repo and extract structured signal.
  Always respond with valid JSON only. No preamble, no markdown fences.

User:
  Analyze this GitHub issue from the Airbyte open source repo.

  TITLE: {title}
  LABELS: {labels}
  BODY: {body[:600]}

  Return a JSON object with exactly these fields:
  {{
    "pain_point": "one sentence: what problem is this person facing",
    "tools_mentioned": ["array", "of", "tool", "names"],
    "airbyte_relevant": true or false,
    "relevance_reason": "one sentence or null",
    "unmet_need": "what need isn't fully addressed yet, or null",
    "category": one of exactly: documentation-gap | feature-request |
                question | bug-with-advocacy-angle |
                integration-request | other,
    "community_sentiment": one of exactly: frustrated | confused |
                           hopeful | neutral,
    "advocate_opportunity": true or false,
    "advocate_action": "one sentence: what a DA could do here, or null"
  }}

Parse JSON response. On failure log to data/enrich_errors.log and skip.
Batch in groups of 5 with 1 second sleep between batches.
Store results in enrichment table with enriched_at timestamp.
Add CLI entrypoint: python -m pipeline.enrich
Print summary at end: total enriched, errors, advocate opportunities.

## Step 4 — Analyst agent (agent/analyst.py)

Build AnalystAgent class with method:
  def ask(self, question: str) -> dict
  returns: {"sql": str, "results": list[dict],
            "interpretation": str, "error": str | None}

Two Claude API calls:

Call 1 — SQL generation:
  System prompt includes full schema for both tables with all column
  names and types. Include these 3 few-shot examples:

  Q: "What are the most common issue categories?"
  SQL: SELECT category, COUNT(*) as count FROM enrichment
       GROUP BY category ORDER BY count DESC

  Q: "Which issues are advocate opportunities?"
  SQL: SELECT i.title, i.labels, e.advocate_action
       FROM issues i JOIN enrichment e
       ON i.issue_number = e.issue_number
       WHERE e.advocate_opportunity = true
       ORDER BY i.created_at DESC LIMIT 10

  Q: "What tools are mentioned most often?"
  SQL: SELECT value as tool, COUNT(*) as count
       FROM enrichment,
       json_each('["' || replace(tools_mentioned, ', ', '","') || '"]')
       WHERE tools_mentioned != ''
       GROUP BY value ORDER BY count DESC LIMIT 15

  Return SQL only, no explanation, no markdown fences.

Call 2 — Interpretation:
  Pass question + SQL + results (max 30 rows as compact JSON).
  Interpret in 2-4 sentences for a developer audience.
  If empty results, say so clearly.

SQL retry: on DuckDB error, pass error back to Claude to fix.
Max 2 retries before returning error in dict.

## Step 5 — Streamlit UI (app/streamlit_app.py)

HEADER:
  Title: "Airbyte Issue Analyst"
  Subtitle: "Surfacing developer advocacy opportunities from
             airbytehq/airbyte GitHub issues — powered by
             PyAirbyte + Claude"

SUMMARY DASHBOARD (loads on startup from DuckDB):
  4 metric cards:
  - Total issues analyzed
  - Advocate opportunities (count + %)
  - Most common category
  - Most common sentiment

  Bar chart: count by category

SIDEBAR — "Example questions" with 5 st.button elements:
  1. "What documentation gaps come up most often?"
  2. "Which issues represent the best developer advocate opportunities?"
  3. "What features are developers requesting most?"
  4. "Give me 3 specific advocate actions based on these issues"
  5. "What connectors or integrations are mentioned most?"

MAIN:
  st.text_input: "Ask a question about Airbyte's GitHub issues..."
  st.button: "Analyze"

  On submit:
    st.spinner("Thinking...")
    Call agent.ask()
    If error: st.error
    If success:
      st.expander "Generated SQL" (collapsed): st.code, language="sql"
      st.markdown with interpretation
      st.dataframe with raw results if non-empty

SESSION STATE for sidebar buttons populating the input.

## Step 6 — README.md

Sections: What this is, Why GitHub Issues, Setup instructions
(venv → pip install → .env → docker pull → ingest → enrich →
streamlit run), Architecture, Demo questions.

## Global constraints
- Type hints on all functions
- Docstrings on all classes and public functions
- All credentials from .env via python-dotenv
- No async
- docker_image=True on source-github always
- DuckDB path: "data/community.db" relative to project root
- CLI via if __name__ == "__main__"
- MVP only — no extra features