import pytest
from yt_dlp.utils import DownloadError

from playalong import download
from playalong.cli import build_parser

AGE = ("ERROR: [youtube] abc: Sign in to confirm your age. Use --cookies-from-browser or --cookies for the "
       "authentication. See https://github.com/yt-dlp/yt-dlp/wiki/FAQ for how to manually pass cookies.")


class FakeYoutubeDL:
    seen: list[dict] = []
    error: str | None = None

    def __init__(self, opts):
        FakeYoutubeDL.seen.append(opts)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        if FakeYoutubeDL.error:
            raise DownloadError(FakeYoutubeDL.error)
        return {"id": "abc", "title": "Artist - Song"}


@pytest.fixture
def ydl(monkeypatch):
    FakeYoutubeDL.seen, FakeYoutubeDL.error = [], None
    monkeypatch.setattr(download, "YoutubeDL", FakeYoutubeDL)
    return FakeYoutubeDL


def test_an_age_restricted_video_says_how_to_sign_in(ydl, tmp_path):
    ydl.error = AGE
    with pytest.raises(SystemExit) as e:
        download.fetch("https://youtu.be/abc", tmp_path)
    assert "Sign in to confirm your age." in str(e.value)
    assert "--cookies-from-browser chrome" in str(e.value)
    assert "Traceback" not in str(e.value)


def test_the_browser_login_is_passed_to_yt_dlp(ydl, tmp_path):
    ydl.error = "ERROR: stop after the first call"
    with pytest.raises(SystemExit):
        download.fetch("https://youtu.be/abc", tmp_path, browser="safari")
    assert ydl.seen[0]["cookiesfrombrowser"] == ("safari",)


def test_run_and_download_take_a_browser():
    parse = build_parser().parse_args
    assert parse(["run", "https://youtu.be/x", "--cookies-from-browser", "chrome"]).browser == "chrome"
    assert parse(["download", "https://youtu.be/x"]).browser is None
