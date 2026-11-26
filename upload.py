import os
import json
import re
import hashlib
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

VERSION = "1.0"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

credentials = Credentials(
    token=None,
    refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
    token_uri="https://oauth2.googleapis.com/token",
    client_id=os.environ["YOUTUBE_CLIENT_ID"],
    client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
    scopes=SCOPES
)

youtube = build(
    "youtube",
    "v3",
    credentials=credentials,
    cache_discovery=False
)

folder = Path("videos")
privacy = "private"

channel = youtube.channels().list(
    part="snippet",
    mine=True
).execute()

channels = channel.get("items", [])

if not channels:
    raise RuntimeError("YouTube channel not found")

expected = os.environ["YOUTUBE_CHANNEL_ID"]

if channels[0]["id"] != expected:
    raise RuntimeError("Wrong YouTube channel")

print("Connected:", channels[0]["snippet"]["title"])

history_file = Path("upload_history.json")

if history_file.exists():
    history = json.loads(
        history_file.read_text(encoding="utf-8")
    )
else:
    history = {}


def save_history():
    temp = history_file.with_suffix(".tmp")
    temp.write_text(
        json.dumps(history, indent=2),
        encoding="utf-8"
    )
    temp.replace(history_file)


def upload_video(path, item, index, short=False):

    digest = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()

    if digest in history:
        print("Already uploaded:", path.name)
        return

    if short:
        title = item.get("short_title") or item["title"]
        description = item.get("short_description", "")
    else:
        title = item["title"]
        description = item.get("description", "")

    title = re.sub(r"[<>]", "", str(title)).strip()

    if short:
        title = title[:92] + " #Shorts"

    title = title[:100]

    hashtags = item.get("hashtags", [])

    if isinstance(hashtags, list):
        hashtags = " ".join(map(str, hashtags))

    sources = item.get("sources", [])

    if not isinstance(sources, list):
        sources = []

    links = []

    for source in sources:
        if isinstance(source, str):
            links.append(source)
        elif isinstance(source, dict):
            url = source.get("url") or source.get("link")
            if url:
                links.append(str(url))

    description = (
        str(description)
        + "\n\nSubscribe to TrendPulse Global."
        + "\n\n" + str(hashtags)
        + "\n\nSources:\n"
        + "\n".join(links)
    )

    credits = folder / f"credits_{index}.txt"

    if credits.exists():
        description += (
            "\n\nMedia credits:\n"
            + credits.read_text(encoding="utf-8")
        )

    description = re.sub(r"[<>]", "", description)

    if len(description.encode("utf-8")) > 5000:
        raise RuntimeError("Description exceeds limit")

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "28",
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en"
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True
        }
    }

    media = MediaFileUpload(
        str(path),
        mimetype="video/mp4",
        chunksize=8 * 1024 * 1024,
        resumable=True
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None

    while response is None:
        status, response = request.next_chunk(
            num_retries=3
        )

        if status:
            print(
                "Uploading:",
                int(status.progress() * 100),
                "%"
            )

    video_id = response["id"]

    history[digest] = {
        "video_id": video_id,
        "title": title,
        "privacy": privacy
    }

    save_history()

    print("UPLOAD SUCCESS:", video_id)

    thumbnail = folder / f"thumbnail_{index}.jpg"

    if not short and thumbnail.exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(
                    str(thumbnail),
                    mimetype="image/jpeg"
                )
            ).execute()

            print("Thumbnail uploaded")

        except Exception as error:
            print("Thumbnail failed:", error)


def main():

    print("TrendPulse Auto Uploader V" + VERSION)

    details = sorted(folder.glob("details_*.json"))

    if not details:
        raise RuntimeError("No video details found")

    for file in details:

        index = file.stem.split("_")[-1]

        item = json.loads(
            file.read_text(encoding="utf-8")
        )

        video = folder / f"video_{index}.mp4"
        short = folder / f"short_{index}.mp4"

        if video.exists():
            upload_video(video, item, index)

        if short.exists():
            upload_video(
                short,
                item,
                index,
                short=True
            )

    print("ALL UPLOADS COMPLETED")


if __name__ == "__main__":
    main()
