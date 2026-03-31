# Airbyte Issue Analyst — Project Context

## What this project is
An AI-powered GitHub issue analyst that uses PyAirbyte's source-github
connector to ingest issues from the airbytehq/airbyte repository into
DuckDB, enriches them with Claude-powered structured analysis, then
exposes a natural language Q&A agent for surfacing developer advocacy
opportunities.

Built as an interview demo for a Senior Developer Advocate role at
Airbyte. The three things this demo proves:
1. PyAirbyte works as real data infrastructure (not mocked) — we use
   the actual source-github connector to ingest live GitHub issues
2. Claude API handles both batch enrichment and conversational analysis
3. The output is genuinely useful: community pain points mapped to
   concrete developer advocacy opportunities for Airbyte

## The strategic framing (important for narrative)
This tool finds the developer advocacy signal hiding inside Airbyte's
own issue tracker. Issues labeled documentation, question, enhancement,
and good first issue are where confused or underserved developers
speak up. Surfacing those patterns at scale is a core developer
advocacy function — this app automates it.

## Stack
- PyAirbyte (source-github connector, docker_image=True) for ingestion
- DuckDB (persisted to disk at data/community.db) for local storage
- Claude API (claude-sonnet-4-20250514) for enrichment and agent
- Streamlit for demo UI
- Python 3.11+

## Project structure
- pipeline/ingest.py    — PyAirbyte source-github → DuckDB
- pipeline/enrich.py   — Batch Claude enrichment per issue
- agent/analyst.py     — Text-to-SQL conversational agent
- app/streamlit_app.py — Streamlit demo interface
- data/community.db    — Persisted DuckDB file (commit before demo)
- CLAUDE.md            — This file

## Confirmed technical details from manual testing
- source-github requires docker_image=True to work correctly
- The discussions stream is NOT available in source-github
- Use issues stream only (comments can be pulled separately if needed)
- Labels come back as a list of dicts — extract label["name"] from each
- User comes back as a dict — extract user["login"] as author
- In PyAirbyte's DuckDB cache, nested fields may be stored as JSON
  strings — handle both list-of-dicts and JSON string representations
- We limit to 100 issues after sync to keep demo fast
- Docker Desktop must be running for source-github to work

## DuckDB schema

### Table: issues
| Column        | Type      | Notes                                    |
|---------------|-----------|------------------------------------------|
| issue_number  | INTEGER   | PRIMARY KEY, from "number" field         |
| title         | TEXT      |                                          |
| body          | TEXT      | Truncated to first 1000 chars            |
| author        | TEXT      | From user["login"]                       |
| state         | TEXT      | open or closed                           |
| labels        | TEXT      | Comma-separated label names              |
| comment_count | INTEGER   | From "comments" field                    |
| created_at    | TIMESTAMP |                                          |
| updated_at    | TIMESTAMP |                                          |
| html_url      | TEXT      |                                          |

### Table: enrichment
| Column             | Type      | Notes                              |
|--------------------|-----------|------------------------------------|
| issue_number       | INTEGER   | PRIMARY KEY, FK to issues          |
| pain_point         | TEXT      | One sentence                       |
| tools_mentioned    | TEXT      | Comma-separated tool names         |
| airbyte_relevant   | BOOLEAN   |                                    |
| relevance_reason   | TEXT      | One sentence or null               |
| unmet_need         | TEXT      | What isn't addressed yet, or null  |
| category           | TEXT      | See allowed values below           |
| community_sentiment| TEXT      | See allowed values below           |
| advocate_opportunity| BOOLEAN  |                                    |
| advocate_action    | TEXT      | One sentence or null               |
| enriched_at        | TIMESTAMP |                                    |

### Allowed category values
documentation-gap | feature-request | question |
bug-with-advocacy-angle | integration-request | other

### Allowed community_sentiment values
frustrated | confused | hopeful | neutral

## Key design decisions
1. docker_image=True is required for source-github — the Python-native
   install has a dependency conflict with airbyte-cdk. Always use
   docker_image=True, no exceptions.
2. DuckDB is persisted to disk. Ingest and enrich are one-time setup
   steps. The agent and Streamlit never re-ingest or re-enrich.
3. After PyAirbyte sync we immediately DELETE all but the 100 most
   recent issues matching our label filter. This keeps the demo fast.
4. Label filter: keep only issues where labels contains at least one
   of: documentation, question, enhancement, good first issue,
   kind/feature, help wanted
5. Enrichment is idempotent — re-running enrich.py skips issues that
   already have a row in the enrichment table.
6. The agent uses text-to-SQL: Claude generates SQL → runs against
   DuckDB → Claude interprets results. Raw issue body text never
   enters the agent context window — only structured enrichment
   records do. This keeps context lean and responses sharp.
7. On SQL errors the agent passes the error back to Claude to fix,
   max 2 retries before returning the error to the UI.

## Environment variables
ANTHROPIC_API_KEY=
GITHUB_TOKEN=         # Personal access token with repo read scope

## Demo flow (for interview)
1. Open Streamlit — show the summary dashboard (issue count, advocate
   opportunity %, top category, top sentiment)
2. Ask 2-3 natural language questions, show the SQL expander, narrate
   the interpretation
3. Pull up pipeline/ingest.py — show the PyAirbyte source-github
   config, point out docker_image=True and the label filter
4. Pull up pipeline/enrich.py — show the two-field prompt design
   (title + labels + body → structured JSON)
5. Tie back: "This is the same pattern Airbyte's Agent Engine uses
   at enterprise scale — data in, context out, agents on top"

## Demo questions (pre-loaded in Streamlit sidebar)
1. "What documentation gaps come up most often?"
2. "Which issues represent the best developer advocate opportunities?"
3. "What features are developers requesting most?"
4. "Give me 3 specific advocate actions based on these issues"
5. "What connectors or integrations are mentioned most?"

## What NOT to do
- Do NOT use docker_image=False for source-github — it will fail
- Do NOT use OpenAI — Anthropic Claude API only
- Do NOT pass raw issue body text into the agent context window
- Do NOT mock data — real PyAirbyte ingestion only
- Do NOT use async — keep everything synchronous
- Do NOT add features not described here — MVP only
- Do NOT hardcode credentials — always load from .env via python-dotenv