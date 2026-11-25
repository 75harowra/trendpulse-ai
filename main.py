import urllib.request
import xml.etree.ElementTree as ET
import json
from datetime import datetime, timezone

CHANNEL = "TrendPulse Global"
LANGUAGE = "English"
VIDEOS_PER_DAY = 2
VIDEO_DURATION = "3-5 minutes"

def get_trends():
    url = "https://trends.google.com/trending/rss?geo=US"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())

    trends = []

    for item in root.findall("./channel/item"):
        title = item.findtext("title")
        if title and title not in trends:
            trends.append(title)

    if not trends:
        raise RuntimeError("No trends found")

    return trends[:VIDEOS_PER_DAY]

def main():
    print("TrendPulse AI started")

    topics = get_trends()

    report = {
        "channel": CHANNEL,
        "language": LANGUAGE,
        "duration": VIDEO_DURATION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "topics": topics,
        "status": "research_pending"
    }

    with open("trends.json", "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
