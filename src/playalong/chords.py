"""Chords per beat from the whole song, as a bar chart, a chord sheet page and a .lab file.

Chords are read from everything playing together, the way a listener hears them; the bass line (the low
register of the same mix) votes for the root. Nothing depends on how the song was split into stems.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from playalong.countin import BEATS_PER_BAR
from playalong.tempo import OnsetEnvelope

N_FFT = 16384  # 2.7 Hz bins: fine enough to tell semitones apart down to the bass register
HOP = 4096
HARMONY_RANGE = (48, 96)  # C3–C7
BASS_RANGE = (28, 60)  # E1–C4
BASS_WEIGHT = 0.75  # how much the bass stem counts towards a chord whose root it plays
BASS_OTHER_TONES = 0.5  # share of that when it plays the chord's third or fifth instead
SHARPNESS = 12.0  # turns chord-template similarity into log-likelihood for the Viterbi pass
STAY = 0.85  # probability a chord lasts another beat; one odd beat shouldn't flip it
# Template-similarity lead a single beat needs to become a one-beat chord. Against Chordify's chart of
# the reference song, 0.2 keeps its three "A♭ · D♭ A♭" bars without adding wrong ones.
QUICK_MARGIN = 0.2
QUIET_DB = -30.0  # beats this far below the song's loud parts are "no chord"
# In the second pass, chords that belong to the song's key get this much extra template similarity:
# enough to settle a missing third (a sus-like guitar voicing) towards the key, not to overrule a clear
# borrowed chord.
KEY_BONUS = 0.06
DRIFT_LIMIT = 0.25  # a bar anchor may move this share of a beat; more means the onsets are unreliable

SHARPS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
FLATS = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")
# Keys written with flats; the rest (and C / A minor) use sharps.
FLAT_KEYS = {"F major", "Bb major", "Eb major", "Ab major", "Db major", "Gb major",
             "D minor", "G minor", "C minor", "F minor", "Bb minor", "Eb minor"}
# Krumhansl–Kessler key profiles.
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


@dataclass
class Chord:
    start: float  # seconds in the track's audio
    end: float
    name: str  # "C", "Am", "F#", "Bb", or "N" for no chord


@dataclass
class ChordResult:
    key: str
    bpm: float
    first_beat: float  # where bar 1 starts
    chords: list[Chord]
    beats: list[float]  # every beat from the song start on; chords change only on these
    pickup: int = 0  # beats before bar 1


def _note_names(key: str) -> tuple[str, ...]:
    return FLATS if key in FLAT_KEYS else SHARPS


def chord_name(root: int | None, quality: str | None, key: str) -> str:
    if root is None:
        return "N"
    return _note_names(key)[root] + ("m" if quality == "min" else "")


def estimate_key(chroma: np.ndarray) -> str:
    """Best-correlating major or minor key for a 12-bin pitch-class profile."""
    best, best_r = "C major", -np.inf
    for tonic in range(12):
        for mode, profile in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
            r = np.corrcoef(chroma, np.roll(profile, tonic))[0, 1]
            if r > best_r:
                name = (FLATS if f"{FLATS[tonic]} {mode}" in FLAT_KEYS else SHARPS)[tonic]
                best, best_r = f"{name} {mode}", r
    return best


def _diatonic(tonic: int) -> set[tuple[int, str]]:
    """The major and minor triads of a major key (and of its relative minor)."""
    return {((tonic + step) % 12, quality) for step, quality in
            ((0, "maj"), (2, "min"), (4, "min"), (5, "maj"), (7, "maj"), (9, "min"))}


def _key_from_chords(beats_per_chord: dict[tuple[int, str], int]) -> tuple[str, set[tuple[int, str]]] | None:
    """The key whose triads cover the most beats; minor when its tonic chord outlasts the major one's.

    Counting chords rather than pitch-class energy keeps a guitar voicing's added notes (a ninth, a
    major seventh) from pulling the key sideways.
    """
    if not beats_per_chord:
        return None
    tonic = max(range(12), key=lambda t: sum(beats_per_chord.get(c, 0) for c in _diatonic(t)))
    relative = (tonic + 9) % 12
    if beats_per_chord.get((relative, "min"), 0) > beats_per_chord.get((tonic, "maj"), 0):
        name = (FLATS if f"{FLATS[relative]} minor" in FLAT_KEYS else SHARPS)[relative]
        return f"{name} minor", _diatonic(tonic)
    name = (FLATS if f"{FLATS[tonic]} major" in FLAT_KEYS else SHARPS)[tonic]
    return f"{name} major", _diatonic(tonic)


def _mono(stems: dict[str, np.ndarray], names) -> np.ndarray:
    present = [stems[n] for n in names if n in stems]
    length = max(len(s) for s in stems.values())
    out = np.zeros(length, dtype=np.float32)
    for s in present:
        out[: len(s)] += s.mean(axis=1)
    return out


def _spectrogram(signal: np.ndarray) -> np.ndarray:
    """Magnitude frames (time × bin), centred like the onset envelope."""
    padded = np.pad(signal, N_FFT // 2)
    frames = max(1, (len(padded) - N_FFT) // HOP + 1)
    view = np.lib.stride_tricks.sliding_window_view(padded, N_FFT)[::HOP][:frames]
    window = np.hanning(N_FFT).astype(np.float32)
    return np.concatenate([np.abs(np.fft.rfft(view[i : i + 256] * window, axis=1)).astype(np.float32)
                           for i in range(0, len(view), 256)])


def _bin_pitches(rate: int) -> np.ndarray:
    freqs = np.arange(N_FFT // 2 + 1) * rate / N_FFT
    # The DC bin has no pitch; any value far outside every range keeps it out.
    freqs[0] = 1e-3
    return 69 + 12 * np.log2(freqs / 440.0)


def _tuning(spec: np.ndarray, pitches: np.ndarray) -> float:
    """How far (in semitones, within ±0.5) the recording sits from A440, from its strongest partials."""
    lo, hi = HARMONY_RANGE
    band = (pitches >= lo) & (pitches <= hi)
    mags = spec[:, band].sum(axis=0)
    strong = mags > np.percentile(mags, 99)
    deviation = pitches[band][strong] - np.round(pitches[band][strong])
    angle = np.angle(np.sum(mags[strong] * np.exp(2j * np.pi * deviation)))
    return float(angle / (2 * np.pi))


def _chroma(spec: np.ndarray, pitches: np.ndarray, pitch_range: tuple[int, int]) -> np.ndarray:
    """Frames × 12 pitch-class energy, counting only bins close to a semitone centre."""
    lo, hi = pitch_range
    nearest = np.round(pitches)
    keep = (pitches >= lo) & (pitches <= hi) & (np.abs(pitches - nearest) < 0.4)
    classes = (nearest[keep].astype(int)) % 12
    chroma = np.zeros((len(spec), 12), dtype=np.float32)
    for pc in range(12):
        chroma[:, pc] = spec[:, keep][:, classes == pc].sum(axis=1)
    return chroma


def beat_grid(envelope: OnsetEnvelope, bpm: float, first: float, end: float) -> np.ndarray:
    """Beats from `first` to `end`, re-anchored to the onsets at each bar so tempo drift doesn't
    smear chords across beats."""
    period = 60.0 / bpm
    beats, anchor = [], first
    while anchor < end:
        beats.extend(anchor + k * period for k in range(BEATS_PER_BAR))
        expected = anchor + BEATS_PER_BAR * period
        found = envelope.beat_near(bpm, expected)
        anchor = found if abs(found - expected) <= DRIFT_LIMIT * period else expected
    beats.append(anchor)
    return np.array([b for b in beats if b <= end] + ([end] if beats[-1] > end else []))


def _templates() -> tuple[np.ndarray, list[tuple[int, str]]]:
    rows, labels = [], []
    for quality, third in (("maj", 4), ("min", 3)):
        for root in range(12):
            t = np.zeros(12)
            t[[root, (root + third) % 12, (root + 7) % 12]] = 1
            rows.append(t / np.linalg.norm(t))
            labels.append((root, quality))
    return np.array(rows), labels


def _viterbi(log_likelihood: np.ndarray, stay: np.ndarray | None = None) -> np.ndarray:
    """Most likely state per beat, with a sticky transition so chords don't flicker. `stay` gives each
    beat's probability of keeping the previous beat's chord (STAY everywhere when not given)."""
    beats, states = log_likelihood.shape
    if stay is None:
        stay = np.full(beats, STAY)
    score = log_likelihood[0].copy()
    back = np.zeros((beats, states), dtype=int)
    for t in range(1, beats):
        with np.errstate(divide="ignore"):
            trans = np.full((states, states), np.log((1 - stay[t]) / (states - 1)))
        np.fill_diagonal(trans, np.log(stay[t]))
        total = score[:, None] + trans
        back[t] = total.argmax(axis=0)
        score = total.max(axis=0) + log_likelihood[t]
    path = np.zeros(beats, dtype=int)
    path[-1] = score.argmax()
    for t in range(beats - 1, 0, -1):
        path[t - 1] = back[t, path[t]]
    return path


def _quick_chords(path: np.ndarray, likelihood: np.ndarray, margin: float) -> np.ndarray:
    """A single beat inside a held chord that clearly sounds like another chord becomes that chord for
    the beat, as in "A♭ · D♭ A♭". The steady decode can't keep these: a one-beat chord pays for two
    changes, and most single odd beats are passing notes, so only a clear winner counts."""
    path = path.copy()
    for t in range(1, len(path) - 1):
        if path[t - 1] == path[t] == path[t + 1]:
            best = int(np.argmax(likelihood[t]))
            if best != path[t] and likelihood[t, best] - likelihood[t, path[t]] >= margin:
                path[t] = best
    return path


def detect_chords(
    stems: dict[str, np.ndarray], rate: int, start: float, bpm: float | None = None, beat: float | None = None
) -> ChordResult:
    """Chords from the song start to the end. `bpm` and `beat` (the beat at the start) are detected
    when not given."""
    envelope = OnsetEnvelope.from_stems(stems, rate)
    if bpm is None:
        tempo = envelope.tempo()
        if tempo is None:
            raise ValueError("couldn't find the song's tempo; pass it with --bpm")
        bpm = tempo.bpm
    if beat is None:
        beat = envelope.beat_near(bpm, start)

    mix = _mono(stems, stems.keys())
    pitches = _bin_pitches(rate)
    spec = _spectrogram(mix)
    pitches = pitches - _tuning(spec, pitches)
    chroma = _chroma(spec, pitches, HARMONY_RANGE)
    bass_chroma = _chroma(spec, pitches, BASS_RANGE)

    duration = len(mix) / rate
    beats = beat_grid(envelope, bpm, beat, duration)
    frame_times = np.arange(len(chroma)) * HOP / rate
    half_window = N_FFT / 2 / rate

    templates, labels = _templates()
    per_beat, bass_per_beat, energy = [], [], []
    for a, b in zip(beats[:-1], beats[1:]):
        # Only frames whose whole window lies inside the beat: a frame straddling the next beat already
        # hears the next chord and pulls changes a beat early. Fast tempi fall back to the middle frame.
        inside = (frame_times - half_window >= a) & (frame_times + half_window <= b)
        if not inside.any():
            middle = np.abs(frame_times - (a + b) / 2)
            inside = middle == middle.min()
        c = chroma[inside].sum(axis=0)
        per_beat.append(np.log1p(c / (c.max() + 1e-9) * 10))
        bc = bass_chroma[inside].sum(axis=0)
        bass_per_beat.append(bc / (bc.max() + 1e-9))
        energy.append(c.sum())
    per_beat, bass_per_beat, energy = np.array(per_beat), np.array(bass_per_beat), np.array(energy)

    norm = per_beat / (np.linalg.norm(per_beat, axis=1, keepdims=True) + 1e-9)
    scores = norm @ templates.T
    # The bass mostly plays the root, but inversions and walking lines sit on the third or fifth: those
    # count too, for less, so a chord over its fifth (D♭/A♭) isn't read as the fifth's own chord.
    roots = np.array([root for root, _ in labels])
    thirds = np.array([(root + (3 if quality == "min" else 4)) % 12 for root, quality in labels])
    fifths = (roots + 7) % 12
    other_tones = np.maximum(bass_per_beat[:, thirds], bass_per_beat[:, fifths])
    scores = scores + BASS_WEIGHT * (bass_per_beat[:, roots] + BASS_OTHER_TONES * other_tones)
    # "No chord" wins on beats far quieter than the song's loud parts.
    rel_db = 10 * np.log10(energy / (np.percentile(energy, 95) + 1e-12) + 1e-12)
    quiet = np.clip((QUIET_DB + 10 - rel_db) / 10, 0, 1)
    no_chord = 0.5 + (1.5 + BASS_WEIGHT) * quiet
    likelihood = SHARPNESS * np.column_stack([scores, no_chord])
    path = _viterbi(likelihood)

    # Second pass: find the key from the chords, then let it settle close calls.
    counts: dict[tuple[int, str], int] = {}
    for state in path:
        if state < len(labels):
            counts[labels[state]] = counts.get(labels[state], 0) + 1
    found_key = _key_from_chords(counts)
    if found_key is not None:
        key, diatonic = found_key
        in_key = np.array([label in diatonic for label in labels], dtype=float)
        likelihood = SHARPNESS * np.column_stack([scores + KEY_BONUS * in_key, no_chord])
        path = _viterbi(likelihood)

    # Beat tracking finds beats, not which one is the "one". Chords mostly change on the downbeat, so
    # bar 1 starts at the beat phase that puts the most changes on bar lines; beats before it are a pickup.
    changes = np.flatnonzero(path[1:] != path[:-1]) + 1
    pickup = int(np.argmax([np.sum(changes % BEATS_PER_BAR == p) for p in range(BEATS_PER_BAR)]))
    # Songs change chords on the bar or the half bar. With the bar lines known, decode once more allowing
    # changes only there, then let through the quick one-beat chords that decode can't keep.
    position = (np.arange(len(path)) - pickup) % BEATS_PER_BAR
    path = _viterbi(likelihood, np.where(position % (BEATS_PER_BAR // 2) == 0, STAY, 1.0))
    path = _quick_chords(path, likelihood / SHARPNESS, QUICK_MARGIN)

    if found_key is None:
        key = estimate_key((per_beat * (1 - quiet)[:, None]).sum(axis=0))
    names = [chord_name(*labels[s], key) if s < len(labels) else "N" for s in path]
    chords: list[Chord] = []
    for name, a, b in zip(names, beats[:-1], beats[1:]):
        if chords and chords[-1].name == name:
            chords[-1].end = float(b)
        else:
            chords.append(Chord(float(a), float(b), name))
    return ChordResult(key=key, bpm=bpm, first_beat=float(beats[min(pickup, len(beats) - 1)]), chords=chords,
                       beats=[float(b) for b in beats], pickup=pickup)


def _clock(seconds: float) -> str:
    whole = round(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def format_chart(result: ChordResult, bars_per_line: int = 4) -> str:
    """Bar chart from the song start: each cell names the chord at the bar's first beat and any
    change inside the bar ("Am  G"); "N" is no chord."""
    def chord_at(t: float) -> str:
        return next((c.name for c in result.chords if c.start <= t + 1e-6 < c.end), "N")

    def cell(beats: list[float]) -> str:
        names: list[str] = []
        for t in beats:
            if not names or chord_at(t) != names[-1]:
                names.append(chord_at(t))
        return "  ".join(names)

    grid = result.beats[:-1]
    bar_starts = list(range(result.pickup, len(grid), BEATS_PER_BAR))
    cells = [cell(grid[i : i + BEATS_PER_BAR]) for i in bar_starts]
    lines = [f"Key: {result.key}   Tempo: {result.bpm:.1f} BPM   (N = no chord; times from the song start)", ""]
    if result.pickup:
        lines.append(f"    pickup: {cell(grid[: result.pickup])}")
    for i in range(0, len(cells), bars_per_line):
        row = "|".join(f" {c:<10}" for c in cells[i : i + bars_per_line])
        lines.append(f"{i + 1:>3} |{row}|   {_clock(grid[bar_starts[i]] - grid[0])}")
    return "\n".join(lines) + "\n"


def format_lab(result: ChordResult) -> str:
    """start, end and chord per line, in seconds of the track's audio (the common .lab format)."""
    return "".join(f"{c.start:.3f}\t{c.end:.3f}\t{c.name.replace('m', ':min') if c.name != 'N' else 'N'}\n"
                   for c in result.chords)


def track_chords(track_dir: Path, start: float | None = None, bpm: float | None = None) -> ChordResult:
    """Detect a track's chords and write chords.txt, chords.lab and chords.html next to its stems."""
    from playalong.intro import song_start
    from playalong.mix import load_stems
    from playalong.tempo import song_tempo

    stems, rate = load_stems(track_dir / "stems")
    if start is None:
        start = song_start(track_dir, stems, rate)
    found = song_tempo(track_dir, stems, rate, start, bpm)
    if found is None:
        raise ValueError("couldn't find the song's tempo; pass it with --bpm")
    result = detect_chords(stems, rate, start, *found)
    (track_dir / "chords.txt").write_text(format_chart(result))
    (track_dir / "chords.lab").write_text(format_lab(result))

    import json

    from playalong.chord_page import render_page

    info_path = track_dir / "info.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else {}
    page = render_page(result, info.get("title") or track_dir.name, info.get("uploader") or "")
    (track_dir / "chords.html").write_text(page)
    return result
