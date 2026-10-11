import json

import numpy as np
import pytest
import soundfile as sf

from playalong.garageband import export_stems
from playalong.mix import PEAK_CEILING
from playalong.separate import STEMS
from test_tempo import RATE, hits


def track(tmp_path, bpm=100.0, drums_level=1.0):
    stems_dir = tmp_path / "song" / "stems"
    stems_dir.mkdir(parents=True)
    drums = hits(bpm, offset=5.17) * drums_level
    for name in STEMS:
        audio = drums if name == "drums" else np.full(len(drums), 0.1, dtype=np.float32)
        sf.write(stems_dir / f"{name}.wav", np.stack([audio, audio], axis=1), RATE, subtype="FLOAT")
    (tmp_path / "song" / "info.json").write_text(json.dumps({"song_start": 5.0, "title": "Song"}))
    return tmp_path / "song"


def test_writes_one_aligned_file_per_stem_with_the_first_beat_on_bar_two(tmp_path):
    folder = export_stems(track(tmp_path))
    assert folder.name == "song - GarageBand 100 BPM"
    files = sorted(folder.glob("*.wav"))
    assert [f.stem for f in files] == sorted(n.capitalize() for n in STEMS)
    lengths = {sf.info(f).frames for f in files}
    assert len(lengths) == 1

    drums, rate = sf.read(folder / "Drums.wav")
    first_hit = np.flatnonzero(np.abs(drums[:, 0]) > 0.05)[0] / rate
    assert first_hit == pytest.approx(4 * 60 / 100, abs=0.02)  # one bar in: bar 2 starts here
    # The intro (everything before the song start) doesn't come along.
    bass, _ = sf.read(folder / "Bass.wav")
    assert not np.abs(bass[: int((2.4 - 0.2) * rate)]).max() > 1e-4


def test_stems_keep_their_balance_and_fit_under_the_ceiling(tmp_path):
    song = track(tmp_path, drums_level=3.0)  # stems peaking well above full scale
    source_peak = np.abs(sf.read(song / "stems" / "drums.wav")[0]).max()
    folder = export_stems(song)
    drums, _ = sf.read(folder / "Drums.wav")
    bass, _ = sf.read(folder / "Bass.wav")
    assert np.abs(drums).max() <= PEAK_CEILING + 1e-3
    loud = np.abs(bass[:, 0]) > 0
    ratio = np.abs(drums).max() / np.abs(bass[loud][:, 0]).max()
    assert ratio == pytest.approx(source_peak / 0.1, rel=0.01)


def test_without_a_tempo_the_stems_just_start_at_the_song(tmp_path, capsys):
    song = track(tmp_path, drums_level=0.0)
    for name in STEMS:
        sf.write(song / "stems" / f"{name}.wav", np.zeros((RATE * 20, 2), dtype=np.float32), RATE, subtype="FLOAT")
    folder = export_stems(song)
    assert folder.name == "song - GarageBand"
    assert sf.info(folder / "Drums.wav").frames == RATE * 15
    assert "set the tempo" in capsys.readouterr().out
