import airbyte as ab
from dotenv import load_dotenv
import os

load_dotenv()

source = ab.get_source(
    "source-github",
    docker_image=True,
    config={
        "credentials": {
            "personal_access_token": os.getenv("GITHUB_TOKEN")
        },
        "repositories": ["airbytehq/airbyte"]
    }
)

source.check()
print(source.get_available_streams())
print("Check passed!")

source.select_streams(["issues"])
result = source.read()
df = result["issues"].to_pandas()
print(df.columns.tolist())
print(df.head(2).to_dict())