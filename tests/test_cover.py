import json

import pytest

from playalong import cover
from playalong.cover import fetch_cover, guess_query


@pytest.mark.parametrize("info, expected", [
    ({"title": "Lee Brice - Love Like Crazy (Official Music Video)", "uploader": "Lee Brice"},
     ("Lee Brice", "Love Like Crazy")),
    ({"title": "Kad izdzisīs [Lyric Video]", "uploader": "Miks Galvanovskis - Topic"},
     ("Miks Galvanovskis", "Kad izdzisīs")),
    ({"title": "whatever", "artist": "Queen, David Bowie", "track": "Under Pressure"},
     ("Queen", "Under Pressure")),
])
def test_the_search_comes_from_the_video_metadata(info, expected):
    assert guess_query(info) == expected


def serve(monkeypatch, pages):
    asked = []

    def get(url):
        asked.append(url)
        for prefix, body in pages.items():
            if url.startswith(prefix):
                if isinstance(body, Exception):
                    raise body
                return body
        raise OSError(f"404 {url}")

    monkeypatch.setattr(cover, "_get", get)
    return asked


def track(tmp_path, **info):
    d = tmp_path / "song"
    d.mkdir()
    (d / "info.json").write_text(json.dumps({"id": "vid", "title": "Artist - Song (Official Video)", **info}))
    return d


def test_takes_the_catalogue_artwork_by_the_same_artist(tmp_path, monkeypatch):
    results = {"results": [
        {"artistName": "Someone Else", "artworkUrl100": "https://art/other/100x100bb.jpg"},
        {"artistName": "Artist", "collectionName": "Album", "artworkUrl100": "https://art/mine/100x100bb.jpg"},
    ]}
    asked = serve(monkeypatch, {cover.SEARCH: json.dumps(results).encode(), "https://art/mine/600x600bb.jpg": b"jpg"})
    d = track(tmp_path)
    assert fetch_cover(d) == d / "cover.jpg"
    assert (d / "cover.jpg").read_bytes() == b"jpg"
    assert "term=Artist+Song" in asked[0]
    info = json.loads((d / "info.json").read_text())
    assert info["cover_source"] == "itunes" and info["album"] == "Album"


def test_falls_back_to_the_video_thumbnail(tmp_path, monkeypatch):
    results = {"results": [{"artistName": "Someone Else", "artworkUrl100": "https://art/x/100x100bb.jpg"}]}
    serve(monkeypatch, {cover.SEARCH: json.dumps(results).encode(), "https://i.ytimg.com/vi/vid/hqdefault": b"thumb"})
    d = track(tmp_path)
    fetch_cover(d)
    assert (d / "cover.jpg").read_bytes() == b"thumb"
    assert json.loads((d / "info.json").read_text())["cover_source"] == "youtube"


def test_no_network_means_no_cover_but_no_error(tmp_path, monkeypatch):
    serve(monkeypatch, {})
    assert fetch_cover(track(tmp_path)) is None


def test_an_existing_cover_is_kept_unless_forced(tmp_path, monkeypatch):
    asked = serve(monkeypatch, {})
    d = track(tmp_path)
    (d / "cover.jpg").write_bytes(b"mine")
    assert fetch_cover(d) == d / "cover.jpg" and asked == []
