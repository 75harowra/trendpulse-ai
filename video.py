
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

output = Path("videos")
output.mkdir(exist_ok=True)

with open("scripts.json", encoding="utf-8") as f:
    data = json.load(f)

topics = data["selected_topics"]

session = requests.Session()
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


def keywords(title, item):
    words = []

    topic = item.get("topic")
    if isinstance(topic, str):
        words.append(topic)

    words.append(title.split(":")[0])

    low = title.lower()

    categories = {
        "basketball": ["nba", "76ers", "basketball", "heat"],
        "football": ["soccer", "football", "goal", "fifa"],
        "social media smartphone": [
            "social media", "viral", "influencer",
            "celebrity", "tiktok"
        ],
        "technology": ["robot", "ai ", "technology"],
        "finance": ["money", "stock", "economy"],
        "space": ["space", "nasa", "planet"],
        "weather": ["storm", "weather", "rain"]
    }

    for category, triggers in categories.items():
        if any(x in low for x in triggers):
            words.append(category)

    clean = re.sub(r"[^a-zA-Z0-9 ]", " ", title)
    words.append(" ".join(clean.split()[:3]))

    return list(dict.fromkeys(
        x.strip()[:100] for x in words if x.strip()
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
        "q": query,
        "per_page": 10,
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
        print("Search unavailable")
        return []


def download(url, path):
    with session.get(
        url, timeout=60, stream=True
    ) as response:
        response.raise_for_status()

        with open(path, "wb") as f:
            for chunk in response.iter_content(65536):
                if chunk:
                    f.write(chunk)


def get_media(title, item, folder):
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
                        "query": query
                    })

                except Exception:
                    print("Media download skipped")
                    path.unlink(missing_ok=True)

                if len(files) >= 6:
                    return files, sources

            if len(files) >= 3:
                return files, sources

    return files, sources


def make_scene(source, target, seconds):
    base_filter = (
        "scale=1280:720:"
        "force_original_aspect_ratio=increase,"
        "crop=1280:720,setsar=1"
    )

    if source.suffix.lower() == ".jpg":
        frames = max(1, math.ceil(seconds * 25))

        command = [
            "ffmpeg", "-y",
            "-i", str(source),
            "-vf",
            base_filter + ","
            "zoompan=z='min(zoom+0.0007,1.12)':"
            "x='iw/2-iw/zoom/2':"
            "y='ih/2-ih/zoom/2':"
            f"d={frames}:s=1280x720:fps=25"
        ]
    else:
        command = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", str(source),
            "-vf", base_filter
        ]

    command += [
        "-t", f"{seconds:.3f}",
        "-an",
        "-r", "25",
        "-c:v", "libx264",
        "-threads", "2",
        "-preset", "veryfast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-loglevel", "error",
        str(target)
    ]

    run(command)


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

    print("Creating:", title, flush=True)

    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)

        media, sources = get_media(
            title, item, folder
        )

        if not media:
            print("No media found. Skipping topic.")
            return False

        scenes = []
        count = math.ceil(total / 7)

        for n in range(count):
            seconds = min(7, total - n * 7)

            if seconds <= 0:
                break

            scene = folder / f"scene_{n}.mp4"

            print(
                f"Scene {n + 1}/{count}",
                flush=True
            )

            for offset in range(len(media)):
                source = media[
                    (n + offset) % len(media)
                ]

                try:
                    make_scene(source, scene, seconds)
                    scenes.append(scene)
                    break

                except subprocess.CalledProcessError:
                    scene.unlink(missing_ok=True)

            else:
                raise RuntimeError("No usable media")

        concat = folder / "concat.txt"

        concat.write_text(
            "\n".join(
                f"file '{p.as_posix()}'"
                for p in scenes
            ),
            encoding="utf-8"
        )

        title_file = folder / "title.txt"

        title_file.write_text(
            textwrap.fill(title, width=46),
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

        filters = (
            "drawbox=x=0:y=0:w=iw:h=10:"
            "color=cyan:t=fill,"
            "drawtext=text='TRENDPULSE AI':"
            "fontsize=30:fontcolor=white:"
            "box=1:boxcolor=black@0.6:"
            "x=25:y=25,"
            f"drawtext=textfile={title_file}:"
            "expansion=none:"
            "fontsize=32:fontcolor=white:"
            "box=1:boxcolor=black@0.7:"
            "boxborderw=12:"
            "x=(w-tw)/2:y=h-th-50:"
            "enable='lt(t,8)',"
            "drawtext=text='Illustrative footage':"
            "fontsize=19:fontcolor=white:"
            "box=1:boxcolor=black@0.6:"
            "x=25:y=h-35"
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
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
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
            f"Video {index} skipped: "
            f"{type(error).__name__}",
            flush=True
        )
        continue

print(f"Finished: {success}/{len(topics)} videos")

if success == 0:
    raise RuntimeError("No videos generated")
