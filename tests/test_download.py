import plistlib

import pytest
from yt_dlp.utils import DownloadError

from playalong import download
from playalong.cli import build_parser

AGE = ("\x1b[0;31mERROR:\x1b[0m [youtube] abc: Sign in to confirm your age. Use --cookies-from-browser or --cookies "
       "for the authentication. See https://github.com/yt-dlp/yt-dlp/wiki/FAQ for how to manually pass cookies.")


class FakeYoutubeDL:
    """Asks for a login unless given a browser's; `unreadable` makes reading that login fail."""

    seen: list[dict] = []
    unreadable = False
    refused = False

    def __init__(self, opts):
        FakeYoutubeDL.seen.append(opts)
        self.browser = opts.get("cookiesfrombrowser")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        if not self.browser:
            raise DownloadError(AGE)
        if FakeYoutubeDL.unreadable:
            raise PermissionError(1, "Operation not permitted")
        if FakeYoutubeDL.refused:
            raise DownloadError("ERROR: [youtube] abc: The page needs to be reloaded.")
        return {"id": "abc", "title": "Artist - Song"}


@pytest.fixture
def ydl(monkeypatch, tmp_path):
    FakeYoutubeDL.seen, FakeYoutubeDL.unreadable, FakeYoutubeDL.refused = [], False, False
    monkeypatch.setattr(download, "YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(download, "default_browser", lambda: "safari")
    # Already downloaded, so a successful lookup stops before any real download.
    (tmp_path / "artist-song").mkdir()
    (tmp_path / "artist-song" / "source.wav").write_bytes(b"")
    return FakeYoutubeDL


def test_a_video_that_needs_a_login_is_retried_with_the_default_browser(ydl, tmp_path, capsys):
    assert download.fetch("https://youtu.be/abc", tmp_path) == tmp_path / "artist-song"
    assert [o.get("cookiesfrombrowser") for o in ydl.seen] == [None, ("safari",)]
    assert "using your Safari login" in capsys.readouterr().out


def test_an_unreadable_safari_login_says_how_to_allow_it(ydl, tmp_path):
    ydl.unreadable = True
    with pytest.raises(SystemExit) as e:
        download.fetch("https://youtu.be/abc", tmp_path)
    assert "Full Disk Access" in str(e.value)


def test_a_login_youtube_still_refuses_is_not_blamed_on_access(ydl, tmp_path):
    ydl.refused = True
    with pytest.raises(SystemExit) as e:
        download.fetch("https://youtu.be/abc", tmp_path)
    assert "The page needs to be reloaded." in str(e.value)
    assert "still refused it with your Safari login" in str(e.value)
    assert "Full Disk Access" not in str(e.value)


def test_a_named_browser_is_used_straight_away(ydl, tmp_path):
    download.fetch("https://youtu.be/abc", tmp_path, browser="chrome")
    assert [o.get("cookiesfrombrowser") for o in ydl.seen] == [("chrome",)]


def test_messages_lose_the_colours_and_the_cookie_faq():
    assert download._brief(DownloadError(AGE)) == "[youtube] abc: Sign in to confirm your age."


def test_the_default_browser_comes_from_launch_services(tmp_path):
    plist = tmp_path / "ls.plist"
    plist.write_bytes(plistlib.dumps({"LSHandlers": [
        {"LSHandlerURLScheme": "mailto", "LSHandlerRoleAll": "com.apple.mail"},
        {"LSHandlerURLScheme": "https", "LSHandlerRoleAll": "com.google.Chrome"},
    ]}))
    assert download.default_browser(plist) == "chrome"


def test_run_and_download_take_a_browser():
    parse = build_parser().parse_args
    assert parse(["run", "https://youtu.be/x", "--cookies-from-browser", "chrome"]).browser == "chrome"
    assert parse(["download", "https://youtu.be/x"]).browser is None
