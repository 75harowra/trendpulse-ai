import subprocess
import json
import textwrap
from pathlib import Path

output = Path("videos")
output.mkdir(exist_ok=True)

with open("scripts.json", encoding="utf-8") as f:
    data = json.load(f)

topics = data["selected_topics"]

colors = [
    "0x101B35",
    "0x173B46",
    "0x302044",
    "0x16324F"
]

for i, item in enumerate(topics, 1):
    audio = Path(f"audio/video_{i}.mp3")
    video = output / f"video_{i}.mp4"

    if not audio.exists():
        raise FileNotFoundError(audio)

    title = str(
        item.get("title")
        or item.get("topic")
        or "Trending Today"
    )

    title_file = output / f"title_{i}.txt"
    title_file.write_text(
        textwrap.fill(title, width=32),
        encoding="utf-8"
    )

    color = colors[(i - 1) % len(colors)]

    filters = (
        "drawbox=x=0:y=0:w=iw:h=12:"
        "color=cyan:t=fill,"
        "drawtext=text='TRENDPULSE AI':"
        "fontsize=42:fontcolor=cyan:"
        "x=(w-tw)/2:y=80,"
        f"drawtext=textfile={title_file}:"
        "expansion=none:"
        "fontsize=54:fontcolor=white:"
        "x=(w-tw)/2:y=(h-th)/2,"
        "drawtext=text='TRENDING NOW':"
        "fontsize=30:fontcolor=white:"
        "x=(w-tw)/2:y=h-100"
    )

    command = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"color=c={color}:s=1280x720:r=25",
        "-i", str(audio),
        "-vf", filters,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        "-movflags", "+faststart",
        str(video)
    ]

    subprocess.run(command, check=True)
    title_file.unlink()

    print(f"SUCCESS: {video}")

print("All videos generated successfully")
