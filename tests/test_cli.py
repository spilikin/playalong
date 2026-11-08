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


def test_garageband_stems_only_when_asked():
    parse = build_parser().parse_args
    assert parse(["mix", "t"]).garageband is False
    assert parse(["mix", "t", "--garageband"]).garageband is True
    # A new song's GarageBand stems are made on request, like its mixes.
    assert parse(["run", "https://youtu.be/x"]).garageband is False
    assert parse(["run", "https://youtu.be/x", "--garageband"]).garageband is True
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
    assert _presets(parse(["mix", "t"])) == main
    assert _presets(parse(["mix", "t", "--all"])) == list(PRESETS)
    assert _presets(parse(["mix", "t", "-p", "guide"])) == ["guide"]
    assert _presets(parse(["mix", "t", "-g", "guitar=off"])) == []


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


def _bundle(tmp_path):
    import json

    d = tmp_path / "song"
    (d / "stems").mkdir(parents=True)
    (d / "info.json").write_text(json.dumps({"title": "Song", "song_start": 2.0, "bpm": 120.0}))
    return d


def test_run_makes_no_mix_files_but_the_default_recipes(tmp_path, monkeypatch):
    from playalong import cli, cover, recipes, separate

    d = _bundle(tmp_path)
    monkeypatch.setattr(cli, "_ingest", lambda source, library, browser=None: d)
    monkeypatch.setattr(cover, "fetch_cover", lambda track, *a, **k: None)
    monkeypatch.setattr(separate, "separate", lambda track, device=None, force=False: track / "stems")
    monkeypatch.setattr(cli, "_detect_chords", lambda track, start, bpm: None)
    monkeypatch.setattr(cli, "make_mixes", lambda *a, **k: pytest.fail("run renders no mixes"))
    cli.main(["-l", str(tmp_path), "run", "https://youtu.be/x"])
    assert [r["id"] for r in recipes.read_recipes(d)] == ["original", "guide", "no-guitar"]
    assert not (d / "mixes").exists() or not any((d / "mixes").glob("*.mp3"))


def test_refresh_deletes_rendered_mixes_and_keeps_the_rest(tmp_path, monkeypatch):
    from playalong import cli, recipes

    d = _bundle(tmp_path)
    mixes = d / "mixes"
    gb = mixes / "song - GarageBand 120 BPM"
    gb.mkdir(parents=True)
    (gb / "Bass.wav").write_bytes(b"")
    (mixes / "song - GarageBand 120 BPM.band").mkdir()
    for name in ("song - guide.mp3", "song - backing @80%.wav", "song - x.flac", "mixes.json"):
        (mixes / name).write_bytes(b"")
    (d / "stems" / "bass.wav").write_bytes(b"")
    monkeypatch.setattr(cli, "_update_song", lambda track, chords=None: None)
    cli.main(["refresh", str(d)])
    assert sorted(p.name for p in mixes.iterdir()) == ["song - GarageBand 120 BPM", "song - GarageBand 120 BPM.band"]
    assert (d / "stems" / "bass.wav").exists() and (gb / "Bass.wav").exists()
    assert recipes.read_recipes(d) == recipes.DEFAULTS


def test_retime_saves_the_users_start_and_bpm_and_marks_the_change(tmp_path, monkeypatch):
    import json

    from playalong import cli

    d = _bundle(tmp_path)
    seen = {}
    monkeypatch.setattr(cli, "_detect_chords", lambda track, start, bpm: seen.update(start=start, bpm=bpm))
    monkeypatch.setattr(cli, "_update_song", lambda track, chords=None: None)
    cli.main(["retime", str(d), "--start", "3.5", "--bpm", "96"])
    info = json.loads((d / "info.json").read_text())
    assert info["song_start"] == 3.5 and info["song_start_source"] == "user"
    assert seen == {"start": None, "bpm": 96.0}  # the stored start is used, so the beat is anchored on it
    assert info["timing_changed"] > 0


def test_export_renders_one_recipe_to_the_exports_folder(tmp_path, monkeypatch):
    from playalong import cli, mix, recipes

    d = _bundle(tmp_path)
    recipes.write_recipes(d, [{**recipes.DEFAULTS[1], "transpose": -2, "tempo": 0.9, "count_in": 0}])
    got = {}
    monkeypatch.setattr(mix, "render_recipe", lambda track, recipe, dest: got.update(recipe=recipe, dest=dest) or dest)
    cli.main(["export", str(d), "guide"])
    assert got["recipe"]["transpose"] == -2 and got["recipe"]["tempo"] == 0.9
    assert got["dest"] == d / "exports" / "song - Guide.mp3"
    with pytest.raises(SystemExit):
        cli.main(["export", str(d), "nope"])
