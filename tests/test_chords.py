import numpy as np
import pytest

from playalong.chords import chord_name, detect_chords, estimate_key, format_chart
from test_tempo import RATE, hits

NOTE = {"C": 0, "C#": 1, "Db": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "Ab": 8, "A": 9,
        "Bb": 10, "B": 11}


def tone(midi, seconds, level=0.1, detune=0.0):
    t = np.arange(int(seconds * RATE)) / RATE
    f = 440.0 * 2 ** ((midi - 69 + detune) / 12)
    wave = sum(level / k * np.sin(2 * np.pi * f * k * t) for k in (1, 2, 3))
    return (wave * np.exp(-t / 1.5)).astype(np.float32)


def song(progression, bpm=120.0, detune=0.0, lead=0.5):
    """Stems for a 4/4 song: one chord per bar (triad on the piano, root on the bass), drums on each beat."""
    bar = 4 * 60.0 / bpm
    length = int((lead + bar * len(progression) + 1) * RATE)
    piano, bass = np.zeros(length, np.float32), np.zeros(length, np.float32)
    for i, name in enumerate(progression):
        minor = name.endswith("m")
        root = NOTE[name.rstrip("m")]
        start = int((lead + i * bar) * RATE)
        for step in (0, 3 if minor else 4, 7):
            note = tone(60 + root + step, bar, detune=detune)
            piano[start : start + len(note)] += note
        low = tone(36 + root, bar, level=0.2, detune=detune)
        bass[start : start + len(low)] += low
    drums = hits(bpm, seconds=length / RATE, offset=lead)
    stereo = lambda x: np.stack([x, x], axis=1)  # noqa: E731
    silent = np.zeros((length, 2), np.float32)
    return {"piano": stereo(piano), "bass": stereo(bass), "drums": stereo(drums),
            "guitar": silent, "other": silent, "vocals": silent}


def bar_chords(result, bars):
    """The chord sounding at the middle of each bar."""
    out = []
    for i in range(bars):
        t = result.first_beat + (i + 0.5) * 4 * 60 / result.bpm
        out.append(next(c.name for c in result.chords if c.start <= t < c.end))
    return out


def test_finds_a_major_minor_progression_and_its_key():
    progression = ["C", "G", "Am", "F"] * 2
    result = detect_chords(song(progression), RATE, start=0.5)
    assert bar_chords(result, 8) == progression
    assert result.key == "C major"


def test_detuned_recordings_still_read_right():
    progression = ["Dm", "Bb", "F", "C"] * 2
    result = detect_chords(song(progression, bpm=96.0, detune=0.4), RATE, start=0.5)
    assert bar_chords(result, 8) == progression
    assert result.key in ("F major", "D minor")


def test_silence_is_no_chord():
    stems = song(["C", "G"])
    for s in stems.values():
        s[: int(0.5 * RATE)] = 0
    quiet = {name: np.concatenate([np.zeros((RATE * 4, 2), np.float32), a]) for name, a in stems.items()}
    result = detect_chords(quiet, RATE, start=0.0, bpm=120.0)
    assert result.chords[0].name == "N"


@pytest.mark.parametrize("root,quality,key,expected", [
    (10, "maj", "F major", "Bb"),
    (10, "maj", "B major", "A#"),
    (3, "min", "C minor", "Ebm"),
    (6, "maj", "F# major", "F#"),
    (None, None, "C major", "N"),
])
def test_names_follow_the_key(root, quality, key, expected):
    assert chord_name(root, quality, key) == expected


def test_key_from_a_chroma_profile():
    c_major = np.zeros(12)
    for pc, w in ((0, 3), (4, 2), (7, 2.5), (2, 1), (5, 1.5), (9, 1.2), (11, 0.8)):
        c_major[pc] = w
    assert estimate_key(c_major) == "C major"
    a_minor = np.roll(np.zeros(12), 0)
    for pc, w in ((9, 3), (0, 2), (4, 2.5), (11, 1), (2, 1.5), (5, 1.2), (7, 0.8)):
        a_minor[pc] = w
    assert estimate_key(a_minor) == "A minor"


def test_chart_puts_four_bars_on_a_line_and_marks_changes_inside_a_bar():
    progression = ["C", "G", "Am", "F", "C"]
    result = detect_chords(song(progression), RATE, start=0.5)
    chart = format_chart(result)
    lines = [l for l in chart.splitlines() if l.lstrip().startswith(("1 ", "5 "))]
    assert lines[0].split("|")[1:5] == [f" {c:<10}" for c in ["C", "G", "Am", "F"]]
    assert lines[1].split("|")[1].strip() == "C"


def test_bars_start_where_the_chords_change_even_after_a_pickup():
    # Two beats of pickup (on F) before bar 1: the chords change on every bar line after it.
    pickup_then = ["F"] + ["C", "G", "Am", "F"] * 2
    stems = song(pickup_then, lead=0.5)
    # Start the song half a bar into that pickup bar, so the first detected beat is beat 3 of it.
    result = detect_chords(stems, RATE, start=1.5, bpm=120.0, beat=1.5)
    assert result.pickup == 2
    chart = format_chart(result)
    assert "pickup: F" in chart
    first = next(l for l in chart.splitlines() if l.lstrip().startswith("1 "))
    assert first.split("|")[1:5] == [f" {c:<10}" for c in ["C", "G", "Am", "F"]]


def test_clock_never_shows_sixty_seconds():
    from playalong.chords import _clock

    assert _clock(59.97) == "1:00"
    assert _clock(125.2) == "2:05"


def test_a_clear_one_beat_chord_inside_a_held_one_is_kept():
    from playalong.chords import _quick_chords

    path = np.array([0, 0, 0, 0, 0, 0])
    likelihood = np.zeros((6, 3))
    likelihood[:, 0] = 1.0
    likelihood[2, 1] = 1.3  # clearly another chord on one beat
    likelihood[4, 2] = 1.05  # a passing note, not a chord change
    assert list(_quick_chords(path, likelihood, 0.2)) == [0, 0, 1, 0, 0, 0]
    # Only inside a held chord: next to a change it's left to the main decode.
    assert list(_quick_chords(np.array([0, 2, 2, 2]), np.eye(3)[[0, 1, 2, 2]] * 2, 0.2)) == [0, 2, 2, 2]


def test_a_quick_change_on_beat_three_shows_up():
    progression = ["Ab", "Ab", "Gb"]
    stems = song(progression)
    # Turn beat 3 of bar 2 into Db: piano triad and bass for one beat.
    bar, beat = 4 * 60.0 / 120.0, 60.0 / 120.0
    at = int((0.5 + bar + 2 * beat) * RATE)
    n = int(beat * RATE)
    for stem in ("piano", "bass"):
        stems[stem][at : at + n] = 0
    for step in (0, 4, 7):
        stems["piano"][at : at + n] += tone(61 + step, beat)[:n, None]
    stems["bass"][at : at + n] += tone(37, beat, level=0.2)[:n, None]
    result = detect_chords(stems, RATE, start=0.5)
    names = [c.name for c in result.chords if c.name != "N"]
    assert names == ["Ab", "Db", "Ab", "Gb"]
