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


def test_run_writes_garageband_stems_unless_told_not_to_and_mix_only_when_asked():
    parse = build_parser().parse_args
    assert parse(["mix", "t"]).garageband is False
    assert parse(["mix", "t", "--garageband"]).garageband is True
    assert parse(["run", "https://youtu.be/x"]).garageband is True
    assert parse(["run", "https://youtu.be/x", "--garageband"]).garageband is True
    assert parse(["run", "https://youtu.be/x", "--no-garageband"]).garageband is False
    with pytest.raises(SystemExit):
        parse(["mix", "t", "--no-garageband"])


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


def test_transposed_mixes_are_named_and_recorded_with_their_semitones(tmp_path):
    import json

    stems = tmp_path / "song" / "stems"
    stems.mkdir(parents=True)
    for name in ("drums", "guitar"):
        sf.write(stems / f"{name}.wav", np.zeros((44100, 2), np.float32), 44100, subtype="FLOAT")
    (written,) = make_mixes(tmp_path / "song", ["no-guitar"], fmt="wav", tempo=0.8, start=0.0, transpose=-2)
    assert written.name == "song - no-guitar -2 @80%.wav"
    index = json.loads((tmp_path / "song" / "mixes" / "mixes.json").read_text())
    assert index[written.name]["transpose"] == -2


def test_transpose_is_a_mix_option_within_an_octave(tmp_path):
    from playalong.cli import main

    parse = build_parser().parse_args
    assert parse(["mix", "t"]).transpose == 0
    assert parse(["mix", "t", "-k", "-2"]).transpose == -2
    assert parse(["run", "https://youtu.be/x", "--transpose", "3"]).transpose == 3
    with pytest.raises(SystemExit, match="--transpose"):
        main(["mix", str(tmp_path), "--transpose", "13"])


def test_updating_the_downloader_needs_the_portable_runtime(monkeypatch):
    from playalong.cli import main

    monkeypatch.delenv("PLAYALONG_RUNTIME", raising=False)
    with pytest.raises(SystemExit, match="uv lock --upgrade-package yt-dlp"):
        main(["update-downloader"])


def test_garageband_stems_can_be_made_on_their_own(tmp_path, monkeypatch):
    from playalong import cli, garageband

    made = {}
    monkeypatch.setattr(garageband, "export_stems",
                        lambda track, start, bpm, transpose: made.update(track=track, start=start, transpose=transpose))
    monkeypatch.setattr(cli, "_update_song", lambda track, chords=None: made.update(updated=track))
    cli.main(["garageband", str(tmp_path), "-k", "-2", "--no-trim"])
    assert made == {"track": tmp_path, "start": 0.0, "transpose": -2, "updated": tmp_path}
    with pytest.raises(SystemExit):
        cli.main(["garageband", str(tmp_path), "-k", "13"])
