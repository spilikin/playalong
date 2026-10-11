"""The song file: one JSON document per track that a player opens to get everything about the song.

`<track>/<track>.playalong` gathers the metadata, timing, chords with their finger shapes, and where the
audio lives. Times are seconds in `audio.file`; paths are relative to the song file. Each CLI step
rewrites it, keeping chords from an earlier run when the step didn't detect them.
"""

import json
import os
import re
import tempfile
from pathlib import Path

import soundfile as sf

from playalong.chord_page import parse, voicing
from playalong.chords import ChordResult
from playalong.countin import BEATS_PER_BAR
from playalong.cover import COVER
from playalong.mix import MIX_INDEX

SONG_FORMAT = "playalong-song"
SONG_VERSION = 1
SUFFIX = ".playalong"
QUALITY = {False: "major", True: "minor"}


def song_path(track_dir: Path) -> Path:
    return track_dir / f"{track_dir.name}{SUFFIX}"


def read_song(track_dir: Path) -> dict | None:
    path = song_path(track_dir)
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _shape(name: str) -> dict:
    v = voicing(name)
    barre = None
    if v.barre is not None:
        barre = {"fret": v.barre, "strings": [v.barre_from, len(v.frets) - 1]}
    return {"frets": list(v.frets), "fingers": list(v.fingers), "barre": barre}


def _chord_data(result: ChordResult) -> dict:
    chords = []
    for c in result.chords:
        if c.name == "N":
            chords.append({"start": c.start, "end": c.end, "name": "N", "root": None, "quality": None})
        else:
            _, minor = parse(c.name)
            chords.append({"start": c.start, "end": c.end, "name": c.name,
                           "root": c.name[:-1] if minor else c.name, "quality": QUALITY[minor]})
    grid = result.beats[:-1]
    return {
        "key": result.key,
        "beats": list(result.beats),
        "bars": [grid[i] for i in range(result.pickup, len(grid), BEATS_PER_BAR)],
        "chords": chords,
        "chord_shapes": {name: _shape(name) for name in dict.fromkeys(c.name for c in result.chords) if name != "N"},
    }


MIX_NAME = re.compile(r" - (?P<name>.+?)(?: @(?P<percent>\d+)%)?$")
GARAGEBAND = re.compile(r" - GarageBand(?: (?P<bpm>\d+) BPM)?$")


def _files(track_dir: Path) -> dict:
    def rel(p: Path) -> str:
        return p.relative_to(track_dir).as_posix()

    stems_dir, mixes_dir = track_dir / "stems", track_dir / "mixes"
    stems = {p.stem: rel(p) for p in sorted(stems_dir.glob("*.wav"))} if stems_dir.is_dir() else {}
    mixes, garageband = [], None
    try:
        index = json.loads((mixes_dir / MIX_INDEX).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        index = {}
    if mixes_dir.is_dir():
        for p in sorted(mixes_dir.iterdir()):
            if p.is_dir():
                if m := GARAGEBAND.search(p.name):
                    garageband = {"folder": rel(p), "bpm": int(m["bpm"]) if m["bpm"] else None}
            elif p.suffix in (".mp3", ".wav", ".flac") and (m := MIX_NAME.search(p.stem)):
                tempo = int(m["percent"]) / 100 if m["percent"] else 1.0
                # Timing is only known for mixes rendered since mixes.json existed; older ones get nulls.
                timing = index.get(p.name, {})
                mixes.append({"file": rel(p), "name": m["name"], "tempo": tempo,
                              "source_offset": timing.get("source_offset"), "count_in": timing.get("count_in")})
    sheet = track_dir / "chords.html"
    return {"stems": stems, "mixes": mixes, "garageband": garageband,
            "chord_sheet": rel(sheet) if sheet.exists() else None}


def _cover(track_dir: Path, info: dict) -> dict | None:
    if not (track_dir / COVER).exists():
        return None
    return {"file": COVER, "source": info.get("cover_source"), "album": info.get("album")}


def write_song(track_dir: Path, chords: ChordResult | None = None) -> Path:
    """Write (or refresh) the track's song file and return its path."""
    info_path = track_dir / "info.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else {}
    source = track_dir / "source.wav"
    audio = None
    if source.exists():
        meta = sf.info(source)
        audio = {"file": "source.wav", "sample_rate": meta.samplerate, "duration": round(meta.duration, 3)}

    previous = read_song(track_dir) or {}
    if chords is not None:
        chord_data = _chord_data(chords)
    else:
        chord_data = {k: previous.get(k) for k in ("key", "beats", "bars", "chords", "chord_shapes")}
    chord_data = {"key": chord_data["key"], "beats": chord_data["beats"] or [], "bars": chord_data["bars"] or [],
                  "chords": chord_data["chords"], "chord_shapes": chord_data["chord_shapes"] or {}}

    song = {
        "format": SONG_FORMAT,
        "version": SONG_VERSION,
        "title": info.get("title") or track_dir.name,
        "artist": info.get("uploader"),
        "source": {"url": info.get("webpage_url"), "youtube_id": info.get("id")} if info.get("id") else None,
        "audio": audio,
        "cover": _cover(track_dir, info),
        "song_start": ({"seconds": info["song_start"], "source": info.get("song_start_source")}
                       if "song_start" in info else None),
        "tempo": ({"bpm": info["bpm"], "confidence": info.get("bpm_confidence"), "source": info.get("bpm_source"),
                   "beats_per_bar": BEATS_PER_BAR} if info.get("bpm") else None),
        **chord_data,
        **_files(track_dir),
    }

    # Written to a temporary name and renamed, so a player never reads a half-written file.
    path = song_path(track_dir)
    fd, tmp = tempfile.mkstemp(dir=track_dir, prefix=".song-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(song, f, indent=2, ensure_ascii=False)
            f.write("\n")
        # mkstemp makes the file private; a song file is as shareable as the audio next to it.
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(tmp, 0o666 & ~umask)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path
