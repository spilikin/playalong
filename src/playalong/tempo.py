"""Tempo and beat positions from a spectral-flux onset envelope.

The same method and constants as the desktop app's `audio::tempo` (branch `experimental`), so both
agree on a track's tempo and share it through info.json.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

N_FFT = 2048
HOP = 512
MIN_BPM = 60.0
MAX_BPM = 200.0
# Below this RMS the drums stem is treated as absent (acoustic songs) and bass + guitar are used.
SILENT_RMS = 1e-3
# Tempo prior: log-normal around 120 BPM, 1.5 octaves wide, to settle ties between related tempi.
PRIOR_CENTER = 120.0
PRIOR_OCTAVES = 1.5
# A related period (half or double) counts as a candidate when its autocorrelation is at least this strong.
OCTAVE_SUPPORT = 0.8
# The faster of two candidate tempi wins only when the onsets between the slower one's beats carry at
# least this share of the beats' energy (-3 dB). Hi-hats between kick and snare fall well below it.
ACCENT_RATIO = 0.5
# Accents are compared window by window, each with its own beat phase, so tempo drift doesn't smear them.
ACCENT_WINDOW_SECONDS = 8.0
PHASE_WINDOW_SECONDS = 4.0
BLOCK = 2048  # frames per FFT batch, so a long song doesn't hold its whole spectrogram


def _round(x: float) -> int:
    """Halves away from zero, like Rust: halving an odd lag lands exactly on .5, and Python's
    round-half-to-even would pick a different neighbour than the app does."""
    return math.floor(x + 0.5)


@dataclass
class Tempo:
    bpm: float
    confidence: float


class OnsetEnvelope:
    def __init__(self, signal: np.ndarray, rate: int):
        signal = np.asarray(signal, dtype=np.float32)
        self.fps = rate / HOP
        # A Hann-windowed frame registers an onset's biggest flux jump as it crosses the steepest part
        # of the window's rising half, a quarter window before the frame centre, so beats read early.
        self.lead = (N_FFT / 4) / rate
        if not len(signal):
            self.values = self.energy = np.zeros(0, dtype=np.float32)
            return

        frames = len(signal) // HOP + 1
        padded = np.pad(signal, N_FFT // 2)
        view = np.lib.stride_tricks.sliding_window_view(padded, N_FFT)[::HOP][:frames]
        window = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)

        # Half-wave-rectified log-spectral flux of centred frames.
        flux = np.zeros(frames, dtype=np.float32)
        prev = None
        for i in range(0, frames, BLOCK):
            mag = np.log1p(100 * np.abs(np.fft.rfft(view[i : i + BLOCK] * window, axis=1))).astype(np.float32)
            rows = mag if prev is None else np.vstack([prev, mag])
            diff = np.maximum(rows[1:] - rows[:-1], 0).sum(axis=1)
            flux[i + (prev is None) : i + len(mag)] = diff
            prev = mag[-1:]

        # Subtract a ±0.25 s moving average so a crescendo doesn't read as a stream of onsets.
        half = _round(0.25 * self.fps)
        idx = np.arange(frames)
        lo, hi = np.maximum(idx - half, 0), np.minimum(idx + half + 1, frames)
        prefix = np.concatenate([[0.0], np.cumsum(flux, dtype=np.float64)])
        values = np.maximum(flux - (prefix[hi] - prefix[lo]) / (hi - lo), 0).astype(np.float32)
        peak = values.max()
        self.values = values / peak if peak > 0 else values

        # Mean-square level around each frame centre, for comparing accents.
        squares = np.concatenate([[0.0], np.cumsum(signal.astype(np.float64) ** 2)])
        centre = idx * HOP
        lo, hi = np.maximum(centre - HOP // 2, 0), np.minimum(centre + HOP // 2, len(signal))
        self.energy = ((squares[hi] - squares[lo]) / np.maximum(hi - lo, 1)).astype(np.float32)

    @classmethod
    def from_stems(cls, stems: dict[str, np.ndarray], rate: int) -> "OnsetEnvelope":
        def mono(names):
            present = [stems[n] for n in names if n in stems]
            if not present:
                return np.zeros(0, dtype=np.float32)
            length = min(len(s) for s in present)
            return sum(s[:length].mean(axis=1) for s in present).astype(np.float32)

        drums = mono(["drums"])
        rms = float(np.sqrt(np.mean(drums.astype(np.float64) ** 2))) if len(drums) else 0.0
        return cls(drums if rms > SILENT_RMS else mono(["bass", "guitar"]), rate)

    def at(self, frames) -> np.ndarray:
        """The envelope at fractional frame positions, 0 outside it."""
        f = np.asarray(frames, dtype=np.float64)
        i = np.floor(f)
        inside = (i >= 0) & (i + 1 < len(self.values))
        j = np.where(inside, i, 0).astype(int)
        frac = (f - i).astype(np.float32)
        v = self.values[j] * (1 - frac) + self.values[np.minimum(j + 1, max(len(self.values) - 1, 0))] * frac
        return np.where(inside, v, 0.0)

    def _grid_scores(self, start: float, end: float, period: float, phases: np.ndarray):
        """Envelope summed over a beat grid for each phase, plus the grid positions and which are in range."""
        beats = np.arange(math.ceil((end - start) / period) + 1)
        grid = start + phases[:, None] + beats[None, :] * period
        inside = grid < end
        return (self.at(grid) * inside).sum(axis=1), grid, inside

    def _offbeat_ratio(self, period: float) -> float:
        """Energy of the onsets halfway between beats of the given period, relative to the beats themselves."""
        n = len(self.values)
        window = max(int(ACCENT_WINDOW_SECONDS * self.fps), 1)
        padded = np.pad(self.energy, 2)
        loudest = np.lib.stride_tricks.sliding_window_view(padded, 5).max(axis=1)

        def accent(frames):
            c = np.floor(np.asarray(frames) + 0.5).astype(int)
            return np.where(c < len(loudest), loudest[np.minimum(c, len(loudest) - 1)], 0.0).sum()

        on = off = 0.0
        phases = np.arange(math.ceil(period * 4)) / 4
        for start in range(0, n, window):
            end = min(start + window, n)
            scores, grid, inside = self._grid_scores(start, end, period, phases)
            best = int(np.argmax(scores))
            beats = grid[best][inside[best]]
            on += accent(beats)
            off += accent(beats + period / 2)
        return off / on if on > 0 else 0.0

    def _autocorrelation(self, lag: int) -> float:
        n = len(self.values)
        if lag >= n:
            return 0.0
        return float(np.dot(self.values[: n - lag], self.values[lag:]) / (n - lag))

    def tempo(self) -> Tempo | None:
        min_lag = math.floor(60 * self.fps / MAX_BPM)
        max_lag = math.ceil(60 * self.fps / MIN_BPM)
        if len(self.values) < 2 * max_lag + 2:
            return None
        r0 = self._autocorrelation(0)
        if r0 <= 0:
            return None
        r = np.array([self._autocorrelation(lag) for lag in range(max_lag + 2)])
        lags = np.arange(min_lag, max_lag + 1)
        prior = np.exp(-0.5 * (np.log2(60 * self.fps / lags / PRIOR_CENTER) / PRIOR_OCTAVES) ** 2)
        best = int(lags[np.argmax(r[lags] * prior)])

        # Autocorrelation can't tell a beat from its subdivision or its bar: onsets repeat at all of them.
        # Take the slowest related period it supports, then speed up only while the onsets in between
        # are as strong as the beats (equal hits), not weaker (hi-hats between kick and snare).
        # A period between two integer lags splits its correlation across both, so compare neighbourhoods.
        def near(lag: float) -> float:
            n = _round(lag)
            return 0.0 if n <= min_lag - 1 or n > max_lag else float(r[n - 1] + r[n] + r[n + 1])

        period = float(best)
        while period * 2 <= max_lag and near(period * 2) >= OCTAVE_SUPPORT * near(period):
            period *= 2
        while (
            period / 2 >= min_lag
            and near(period / 2) >= OCTAVE_SUPPORT * near(period)
            and self._offbeat_ratio(period) >= ACCENT_RATIO
        ):
            period /= 2
        best = _round(period)
        # Parabolic interpolation around the peak for sub-frame period resolution.
        a, b, c = r[best - 1], r[best], r[best + 1]
        denom = a - 2 * b + c
        offset = float(np.clip(0.5 * (a - c) / denom, -0.5, 0.5)) if abs(denom) > 1e-12 else 0.0
        # Periodicity above the level a constant envelope would give, so loud songs aren't more "confident".
        mean = float(self.values.mean())
        confidence = float(np.clip((b - mean * mean) / (r0 - mean * mean), 0, 1))
        return Tempo(bpm=60 * self.fps / (best + offset), confidence=confidence)

    def beat_near(self, bpm: float, seconds: float) -> float:
        """The beat closest to `seconds`, fitting a grid of the given tempo to the onsets just after it.

        Local rather than global, so songs that drift in tempo still get clicks on their beats.
        """
        period = 60 * self.fps / bpm
        start = seconds * self.fps
        end = min(start + PHASE_WINDOW_SECONDS * self.fps, len(self.values))
        if not period > 0 or end <= start:
            return seconds
        phases = np.arange(math.ceil(period * 10)) / 10
        scores, _, _ = self._grid_scores(start, end, period, phases)
        phase = float(phases[int(np.argmax(scores))])
        # The score is piecewise linear between envelope frames, so its maximum sits on a frame;
        # a parabola through the neighbouring frames recovers where between them the onset lies.
        a, b, c = self._grid_scores(start, end, period, np.array([phase - 1, phase, phase + 1]))[0]
        denom = a - 2 * b + c
        if abs(denom) > 1e-12:
            phase += float(np.clip(0.5 * (a - c) / denom, -0.5, 0.5))
        beat = start + phase - period if phase > period / 2 and start + phase - period >= 0 else start + phase
        return beat / self.fps + self.lead


def song_tempo(
    track_dir: Path, stems: dict[str, np.ndarray], rate: int, start: float, bpm: float | None = None
) -> tuple[float, float] | None:
    """The track's tempo and the beat nearest `start`, or None when no tempo can be found.

    A given `bpm` is saved as the user's and wins over detection from then on, here and in the app.
    """
    info_path = track_dir / "info.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else {}
    envelope = OnsetEnvelope.from_stems(stems, rate)

    if bpm is not None:
        info.update(bpm=bpm, bpm_source="user")
    elif info.get("bpm") is None:
        tempo = envelope.tempo()
        if tempo is None:
            return None
        info.update(bpm=round(tempo.bpm, 1), bpm_confidence=round(tempo.confidence, 3), bpm_source="detected")

    beat = envelope.beat_near(info["bpm"], start)
    # The app anchors its count-in grid on the beat at the detected song start, not on a one-off --start.
    if start == info.get("song_start", 0.0):
        info["beat_offset"] = beat
    info_path.write_text(json.dumps(info, indent=2, ensure_ascii=False))
    return info["bpm"], beat
