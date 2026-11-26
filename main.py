
import urllib.request
import xml.etree.ElementTree as ET
import json
from datetime import datetime, timezone

CHANNEL = "TrendPulse Global"
LANGUAGE = "English"
VIDEOS_PER_DAY = 2
VIDEO_DURATION = "3-5 minutes"
MAX_TRENDS = 15


def get_trends():
    url = "https://trends.google.com/trending/rss?geo=US"

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(
        request, timeout=30
    ) as response:
        root = ET.fromstring(response.read())

    trends = []
    news_sources = {}

    def get_text(element, name):
        for child in element:
            if child.tag.split("}")[-1] == name:
                return (child.text or "").strip()
        return ""

    for item in root.findall("./channel/item"):

        title = item.findtext("title", "").strip()

        if not title or title in trends:
            continue

        trends.append(title)

        articles = []
        seen_urls = set()

        for news in item:

            if news.tag.split("}")[-1] != "news_item":
                continue

            link = get_text(news, "news_item_url")

            if not link.startswith("https://"):
                continue

            if link in seen_urls:
                continue

            seen_urls.add(link)

            articles.append({
                "title": get_text(
                    news, "news_item_title"
                ),
                "url": link,
                "source": get_text(
                    news, "news_item_source"
                ),
                "snippet": get_text(
                    news, "news_item_snippet"
                ),
                "published_at": get_text(
                    news, "news_item_pubdate"
                )
            })

        news_sources[title] = articles[:5]

        if len(trends) >= MAX_TRENDS:
            break

    if not trends:
        raise RuntimeError("No trends found")

    return trends, news_sources


def main():

    print("TrendPulse AI started")
    print("Searching trending news...")

    topics, news_sources = get_trends()

    total_sources = sum(
        len(articles)
        for articles in news_sources.values()
    )

    report = {
        "channel": CHANNEL,
        "language": LANGUAGE,
        "duration": VIDEO_DURATION,
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "topics": topics,
        "news_sources": news_sources,
        "videos_per_day": VIDEOS_PER_DAY,
        "status": "research_pending",
        "review_required": True
    }

    with open(
        "trends.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(json.dumps(
        report,
        ensure_ascii=False,
        indent=2
    ))

    print("=" * 45)
    print("SUCCESS: TrendPulse AI Research")
    print("Trending topics:", len(topics))
    print("News sources:", total_sources)
    print("Target videos:", VIDEOS_PER_DAY)
    print("Saved to trends.json")

    if total_sources == 0:
        print("WARNING: No news sources found")

    print("=" * 45)


if __name__ == "__main__":
    main()
