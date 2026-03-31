"""Batch-enrich GitHub issues with Claude-powered structured analysis."""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import duckdb
from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(__file__).parent.parent / "data" / "community.db"
ERROR_LOG = Path(__file__).parent.parent / "data" / "enrich_errors.log"

MODEL = "claude-sonnet-4-20250514"
BATCH_SIZE = 5
BATCH_SLEEP = 1  # seconds between batches

VALID_CATEGORIES = {
    "documentation-gap",
    "feature-request",
    "question",
    "bug-with-advocacy-angle",
    "integration-request",
    "other",
}

VALID_SENTIMENTS = {"frustrated", "confused", "hopeful", "neutral"}

logging.basicConfig(
    filename=str(ERROR_LOG),
    level=logging.ERROR,
    format="%(asctime)s %(message)s",
)


def _build_prompt(title: str, labels: str, body: str) -> str:
    """Build the user prompt for a single issue."""
    return f"""Analyze this GitHub issue from the Airbyte open source repo.

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
  "category": "one of exactly: documentation-gap | feature-request | question | bug-with-advocacy-angle | integration-request | other",
  "community_sentiment": "one of exactly: frustrated | confused | hopeful | neutral",
  "advocate_opportunity": true or false,
  "advocate_action": "one sentence: what a DA could do here, or null"
}}"""


def _parse_response(text: str) -> dict:
    """Parse and validate Claude's JSON response."""
    parsed = json.loads(text.strip())

    # Normalise tools_mentioned to a comma-separated string for storage
    tools = parsed.get("tools_mentioned", [])
    if isinstance(tools, list):
        parsed["tools_mentioned"] = ", ".join(str(t) for t in tools)

    # Coerce category / sentiment to allowed values
    if parsed.get("category") not in VALID_CATEGORIES:
        parsed["category"] = "other"
    if parsed.get("community_sentiment") not in VALID_SENTIMENTS:
        parsed["community_sentiment"] = "neutral"

    return parsed


def _ensure_enrichment_table(con: duckdb.DuckDBPyConnection) -> None:
    """Create the enrichment table if it doesn't exist."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS enrichment (
            issue_number        INTEGER PRIMARY KEY,
            pain_point          TEXT,
            tools_mentioned     TEXT,
            airbyte_relevant    BOOLEAN,
            relevance_reason    TEXT,
            unmet_need          TEXT,
            category            TEXT,
            community_sentiment TEXT,
            advocate_opportunity BOOLEAN,
            advocate_action     TEXT,
            enriched_at         TIMESTAMP
        )
    """)


def run_enrich() -> None:
    """Enrich all un-enriched issues in DuckDB using the Claude API."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY environment variable is not set.")

    client = anthropic.Anthropic(api_key=api_key)
    con = duckdb.connect(str(DB_PATH))
    _ensure_enrichment_table(con)

    rows = con.execute("""
        SELECT i.issue_number, i.title, i.labels, i.body
        FROM issues i
        LEFT JOIN enrichment e ON i.issue_number = e.issue_number
        WHERE e.issue_number IS NULL
        ORDER BY i.created_at DESC
    """).fetchall()

    total = len(rows)
    print(f"Issues to enrich: {total}")

    enriched_count = 0
    error_count = 0
    advocate_count = 0

    for batch_start in range(0, total, BATCH_SIZE):
        batch = rows[batch_start: batch_start + BATCH_SIZE]

        for issue_number, title, labels, body in batch:
            try:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=512,
                    system=(
                        "You are a developer community analyst helping a Developer Advocate "
                        "at Airbyte understand what developers need. Analyze GitHub issues "
                        "from the airbytehq/airbyte repo and extract structured signal. "
                        "Always respond with valid JSON only. No preamble, no markdown fences."
                    ),
                    messages=[
                        {
                            "role": "user",
                            "content": _build_prompt(title, labels, body or ""),
                        }
                    ],
                )

                parsed = _parse_response(response.content[0].text)
                now = datetime.now(timezone.utc)

                con.execute("""
                    INSERT INTO enrichment VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    ON CONFLICT (issue_number) DO NOTHING
                """, [
                    issue_number,
                    parsed.get("pain_point"),
                    parsed.get("tools_mentioned"),
                    bool(parsed.get("airbyte_relevant")),
                    parsed.get("relevance_reason"),
                    parsed.get("unmet_need"),
                    parsed.get("category"),
                    parsed.get("community_sentiment"),
                    bool(parsed.get("advocate_opportunity")),
                    parsed.get("advocate_action"),
                    now,
                ])

                enriched_count += 1
                if parsed.get("advocate_opportunity"):
                    advocate_count += 1

                print(f"  [{enriched_count}/{total}] #{issue_number} enriched")

            except Exception as exc:
                error_count += 1
                logging.error("issue_number=%s error=%s", issue_number, exc)
                print(f"  [ERROR] #{issue_number}: {exc}")

        if batch_start + BATCH_SIZE < total:
            time.sleep(BATCH_SLEEP)

    con.close()

    print(f"\n--- Enrichment summary ---")
    print(f"  Total enriched         : {enriched_count}")
    print(f"  Errors (logged)        : {error_count}")
    print(f"  Advocate opportunities : {advocate_count}")


if __name__ == "__main__":
    run_enrich()
