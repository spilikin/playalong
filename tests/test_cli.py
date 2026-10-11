import numpy as np
import pytest
import soundfile as sf

from playalong.cli import build_parser
from playalong.mix import make_mixes


def test_count_in_is_on_by_default_and_can_be_turned_off():
    parse = build_parser().parse_args
    assert parse(["mix", "t"]).count_in == 1
    assert parse(["mix", "t", "--count-in", "2"]).count_in == 2
    assert parse(["mix", "t", "--no-count-in"]).count_in == 0


def test_a_song_without_a_tempo_is_mixed_without_a_count(tmp_path, capsys):
    stems = tmp_path / "song" / "stems"
    stems.mkdir(parents=True)
    for name in ("drums", "bass", "guitar"):
        sf.write(stems / f"{name}.wav", np.zeros((44100 * 20, 2), dtype=np.float32), 44100, subtype="FLOAT")
    (written,) = make_mixes(tmp_path / "song", ["no-guitar"], fmt="wav", start=0.0, count_in=1)
    assert written.name == "song - no-guitar.wav"
    assert len(sf.read(written)[0]) == 44100 * 20
    assert "without a count-in" in capsys.readouterr().out


def test_garageband_stems_are_only_written_when_asked_for():
    parse = build_parser().parse_args
    assert parse(["mix", "t"]).garageband is False
    assert parse(["mix", "t", "--garageband"]).garageband is True
    assert parse(["run", "https://youtu.be/x", "--garageband"]).garageband is True


def test_mixes_record_their_timing_for_players(tmp_path):
    import json

    from test_tempo import hits

    stems = tmp_path / "song" / "stems"
    stems.mkdir(parents=True)
    drums = hits(120.0, seconds=20.0, offset=5.17)
    for name in ("drums", "bass", "guitar", "other", "vocals", "piano"):
        audio = drums if name == "drums" else np.zeros_like(drums)
        sf.write(stems / f"{name}.wav", np.stack([audio, audio], axis=1), 44100, subtype="FLOAT")
    make_mixes(tmp_path / "song", ["no-guitar"], fmt="wav", start=5.0, count_in=1)
    make_mixes(tmp_path / "song", ["backing"], fmt="wav", start=5.0, count_in=0)
    index = json.loads((tmp_path / "song" / "mixes" / "mixes.json").read_text())
    counted, plain = index["song - no-guitar.wav"], index["song - backing.wav"]
    assert counted["name"] == "no-guitar" and counted["tempo"] == 1.0
    assert [c["count"] for c in counted["count_in"]["clicks"]] == [1, 2, 3, 4]
    assert counted["source_offset"] == pytest.approx(5.17 - 0.25 - 2.0, abs=0.02)
    assert plain["count_in"] is None and plain["source_offset"] == 5.0


def test_the_four_main_mixes_unless_told_which():
    from playalong.cli import _presets
    from playalong.mix import PRESETS

    parse = build_parser().parse_args
    main = ["original", "guide", "no-guitar", "vocals-only"]
    assert _presets(parse(["run", "https://youtu.be/x"])) == main
    assert _presets(parse(["run", "https://youtu.be/x", "--all"])) == list(PRESETS)
    assert _presets(parse(["run", "https://youtu.be/x", "-p", "guide"])) == ["guide"]
    assert _presets(parse(["run", "https://youtu.be/x", "-g", "guitar=off"])) == []
    assert _presets(parse(["mix", "t"])) == main


def test_the_original_is_the_recording_not_the_stems(tmp_path):
    track = tmp_path / "song"
    (track / "stems").mkdir(parents=True)
    tone = (0.2 * np.sin(np.linspace(0, 2000, 44100 * 2))).astype(np.float32)
    sf.write(track / "source.wav", np.stack([tone, tone], axis=1), 44100, subtype="FLOAT")
    for name in ("drums", "guitar"):
        sf.write(track / "stems" / f"{name}.wav", np.zeros((44100 * 2, 2), np.float32), 44100, subtype="FLOAT")
    (written,) = make_mixes(track, ["original"], fmt="wav", start=0.0, count_in=0)
    assert np.abs(sf.read(written)[0]).max() == pytest.approx(0.2, abs=1e-3)
