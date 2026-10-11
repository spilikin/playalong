"""Stems laid out for a GarageBand project: one file per instrument, the song's first beat on bar 2.

GarageBand's project format is undocumented, so this writes the audio and the tempo to set; dragging
the files into an empty project gives one track per stem.
"""

import math
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf

from playalong.countin import BEATS_PER_BAR
from playalong.intro import song_start
from playalong.mix import PEAK_CEILING, load_stems, place_beat, trim
from playalong.tempo import song_tempo


def export_stems(track_dir: Path, start: float | None = None, bpm: float | None = None) -> Path:
    """Write the stems to `mixes/<track> - GarageBand <tempo> BPM/` and return that folder.

    start=None detects the song start, 0 keeps the whole recording.
    """
    stems, rate = load_stems(track_dir / "stems")
    if start is None:
        start = song_start(track_dir, stems, rate)
    length = max(len(a) for a in stems.values())
    stems = {n: np.pad(a, ((0, length - len(a)), (0, 0))) for n, a in stems.items()}

    found = song_tempo(track_dir, stems, rate, start, bpm)
    # GarageBand takes whole-number tempi; bar 2 has to start where that tempo puts it.
    tempo = None if found is None else math.floor(found[0] + 0.5)
    name = f"{track_dir.name} - GarageBand" + ("" if tempo is None else f" {tempo} BPM")

    def place(audio: np.ndarray) -> np.ndarray:
        if tempo is None:
            return trim(audio, rate, start)
        return place_beat(audio, rate, start, found[1], BEATS_PER_BAR * 60 / tempo)

    # One gain for all stems keeps their balance: the tracks at 0 dB in GarageBand sum to the song.
    peak = max(float(np.abs(a).max()) for a in stems.values())
    gain = np.float32(min(1.0, PEAK_CEILING / peak)) if peak > 0 else np.float32(1.0)

    folder = track_dir / "mixes" / name
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    for stem, audio in stems.items():
        sf.write(folder / f"{stem.capitalize()}.wav", place(audio) * gain, rate, subtype="PCM_24")

    if tempo is None:
        print("No steady tempo found: set the tempo in GarageBand by ear (or pass --bpm).")
    tempo_step = "" if tempo is None else f", set the tempo to {tempo} BPM"
    print(f"In GarageBand: File > New > Empty Project{tempo_step}, then drag all {len(stems)} files from\n"
          f"  {folder}\ninto the empty area below the tracks. Each lands on its own track"
          + ("." if tempo is None else ", with the song's first beat on bar 2."))
    return folder
