import subprocess
from pathlib import Path

output = Path("videos")
output.mkdir(exist_ok=True)

audio_files = sorted(Path(".").rglob("*.mp3"))

if not audio_files:
    raise SystemExit("No audio files found")

for audio in audio_files:
    video = output / (audio.stem + ".mp4")

    command = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", "color=c=0x101828:s=1920x1080:r=30",
        "-i", str(audio),
        "-vf",
        "drawtext=text='TrendPulse AI':"
        "fontsize=90:fontcolor=white:"
        "x=(w-tw)/2:y=(h-th)/2",
        "-c:v", "libx264",
        "-preset", "fast",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        "-movflags", "+faststart",
        str(video)
    ]

    subprocess.run(command, check=True)
    print(f"SUCCESS: {video}")

print("All videos generated successfully")
