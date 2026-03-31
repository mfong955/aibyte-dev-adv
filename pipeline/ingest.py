"""
Ingest GitHub issues from airbytehq/airbyte into DuckDB.

Uses the GitHub REST API directly with a hard limit to keep
the demo fast. Fetches all non-PR issues; advocacy relevance
is determined during enrichment by Claude.
"""

import duckdb
import urllib.request
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "airbytehq/airbyte"
MAX_ISSUES = 1000
DB_PATH = "data/community.db"


def fetch_issues(max_issues: int = MAX_ISSUES) -> list[dict]:
    """Fetch open issues from GitHub API filtered by advocacy labels."""
    issues = []
    page = 1
    per_page = 50

    print(f"Fetching up to {max_issues} issues from {REPO}...")

    while len(issues) < max_issues:
        url = (
            f"https://api.github.com/repos/{REPO}/issues"
            f"?state=open&per_page={per_page}&page={page}"
            f"&sort=created&direction=desc"
        )
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json"
            }
        )
        with urllib.request.urlopen(req) as response:
            batch = json.loads(response.read())

        if not batch:
            break

        # GitHub issues endpoint returns PRs too — filter them out
        for item in batch:
            if "pull_request" in item:
                continue
            issues.append(item)
            if len(issues) >= max_issues:
                break

        print(f"  Page {page}: {len(issues)} qualifying issues so far...")
        page += 1
        time.sleep(0.5)  # be polite to the API

    return issues[:max_issues]


def save_to_duckdb(issues: list[dict]) -> None:
    """Write issues to DuckDB."""
    os.makedirs("data", exist_ok=True)
    con = duckdb.connect(DB_PATH)

    con.execute("""
        CREATE TABLE IF NOT EXISTS issues (
            issue_number INTEGER PRIMARY KEY,
            title TEXT,
            body TEXT,
            author TEXT,
            state TEXT,
            labels TEXT,
            comment_count INTEGER,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            html_url TEXT
        )
    """)

    inserted = 0
    skipped = 0

    for issue in issues:
        label_names = ", ".join(
            l["name"] for l in issue.get("labels", [])
        )
        body = (issue.get("body") or "")[:1000]
        author = issue.get("user", {}).get("login", "unknown")

        try:
            con.execute("""
                INSERT OR IGNORE INTO issues VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                issue["number"],
                issue["title"],
                body,
                author,
                issue["state"],
                label_names,
                issue.get("comments", 0),
                issue["created_at"],
                issue["updated_at"],
                issue["html_url"]
            ])
            inserted += 1
        except Exception as e:
            print(f"  Skipping issue #{issue['number']}: {e}")
            skipped += 1

    con.close()
    print(f"\nDone. {inserted} issues inserted, {skipped} skipped.")
    print(f"Database: {DB_PATH}")


if __name__ == "__main__":
    issues = fetch_issues()
    save_to_duckdb(issues)