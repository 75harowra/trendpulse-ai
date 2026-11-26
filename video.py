import os
import json
import math
import re
import requests
import subprocess
import tempfile
import textwrap
from pathlib import Path

API_KEY = os.getenv("PIXABAY_API_KEY")

if not API_KEY:
    raise RuntimeError("Missing PIXABAY_API_KEY")

WIDTH = 1920
HEIGHT = 1080
FPS = 25
SCENE_TIME = 5
MAX_MEDIA = 30

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

output = Path("videos")
output.mkdir(exist_ok=True)

with open("scripts.json", encoding="utf-8") as f:
    topics = json.load(f)["selected_topics"]

session = requests.Session()
cache = {}


def run(cmd):
    subprocess.run(cmd, check=True)


def duration(path):
    result = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path)
    ])
    return float(result.strip())


def keywords(item):
    title = str(item.get("title", ""))
    topic = str(item.get("topic", ""))
    content = (title + " " + topic).lower()

    categories = [
        (
            ["nba", "basketball", "wembanyama"],
            ["basketball court", "basketball player",
             "basketball arena", "basketball hoop"]
        ),
        (
            ["nfl", "garrett", "american football"],
            ["american football", "football helmet",
             "american football stadium"]
        ),
        (
            ["soccer", "football", "fifa"],
            ["soccer stadium", "soccer player",
             "soccer ball"]
        ),
        (
            ["robot", "artificial intelligence", "chatgpt"],
            ["artificial intelligence", "robot technology",
             "computer processor"]
        ),
        (
            ["electric car", "tesla", "electric vehicle"],
            ["electric car", "car charging",
             "automotive technology"]
        ),
        (
            ["finance", "stock", "economy", "interest rate"],
            ["stock market", "financial chart",
             "business meeting"]
        ),
        (
            ["space", "nasa", "planet"],
            ["space exploration", "rocket",
             "planet earth"]
        ),
        (
            ["celebrity", "marketing", "viral"],
            ["social media", "content creator",
             "digital marketing"]
        )
    ]

    for triggers, queries in categories:
        if any(word in content for word in triggers):
            return queries

    queries = item.get("visual_keywords", [])

    if not isinstance(queries, list):
        queries = []

    queries = [
        q.strip()[:100]
        for q in queries
        if isinstance(q, str) and q.strip()
    ]

    return list(dict.fromkeys(queries))[:5]


def search(query, media):
    key = (query, media)

    if key in cache:
        return cache[key]

    endpoint = "https://pixabay.com/api/"

    if media == "video":
        endpoint += "videos/"

    params = {
        "key": API_KEY,
        "q": query,
        "per_page": 30,
        "safesearch": "true",
        "order": "popular"
    }

    if media == "image":
        params["image_type"] = "photo"
        params["orientation"] = "horizontal"

    try:
        response = session.get(
            endpoint,
            params=params,
            timeout=30
        )

        if response.status_code != 200:
            return []

        hits = response.json().get("hits", [])
        cache[key] = hits
        return hits

    except (requests.RequestException, ValueError):
        return []


def download(url, path):
    with session.get(
        url, stream=True, timeout=60
    ) as response:

        response.raise_for_status()
        size = 0

        with open(path, "wb") as f:
            for chunk in response.iter_content(65536):
                if chunk:
                    size += len(chunk)

                    if size > 40 * 1024 * 1024:
                        raise ValueError("Media too large")

                    f.write(chunk)


def relevant(hit, query):
    tags = str(hit.get("tags", "")).lower()

    words = re.findall(
        r"[a-z0-9]+", query.lower()
    )

    ignored = {
        "the", "and", "with", "for",
        "news", "global", "today"
    }

    words = [
        w for w in words
        if len(w) > 2 and w not in ignored
    ]

    if not words:
        return False

    return all(
        re.search(r"\b" + re.escape(w) + r"s?\b", tags)
        for w in words
    )


def get_media(item, folder, limit):
    files = []
    sources = []
    seen = set()

    queries = keywords(item)

    print("Visual keywords:", queries, flush=True)

    pools = []

    for query in queries:
        for media in ["video", "image"]:
            hits = [
                hit for hit in search(query, media)
                if relevant(hit, query)
            ]

            pools.append((query, media, iter(hits)))

    while len(files) < limit and pools:
        active = []

        for query, media, hits in pools:
            if len(files) >= limit:
                break

            for hit in hits:
                identity = (media, hit.get("id"))

                if identity in seen:
                    continue

                seen.add(identity)

                if media == "video":
                    versions = hit.get("videos", {})

                    url = (
                        versions.get("medium", {}).get("url")
                        or versions.get("small", {}).get("url")
                    )

                    ext = ".mp4"

                else:
                    url = hit.get("largeImageURL")
                    ext = ".jpg"

                if not url:
                    continue

                path = folder / f"media_{len(files)}{ext}"

                try:
                    download(url, path)

                    files.append(path)

                    sources.append({
                        "url": hit.get("pageURL"),
                        "author": hit.get("user"),
                        "query": query,
                        "type": media
                    })

                    active.append((query, media, hits))
                    break

                except Exception:
                    path.unlink(missing_ok=True)

        pools = active

    return files, sources


def make_scene(source, target, seconds):
    base = (
        f"scale={WIDTH}:{HEIGHT}:"
        "force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},setsar=1"
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
        "-preset", "ultrafast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-loglevel", "error",
        str(target)
    ]

    run(command)


def fallback_scene(target, seconds):
    run([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i",
        f"color=c=0x101B35:s={WIDTH}x{HEIGHT}:r={FPS}",
        "-t", str(seconds),
        "-an",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-threads", "2",
        "-pix_fmt", "yuv420p",
        "-loglevel", "error",
        str(target)
    ])


def find_subtitles(index):
    candidates = [
        Path(f"audio/video_{index}.srt"),
        Path(f"subtitles/video_{index}.srt"),
        Path(f"captions/video_{index}.srt")
    ]

    for path in candidates:
        if path.exists() and path.stat().st_size > 0:
            return path.resolve()

    return None


def make_thumbnail(index, item, combined, folder):
    words = str(
        item.get("thumbnail_text")
        or item.get("topic")
        or "TRENDING NOW"
    ).split()[:4]

    headline = textwrap.fill(
        " ".join(words).upper(),
        width=20
    )

    text_file = folder / "thumbnail.txt"
    text_file.write_text(headline, encoding="utf-8")

    filters = (
        "scale=1280:720,"
        "drawbox=x=0:y=0:w=iw:h=ih:"
        "color=black@0.45:t=fill,"
        f"drawtext=fontfile={FONT}:"
        "text='TRENDPULSE GLOBAL':"
        "fontsize=32:fontcolor=white:"
        "x=35:y=35,"
        f"drawtext=fontfile={FONT}:"
        f"textfile={text_file}:"
        "expansion=none:"
        "fontsize=76:fontcolor=yellow:"
        "borderw=4:bordercolor=black:"
        "x=(w-tw)/2:y=(h-th)/2"
    )

    run([
        "ffmpeg", "-y",
        "-i", str(combined),
        "-vf", filters,
        "-frames:v", "1",
        "-q:v", "3",
        "-loglevel", "error",
        str(output / f"thumbnail_{index}.jpg")
    ])


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
        raise RuntimeError("Invalid audio duration")

    count = math.ceil(total / SCENE_TIME)

    print("Creating:", title, flush=True)

    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)

        media, sources = get_media(
            item,
            folder,
            min(count, MAX_MEDIA)
        )

        if not media:
            print("WARNING: No relevant footage found")

        scenes = []

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
                source = media[
                    (n + offset) % len(media)
                ]

                try:
                    make_scene(source, scene, seconds)
                    created = True
                    break

                except subprocess.CalledProcessError:
                    scene.unlink(missing_ok=True)

            if not created:
                fallback_scene(scene, seconds)

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
            "fontsize=32:fontcolor=white:"
            "box=1:boxcolor=black@0.7:"
            "boxborderw=10:x=40:y=40,"
            f"drawtext=fontfile={FONT}:"
            f"textfile={title_file}:"
            "expansion=none:"
            "fontsize=52:fontcolor=white:"
            "box=1:boxcolor=black@0.75:"
            "boxborderw=18:"
            "x=(w-tw)/2:y=(h-th)/2:"
            "enable='lt(t,3)',"
            f"drawtext=fontfile={FONT}:"
            "text='Illustrative footage':"
            "fontsize=22:fontcolor=white:"
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

        temporary.replace(video)

        try:
            make_thumbnail(
                index, item, combined, folder
            )
        except subprocess.CalledProcessError:
            print("WARNING: Thumbnail generation failed")

        (output / f"sources_{index}.json").write_text(
            json.dumps(sources, indent=2),
            encoding="utf-8"
        )

        (output / f"details_{index}.json").write_text(
            json.dumps(
                item,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

    print("SUCCESS:", video, flush=True)
    return True


success = 0

for index, item in enumerate(topics, 1):
    try:
        if make_video(index, item):
            success += 1

    except Exception as error:
        print(
            f"Video {index} failed: "
            f"{type(error).__name__}: {error}",
            flush=True
        )

print(f"Finished: {success}/{len(topics)} videos")

if success == 0:
    raise RuntimeError("No videos generated")
