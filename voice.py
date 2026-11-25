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
os.makedirs("subtitles", exist_ok=True)

with open("scripts.json", "r", encoding="utf-8") as f:
    data = json.load(f)

topics = data["selected_topics"]

async def main():
    for i, item in enumerate(topics, 1):
        text = item["script"]

        if not isinstance(text, str) or not text.strip():
            raise ValueError("Invalid video script")

        audio_file = f"audio/video_{i}.mp3"
        subtitle_file = f"subtitles/video_{i}.srt"

        print(f"Generating voice and subtitles {i}...")

        communicate = edge_tts.Communicate(
            text=text,
            voice=VOICE,
            rate="+0%",
            boundary="SentenceBoundary"
        )

        submaker = edge_tts.SubMaker()

        with open(audio_file, "wb") as audio:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio.write(chunk["data"])
                elif chunk["type"] == "SentenceBoundary":
                    submaker.feed(chunk)

        with open(subtitle_file, "w", encoding="utf-8") as f:
            f.write(submaker.get_srt())

        print(f"SUCCESS: {audio_file}")
        print(f"SUCCESS: {subtitle_file}")

    print("All audio and subtitles generated successfully")

asyncio.run(main())
