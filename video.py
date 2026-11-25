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
    topics = json.load(f)["selected_topics"]

def run(command):
    subprocess.run(command, check=True)

def duration(path):
    return float(subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]).decode().strip())

def search_videos(query):
    response = requests.get(
        "https://pixabay.com/api/videos/",
        params={
            "key": API_KEY,
            "q": query[:100],
            "video_type": "film",
            "safesearch": "true",
            "per_page": 15
        },
        timeout=30
    )

    if not response.ok:
        raise RuntimeError(
            f"Pixabay HTTP {response.status_code}"
        )

    return response.json().get("hits", [])

stopwords = set("""
the a an and or to of in on for with from
is are was were how why what this that
today now full story trending viral
""".split())

for i, item in enumerate(topics, 1):

    title = str(
        item.get("title")
        or item.get("topic")
        or "Trending Today"
    )

    audio = Path(f"audio/video_{i}.mp3")
    video = output / f"video_{i}.mp4"

    if not audio.exists():
        raise FileNotFoundError(audio)

    length = duration(audio)

    print(f"Creating video {i}: {title}")

    topic = str(item.get("topic") or title)

    words = [
        w for w in re.findall(r"[A-Za-z]+", topic)
        if w.lower() not in stopwords
        and len(w) > 2
    ]

    queries = [
        topic,
        " ".join(words[:3]),
        " ".join(words[:2])
    ]

    queries += words[:6]

    hits = {}

    for query in dict.fromkeys(queries):

        if not query.strip():
            continue

        print(f"Searching: {query}")

        for hit in search_videos(query):
            hits[hit["id"]] = hit

        if len(hits) >= 20:
            break

    if not hits:
        raise RuntimeError(
            f"No stock videos found: {title}"
        )

    with tempfile.TemporaryDirectory() as folder:

        work = Path(folder)
        sources = []

        title_file = work / "title.txt"

        title_file.write_text(
            textwrap.fill(title, width=38),
            encoding="utf-8"
        )

        for n, hit in enumerate(list(hits.values())[:20]):

            variants = hit.get("videos", {})

            info = (
                variants.get("medium")
                or variants.get("small")
                or variants.get("large")
                or {}
            )

            url = info.get("url")

            if not url:
                continue

            source = work / f"source_{n}.mp4"

            try:
                with requests.get(
                    url,
                    stream=True,
                    timeout=60
                ) as response:

                    response.raise_for_status()

                    with open(source, "wb") as f:
                        for chunk in response.iter_content(
                            chunk_size=1048576
                        ):
                            f.write(chunk)

                seconds = duration(source)

                if seconds >= 3:
                    sources.append((source, seconds))

            except Exception as e:
                print(
                    f"Clip skipped: {type(e).__name__}"
                )

        if not sources:
            raise RuntimeError(
                "No usable videos downloaded"
            )

        clips = []
        count = math.ceil(length / 6)

        for n in range(count):

            source, seconds = sources[
                n % len(sources)
            ]

            clip = work / f"clip_{n}.mp4"

            start = min(
                (n // len(sources)) * 6,
                max(0, seconds - 6)
            )

            filters = (
                "scale=1920:1080:"
                "force_original_aspect_ratio=increase,"
                "crop=1920:1080,"
                "setsar=1,fps=25,"
                "drawtext=text='TRENDPULSE AI':"
                "fontsize=38:fontcolor=white:"
                "box=1:boxcolor=black@0.6:"
                "boxborderw=15:x=40:y=40"
            )

            if n == 0:
                filters += (
                    ",drawbox=x=0:y=0:"
                    "w=iw:h=ih:color=black@0.45:t=fill,"
                    f"drawtext=textfile={title_file}:"
                    "expansion=none:"
                    "fontsize=58:fontcolor=white:"
                    "x=(w-tw)/2:y=(h-th)/2"
                )

            run([
                "ffmpeg", "-y",
                "-loglevel", "error",
                "-stream_loop", "-1",
                "-ss", str(start),
                "-i", str(source),
                "-vf", filters,
                "-t", "6",
                "-an",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                str(clip)
            ])

            clips.append(clip)

            print(f"Scene {n+1}/{count}")

        concat = work / "concat.txt"

        concat.write_text(
            "\n".join(
                f"file '{p.resolve()}'"
                for p in clips
            ),
            encoding="utf-8"
        )

        run([
            "ffmpeg", "-y",
            "-loglevel", "error",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat),
            "-i", str(audio),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            str(video)
        ])

    print(f"SUCCESS: {video}")

print("All videos generated successfully")
