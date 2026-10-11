import numpy as np
import pytest

from playalong.mix import PEAK_CEILING, PRESETS, parse_gain, render, trim
from playalong.separate import STEMS


def stems(value=0.1, length=100):
    return {name: np.full((length, 2), value, dtype=np.float32) for name in STEMS}


def test_presets_only_reference_model_stems():
    for gains in PRESETS.values():
        assert set(gains) <= set(STEMS)


def test_off_removes_stem():
    s = stems()
    s["guitar"][:] = 0.3
    out = render(s, {"guitar": None})
    assert np.allclose(out, 0.1 * (len(STEMS) - 1))


def test_gain_in_db():
    s = {"guitar": np.full((10, 2), 0.5, dtype=np.float32)}
    out = render(s, {"guitar": -6.0206})
    assert np.allclose(out, 0.25, atol=1e-4)


def test_loud_mix_is_limited_to_ceiling():
    out = render(stems(value=0.5), {})
    assert np.isclose(np.abs(out).max(), PEAK_CEILING)


def test_quiet_mix_is_not_boosted():
    out = render(stems(value=0.01), {"drums": None})
    assert np.allclose(out, 0.05)


def test_unequal_lengths_are_padded():
    s = {"a": np.ones((5, 2), np.float32) * 0.1, "b": np.ones((8, 2), np.float32) * 0.1}
    out = render(s, {})
    assert out.shape == (8, 2)
    assert np.allclose(out[5:], 0.1)


def test_unknown_stem_rejected():
    with pytest.raises(ValueError, match="unknown stems"):
        render(stems(), {"kazoo": None})


@pytest.mark.parametrize("spec,expected", [
    ("guitar=off", ("guitar", None)),
    ("vocals=-12", ("vocals", -12.0)),
    (" bass = 3 ", ("bass", 3.0)),
])
def test_parse_gain(spec, expected):
    assert parse_gain(spec) == expected


def test_parse_gain_rejects_garbage():
    with pytest.raises(ValueError):
        parse_gain("guitar")


def test_trim_cuts_and_fades_in():
    audio = np.ones((1000, 2), dtype=np.float32)
    out = trim(audio, 100, 2.5)
    assert out.shape == (750, 2)
    assert out[0, 0] == 0.0
    assert np.all(out[10:] == 1.0)


def test_trim_zero_is_noop():
    audio = np.ones((10, 2), dtype=np.float32)
    assert trim(audio, 100, 0.0) is audio


def test_vocals_only_keeps_just_the_vocals():
    s = stems()
    s["vocals"][:] = 0.3
    out = render(s, PRESETS["vocals-only"])
    assert np.allclose(out, 0.3)


def test_place_beat_puts_the_beat_at_the_given_time():
    from playalong.mix import place_beat

    rate = 1000
    music = np.zeros((10 * rate, 2), dtype=np.float32)
    music[int(2.3 * rate)] = 0.5
    out = place_beat(music, rate, start=2.0, beat=2.3, at=2.0)
    assert np.flatnonzero(out[:, 0] == 0.5)[0] == 2000
    # Before the song start there is only silence, not the intro.
    assert not out[: int(1.7 * rate)].any()


def test_place_beat_cuts_music_that_would_come_before_time_zero():
    from playalong.mix import place_beat

    rate = 1000
    music = np.zeros((20 * rate, 2), dtype=np.float32)
    music[int(8.0 * rate)] = 0.5
    out = place_beat(music, rate, start=3.0, beat=8.0, at=2.0)
    assert np.flatnonzero(out[:, 0] == 0.5)[0] == 2000
