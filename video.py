import os
import json
import math
import requests
import subprocess
import tempfile
from pathlib import Path
from PIL import Image, ImageOps

API_KEY = os.getenv("PIXABAY_API_KEY")

if not API_KEY:
    raise RuntimeError("Missing PIXABAY_API_KEY")

output = Path("videos")
output.mkdir(exist_ok=True)

with open("scripts.json", encoding="utf-8") as f:
    data = json.load(f)

topics = data["selected_topics"]

def run(command):
    subprocess.run(command, check=True)

def search_images(query):
    response = requests.get(
        "https://pixabay.com/api/",
        params={
            "key": API_KEY,
            "q": query[:100],
            "image_type": "photo",
            "orientation": "horizontal",
            "safesearch": "true",
            "per_page": 20
        },
        timeout=30
    )
    if not response.ok:
        raise RuntimeError(
            f"Pixabay HTTP {response.status_code}"
        )
    return response.json().get("hits", [])

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

    duration = float(
        subprocess.check_output([
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio)
        ]).decode().strip()
    )

    print(f"Creating: {title}")

    query = str(
        item.get("topic") or title
    )

    images = search_images(query)

    if not images:
        images = search_images(
            " ".join(query.split()[:3])
        )

    if not images:
        images = search_images(
            " ".join(query.split()[:2])
        )

    if not images:
        raise RuntimeError(
            f"No relevant images found: {title}"
        )

    with tempfile.TemporaryDirectory() as folder:

        work = Path(folder)
        photos = []

        for n, image in enumerate(images[:15]):

            url = image.get("largeImageURL")

            if not url:
                continue

            try:
                response = requests.get(
                    url, timeout=30
                )
                response.raise_for_status()

                raw = work / f"raw_{n}.jpg"
                raw.write_bytes(response.content)

                photo = work / f"photo_{n}.jpg"

                with Image.open(raw) as img:
                    img = ImageOps.fit(
                        img.convert("RGB"),
                        (1280, 720)
                    )
                    img.save(photo, quality=92)

                photos.append(photo)

            except Exception as e:
                print(f"Image skipped: {type(e).__name__}")

        if not photos:
            raise RuntimeError("No images downloaded")

        count = math.ceil(duration / 8)
        clips = []

        for n in range(count):

            photo = photos[n % len(photos)]
            clip = work / f"clip_{n}.mp4"

            run([
                "ffmpeg", "-y",
                "-loglevel", "error",
                "-loop", "1",
                "-i", str(photo),
                "-vf",
                "scale=2560:1440,"
                "zoompan=z='min(zoom+0.0007,1.15)':"
                "x='iw/2-iw/zoom/2':"
                "y='ih/2-ih/zoom/2':"
                "d=1:s=1280x720:fps=25,"
                "drawtext=text='TRENDPULSE AI':"
                "fontsize=28:fontcolor=white:"
                "box=1:boxcolor=black@0.5:"
                "x=30:y=30",
                "-t", "8",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-an",
                str(clip)
            ])

            clips.append(clip)

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
