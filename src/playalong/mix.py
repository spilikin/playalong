import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from playalong.intro import song_start

OFF = None

# Gains in dB relative to the separated stem; OFF drops the stem entirely.
# Stems not listed in a preset are kept at 0 dB.
# The first four are the ones a player numbers and `run` renders; the rest are on request.
ORIGINAL = "original"
PRESETS: dict[str, dict[str, float | None]] = {
    ORIGINAL: {},
    "guide": {"guitar": -15.0},
    "no-guitar": {"guitar": OFF},
    "vocals-only": {"drums": OFF, "bass": OFF, "other": OFF, "guitar": OFF, "piano": OFF},
    "backing": {"guitar": OFF, "vocals": OFF},
    "rhythm-section": {"guitar": OFF, "vocals": OFF, "other": OFF, "piano": OFF},
    "drums-only": {"guitar": OFF, "vocals": OFF, "other": OFF, "piano": OFF, "bass": OFF},
    "guitar-only": {"drums": OFF, "bass": OFF, "other": OFF, "vocals": OFF, "piano": OFF},
}
MAIN_PRESETS = list(PRESETS)[:4]

PRESET_HELP = {
    ORIGINAL: "the recording itself, with the same intro cut and count-in as the others",
    "guide": "full song with guitar ducked 15 dB: play along with a faint reference",
    "no-guitar": "full song minus guitar: take over the guitar part",
    "vocals-only": "isolated vocals: learn the melody and lyrics, or sing along",
    "backing": "no guitar, no vocals: room for soloing / leads",
    "rhythm-section": "drums + bass only: jam or practise timing",
    "drums-only": "just drums: a musical metronome",
    "guitar-only": "isolated guitar: study the part",
}

PEAK_CEILING = 10 ** (-1.0 / 20)  # -1 dBFS
FADE_IN = 0.03  # seconds; cutting mid-waveform would otherwise click


def parse_gain(spec: str) -> tuple[str, float | None]:
    """Parse 'stem=-6' or 'stem=off'."""
    stem, _, value = spec.partition("=")
    if not stem or not value:
        raise ValueError(f"expected STEM=DB or STEM=off, got {spec!r}")
    return stem.strip(), OFF if value.strip().lower() == "off" else float(value)


def load_stems(stems_dir: Path) -> tuple[dict[str, np.ndarray], int]:
    stems, rate = {}, None
    for path in sorted(stems_dir.glob("*.wav")):
        data, sr = sf.read(path, dtype="float32", always_2d=True)
        if rate is not None and sr != rate:
            raise ValueError(f"{path.name} has sample rate {sr}, expected {rate}")
        stems[path.stem], rate = data, sr
    if not stems:
        raise FileNotFoundError(f"no stems in {stems_dir}")
    return stems, rate


def render(stems: dict[str, np.ndarray], gains: dict[str, float | None]) -> np.ndarray:
    unknown = set(gains) - set(stems)
    if unknown:
        raise ValueError(f"unknown stems: {', '.join(sorted(unknown))}; have {', '.join(sorted(stems))}")

    length = max(len(s) for s in stems.values())
    channels = max(s.shape[1] for s in stems.values())
    out = np.zeros((length, channels), dtype=np.float32)
    for name, audio in stems.items():
        db = gains.get(name, 0.0)
        if db is OFF:
            continue
        out[: len(audio)] += audio * np.float32(10 ** (db / 20))

    # Only pull the level down: boosting a sparse mix (e.g. drums-only) up to full scale
    # would make switching between playalong versions jarring.
    peak = float(np.abs(out).max())
    if peak > PEAK_CEILING:
        out *= PEAK_CEILING / peak
    return out


def trim(audio: np.ndarray, rate: int, start: float) -> np.ndarray:
    offset = int(start * rate)
    if offset <= 0:
        return audio
    out = audio[offset:].copy()
    fade = min(len(out), int(FADE_IN * rate))
    out[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)[:, None]
    return out


def place_beat(audio: np.ndarray, rate: int, start: float, beat: float, at: float) -> np.ndarray:
    """The song from `start` on, shifted so `beat` (a time in `audio`) lands at `at` seconds.

    Anything before `start` (the video intro) is left out, and so is music that would land before 0
    (a pickup longer than `at`).
    """
    zero = beat - at
    cut = max(start, zero)
    out = trim(audio, rate, cut) if cut > 0 else audio.copy()
    silence = int(round((cut - zero) * rate))
    return np.concatenate([np.zeros((silence, audio.shape[1]), dtype=audio.dtype), out])


def write(audio: np.ndarray, rate: int, dest: Path, tempo: float = 1.0) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.suffix == ".wav" and tempo == 1.0:
        sf.write(dest, audio, rate, subtype="PCM_24")
        return dest

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "mix.wav"
        sf.write(raw, audio, rate, subtype="FLOAT")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw)]
        if tempo != 1.0:
            cmd += ["-filter:a", f"atempo={tempo}"]  # time-stretch, pitch preserved
        if dest.suffix == ".mp3":
            cmd += ["-codec:a", "libmp3lame", "-b:a", "320k"]
        elif dest.suffix == ".wav":
            cmd += ["-codec:a", "pcm_s24le"]
        subprocess.run([*cmd, str(dest)], check=True)
    return dest


MIX_INDEX = "mixes.json"


def _record_mix(track_dir: Path, dest: Path, entry: dict) -> None:
    """Note how a mix lines up with the song, so a player can follow it (see song.py)."""
    index_path = track_dir / "mixes" / MIX_INDEX
    try:
        index = json.loads(index_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        index = {}
    index[dest.name] = entry
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False))


def make_mixes(
    track_dir: Path,
    presets: list[str],
    custom: dict[str, float | None] | None = None,
    custom_name: str = "custom",
    fmt: str = "mp3",
    tempo: float = 1.0,
    start: float | None = None,
    count_in: int = 0,
    bpm: float | None = None,
) -> list[Path]:
    """Render mixes; start=None detects the song start, 0 keeps the whole recording.

    count_in adds that many bars of stick clicks at the song's tempo (detected, or `bpm`).
    """
    stems, rate = load_stems(track_dir / "stems")
    if start is None:
        start = song_start(track_dir, stems, rate)
    if start:
        print(f"Song starts at {int(start // 60)}:{start % 60:04.1f}, cutting the intro before it")
    if count_in:
        from playalong.countin import with_count_in
        from playalong.tempo import song_tempo

        found = song_tempo(track_dir, stems, rate, start, bpm)
        if found is None:
            # The count-in is on by default, so a song with no steady beat still gets its mixes.
            print("No steady tempo found, mixing without a count-in (give one with --bpm)")
            count_in = 0
        else:
            bpm, beat = found
            print(f"Tempo {bpm:.1f} BPM, counting in {count_in} bar{'s' if count_in > 1 else ''}")

    def finish(audio: np.ndarray) -> np.ndarray:
        if count_in:
            return with_count_in(audio, rate, start, beat, bpm, count_in)
        return trim(audio, rate, start)

    jobs = [(name, PRESETS[name]) for name in presets]
    if custom:
        jobs.append((custom_name, custom))

    suffix = "" if tempo == 1.0 else f" @{round(tempo * 100)}%"
    if count_in:
        from playalong.countin import count_timing

        timing = count_timing(beat, bpm, count_in, tempo)
        source_offset = timing.pop("source_offset")
    else:
        timing, source_offset = None, start

    def mixed(name: str, gains: dict[str, float | None]) -> np.ndarray:
        # The separated stems never add back up to the recording exactly, so the original is the source itself.
        if name == ORIGINAL and not gains and (source := track_dir / "source.wav").exists():
            audio, sr = sf.read(source, dtype="float32", always_2d=True)
            if sr == rate:
                return render({"source": audio}, {})
        return render(stems, gains)

    written = []
    for name, gains in jobs:
        dest = track_dir / "mixes" / f"{track_dir.name} - {name}{suffix}.{fmt}"
        written.append(write(finish(mixed(name, gains)), rate, dest, tempo))
        # Song time at a point in the mix: source_offset + mix seconds * tempo.
        _record_mix(track_dir, dest, {"name": name, "tempo": tempo, "source_offset": source_offset,
                                      "count_in": timing})
        print(f"  {dest}")
    return written
