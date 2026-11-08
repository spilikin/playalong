"""A song's mixes as recipes: levels, mute and solo per instrument, key, tempo and count-in.

The app plays them live from the stems and edits them in place, so they live in a file of their own
(`mixes.json` in the song folder) that the song file, rebuilt from what's on disk, never touches. The
CLI writes the defaults for a new song and renders a recipe when one is exported.
"""

import json
from pathlib import Path

from playalong.separate import STEMS

FILE = "mixes.json"
FORMAT = "playalong-mixes"
VERSION = 1


class NewerFormat(RuntimeError):
    pass


def _recipe(id: str, name: str, levels: dict | None = None, mute: list | None = None) -> dict:
    return {"id": id, "name": name, "levels": {s: 0.0 for s in STEMS} | (levels or {}), "mute": mute or [],
            "solo": [], "transpose": 0, "tempo": 1.0, "count_in": 1}


DEFAULTS = [
    _recipe("original", "Original"),
    _recipe("guide", "Guide", {"guitar": -15.0}),
    _recipe("no-guitar", "No guitar", mute=["guitar"]),
]


def read_recipes(track_dir: Path) -> list[dict]:
    """The song's mixes; the defaults when there's no file yet or it can't be read."""
    try:
        stored = json.loads((track_dir / FILE).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return [dict(r) for r in DEFAULTS]
    if stored.get("format") != FORMAT:
        return [dict(r) for r in DEFAULTS]
    if stored.get("version", 0) > VERSION:
        raise NewerFormat(f"{track_dir / FILE} is from a newer Playalong; update it to read these mixes")
    return stored.get("mixes") or [dict(r) for r in DEFAULTS]


def write_recipes(track_dir: Path, recipes: list[dict]) -> None:
    path = track_dir / FILE
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"format": FORMAT, "version": VERSION, "mixes": recipes}, indent=2,
                              ensure_ascii=False))
    tmp.replace(path)


def ensure_recipes(track_dir: Path) -> None:
    """Give a song the default mixes, leaving any it already has (or a newer app's file) alone."""
    if not (track_dir / FILE).exists():
        write_recipes(track_dir, [dict(r) for r in DEFAULTS])


def gains(recipe: dict) -> dict[str, float | None]:
    """dB per instrument, None for silent. With any instrument soloed only those sound; a muted one stays
    silent even when soloed, as in a mixing desk."""
    solo = set(recipe.get("solo") or [])
    mute = set(recipe.get("mute") or [])
    levels = recipe.get("levels") or {}
    return {s: None if s in mute or (solo and s not in solo) else float(levels.get(s, 0.0)) for s in STEMS}


def plays_source(recipe: dict) -> bool:
    """An untouched mix plays the recording itself: the separated stems never add back up to it exactly."""
    return not recipe.get("solo") and not recipe.get("mute") and all(
        float(v) == 0.0 for v in (recipe.get("levels") or {}).values())
