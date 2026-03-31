import urllib.request
import json
import os

token = os.getenv("GITHUB_TOKEN")
req = urllib.request.Request(
    "https://api.github.com/repos/airbytehq/airbyte/discussions?per_page=5",
    headers={"Authorization": f"token {token}"}
)
with urllib.request.urlopen(req) as response:
    data = json.loads(response.read())
    print(json.dumps(data[0], indent=2))
    
