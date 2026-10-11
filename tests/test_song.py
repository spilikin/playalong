import json

import numpy as np
import soundfile as sf

from playalong.chords import Chord, ChordResult
from playalong.song import SONG_FORMAT, read_song, song_path, write_song

INFO = {
    "id": "abc123",
    "title": "Artist - Song",
    "uploader": "Artist",
    "duration": 12,
    "webpage_url": "https://www.youtube.com/watch?v=abc123",
    "song_start": 2.0,
    "song_start_source": "sponsorblock",
    "bpm": 120.0,
    "bpm_confidence": 0.7,
    "bpm_source": "detected",
}


def track(tmp_path, stems=True, mixes=True):
    d = tmp_path / "artist-song"
    d.mkdir()
    (d / "info.json").write_text(json.dumps(INFO))
    sf.write(d / "source.wav", np.zeros((44100 * 12, 2), np.float32), 44100)
    if stems:
        (d / "stems").mkdir()
        for name in ("bass", "drums", "guitar"):
            sf.write(d / "stems" / f"{name}.wav", np.zeros((10, 2), np.float32), 44100)
    if mixes:
        (d / "mixes").mkdir()
        for name in ("artist-song - no-guitar.mp3", "artist-song - backing @80%.wav", "artist-song - quiet-guitar.flac"):
            (d / "mixes" / name).write_bytes(b"")
        gb = d / "mixes" / "artist-song - GarageBand 120 BPM"
        gb.mkdir()
        (gb / "Bass.wav").write_bytes(b"")
    return d


def chords():
    beats = [2.0 + i * 0.5 for i in range(9)]
    return ChordResult(key="Bb minor", bpm=120.0, first_beat=2.5, beats=beats, pickup=1,
                       chords=[Chord(2.0, 2.5, "N"), Chord(2.5, 4.5, "Bbm"), Chord(4.5, 6.0, "Gb")])


def test_the_song_file_sits_in_the_track_folder_named_after_it(tmp_path):
    d = track(tmp_path)
    path = write_song(d, chords())
    assert path == song_path(d) == d / "artist-song.playalong"
    assert [p.name for p in d.iterdir() if p.name.startswith(".")] == []  # written via a temp file, nothing left over


def test_it_describes_the_song_its_timing_and_files(tmp_path):
    d = track(tmp_path)
    song = json.loads(write_song(d, chords()).read_text())
    assert song["format"] == SONG_FORMAT and song["version"] == 1
    assert song["title"] == "Artist - Song" and song["artist"] == "Artist"
    assert song["source"] == {"url": "https://www.youtube.com/watch?v=abc123", "youtube_id": "abc123"}
    assert song["audio"] == {"file": "source.wav", "sample_rate": 44100, "duration": 12.0}
    assert song["song_start"] == {"seconds": 2.0, "source": "sponsorblock"}
    assert song["tempo"] == {"bpm": 120.0, "confidence": 0.7, "source": "detected", "beats_per_bar": 4}
    assert song["key"] == "Bb minor"
    assert song["beats"] == [2.0 + i * 0.5 for i in range(9)]
    assert song["bars"] == [2.5, 4.5]  # pickup of one beat, then a bar every four beats
    assert song["stems"] == {"bass": "stems/bass.wav", "drums": "stems/drums.wav", "guitar": "stems/guitar.wav"}
    unknown = {"source_offset": None, "count_in": None}
    assert song["mixes"] == [
        {"file": "mixes/artist-song - backing @80%.wav", "name": "backing", "tempo": 0.8, **unknown},
        {"file": "mixes/artist-song - no-guitar.mp3", "name": "no-guitar", "tempo": 1.0, **unknown},
        {"file": "mixes/artist-song - quiet-guitar.flac", "name": "quiet-guitar", "tempo": 1.0, **unknown},
    ]
    assert song["garageband"] == {"folder": "mixes/artist-song - GarageBand 120 BPM", "bpm": 120}
    assert song["cover"] is None
    assert song["chord_sheet"] is None  # no chords.html in this folder


def test_chords_come_with_their_shapes(tmp_path):
    song = json.loads(write_song(track(tmp_path), chords()).read_text())
    assert song["chords"] == [
        {"start": 2.0, "end": 2.5, "name": "N", "root": None, "quality": None},
        {"start": 2.5, "end": 4.5, "name": "Bbm", "root": "Bb", "quality": "minor"},
        {"start": 4.5, "end": 6.0, "name": "Gb", "root": "Gb", "quality": "major"},
    ]
    assert set(song["chord_shapes"]) == {"Bbm", "Gb"}
    assert song["chord_shapes"]["Bbm"] == {"frets": [-1, 1, 3, 3, 2, 1], "fingers": [0, 1, 3, 4, 2, 1],
                                           "barre": {"fret": 1, "strings": [1, 5]}}
    assert song["chord_shapes"]["Gb"]["barre"] == {"fret": 2, "strings": [0, 5]}
    assert song["chord_shapes"]["Gb"]["frets"] == [2, 4, 4, 3, 2, 2]


def test_later_steps_keep_the_chords_and_pick_up_new_files(tmp_path):
    d = track(tmp_path, mixes=False)
    write_song(d, chords())
    (d / "mixes").mkdir()
    (d / "mixes" / "artist-song - guide.mp3").write_bytes(b"")
    (d / "chords.html").write_text("<html></html>")
    assert read_song(d)["key"] == "Bb minor"
    song = json.loads(write_song(d).read_text())
    assert song["key"] == "Bb minor" and len(song["chords"]) == 3
    assert [m["name"] for m in song["mixes"]] == ["guide"]
    assert song["chord_sheet"] == "chords.html"


def test_a_fresh_download_already_has_a_song_file(tmp_path):
    d = track(tmp_path, stems=False, mixes=False)
    song = json.loads(write_song(d).read_text())
    assert song["stems"] == {} and song["mixes"] == [] and song["garageband"] is None
    assert song["chords"] is None and song["chord_shapes"] == {} and song["beats"] == []
    assert song["key"] is None


def test_mixes_carry_the_timing_recorded_when_they_were_rendered(tmp_path):
    d = track(tmp_path)
    count = {"bars": 1, "clicks": [{"time": 0.25, "accent": True, "count": 1}], "downbeat": 2.25}
    (d / "mixes" / "mixes.json").write_text(json.dumps(
        {"artist-song - no-guitar.mp3": {"name": "no-guitar", "tempo": 1.0, "source_offset": 0.1, "count_in": count},
         "artist-song - gone.mp3": {"name": "gone", "tempo": 1.0, "source_offset": 0.0, "count_in": None}}))
    song = json.loads(write_song(d).read_text())
    by_name = {m["name"]: m for m in song["mixes"]}
    assert by_name["no-guitar"]["source_offset"] == 0.1 and by_name["no-guitar"]["count_in"] == count
    assert "gone" not in by_name  # deleted files drop out


def test_the_cover_is_listed_with_where_it_came_from(tmp_path):
    d = track(tmp_path)
    (d / "cover.jpg").write_bytes(b"jpg")
    info = json.loads((d / "info.json").read_text())
    (d / "info.json").write_text(json.dumps({**info, "cover_source": "itunes", "album": "Album"}))
    write_song(d)
    assert read_song(d)["cover"] == {"file": "cover.jpg", "source": "itunes", "album": "Album"}
