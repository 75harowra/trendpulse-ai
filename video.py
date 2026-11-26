
# ==========================================
# TrendPulse Global V4.2
# Enhanced Media Search
# ==========================================

VERSION = "4.2"

session.headers.update({
    "User-Agent": "TrendPulseGlobal/4.2"
})

original_keywords = keywords


def keywords(item):

    content = (
        str(item.get("title", "")) + " " +
        str(item.get("topic", ""))
    ).lower()

    queries = original_keywords(item)

    categories = [
        (
            r"\b(gta|gaming|game|games|rockstar|playstation|xbox)\b",
            [
                "video game",
                "gaming controller",
                "gaming computer",
                "game development",
                "gaming setup",
                "computer graphics",
                "game console",
                "gaming keyboard",
                "esports"
            ]
        ),
        (
            r"\b(ai|nvidia|gpu|chatgpt|robot|artificial intelligence)\b",
            [
                "computer chip",
                "graphics card",
                "data center",
                "microprocessor",
                "artificial intelligence",
                "computer technology",
                "semiconductor"
            ]
        ),
        (
            r"\b(storm|weather|hurricane|flood|rain)\b",
            [
                "storm clouds",
                "heavy rain",
                "weather radar",
                "strong wind",
                "rainfall",
                "thunderstorm"
            ]
        ),
        (
            r"\b(restaurant|denny|pancake|mcdonald|food)\b",
            [
                "restaurant interior",
                "pancakes",
                "restaurant kitchen",
                "breakfast"
            ]
        ),
        (
            r"\b(electric car|electric vehicle|tesla|hybrid car)\b",
            [
                "electric vehicle",
                "car charging",
                "electric motor",
                "car battery",
                "car factory"
            ]
        ),
        (
            r"\b(space|nasa|rocket|satellite)\b",
            [
                "rocket launch",
                "space exploration",
                "satellite",
                "planet earth",
                "space station"
            ]
        ),
        (
            r"\b(economy|finance|stock market|banking)\b",
            [
                "stock market",
                "financial chart",
                "business meeting",
                "banking"
            ]
        ),
        (
            r"\b(technology|innovation|invention)\b",
            [
                "computer technology",
                "electronics",
                "engineering laboratory",
                "computer processor"
            ]
        )
    ]

    fallback = []

    for pattern, extra in categories:
        if re.search(pattern, content):
            fallback.extend(extra)

    unique = []
    seen = set()

    for query in queries + fallback:

        if not isinstance(query, str):
            continue

        query = query.strip()[:100]
        key = query.lower()

        if key and key not in seen:
            unique.append(query)
            seen.add(key)

    print(
        "Enhanced search V4.2:",
        len(unique),
        "queries",
        flush=True
    )

    return unique[:32]


original_get_media = get_media


def get_media(item, folder, limit):

    media, sources = original_get_media(
        item,
        folder,
        limit
    )

    print(
        "V4.2 media collected:",
        len(media),
        flush=True
    )

    if len(media) < 3:

        print(
            "WARNING: Not enough relevant licensed media",
            flush=True
        )

    elif len(media) < 10:

        print(
            "WARNING: Limited visual variety",
            flush=True
        )

    return media, sources


print("=" * 50)
print("TrendPulse Global V4.2")
print("Enhanced media search enabled")
print("License protection enabled")
print("Full HD rendering enabled")
print("=" * 50)

