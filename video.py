
import os
import json
import math
import re
import html
import requests
import subprocess
import tempfile
import textwrap
from pathlib import Path

API_KEY = os.getenv("PIXABAY_API_KEY")

WIDTH = 1920
HEIGHT = 1080
FPS = 25
SCENE_TIME = 6
MAX_MEDIA = 20

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

output = Path("videos")
output.mkdir(exist_ok=True)

with open("scripts.json", encoding="utf-8") as f:
    topics = json.load(f)["selected_topics"]

session = requests.Session()
session.headers.update({
    "User-Agent": "TrendPulseGlobal/3.0 (https://github.com/75harowra/trendpulse-ai)"
})

cache = {}


def run(cmd):
    subprocess.run(cmd, check=True)


def duration(path):
    result = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ])
    return float(result.strip())


def clean(value):
    return html.unescape(
        re.sub(r"<[^>]+>", "", str(value))
    ).strip()


def keywords(item):
    title = str(item.get("title", ""))
    topic = str(item.get("topic", ""))
    content = (title + " " + topic).lower()

    queries = item.get("visual_keywords", [])

    if not isinstance(queries, list):
        queries = []

    queries = [
        q.strip()[:100]
        for q in queries
        if isinstance(q, str) and q.strip()
    ]

    categories = [
        (
            ["nba", "basketball", "wembanyama",
             "anunoby", "jrue holiday"],
            ["basketball", "basketball player",
             "basketball court"]
        ),
        (
            ["nfl", "american football", "garrett"],
            ["american football", "football helmet"]
        ),
        (
            ["soccer", "fifa", "football"],
            ["soccer", "soccer stadium"]
        ),
        (
            ["artificial intelligence", "robot", "chatgpt"],
            ["robot technology", "computer processor"]
        ),
        (
            ["electric car", "tesla", "electric vehicle"],
            ["electric car", "car charging"]
        ),
        (
            ["finance", "economy", "stock market"],
            ["financial chart", "stock market"]
        ),
        (
            ["space", "nasa", "rocket"],
            ["rocket launch", "space exploration"]
        ),
        (
            ["marketing", "social media", "viral"],
            ["digital marketing", "social media"]
        )
    ]

    for triggers, extra in categories:
        if any(word in content for word in triggers):
            queries.extend(extra)
            break

    if not queries and topic:
        queries.append(topic[:100])

    return list(dict.fromkeys(queries))[:8]


def download(url, path):
    with session.get(
        url, stream=True, timeout=45
    ) as response:

        response.raise_for_status()
        size = 0

        with open(path, "wb") as f:
            for chunk in response.iter_content(65536):
                if not chunk:
                    continue

                size += len(chunk)

                if size > 35 * 1024 * 1024:
                    raise ValueError("File too large")

                f.write(chunk)


def valid_media(path):
    try:
        result = subprocess.check_output([
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json", str(path)
        ])

        streams = json.loads(result).get("streams", [])

        return bool(
            streams
            and streams[0].get("width", 0) >= 400
            and streams[0].get("height", 0) >= 300
        )

    except Exception:
        return False


def search_pixabay(query, media):
    if not API_KEY:
        return []

    key = ("pixabay", query, media)

    if key in cache:
        return cache[key]

    endpoint = "https://pixabay.com/api/"

    if media == "video":
        endpoint += "videos/"

    params = {
        "key": API_KEY,
        "q": query,
        "per_page": 20,
        "safesearch": "true",
        "order": "popular"
    }

    if media == "image":
        params["image_type"] = "photo"

    try:
        response = session.get(
            endpoint,
            params=params,
            timeout=30
        )

        response.raise_for_status()

        hits = response.json().get("hits", [])
        cache[key] = hits
        return hits

    except Exception:
        return []


def relevant(tags, query):
    tags = str(tags).lower()

    words = re.findall(
        r"[a-z0-9]+", query.lower()
    )

    ignored = {
        "the", "and", "with", "for",
        "news", "today", "global",
        "professional"
    }

    words = [
        w for w in words
        if len(w) > 2 and w not in ignored
    ]

    if not words:
        return False

    matches = sum(
        bool(re.search(
            r"\b" + re.escape(w) + r"s?\b",
            tags
        ))
        for w in words
    )

    return matches == len(words)


def search_commons(query):
    key = ("commons", query)

    if key in cache:
        return cache[key]

    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query + " filetype:bitmap",
        "gsrnamespace": 6,
        "gsrlimit": 15,
        "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata",
        "iiurlwidth": 1280,
        "format": "json"
    }

    results = []

    try:
        response = session.get(
            "https://commons.wikimedia.org/w/api.php",
            params=params,
            timeout=30
        )

        response.raise_for_status()

        pages = response.json().get(
            "query", {}
        ).get("pages", {})

        for page in pages.values():
            info = page.get("imageinfo", [])

            if not info:
                continue

            info = info[0]

            if info.get("mime") != "image/jpeg":
                continue

            meta = info.get("extmetadata", {})

            license_name = clean(
                meta.get(
                    "LicenseShortName", {}
                ).get("value", "")
            )

            allowed = {
                "CC0",
                "Public domain",
                "CC BY 4.0",
                "CC BY 3.0",
                "CC BY 2.0"
            }

            if license_name not in allowed:
                continue

            author = clean(
                meta.get(
                    "Artist", {}
                ).get("value", "")
            )

            license_url = clean(
                meta.get(
                    "LicenseUrl", {}
                ).get("value", "")
            )

            restrictions = clean(
                meta.get(
                    "Restrictions", {}
                ).get("value", "")
            )

            if restrictions:
                continue

            if license_name.startswith("CC BY"):
                if not author or not license_url:
                    continue

            title = page.get("title", "")

            if not relevant(title, query):
                continue

            url = info.get("thumburl") or info.get("url")

            if not url:
                continue

            results.append({
                "id": page.get("pageid"),
                "url": url,
                "page": info.get("descriptionurl", ""),
                "author": author,
                "title": title,
                "license": license_name,
                "license_url": license_url,
                "provider": "Wikimedia Commons",
                "query": query
            })

        cache[key] = results

    except Exception as error:
        print("Commons search:", error)

    return results


def get_media(item, folder, limit):
    files = []
    sources = []
    seen = set()

    queries = keywords(item)

    print("Visual keywords:", queries, flush=True)

    topic = str(item.get("topic", "")).strip()

    commons_queries = list(dict.fromkeys(
        ([topic[:100]] if topic else []) + queries
    ))

    def save(url, extension, source, identity):
        if identity in seen:
            return False

        if len(files) >= limit:
            return False

        seen.add(identity)

        path = folder / (
            f"media_{len(files)}{extension}"
        )

        try:
            download(url, path)

            if not valid_media(path):
                raise ValueError("Invalid media")

            files.append(path)
            sources.append(source)
            return True

        except Exception:
            path.unlink(missing_ok=True)
            return False

    for query in commons_queries:
        for hit in search_commons(query):
            if save(
                hit["url"],
                ".jpg",
                hit,
                ("commons", hit["id"])
            ):
                if len(files) >= min(6, limit):
                    break

        if len(files) >= min(6, limit):
            break

    for query in queries:
        for media in ["video", "image"]:
            added = 0

            for hit in search_pixabay(query, media):
                if len(files) >= limit:
                    return files, sources

                if not relevant(
                    hit.get("tags", ""), query
                ):
                    continue

                if media == "video":
                    versions = hit.get("videos", {})

                    url = (
                        versions.get(
                            "medium", {}
                        ).get("url")
                        or versions.get(
                            "small", {}
                        ).get("url")
                    )

                    extension = ".mp4"

                else:
                    url = hit.get("largeImageURL")
                    extension = ".jpg"

                if not url:
                    continue

                source = {
                    "provider": "Pixabay",
                    "page": hit.get("pageURL", ""),
                    "author": hit.get("user", ""),
                    "license": "Pixabay Content License",
                    "license_url":
                        "https://pixabay.com/service/license-summary/",
                    "query": query,
                    "type": media
                }

                if save(
                    url,
                    extension,
                    source,
                    ("pixabay", media, hit.get("id"))
                ):
                    added += 1

                if added >= 2:
                    break

    return files, sources


def make_scene(source, target, seconds):
    base = (
        f"scale={WIDTH}:{HEIGHT}:"
        "force_original_aspect_ratio=decrease,"
        f"pad={WIDTH}:{HEIGHT}:"
        "(ow-iw)/2:(oh-ih)/2:"
        "color=0x142238,"
        "setsar=1"
    )

    command = ["ffmpeg", "-y"]

    if source.suffix.lower() == ".jpg":
        command += [
            "-loop", "1",
            "-i", str(source)
        ]
    else:
        command += [
            "-stream_loop", "-1",
            "-i", str(source)
        ]

    command += [
        "-vf", base,
        "-t", f"{seconds:.3f}",
        "-an",
        "-r", str(FPS),
        "-c:v", "libx264",
        "-threads", "2",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-loglevel", "error",
        str(target)
    ]

    run(command)


def find_subtitles(index):
    candidates = [
        Path(f"audio/video_{index}.srt"),
        Path(f"subtitles/video_{index}.srt"),
        Path(f"captions/video_{index}.srt")
    ]

    for path in candidates:
        if path.exists() and path.stat().st_size:
            return path.resolve()

    return None


def make_thumbnail(index, item, media, folder):
    headline = str(
        item.get("thumbnail_text")
        or item.get("topic")
        or "TRENDING NOW"
    )

    headline = " ".join(headline.split()[:4])
    headline = textwrap.fill(
        headline.upper(),
        width=18
    )

    text_file = folder / "thumbnail.txt"
    text_file.write_text(
        headline,
        encoding="utf-8"
    )

    filters = (
        "scale=1280:720:"
        "force_original_aspect_ratio=increase,"
        "crop=1280:720,"
        "drawbox=x=0:y=450:w=iw:h=270:"
        "color=0x071329@0.85:t=fill,"
        "drawbox=x=0:y=450:w=iw:h=8:"
        "color=yellow:t=fill,"
        f"drawtext=fontfile={FONT}:"
        "text='TRENDPULSE GLOBAL':"
        "fontsize=30:fontcolor=white:"
        "box=1:boxcolor=0x071329@0.8:"
        "boxborderw=12:x=30:y=30,"
        f"drawtext=fontfile={FONT}:"
        f"textfile={text_file}:"
        "expansion=none:"
        "fontsize=64:fontcolor=yellow:"
        "borderw=3:bordercolor=black:"
        "x=(w-tw)/2:y=460+(250-th)/2"
    )

    target = output / f"thumbnail_{index}.jpg"

    for source in media:
        try:
            command = ["ffmpeg", "-y"]

            if source.suffix == ".mp4":
                command += ["-ss", "1"]

            command += [
                "-i", str(source),
                "-vf", filters,
                "-frames:v", "1",
                "-q:v", "3",
                "-loglevel", "error",
                str(target)
            ]

            run(command)

            if target.exists() and target.stat().st_size:
                return

        except Exception:
            target.unlink(missing_ok=True)

    raise RuntimeError("Thumbnail creation failed")


def save_credits(index, item, sources):
    credits = []
    seen = set()

    for source in sources:
        page = source.get("page", "")

        if page in seen:
            continue

        seen.add(page)

        credits.append(
            f"{source.get('title', source.get('query', 'Media'))}\n"
            f"Author: {source.get('author', '')}\n"
            f"Source: {page}\n"
            f"License: {source.get('license', '')}\n"
            f"{source.get('license_url', '')}\n"
            "Changes: resized, cropped or text overlay.\n"
        )

    credit_text = "\n".join(credits)

    (output / f"credits_{index}.txt").write_text(
        credit_text,
        encoding="utf-8"
    )

    (output / f"sources_{index}.json").write_text(
        json.dumps(
            sources,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    details = dict(item)

    details["media_credits"] = credit_text
    details["review_required"] = True

    (output / f"details_{index}.json").write_text(
        json.dumps(
            details,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def make_video(index, item):
    title = str(
        item.get("title")
        or item.get("topic")
        or "Trending Today"
    )

    audio = Path(f"audio/video_{index}.mp3")
    video = output / f"video_{index}.mp4"

    if not audio.exists():
        raise FileNotFoundError(audio)

    total = duration(audio)

    if total <= 0:
        raise RuntimeError("Invalid audio")

    if total < 180:
        print(
            "WARNING: Video shorter than 3 minutes",
            flush=True
        )

    count = math.ceil(total / SCENE_TIME)

    print("Creating:", title, flush=True)

    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)

        media, sources = get_media(
            item,
            folder,
            min(count, MAX_MEDIA)
        )

        if len(media) < 3:
            raise RuntimeError(
                "Insufficient relevant media. "
                "Video skipped."
            )

        scenes = []
        used_media = []
        used_sources = []

        for n in range(count):
            seconds = min(
                SCENE_TIME,
                total - n * SCENE_TIME
            )

            if seconds <= 0:
                break

            scene = folder / f"scene_{n}.mp4"
            created = False

            for offset in range(len(media)):
                position = (n + offset) % len(media)
                source = media[position]

                try:
                    make_scene(
                        source,
                        scene,
                        seconds
                    )

                    created = True

                    if source not in used_media:
                        used_media.append(source)
                        used_sources.append(
                            sources[position]
                        )

                    break

                except subprocess.CalledProcessError:
                    scene.unlink(missing_ok=True)

            if not created:
                raise RuntimeError(
                    "No valid scene available"
                )

            scenes.append(scene)

        concat = folder / "concat.txt"

        concat.write_text(
            "\n".join(
                f"file '{p.as_posix()}'"
                for p in scenes
            ),
            encoding="utf-8"
        )

        combined = folder / "combined.mp4"

        run([
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat),
            "-c", "copy",
            "-loglevel", "error",
            str(combined)
        ])

        title_file = folder / "title.txt"

        title_file.write_text(
            textwrap.fill(title, width=36),
            encoding="utf-8"
        )

        filters = (
            "drawbox=x=0:y=0:w=iw:h=8:"
            "color=cyan:t=fill,"
            f"drawtext=fontfile={FONT}:"
            "text='TRENDPULSE GLOBAL':"
            "fontsize=30:fontcolor=white:"
            "box=1:boxcolor=0x071329@0.8:"
            "boxborderw=12:x=35:y=35,"
            f"drawtext=fontfile={FONT}:"
            f"textfile={title_file}:"
            "expansion=none:"
            "fontsize=52:fontcolor=white:"
            "box=1:boxcolor=black@0.75:"
            "boxborderw=20:"
            "x=(w-tw)/2:y=(h-th)/2:"
            "enable='lt(t,3)',"
            f"drawtext=fontfile={FONT}:"
            "text='Illustrative footage':"
            "fontsize=20:fontcolor=white:"
            "box=1:boxcolor=black@0.6:"
            "x=30:y=h-40"
        )

        subtitles = find_subtitles(index)

        if subtitles:
            filters += (
                f",subtitles={subtitles.as_posix()}:"
                "force_style='FontName=DejaVu Sans,"
                "FontSize=17,Bold=1,"
                "PrimaryColour=&H00FFFFFF,"
                "OutlineColour=&H00000000,"
                "Outline=2,Shadow=1,"
                "Alignment=2,MarginV=28'"
            )

        temporary = folder / "final.mp4"

        run([
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", str(combined),
            "-i", str(audio),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-vf", filters,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-threads", "2",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-t", str(total),
            "-movflags", "+faststart",
            "-loglevel", "error",
            str(temporary)
        ])

        make_thumbnail(
            index,
            item,
            used_media,
            folder
        )

        save_credits(
            index,
            item,
            used_sources
        )

        temporary.replace(video)

    print("SUCCESS:", video, flush=True)
    return True


success = 0

for index, item in enumerate(topics, 1):
    for name in [
        f"video_{index}.mp4",
        f"thumbnail_{index}.jpg",
        f"credits_{index}.txt",
        f"sources_{index}.json",
        f"details_{index}.json"
    ]:
        (output / name).unlink(missing_ok=True)

    try:
        if make_video(index, item):
            success += 1

    except Exception as error:
        print(
            f"Video {index} failed: "
            f"{type(error).__name__}: {error}",
            flush=True
        )

print(
    f"TrendPulse AI V3.0: "
    f"{success}/{len(topics)} videos generated"
)

if success == 0:
    raise RuntimeError("No suitable videos generated")
