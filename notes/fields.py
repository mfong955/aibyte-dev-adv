import urllib.request
import json
import os
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("GITHUB_TOKEN")
req = urllib.request.Request(
    "https://api.github.com/repos/airbytehq/airbyte/issues?per_page=3&state=open&labels=documentation",
    headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
)
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read())
    issue = data[0]
    print("Has body field:", "body" in issue)
    print("Body preview:", str(issue.get("body", ""))[:200])
    print("Label example:", issue["labels"][0] if issue["labels"] else "no labels")
    print("User field:", issue["user"]["login"])