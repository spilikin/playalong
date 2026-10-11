"""A drummer's stick count before the song, at the song's own tempo."""

import numpy as np

from playalong.mix import place_beat

BEATS_PER_BAR = 4
LEAD = 0.25  # seconds of silence before the first click, so players don't miss it
LEVEL = 0.6  # click peak; loud enough over a quiet pickup, below the mix's -1 dBFS ceiling
CLICK_SECONDS = 0.03


def clicks(bars: int) -> list[tuple[int, bool]]:
    """(beat, accented) for each click. Two bars count the way a drummer does: "ONE . TWO . one two three four"."""
    if bars == 1:
        return [(0, True), (1, False), (2, False), (3, False)]
    if bars == 2:
        return [(0, True), (2, True), (4, True), (5, False), (6, False), (7, False)]
    raise ValueError(f"count-in is 1 or 2 bars, got {bars}")


def count_timing(beat: float, bpm: float, bars: int, tempo: float = 1.0) -> dict:
    """Where a count-in puts things, for a player showing it: the song time at the start of the mix,
    and each click and the downbeat in seconds of the finished (possibly time-stretched) mix."""
    period = 60.0 / bpm
    counts = []
    for b, accent in clicks(bars):
        # Two bars count the first bar in halves: ONE . TWO . | one two three four.
        number = b // 2 + 1 if bars == 2 and b < BEATS_PER_BAR else b % BEATS_PER_BAR + 1
        counts.append({"time": (LEAD + b * period) / tempo, "accent": accent, "count": number})
    return {
        "source_offset": beat - LEAD - BEATS_PER_BAR * bars * period,
        "bars": bars,
        "clicks": counts,
        "downbeat": (LEAD + BEATS_PER_BAR * bars * period) / tempo,
    }


def stick(rate: int, accent: bool) -> np.ndarray:
    """Two sticks struck together: a noise crack for the attack and a short woody ring for the body.

    The accent rings higher and brighter, so the "one" stands out besides being louder.
    """
    n = max(1, int(CLICK_SECONDS * rate))
    t = np.arange(n) / rate
    noise = np.random.default_rng(0x9E3779B9).uniform(-1, 1, n)
    # One-pole high-pass: a crack rather than a hiss.
    keep = 0.8 if accent else 0.65
    crack = np.zeros(n)
    for i in range(1, n):
        crack[i] = keep * (crack[i - 1] + noise[i] - noise[i - 1])
    crack *= np.exp(-t / 0.004)
    body = np.sin(2 * np.pi * (2400.0 if accent else 1800.0) * t) * np.exp(-t / 0.012)
    out = 0.6 * crack + body
    out *= (1.0 if accent else 0.7) * LEVEL / np.abs(out).max()
    return out.astype(np.float32)


def with_count_in(mix: np.ndarray, rate: int, start: float, beat: float, bpm: float, bars: int) -> np.ndarray:
    """The mix from `start` on, preceded by a count that ends one beat before `beat`, so the music
    enters on the beat after the last click. Music before `beat` that would sound under the count
    (a long pickup) is cut; anything before `start` (the video intro) never plays.
    """
    period = 60.0 / bpm
    out = place_beat(mix, rate, start, beat, LEAD + BEATS_PER_BAR * bars * period)
    sounds = {accent: stick(rate, accent) for accent in (True, False)}
    for b, accent in clicks(bars):
        at = int(round((LEAD + b * period) * rate))
        click = sounds[accent][: max(0, len(out) - at)]
        out[at : at + len(click)] += click[:, None]
    return out
