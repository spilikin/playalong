import json

import pytest

from playalong import recipes


def test_defaults_are_original_guide_no_guitar():
    assert [(r["id"], r["name"]) for r in recipes.DEFAULTS] == [
        ("original", "Original"), ("guide", "Guide"), ("no-guitar", "No guitar")]
    guide, no_guitar = recipes.DEFAULTS[1], recipes.DEFAULTS[2]
    assert guide["levels"]["guitar"] == -15 and guide["mute"] == []
    assert no_guitar["mute"] == ["guitar"]
    for r in recipes.DEFAULTS:
        assert (r["transpose"], r["tempo"], r["count_in"], r["solo"]) == (0, 1.0, 1, [])
        assert set(r["levels"]) == set(recipes.STEMS)


def test_missing_or_corrupt_file_gives_defaults(tmp_path):
    assert recipes.read_recipes(tmp_path) == recipes.DEFAULTS
    (tmp_path / recipes.FILE).write_text("{oops")
    assert recipes.read_recipes(tmp_path) == recipes.DEFAULTS


def test_recipes_round_trip_and_are_written_once(tmp_path):
    recipes.ensure_recipes(tmp_path)
    mine = [{**recipes.DEFAULTS[0], "id": "band", "name": "Band −2", "transpose": -2}]
    recipes.write_recipes(tmp_path, mine)
    recipes.ensure_recipes(tmp_path)
    assert recipes.read_recipes(tmp_path) == mine
    stored = json.loads((tmp_path / recipes.FILE).read_text())
    assert stored["format"] == "playalong-mixes" and stored["version"] == 1


def test_newer_file_is_refused_not_overwritten(tmp_path):
    newer = json.dumps({"format": "playalong-mixes", "version": 2, "mixes": []})
    (tmp_path / recipes.FILE).write_text(newer)
    with pytest.raises(recipes.NewerFormat):
        recipes.read_recipes(tmp_path)
    recipes.ensure_recipes(tmp_path)
    assert (tmp_path / recipes.FILE).read_text() == newer


def test_gains_solo_wins_and_mute_silences():
    r = {**recipes.DEFAULTS[0], "levels": {**recipes.DEFAULTS[0]["levels"], "vocals": -6}, "mute": ["guitar"]}
    assert recipes.gains(r)["guitar"] is None and recipes.gains(r)["vocals"] == -6
    solo = {**r, "solo": ["vocals", "guitar"]}
    assert {s for s, g in recipes.gains(solo).items() if g is not None} == {"vocals"}


def test_original_plays_the_source_only_untouched():
    original, guide = recipes.DEFAULTS[0], recipes.DEFAULTS[1]
    assert recipes.plays_source(original) and not recipes.plays_source(guide)
    assert recipes.plays_source({**original, "transpose": -2, "tempo": 0.8})
    assert not recipes.plays_source({**original, "mute": ["piano"]})
    assert not recipes.plays_source({**original, "solo": ["vocals"]})
