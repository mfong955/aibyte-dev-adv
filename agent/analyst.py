"""Text-to-SQL conversational agent for Airbyte issue analysis."""

import json
import os
from pathlib import Path

import anthropic
import duckdb
from dotenv import load_dotenv

load_dotenv()

DB_PATH = Path(__file__).parent.parent / "data" / "community.db"
MODEL = "claude-sonnet-4-20250514"
MAX_RETRIES = 2
MAX_RESULT_ROWS = 30

SCHEMA_CONTEXT = """
You have access to a DuckDB database with two tables:

TABLE: issues
  issue_number  INTEGER  -- primary key
  title         TEXT
  body          TEXT
  author        TEXT
  state         TEXT     -- 'open' or 'closed'
  labels        TEXT     -- comma-separated label names
  comment_count INTEGER
  created_at    TIMESTAMP
  updated_at    TIMESTAMP
  html_url      TEXT

TABLE: enrichment
  issue_number         INTEGER  -- primary key, foreign key to issues
  pain_point           TEXT
  tools_mentioned      TEXT     -- comma-separated tool names
  airbyte_relevant     BOOLEAN
  relevance_reason     TEXT
  unmet_need           TEXT
  category             TEXT     -- documentation-gap | feature-request | question |
                                --   bug-with-advocacy-angle | integration-request | other
  community_sentiment  TEXT     -- frustrated | confused | hopeful | neutral
  advocate_opportunity BOOLEAN
  advocate_action      TEXT
  enriched_at          TIMESTAMP
"""

FEW_SHOT_EXAMPLES = """
Examples:

Q: "What are the most common issue categories?"
SQL: SELECT category, COUNT(*) as count FROM enrichment GROUP BY category ORDER BY count DESC

Q: "Which issues are advocate opportunities?"
SQL: SELECT i.title, i.labels, e.advocate_action
     FROM issues i JOIN enrichment e ON i.issue_number = e.issue_number
     WHERE e.advocate_opportunity = true
     ORDER BY i.created_at DESC LIMIT 10

Q: "What tools are mentioned most often?"
SQL: SELECT value as tool, COUNT(*) as count
     FROM enrichment,
     json_each('["' || replace(tools_mentioned, ', ', '","') || '"]')
     WHERE tools_mentioned != ''
     GROUP BY value ORDER BY count DESC LIMIT 15
"""

SQL_SYSTEM_PROMPT = f"""You are a SQL expert working with a DuckDB database containing GitHub issue data.
{SCHEMA_CONTEXT}
{FEW_SHOT_EXAMPLES}
Return SQL only. No explanation, no markdown fences, no preamble.
The query must be valid DuckDB SQL."""

INTERPRET_SYSTEM_PROMPT = """You are a developer advocate analyst interpreting GitHub issue data for a developer audience.
Summarize the query results in 2-4 sentences. Be specific and actionable.
If the results are empty, say so clearly and suggest why that might be."""


class AnalystAgent:
    """Agent that answers natural language questions about Airbyte GitHub issues.

    Uses two Claude API calls per question:
    1. Generate DuckDB SQL from the question (with few-shot examples).
    2. Interpret the query results in plain language.

    SQL errors are retried up to MAX_RETRIES times by passing the error
    back to Claude for correction.
    """

    def __init__(self) -> None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY environment variable is not set.")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.db_path = str(DB_PATH)

    def _generate_sql(self, question: str, error_feedback: str | None = None) -> str:
        """Call Claude to generate SQL for the given question.

        Args:
            question: Natural language question from the user.
            error_feedback: Previous SQL error to include for retry correction.

        Returns:
            SQL string from Claude.
        """
        user_content = f'Question: "{question}"'
        if error_feedback:
            user_content += f"\n\nThe previous SQL failed with this error:\n{error_feedback}\nPlease fix the SQL."

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=SQL_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text.strip()

    def _run_sql(self, sql: str) -> list[dict]:
        """Execute SQL against DuckDB and return rows as a list of dicts.

        Args:
            sql: Valid DuckDB SQL query string.

        Returns:
            List of row dicts, up to MAX_RESULT_ROWS entries.

        Raises:
            duckdb.Error: If the query fails.
        """
        con = duckdb.connect(self.db_path, read_only=True)
        try:
            rel = con.execute(sql)
            columns = [desc[0] for desc in rel.description]
            rows = rel.fetchmany(MAX_RESULT_ROWS)
            return [dict(zip(columns, row)) for row in rows]
        finally:
            con.close()

    def _interpret(self, question: str, sql: str, results: list[dict]) -> str:
        """Call Claude to interpret query results in plain language.

        Args:
            question: The original user question.
            sql: The SQL that was executed.
            results: Row dicts returned by the query.

        Returns:
            Interpretation string.
        """
        results_json = json.dumps(results, default=str, separators=(",", ":"))
        user_content = (
            f'Question: "{question}"\n\n'
            f"SQL:\n{sql}\n\n"
            f"Results ({len(results)} rows):\n{results_json}"
        )
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=INTERPRET_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text.strip()

    def ask(self, question: str) -> dict:
        """Answer a natural language question about Airbyte GitHub issues.

        Args:
            question: Natural language question from the user.

        Returns:
            Dict with keys:
              - sql (str): The generated SQL query.
              - results (list[dict]): Raw query results.
              - interpretation (str): Claude's plain-language interpretation.
              - error (str | None): Error message if the query ultimately failed.
        """
        sql = ""
        results: list[dict] = []
        error_feedback: str | None = None

        for attempt in range(MAX_RETRIES + 1):
            sql = self._generate_sql(question, error_feedback=error_feedback)
            try:
                results = self._run_sql(sql)
                error_feedback = None
                break
            except Exception as exc:
                error_feedback = str(exc)
                if attempt == MAX_RETRIES:
                    return {
                        "sql": sql,
                        "results": [],
                        "interpretation": "",
                        "error": f"Query failed after {MAX_RETRIES + 1} attempts: {error_feedback}",
                    }

        interpretation = self._interpret(question, sql, results)
        return {
            "sql": sql,
            "results": results,
            "interpretation": interpretation,
            "error": None,
        }


if __name__ == "__main__":
    import sys

    question = " ".join(sys.argv[1:]) or "What are the most common issue categories?"
    agent = AnalystAgent()
    result = agent.ask(question)
    print(f"\nSQL:\n{result['sql']}\n")
    if result["error"]:
        print(f"Error: {result['error']}")
    else:
        print(f"Results ({len(result['results'])} rows):")
        for row in result["results"]:
            print(" ", row)
        print(f"\nInterpretation:\n{result['interpretation']}")
