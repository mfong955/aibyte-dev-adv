# Airbyte Issue Analyst (2 days to build & prepare demo for POC/MVP assignment)

An AI-powered GitHub issue analyst that uses PyAirbyte's `source-github` connector to ingest issues from the `airbytehq/airbyte` repository into DuckDB, enriches them with Claude-powered structured analysis, then exposes a natural language Q&A agent for surfacing developer advocacy opportunities.

**Built & prepped (2 day assignment) as a proof of concept (POC) / minimum viable product (MVP) demo for final stages of interviews.**

---

## What this is

The Airbyte issue tracker is a goldmine of developer advocacy signal. Issues labeled `documentation`, `question`, `enhancement`, and `good first issue` are where confused or underserved developers speak up. This tool ingests those issues at scale, runs each one through a Claude analysis pipeline to extract structured signal (pain point, sentiment, category, advocate opportunity), and then lets you query all of it in plain English.

Three things this demo proves:

1. **PyAirbyte works as real data infrastructure** — the actual `source-github` connector ingests live GitHub issues, no mocks
2. **Claude handles both batch enrichment and conversational analysis** — structured JSON extraction plus text-to-SQL Q&A
3. **The output is genuinely useful** — community pain points mapped to concrete developer advocacy actions

---

## Screenshots

### Summary dashboard
![Airbyte Issue Analyst dashboard](images/Airbyte%20issue%20analysis.png)

The main dashboard surfaces four at-a-glance metrics — total issues analyzed, advocate opportunity count, top category, and dominant community sentiment — alongside a bar chart breaking issues down by category. This lets you instantly answer "where is developer friction concentrated?" without writing a single query, turning a firehose of GitHub noise into a prioritised action list.

---

### Natural language Q&A with generated SQL
![Prompting against AI-enriched dataset](images/Prompting%20against%20AI-enriched%20datatset.png)

Ask a plain-English question and the agent generates SQL against the enriched DuckDB schema, runs it, and returns a structured interpretation with direct links to the relevant GitHub issues. The generated SQL is exposed in a collapsible expander so you can verify exactly what the agent queried — making the analysis auditable, not a black box.

---

### Drilling down and verifying enrichment
![Drilling down and verifying AI-enriched dataset](images/Drilling%20down%20and%20verifying%20AI-enriched%20dataset.png)

Clicking a category bar filters the issue table to matching rows, showing titles and live GitHub URLs side-by-side. This makes it easy to sanity-check Claude's enrichment against the original issues — confirming that the AI labels are grounded in real developer feedback, not hallucinated categories.

---

## Why GitHub Issues?

GitHub issues are where developers describe their problems in their own words. At Airbyte's scale (`airbytehq/airbyte` has thousands of open issues), no one person can read them all. This pipeline automates the triage: every issue gets categorised, its sentiment tagged, and a specific advocate action suggested — turning a firehose of feedback into a prioritised action list.

---

## Architecture

```
source-github (Docker)
        │
        ▼
  PyAirbyte sync
        │
        ▼
  DuckDB (data/community.db)
    ├── issues table        ← 100 most recent matching issues
    └── enrichment table    ← Claude-structured analysis per issue
        │
        ▼
  AnalystAgent
    ├── Call 1: question → SQL   (Claude, few-shot)
    └── Call 2: SQL + results → interpretation  (Claude)
        │
        ▼
  Streamlit UI
    ├── Summary dashboard (metrics + bar chart)
    └── Natural language Q&A
```

---

## Setup

### Prerequisites

- Python 3.11+
- Docker Desktop running (required for `source-github`)
- A GitHub personal access token with `repo` read scope
- An Anthropic API key

### 1. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your keys:

```
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
```

### 4. Pull the source-github Docker image

```bash
docker pull airbyte/source-github:latest
```

### 5. Run the ingest pipeline

Syncs issues from `airbytehq/airbyte`, filters to advocacy-relevant labels, keeps the 100 most recent.

```bash
python -m pipeline.ingest
```

Expected output:
```
Fetched 3000+ raw issues from source.
Issues matching label filter: 450
--- Ingest summary ---
  Total fetched from source : 3412
  After label filter        : 450
  Total stored in DB        : 100
```

### 6. Run the enrichment pipeline

Calls Claude once per issue to extract structured signal. Idempotent — safe to re-run.

```bash
python -m pipeline.enrich
```

Expected output:
```
Issues to enrich: 100
  [1/100] #12345 enriched
  ...
--- Enrichment summary ---
  Total enriched         : 100
  Errors (logged)        : 0
  Advocate opportunities : 42
```

Errors (if any) are logged to `data/enrich_errors.log`.

### 7. Launch the Streamlit app

```bash
streamlit run app/streamlit_app.py
```

Opens at `http://localhost:8501`.

---

## Demo questions

These are pre-loaded in the sidebar:

1. **What documentation gaps come up most often?**
2. **Which issues represent the best developer advocate opportunities?**
3. **What features are developers requesting most?**
4. **Give me 3 specific advocate actions based on these issues**
5. **What connectors or integrations are mentioned most?**

Each answer shows the generated SQL (collapsed expander), a plain-language interpretation, and a raw results table.

---

## Project structure

```
airbyte-devadv/
├── pipeline/
│   ├── ingest.py          # PyAirbyte source-github → DuckDB
│   └── enrich.py          # Batch Claude enrichment per issue
├── agent/
│   └── analyst.py         # Text-to-SQL conversational agent
├── app/
│   └── streamlit_app.py   # Streamlit demo UI
├── data/
│   └── community.db       # Persisted DuckDB file (gitignored)
├── requirements.txt
├── .env.example
└── CLAUDE.md
```
