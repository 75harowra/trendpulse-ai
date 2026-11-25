

import os
import json
import urllib.request

API_KEY = os.environ["GROQ_API_KEY"]

with open("trends.json", "r", encoding="utf-8") as f:
    trends = json.load(f)

    prompt = f"""
    You are a professional YouTube content creator.

    Analyze these trending topics:
    {json.dumps(trends, ensure_ascii=False)}

    Choose the 3 best topics and create:
    - Viral YouTube title
    - Strong opening hook
    - 60-second video script
    - Video description
    - 10 hashtags
    - Thumbnail idea

    Write everything in English.
    Return valid JSON only, as an object.
    """

    data = {
        "model": "llama-3.3-70b-versatile",
            "messages": [
                    {"role": "user", "content": prompt}
                        ],
                            "temperature": 0.7,
                                "response_format": {"type": "json_object"}
                                }

                                request = urllib.request.Request(
                                    "https://api.groq.com/openai/v1/chat/completions",
                                        data=json.dumps(data).encode("utf-8"),
                                            headers={
                                                    "Authorization": f"Bearer {API_KEY}",
                                                            "Content-Type": "application/json"
                                                                }
                                                                )

                                                                with urllib.request.urlopen(request, timeout=120) as response:
                                                                    result = json.load(response)

                                                                    content = result["choices"][0]["message"]["content"]
                                                                    scripts = json.loads(content)

                                                                    with open("scripts.json", "w", encoding="utf-8") as f:
                                                                        json.dump(scripts, f, ensure_ascii=False, indent=2)

                                                                        print("Video scripts generated successfully!")
                                                                        