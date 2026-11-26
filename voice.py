
import os
import sys
import json
import asyncio
import shutil
import subprocess
from pathlib import Path

try:
    import edge_tts
except ImportError:
    subprocess.check_call([
        sys.executable, "-m", "pip",
        "install", "edge-tts"
    ])
    import edge_tts

VERSION = "2.0"
VOICE = "en-US-GuyNeural"

AUDIO = Path("audio")
SUBTITLES = Path("subtitles")

AUDIO.mkdir(exist_ok=True)
SUBTITLES.mkdir(exist_ok=True)

MAX_RETRIES = 3

with open("scripts.json", encoding="utf-8") as f:
    data = json.load(f)

topics = data["selected_topics"]


def clean_text(text):
    if not isinstance(text, str):
        return ""

    return " ".join(text.split()).strip()


async def generate_voice(text, name, rate="+0%"):

    text = clean_text(text)

    if not text:
        raise ValueError(f"Empty script: {name}")

    audio_file = AUDIO / f"{name}.mp3"
    subtitle_file = SUBTITLES / f"{name}.srt"
    audio_subtitle = AUDIO / f"{name}.srt"

    temp_audio = AUDIO / f"{name}.tmp.mp3"

    for path in (
        audio_file,
        subtitle_file,
        audio_subtitle,
        temp_audio
    ):
        path.unlink(missing_ok=True)

    for attempt in range(1, MAX_RETRIES + 1):

        try:
            print(
                f"Generating {name} "
                f"- attempt {attempt}",
                flush=True
            )

            communicate = edge_tts.Communicate(
                text=text,
                voice=VOICE,
                rate=rate,
                boundary="SentenceBoundary"
            )

            submaker = edge_tts.SubMaker()

            with open(temp_audio, "wb") as audio:

                async for chunk in communicate.stream():

                    if chunk["type"] == "audio":
                        audio.write(chunk["data"])

                    elif chunk["type"] == "SentenceBoundary":
                        submaker.feed(chunk)

            if not temp_audio.exists():
                raise RuntimeError("Audio missing")

            if temp_audio.stat().st_size < 1024:
                raise RuntimeError("Audio incomplete")

            srt = submaker.get_srt()

            if not srt.strip():
                raise RuntimeError("Subtitles missing")

            subtitle_file.write_text(
                srt,
                encoding="utf-8"
            )

            shutil.copyfile(
                subtitle_file,
                audio_subtitle
            )

            temp_audio.replace(audio_file)

            print(f"SUCCESS: {audio_file}", flush=True)
            print(f"SUCCESS: {subtitle_file}", flush=True)

            return True

        except Exception as error:

            print(
                f"ERROR {name}: {error}",
                flush=True
            )

            for path in (
                temp_audio,
                audio_file,
                subtitle_file,
                audio_subtitle
            ):
                path.unlink(missing_ok=True)

            if attempt < MAX_RETRIES:
                await asyncio.sleep(attempt * 5)

    return False


async def main():

    print(
        f"TrendPulse Global Voice V{VERSION}",
        flush=True
    )

    if not topics:
        raise RuntimeError("No topics available")

    long_success = 0
    short_success = 0
    failures = []

    for i, item in enumerate(topics, 1):

        print(
            f"Processing topic {i}: "
            f"{item.get('title', 'Untitled')}",
            flush=True
        )

        long_script = clean_text(
            item.get("script", "")
        )

        short_script = clean_text(
            item.get("short_script", "")
        )

        if long_script:

            success = await generate_voice(
                long_script,
                f"video_{i}",
                rate="+0%"
            )

            if success:
                long_success += 1
            else:
                failures.append(f"video_{i}")

        else:
            failures.append(f"video_{i}")

        if short_script:

            success = await generate_voice(
                short_script,
                f"short_{i}",
                rate="+5%"
            )

            if success:
                short_success += 1
            else:
                failures.append(f"short_{i}")

        else:

            print(
                f"WARNING: No short script for topic {i}",
                flush=True
            )

            failures.append(f"short_{i}")

    print("=" * 50)

    print(f"Long audio generated: {long_success}")
    print(f"Short audio generated: {short_success}")

    print("=" * 50)

    if failures:
        raise RuntimeError(
            "Audio generation failed: "
            + ", ".join(failures)
        )

    print("ALL AUDIO GENERATED SUCCESSFULLY")


if __name__ == "__main__":
    asyncio.run(main())
