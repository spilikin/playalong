import json
import re
import subprocess
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from playalong.separate import SAMPLE_RATE

# Resample once on the way in so every later stage can assume the separation model's format.
FFMPEG_ARGS = ["-ar", str(SAMPLE_RATE), "-ac", "2"]


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    return re.sub(r"[-\s]+", "-", text)[:80] or "track"


class _Silent:
    """yt-dlp prints its errors as well as raising them; fetch reports them itself, more briefly."""

    def debug(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...


def fetch(url: str, library: Path, browser: str | None = None) -> Path:
    """Download the audio of a YouTube URL into its own track directory as source.wav.

    `browser` lends yt-dlp that browser's YouTube login, which age-restricted videos need.
    """
    login = {"cookiesfrombrowser": (browser,)} if browser else {}
    try:
        with YoutubeDL({"quiet": True, "noplaylist": True, "logger": _Silent(), **login}) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        message = str(e).removeprefix("ERROR: ")
        if not browser and ("confirm your age" in message or "Sign in" in message):
            raise SystemExit(f"{message.split('. Use --cookies')[0]}.\nYouTube wants a signed-in account for this "
                             "video: log in to YouTube in your browser, then add --cookies-from-browser chrome "
                             "(or safari, firefox, brave, edge).") from e
        raise SystemExit(message) from e

    track_dir = library / slugify(info.get("title") or info["id"])
    source = track_dir / "source.wav"
    if source.exists():
        print(f"Already downloaded: {source}")
        return track_dir
    track_dir.mkdir(parents=True, exist_ok=True)

    opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "outtmpl": str(track_dir / "source.%(ext)s"),
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}],
        "postprocessor_args": {"extractaudio": FFMPEG_ARGS},
        **login,
    }
    with YoutubeDL(opts) as ydl:
        ydl.download([url])

    # artist/track/album are only there for uploads YouTube knows as music; the cover search uses them.
    meta = {k: info.get(k) for k in ("id", "title", "uploader", "artist", "track", "album", "duration", "webpage_url")}
    (track_dir / "info.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return track_dir


def import_file(path: Path, library: Path) -> Path:
    """Bring a local audio file into the library, converting it to source.wav."""
    track_dir = library / slugify(path.stem)
    source = track_dir / "source.wav"
    if source.exists():
        print(f"Already imported: {source}")
        return track_dir
    track_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), *FFMPEG_ARGS, str(source)],
        check=True,
    )
    (track_dir / "info.json").write_text(json.dumps({"title": path.stem, "file": str(path)}, indent=2))
    return track_dir
