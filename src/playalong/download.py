import json
import plistlib
import re
import subprocess
import sys
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


# Bundle ids of the browsers yt-dlp can read logins from, as macOS names them for the default browser.
BROWSERS = {
    "com.apple.safari": "safari",
    "com.google.chrome": "chrome",
    "org.mozilla.firefox": "firefox",
    "com.brave.browser": "brave",
    "com.microsoft.edgemac": "edge",
    "com.vivaldi.vivaldi": "vivaldi",
    "com.operasoftware.opera": "opera",
    "org.chromium.chromium": "chromium",
}
LAUNCH_SERVICES = Path.home() / "Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def default_browser(plist: Path = LAUNCH_SERVICES) -> str | None:
    """The browser that opens web links (Safari unless another was chosen), if yt-dlp can use it."""
    try:
        handlers = plistlib.loads(plist.read_bytes()).get("LSHandlers", [])
    except (OSError, plistlib.InvalidFileException):
        handlers = []
    for handler in handlers:
        if handler.get("LSHandlerURLScheme") == "https":
            return BROWSERS.get(str(handler.get("LSHandlerRoleAll", "")).lower())
    return "safari" if sys.platform == "darwin" else None


def _brief(error: Exception) -> str:
    """yt-dlp's message without its colours, "ERROR:" and the cookie FAQ links."""
    message = ANSI.sub("", str(error)).removeprefix("ERROR: ").strip()
    return message.split(". Use --cookies")[0].rstrip(".") + "."


def _needs_login(message: str) -> bool:
    return "confirm your age" in message or "Sign in" in message


def _login_help(browser: str) -> str:
    if browser == "safari":
        return ("Couldn't read your Safari login: macOS keeps it private unless your terminal app has Full Disk "
                "Access (System Settings > Privacy & Security > Full Disk Access). Allow it, restart the terminal "
                "and run this again, or sign in to YouTube in another browser and add --cookies-from-browser chrome.")
    return (f"Make sure you're signed in to YouTube in {browser.title()}, or name another browser with "
            "--cookies-from-browser (safari, chrome, firefox, brave, edge).")


def _info(url: str, browser: str | None) -> dict:
    login = {"cookiesfrombrowser": (browser,)} if browser else {}
    with YoutubeDL({"quiet": True, "noplaylist": True, "logger": _Silent(), **login}) as ydl:
        return ydl.extract_info(url, download=False)


def fetch(url: str, library: Path, browser: str | None = None) -> Path:
    """Download the audio of a YouTube URL into its own track directory as source.wav.

    `browser` lends yt-dlp that browser's YouTube login, which age-restricted videos need. Without one, a
    video that needs a login is tried again with the default browser's.
    """
    try:
        info = _info(url, browser)
    except DownloadError as e:
        message = _brief(e)
        if browser or not _needs_login(message):
            raise SystemExit(f"{message}\n{_login_help(browser)}" if browser and _needs_login(message) else message) from e
        browser = default_browser()
        if browser is None:
            raise SystemExit(f"{message}\nYouTube wants a signed-in account for this video: sign in to YouTube in "
                             "your browser and add --cookies-from-browser chrome (or safari, firefox...).") from e
        print(f"YouTube wants a signed-in account for this video, using your {browser.title()} login")
        try:
            info = _info(url, browser)
        # Reading another app's login fails in many ways (no permission, no profile, locked keychain).
        except Exception as again:
            raise SystemExit(f"{_brief(again)}\n{_login_help(browser)}") from again
    except Exception as e:
        if not browser:
            raise
        raise SystemExit(f"{_brief(e)}\n{_login_help(browser)}") from e
    login = {"cookiesfrombrowser": (browser,)} if browser else {}

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
