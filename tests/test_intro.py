import json

import numpy as np
import pytest

from playalong import intro

RATE = 8000


def tone(seconds, amp=0.5, freq=220.0):
    t = np.arange(int(seconds * RATE)) / RATE
    return np.stack([amp * np.sin(2 * np.pi * freq * t)] * 2, axis=1).astype(np.float32)


def silence(seconds):
    return np.zeros((int(seconds * RATE), 2), dtype=np.float32)


def band(intro_seconds, song_seconds=20):
    music = np.concatenate([silence(intro_seconds), tone(song_seconds)])
    return {"drums": music, "bass": music.copy()}


def test_detects_start_after_silent_intro():
    assert intro.detect_from_stems(band(8), RATE) == pytest.approx(8 - intro.PRE_ROLL, abs=0.15)


def test_song_starting_immediately_is_not_trimmed():
    assert intro.detect_from_stems(band(0), RATE) == 0.0


def test_short_lead_in_is_kept():
    assert intro.detect_from_stems(band(0.5), RATE) == 0.0


def test_dialogue_in_vocals_and_other_is_ignored():
    stems = band(10)
    speech = np.concatenate([tone(10, freq=300), silence(20)])
    stems["vocals"] = speech
    stems["other"] = speech.copy()
    assert intro.detect_from_stems(stems, RATE) == pytest.approx(10 - intro.PRE_ROLL, abs=0.15)


def test_isolated_hit_in_intro_is_ignored():
    stems = band(10)
    stems["drums"][RATE * 3 : RATE * 3 + RATE // 4] = 0.5
    assert intro.detect_from_stems(stems, RATE) == pytest.approx(10 - intro.PRE_ROLL, abs=0.15)


def test_quiet_room_noise_in_intro_is_ignored():
    stems = band(6)
    rng = np.random.default_rng(0)
    stems["bass"][: 6 * RATE] = rng.normal(0, 0.005, (6 * RATE, 2))
    assert intro.detect_from_stems(stems, RATE) == pytest.approx(6 - intro.PRE_ROLL, abs=0.15)


def test_song_start_is_cached(tmp_path, monkeypatch):
    (tmp_path / "info.json").write_text(json.dumps({"id": "abc"}))
    monkeypatch.setattr(intro, "sponsorblock_start", lambda _: None)
    assert intro.song_start(tmp_path, band(5), RATE) == pytest.approx(4.8, abs=0.15)

    info = json.loads((tmp_path / "info.json").read_text())
    assert info["song_start_source"] == "stems"
    monkeypatch.setattr(intro, "detect_from_stems", lambda *_: pytest.fail("should use cache"))
    assert intro.song_start(tmp_path, band(5), RATE) == info["song_start"]


def test_sponsorblock_wins_over_stems(tmp_path, monkeypatch):
    (tmp_path / "info.json").write_text(json.dumps({"id": "abc"}))
    monkeypatch.setattr(intro, "sponsorblock_start", lambda _: 12.34)
    assert intro.song_start(tmp_path, band(5), RATE) == 12.34
    assert json.loads((tmp_path / "info.json").read_text())["song_start_source"] == "sponsorblock"
