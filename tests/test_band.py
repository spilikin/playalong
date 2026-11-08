import pytest

from playalong import band


def test_keys_are_named_as_garageband_names_them():
    assert band.key_menu_name("F# minor") == "F♯ Minor"
    assert band.key_menu_name("Bb major") == "B♭ Major"
    assert band.key_menu_name("C major") == "C Major"


def test_without_garageband_it_says_the_stems_are_there(tmp_path, monkeypatch):
    monkeypatch.setattr(band, "GARAGEBAND", tmp_path / "missing.app")
    with pytest.raises(band.BandError, match="isn't installed"):
        band.build_project(tmp_path, 120, "C major")


def test_the_cli_builds_the_project_in_the_stems_key_and_tempo(tmp_path, monkeypatch):
    import json

    from playalong import cli, garageband

    stems = tmp_path / "mixes" / "s - GarageBand 162 BPM -1"
    monkeypatch.setattr(garageband, "export_stems", lambda track, start, bpm, transpose: stems)
    monkeypatch.setattr(cli, "_update_song", lambda track, chords=None: None)
    (tmp_path / f"{tmp_path.name}.playalong").write_text(json.dumps({"key": "G minor"}))
    built = {}
    monkeypatch.setattr(band, "build_project", lambda d, bpm, key: built.update(dir=d, bpm=bpm, key=key))
    cli.main(["garageband", str(tmp_path), "-k", "-1", "--band"])
    assert built == {"dir": stems, "bpm": 162, "key": "F# minor"}
