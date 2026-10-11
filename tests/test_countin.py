import numpy as np
import pytest

from playalong.countin import LEAD, clicks, with_count_in

RATE = 1000  # coarse, so positions are easy to reason about


def onsets(audio, threshold=1e-3, gap=0.05):
    """Starts of sounds separated by at least `gap` seconds of quiet (a click crosses zero inside itself)."""
    loud = np.flatnonzero(np.abs(audio[:, 0]) > threshold)
    return loud[np.concatenate([[True], np.diff(loud) > gap * RATE])]


def test_one_bar_is_four_even_clicks_with_the_first_accented():
    pattern = clicks(1)
    assert [beat for beat, _ in pattern] == [0, 1, 2, 3]
    assert [accent for _, accent in pattern] == [True, False, False, False]


def test_two_bars_count_one_two_then_one_two_three_four():
    assert [beat for beat, _ in clicks(2)] == [0, 2, 4, 5, 6, 7]


def test_the_music_enters_on_the_beat_after_the_last_click():
    bpm, start, beat = 120.0, 2.0, 2.3
    music = np.zeros((10 * RATE, 2), dtype=np.float32)
    music[int(beat * RATE)] = 0.5  # the downbeat
    out = with_count_in(music, RATE, start, beat, bpm, bars=1)

    period = 60.0 / bpm
    click_starts = onsets(out)[:4] / RATE
    assert click_starts == pytest.approx([LEAD + k * period for k in range(4)], abs=0.002)
    downbeat = int(np.flatnonzero(np.abs(out[:, 0] - 0.5) < 1e-6)[0])
    assert downbeat / RATE == pytest.approx(LEAD + 4 * period, abs=0.002)


def test_nothing_before_the_song_start_leaks_under_the_clicks():
    music = np.full((10 * RATE, 2), 0.2, dtype=np.float32)  # "intro" everywhere before start
    out = with_count_in(music, RATE, start=3.0, beat=3.1, bpm=120.0, bars=1)
    clicks_only = with_count_in(np.zeros_like(music), RATE, start=3.0, beat=3.1, bpm=120.0, bars=1)
    # The song start is 0.1 s before the downbeat; up to there only the clicks sound.
    song_start = int(round((LEAD + 4 * 0.5 - 0.1) * RATE))
    assert np.array_equal(out[:song_start], clicks_only[:song_start])
    assert out[song_start + 50, 0] == pytest.approx(0.2)


def test_a_long_pickup_is_cut_to_fit_the_count():
    # The beat is 5 s after the song start: the music before it would overlap the count, so it's cut.
    music = np.zeros((20 * RATE, 2), dtype=np.float32)
    music[int(8.0 * RATE)] = 0.5
    out = with_count_in(music, RATE, start=3.0, beat=8.0, bpm=120.0, bars=1)
    downbeat = int(np.flatnonzero(np.abs(out[:, 0] - 0.5) < 1e-6)[0])
    assert downbeat / RATE == pytest.approx(LEAD + 2.0, abs=0.002)


def test_count_timing_says_when_each_click_and_the_downbeat_land_in_the_mix():
    from playalong.countin import count_timing

    timing = count_timing(beat=10.0, bpm=120.0, bars=1, tempo=1.0)
    assert timing["source_offset"] == pytest.approx(10.0 - LEAD - 2.0)
    assert [c["count"] for c in timing["clicks"]] == [1, 2, 3, 4]
    assert [c["accent"] for c in timing["clicks"]] == [True, False, False, False]
    assert [c["time"] for c in timing["clicks"]] == pytest.approx([LEAD + k * 0.5 for k in range(4)])
    assert timing["downbeat"] == pytest.approx(LEAD + 2.0)


def test_two_bar_count_is_numbered_one_two_one_two_three_four_and_follows_the_tempo():
    from playalong.countin import count_timing

    timing = count_timing(beat=10.0, bpm=120.0, bars=2, tempo=0.8)
    assert [c["count"] for c in timing["clicks"]] == [1, 2, 1, 2, 3, 4]
    # A slowed-down mix stretches the count with the music: mix seconds are rendered seconds / tempo.
    assert timing["clicks"][1]["time"] == pytest.approx((LEAD + 2 * 0.5) / 0.8)
    assert timing["downbeat"] == pytest.approx((LEAD + 8 * 0.5) / 0.8)
    assert timing["source_offset"] == pytest.approx(10.0 - LEAD - 4.0)
