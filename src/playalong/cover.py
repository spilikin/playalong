"""Album cover for a track: the iTunes catalogue's artwork, or the video's thumbnail when it has none.

Saved as `cover.jpg` next to `source.wav`; where it came from is kept in `info.json` (`cover_source`, `album`).
"""

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

COVER = "cover.jpg"
SEARCH = "https://itunes.apple.com/search"
SIZE = 600
TIMEOUT = 10

# "(Official Music Video)", "[Lyric Video]", "(HD)"... words that name the upload, not the song.
NOISE = re.compile(r"\s*[(\[][^)\]]*\b(official|video|lyrics?|audio|visuali[sz]er|hd|4k|remaster(ed)?|live)\b[^)\]]*[)\]]",
                   re.IGNORECASE)
CHANNEL = re.compile(r"\s*(- topic|vevo|official)$", re.IGNORECASE)


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "playalong"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def guess_query(info: dict) -> tuple[str, str]:
    """(artist, song) from the YouTube metadata: yt-dlp's music fields if it has them, else "Artist - Song" titles."""
    artist = info.get("artist") or ""
    song = info.get("track") or ""
    title = NOISE.sub("", info.get("title") or "").strip()
    if not song:
        left, sep, right = title.partition(" - ")
        if sep:
            artist, song = artist or left.strip(), right.strip()
        else:
            song = title
    if not artist:
        artist = CHANNEL.sub("", info.get("uploader") or "").strip()
    return artist.split(",")[0].strip(), song


def _norm(text: str) -> str:
    return re.sub(r"\W+", "", text.casefold())


def find_artwork(artist: str, song: str) -> tuple[str, str | None] | None:
    """URL of the catalogue's artwork and the album name, preferring a result by the same artist."""
    query = urllib.parse.urlencode({"term": f"{artist} {song}".strip(), "entity": "song", "limit": 10})
    results = json.loads(_get(f"{SEARCH}?{query}")).get("results", [])
    results = [r for r in results if r.get("artworkUrl100")]
    if artist:
        same = [r for r in results if _norm(artist) in _norm(r.get("artistName", ""))]
        # Another artist's cover is worse than the video's own thumbnail.
        results = same
    if not results:
        return None
    best = results[0]
    return best["artworkUrl100"].replace("100x100bb", f"{SIZE}x{SIZE}bb"), best.get("collectionName")


def _thumbnail(video_id: str) -> bytes | None:
    for name in ("maxresdefault", "hqdefault"):
        try:
            return _get(f"https://i.ytimg.com/vi/{video_id}/{name}.jpg")
        except OSError:
            continue
    return None


def fetch_cover(track_dir: Path, query: str | None = None, force: bool = False) -> Path | None:
    """Download the track's cover unless it has one; `query` replaces the search guessed from the title."""
    dest = track_dir / COVER
    if dest.exists() and not force:
        return dest
    info_path = track_dir / "info.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else {}

    artist, song = ("", query) if query else guess_query(info)
    image, source, album = None, None, None
    try:
        if found := find_artwork(artist, song):
            url, album = found
            image, source = _get(url), "itunes"
    except (OSError, ValueError) as e:
        print(f"Cover search failed: {e}")
    if image is None and info.get("id"):
        if image := _thumbnail(info["id"]):
            source = "youtube"
    if image is None:
        print("No cover found (give a search with `playalong cover --query`)")
        return None

    dest.write_bytes(image)
    info.update(cover_source=source, album=album)
    info_path.write_text(json.dumps(info, indent=2, ensure_ascii=False))
    print(f"Cover: {album or 'video thumbnail'} ({source})")
    return dest
