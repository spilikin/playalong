import json

import numpy as np
import pytest

from playalong.tempo import OnsetEnvelope, song_tempo

RATE = 44100


def hits(bpm, seconds=30.0, offset=0.37, level=1.0, subdivide=1, off_level=0.0):
    """A drum-like stem: short noise bursts on every beat, optionally with quieter ones in between."""
    rng = np.random.default_rng(1)
    out = np.zeros(int(seconds * RATE), dtype=np.float32)
    burst = int(0.02 * RATE)
    shape = np.exp(-np.arange(burst) / (burst / 5)).astype(np.float32)
    period = 60.0 / bpm / subdivide
    t, k = offset, 0
    while t * RATE + burst < len(out):
        i = int(t * RATE)
        amp = level if k % subdivide == 0 else off_level
        out[i : i + burst] += amp * shape * rng.uniform(-1, 1, burst).astype(np.float32)
        t, k = t + period, k + 1
    return out


def stereo(mono):
    return np.stack([mono, mono], axis=1)


@pytest.mark.parametrize("bpm", [84.0, 100.0, 128.0, 172.0])
def test_finds_the_tempo_of_steady_hits(bpm):
    tempo = OnsetEnvelope(hits(bpm), RATE).tempo()
    assert tempo is not None
    assert tempo.bpm == pytest.approx(bpm, abs=1.0)
    assert 0 < tempo.confidence <= 1


def test_quieter_hits_between_beats_do_not_double_the_tempo():
    tempo = OnsetEnvelope(hits(100.0, subdivide=2, off_level=0.3), RATE).tempo()
    assert tempo.bpm == pytest.approx(100.0, abs=1.0)


def test_silence_has_no_tempo():
    assert OnsetEnvelope(np.zeros(RATE * 20, dtype=np.float32), RATE).tempo() is None


def test_beat_near_lands_on_the_closest_hit():
    envelope = OnsetEnvelope(hits(100.0, offset=0.37), RATE)
    # Hits at 0.37 + 0.6k: the one closest to 5.0 s is at 5.17 s.
    assert envelope.beat_near(100.0, 5.0) == pytest.approx(5.17, abs=0.015)


def test_song_tempo_caches_and_keeps_a_users_bpm(tmp_path):
    stems = {"drums": stereo(hits(100.0)), "bass": stereo(np.zeros(RATE * 30, dtype=np.float32))}
    (tmp_path / "info.json").write_text(json.dumps({"song_start": 5.0}))

    bpm, beat = song_tempo(tmp_path, stems, RATE, 5.0)
    info = json.loads((tmp_path / "info.json").read_text())
    assert bpm == pytest.approx(100.0, abs=1.0)
    assert beat == pytest.approx(5.17, abs=0.015)
    assert info["bpm_source"] == "detected"
    assert info["beat_offset"] == pytest.approx(beat)

    bpm, _ = song_tempo(tmp_path, stems, RATE, 5.0, bpm=96.0)
    assert bpm == 96.0
    bpm, _ = song_tempo(tmp_path, stems, RATE, 5.0)
    assert bpm == 96.0
    assert json.loads((tmp_path / "info.json").read_text())["bpm_source"] == "user"


def test_quiet_drums_fall_back_to_bass_and_guitar(tmp_path):
    silent = stereo(np.zeros(RATE * 30, dtype=np.float32))
    stems = {"drums": silent, "bass": stereo(hits(90.0)), "guitar": silent}
    bpm, _ = song_tempo(tmp_path, stems, RATE, 0.0)
    assert bpm == pytest.approx(90.0, abs=1.0)


def test_rounds_halves_like_the_app():
    from playalong.tempo import _round

    # Halving an odd lag lands on .5; the app (Rust) rounds it up, so the port must too.
    assert [_round(x) for x in (20.5, 21.5, 21.4)] == [21, 22, 21]
