
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
SCENE_TIME = 6
MAX_MEDIA = 35

output = Path("videos")
output.mkdir(exist_ok=True)

with open("scripts.json", encoding="utf-8") as f:
    topics = json.load(f)["selected_topics"]

session = requests.Session()
cache = {}

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


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


def keywords(title, item):
    queries = []
    topic = str(item.get("topic") or "")
    script = str(item.get("script") or "")
    content = (title + " " + topic + " " + script).lower()

    categories = {
        "basketball": [
            "nba", "76ers", "basketball"
        ],
        "football": [
            "soccer", "football", "fifa"
        ],
        "robot technology": [
            "robot", "robotics"
        ],
        "artificial intelligence": [
            "artificial intelligence", "chatgpt"
        ],
        "social media smartphone": [
            "social media", "influencer", "tiktok"
        ],
        "stock market": [
            "stock market", "finance", "economy"
        ],
        "space exploration": [
            "nasa", "planet", "space"
        ],
        "storm weather": [
            "storm", "hurricane", "weather"
        ],
        "electric car": [
            "electric vehicle", "electric car", "tesla"
        ],
        "computer technology": [
            "computer", "software", "technology"
        ]
    }

    if topic:
        queries.append(topic[:100])

    queries.append(title.split(":")[0][:100])

    for category, triggers in categories.items():
        if any(word in content for word in triggers):
            queries.append(category)

    clean = re.sub(r"[^a-zA-Z0-9 ]", " ", title)
    queries.append(" ".join(clean.split()[:4]))

    return list(dict.fromkeys(
        q.strip() for q in queries if q.strip()
    ))


def search(query, media):
    key = (query, media)

    if key in cache:
        return cache[key]

    endpoint = "https://pixabay.com/api/"

    if media == "video":
        endpoint += "videos/"

    params = {
        "key": API_KEY,
        "q": query[:100],
        "per_page": 30,
        "safesearch": "true"
    }

    if media == "image":
        params["image_type"] = "photo"
        params["orientation"] = "horizontal"

    print("Searching:", query, media, flush=True)

    try:
        response = session.get(
            endpoint, params=params, timeout=30
        )

        if response.status_code != 200:
            print("Pixabay HTTP:", response.status_code)
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


def get_media(title, item, folder, limit):
    queries = keywords(title, item)
    files = []
    sources = []
    seen = set()

    for media in ["video", "image"]:
        for query in queries:
            hits = search(query, media)

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

                    print(
                        "Downloaded media:", len(files),
                        flush=True
                    )

                except Exception:
                    path.unlink(missing_ok=True)
                    continue

                if len(files) >= limit:
                    return files, sources

    return files, sources


def make_scene(source, target, seconds):
    base = (
        f"scale={WIDTH}:{HEIGHT}:"
        "force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},setsar=1"
    )

    if source.suffix.lower() == ".jpg":
        frames = max(1, math.ceil(seconds * FPS))

        command = [
            "ffmpeg", "-y",
            "-i", str(source),
            "-vf",
            base + ","
            "zoompan=z='min(zoom+0.0005,1.10)':"
            "x='iw/2-iw/zoom/2':"
            "y='ih/2-ih/zoom/2':"
            f"d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS}"
        ]

    else:
        command = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", str(source),
            "-vf", base
        ]

    command += [
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
            title,
            item,
            folder,
            min(count, MAX_MEDIA)
        )

        scenes = []

        for n in range(count):
            seconds = min(
                SCENE_TIME,
                total - n * SCENE_TIME
            )

            if seconds <= 0:
                break

            scene = folder / f"scene_{n}.mp4"

            print(
                f"Scene {n + 1}/{count}",
                flush=True
            )

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
            textwrap.fill(title, width=38),
            encoding="utf-8"
        )

        filters = (
            "drawbox=x=0:y=0:w=iw:h=10:"
            "color=cyan:t=fill,"
            f"drawtext=fontfile={FONT}:"
            "text='TRENDPULSE AI':"
            "fontsize=38:fontcolor=white:"
            "box=1:boxcolor=black@0.7:"
            "boxborderw=12:x=40:y=40,"
            f"drawtext=fontfile={FONT}:"
            f"textfile={title_file}:"
            "expansion=none:"
            "fontsize=48:fontcolor=white:"
            "box=1:boxcolor=black@0.75:"
            "boxborderw=18:"
            "x=(w-tw)/2:y=(h-th)/2:"
            "enable='lt(t,6)',"
            "drawtext=text='Illustrative footage':"
            "fontsize=24:fontcolor=white:"
            "box=1:boxcolor=black@0.6:"
            "x=30:y=h-40"
        )

        subtitles = find_subtitles(index)

        if subtitles:
            filters += (
                f",subtitles={subtitles.as_posix()}:"
                "force_style='FontName=DejaVu Sans,"
                "FontSize=22,Bold=1,"
                "PrimaryColour=&H00FFFFFF,"
                "OutlineColour=&H00000000,"
                "Outline=2,Shadow=1,"
                "Alignment=2,MarginV=25'"
            )

            print("Subtitles added", flush=True)

        else:
            print(
                "No SRT subtitles found",
                flush=True
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

        (output / f"sources_{index}.json").write_text(
            json.dumps(sources, indent=2),
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
