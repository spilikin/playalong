import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

# Dialogue lands in the vocals stem and ambience/SFX in "other", so only these
# are trusted to say when the band actually starts playing.
INSTRUMENT_STEMS = ("drums", "bass", "guitar", "piano")

FRAME = 2048
HOP = 1024
THRESHOLD_DB = -25.0  # relative to the loud part of the song
SUSTAIN_SECONDS = 3.0  # music has to keep going, a lone hit or rumble in the intro doesn't count
SUSTAIN_RATIO = 0.6
PRE_ROLL = 0.2  # back off a little so the first attack isn't clipped
MIN_INTRO = 1.0  # anything shorter is just the song's own lead-in

SPONSORBLOCK_URL = "https://sponsor.ajay.app/api/skipSegments"


def detect_from_stems(stems: dict[str, np.ndarray], rate: int) -> float:
    """Seconds from the start of the audio to where sustained instrumental playing begins."""
    present = [stems[n] for n in INSTRUMENT_STEMS if n in stems]
    if not present:
        return 0.0
    length = min(len(s) for s in present)
    mono = sum(s[:length].mean(axis=1) for s in present)
    if length < FRAME:
        return 0.0

    frames = np.lib.stride_tricks.sliding_window_view(mono, FRAME)[::HOP]
    rms_db = 20 * np.log10(np.sqrt((frames**2).mean(axis=1)) + 1e-10)
    active = rms_db > np.percentile(rms_db, 95) + THRESHOLD_DB

    window = max(1, round(SUSTAIN_SECONDS * rate / HOP))
    # Fraction of active frames in the window starting at each frame.
    padded = np.concatenate([active, np.zeros(window, dtype=bool)]).astype(np.float32)
    density = np.convolve(padded, np.ones(window), mode="valid")[: len(active)] / window

    candidates = np.flatnonzero(active & (density >= SUSTAIN_RATIO))
    if not len(candidates):
        return 0.0
    # Frame centre, not frame start: a frame only partly overlapping the onset already counts as active.
    start = max(0.0, (candidates[0] * HOP + FRAME / 2) / rate - PRE_ROLL)
    return start if start >= MIN_INTRO else 0.0


def sponsorblock_start(video_id: str) -> float | None:
    """End of a community-marked non-music intro, or None if there is no such segment."""
    query = urllib.parse.urlencode({"videoID": video_id, "categories": '["music_offtopic"]'})
    try:
        with urllib.request.urlopen(f"{SPONSORBLOCK_URL}?{query}", timeout=10) as resp:
            segments = json.load(resp)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    intro = [s["segment"][1] for s in segments if s["segment"][0] <= MIN_INTRO]
    return max(intro) if intro else None


def song_start(track_dir: Path, stems: dict[str, np.ndarray], rate: int) -> float:
    """Resolve and cache where the song proper begins, preferring human-marked data."""
    info_path = track_dir / "info.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else {}
    if "song_start" in info:
        return info["song_start"]

    start, source = None, "stems"
    if info.get("id"):
        start = sponsorblock_start(info["id"])
        source = "sponsorblock"
    if start is None:
        start, source = detect_from_stems(stems, rate), "stems"

    info["song_start"] = round(start, 2)
    info["song_start_source"] = source
    info_path.write_text(json.dumps(info, indent=2, ensure_ascii=False))
    return info["song_start"]
