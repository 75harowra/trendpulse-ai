import os
import sys
import json
import asyncio
import subprocess

try:
    import edge_tts
except ImportError:
    subprocess.check_call([
        sys.executable, "-m", "pip",
        "install", "edge-tts"
    ])
    import edge_tts

VOICE = "en-US-GuyNeural"

os.makedirs("audio", exist_ok=True)

with open("scripts.json", "r", encoding="utf-8") as f:
    data = json.load(f)

topics = data["selected_topics"]

async def main():
    for i, item in enumerate(topics, 1):
        text = item["script"]

        if not isinstance(text, str) or not text.strip():
            raise ValueError("Invalid video script")

        filename = f"audio/video_{i}.mp3"

        print(f"Generating voice {i}...")

        communicate = edge_tts.Communicate(
            text=text,
            voice=VOICE,
            rate="+0%"
        )

        await communicate.save(filename)

        print(f"SUCCESS: {filename}")

    print("All audio files generated successfully")

asyncio.run(main())
