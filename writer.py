import os
import sys
import json
import subprocess
from datetime import datetime, timezone

try:
    from groq import Groq
except ImportError:
    subprocess.check_call([
        sys.executable, "-m", "pip",
        "install", "groq"
    ])
    from groq import Groq

API_KEY = os.environ.get("GROQ_API_KEY", "")

if not API_KEY:
    raise SystemExit("Missing GROQ_API_KEY")

client = Groq(
    api_key=API_KEY,
    timeout=120.0,
    max_retries=2
)

with open("trends.json", "r", encoding="utf-8") as f:
    trends = json.load(f)

today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

prompt = f"""
You are TrendPulse AI, a professional
YouTube content creator.

Current date: {today}

Trending topics:
{json.dumps(trends, ensure_ascii=False)}

Select up to 3 distinct trending topics.

For each topic create:

- Engaging YouTube title
- Strong opening hook
- English narration script
- Video duration of 3 to 5 minutes
- Video description
- 10 hashtags
- Thumbnail idea

RULES:

Write everything in English.
Use the current date as context.
Do not invent facts or news.
Do not claim unverified information.
Avoid outdated information.
Write 400 to 650 narration words per topic.
Keep narration separate from visual instructions.

Return valid JSON only.

Use this structure:

{{
    "selected_topics": [
        {{
            "topic": "",
            "title": "",
            "opening_hook": "",
            "script": "",
            "description": "",
            "hashtags": [],
            "thumbnail_idea": ""
        }}
    ]
}}
"""

try:
    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.5,
        max_completion_tokens=10000,
        response_format={
            "type": "json_object"
        }
    )

    content = response.choices[0].message.content

    result = json.loads(content)

    if not result.get("selected_topics"):
        raise ValueError("No topics generated")

    with open(
        "scripts.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("SUCCESS: Video scripts generated")
    print("Saved to scripts.json")

except Exception as e:
    print("ERROR:", str(e))
    sys.exit(1)
