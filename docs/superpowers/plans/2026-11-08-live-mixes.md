# Live Mixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mixes become recipes played live by a Rust audio engine (levels, mute, solo, key, tempo, count-in), edited in place in an Edit mode of the mix list, with song editing (start, BPM, chords, GarageBand, delete) separate, and files only on export.

**Architecture:** The CLI keeps making the song bundle (stems, chords, song file, now version 2) plus a `mixes.json` of recipes, and renders a recipe to MP3 on export. The app's Rust side gets an `engine` module: stems in memory → summed with ramped levels → Rubber Band real-time → count-in clicks → limiter → CoreAudio via cpal; it plays the same timeline a rendered mix had (`source_offset`, `tempo`, `count_in`), so the page's existing `songTime`/`mixTime`/`countAt` keep working. The page drops `<audio>` and drives the engine with commands; position comes back as events.

**Tech Stack:** Python 3.12 CLI (uv, pytest), Rust (Tauri 2, cpal 0.16, rubberband-sys 0.1.4, hound, rtrb), Svelte 5 + vitest.

**Spec:** `docs/superpowers/specs/2026-11-08-live-mixes-design.md`

## Global Constraints

- Apple Silicon macOS only; no AI attribution in commits or files; comments explain why, not what.
- Default mixes for every song: **Original, Guide, No guitar**. Guide = guitar −15 dB; No guitar = guitar muted; all key 0, tempo 100 %, count-in 1 bar.
- Key −12…+12 semitones; tempo 50…150 %; count-in 0, 1 or 2 bars; levels in dB, instruments `vocals, guitar, bass, drums, piano, other`.
- Count-in plays only when playback starts at the top of the song (mix time 0); pause/resume/seek continue straight away.
- Limiter ceiling −1 dBFS on live playback and exports.
- Original with all levels 0 dB and nothing muted or soloed plays `source.wav` (the stems don't sum back exactly), live and in exports.
- Song file version 2: `tempo.beat`, chord transpositions for every key −12…+12, `garagebands[].outdated`; no rendered-mix list.
- Existing songs: rendered mix files (`mixes/*.mp3|wav|flac`, `mixes/mixes.json`) are deleted; stems, chords, cover, GarageBand folders and projects stay.
- UI copy is English with Latvian strings in `i18n.svelte.ts` for every new key.

## Review Focus

- Changing mix, level or key while playing: no restart, no click, no level jump (ramp, limiter); the page's position never jumps backwards.
- Seeking during Rubber Band's start-up delay and right after a key change: the reported position matches what is heard (within 50 ms) so chords stay in sync.
- An old (version 1) song opened in the app: refreshed once through the runtime, then plays; without the runtime installed the app says so instead of failing silently.
- `mixes.json` missing, corrupt or from a newer app: defaults are used, nothing crashes, a newer file is never overwritten.
- A song whose tempo wasn't found (`tempo` null): mixes play without count-in, the count-in control is disabled with a reason.

---

### Task 1: Recipes and song file version 2 (CLI)

**Files:**
- Create: `src/playalong/recipes.py`, `tests/test_recipes.py`
- Modify: `src/playalong/song.py` (version 2, `tempo.beat`, all-key transpositions, `garagebands[].outdated`, drop rendered `mixes`), `src/playalong/cli.py` (`run` without mixes; `refresh`, `retime`, `export` commands), `src/playalong/mix.py` (add `limit`), `tests/test_song.py`, `tests/test_cli.py`, `tests/test_mix.py`, `README.md`

**Interfaces:**
- Produces `mixes.json` in the bundle root: `{"format": "playalong-mixes", "version": 1, "mixes": [Recipe…]}`; Recipe = `{"id": str, "name": str, "levels": {stem: float dB}, "mute": [stem…], "solo": [stem…], "transpose": int, "tempo": float, "count_in": 0|1|2}`.
- `recipes.DEFAULTS: list[dict]` (ids `original`, `guide`, `no-guitar`); `read_recipes(track_dir) -> list[dict]` (defaults when missing/corrupt; raises `NewerFormat` for version > 1); `write_recipes(track_dir, recipes)`; `ensure_recipes(track_dir)` (writes defaults if missing); `gains(recipe) -> dict[str, float | None]` (None = silent, solo wins over mute); `plays_source(recipe) -> bool`.
- `mix.limit(audio: np.ndarray, rate: int, ceiling: float = PEAK_CEILING) -> np.ndarray`: 5 ms look-ahead, 100 ms release, never above ceiling, unity where the signal stays below.
- Song file: `"version": 2`, `"tempo": {..., "beat": float}` (the counted-in beat, `info["beat_offset"]`), `"transpositions": {"-12"…"+12" except "+0": {"key", "chords"}}`, `"garagebands": [{folder, bpm, transpose, project?, outdated: bool}]`, `"mixes"` removed.
- CLI: `run` = download, cover, separate, tempo (`song_tempo`, stores `beat_offset`), chords, `ensure_recipes`, song file. `refresh <track>` = delete rendered mixes, `ensure_recipes`, tempo if missing, song file. `retime <track> [--start S] [--bpm B]` = store overrides in info.json, recompute beat and chords, set `info["timing_changed"]` (epoch s), song file. `export <track> <mix-id>` = render that recipe (offline Rubber Band, count-in, intro cut, `limit`) to `exports/<track> - <mix name>.mp3`, print the path.

- [ ] **Step 1: Write failing tests** — `test_recipes.py`: `test_defaults_are_original_guide_no_guitar` (ids/names, guide `levels["guitar"] == -15`, no-guitar `mute == ["guitar"]`); `test_missing_or_corrupt_file_gives_defaults`; `test_newer_file_is_refused_not_overwritten` (version 2 → `NewerFormat`, file unchanged after `ensure_recipes`); `test_gains_solo_wins_and_mute_silences` (`solo=["vocals"]` → only vocals not None); `test_original_plays_the_source_only_untouched`. `test_mix.py`: `test_limit_holds_the_ceiling_and_leaves_quiet_audio_alone` (2.0-amplitude burst → max ≤ 10**(-1/20)+1e-6; 0.3-amplitude sine unchanged within 1e-6). `test_song.py`: `test_song_file_v2_has_every_key_and_the_beat` (`version == 2`, 24 transposition keys, `"-1"` key of Bb minor == "A minor", `tempo["beat"] == info beat_offset`, no `mixes`); `test_garageband_project_is_outdated_after_retime` (project mtime < `timing_changed` → `outdated True`). `test_cli.py`: `test_run_makes_no_mix_files_but_default_recipes` (monkeypatched steps; `mixes.json` written, `make_mixes` not called); `test_refresh_deletes_rendered_mixes_and_keeps_the_rest` (mp3, wav, `mixes/mixes.json` gone; stems, GarageBand folder, `.band` stay); `test_export_renders_one_recipe` (monkeypatched writer receives guide gains, tempo/transpose from recipe, dest `exports/<track> - Guide.mp3`).
- [ ] **Step 2: Run** `uv run pytest -q tests/test_recipes.py tests/test_song.py tests/test_cli.py tests/test_mix.py` — Expected: the new tests FAIL (import/attribute errors).
- [ ] **Step 3: Implement** recipes.py, `limit`, song file v2, the four CLI commands. Export reuses `mix.write`/`with_count_in`/`trim` with `gains(recipe)`; Original-untouched reads `source.wav`.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: all pass.
- [ ] **Step 5: README** — Usage (`run`, `refresh`, `retime`, `export`), Song file table (v2 fields, `mixes.json`). Commit "Recipes, song file 2, export and retime in the CLI".

### Task 2: Engine core (Rust, no audio device)

**Files:**
- Create: `app/src-tauri/src/engine/mod.rs`, `engine/timeline.rs`, `engine/mixer.rs`, `engine/limiter.rs`, `engine/render.rs`
- Modify: `app/src-tauri/Cargo.toml` (cpal 0.16, rubberband-sys 0.1.4, hound 3, rtrb 0.3), `app/src-tauri/src/lib.rs` (`mod engine`)

**Interfaces:**
- `timeline::Timeline { tempo: f64, source_offset: f64, count_in: Option<CountIn> }` serialized exactly like a rendered mix's timing (`CountIn { bars, clicks: Vec<Click{time, accent, count}>, downbeat }`); `Timeline::new(start: f64, beat: Option<f64>, bpm: Option<f64>, count_in: u8, tempo: f64) -> Timeline` (port of `count_timing`; no count-in when bpm or beat is None or count_in 0, then `source_offset = start`).
- `timeline::stick(rate: u32, accent: bool) -> Vec<f32>` (port of `countin.stick`, same constants).
- `mixer::Recipe` (serde, same fields as `mixes.json`); `mixer::Gains::from(&Recipe) -> [f32; 6]` (solo wins, mute → 0, dB → linear); `mixer::Mixer::block(&mut self, stems: &Stems, from: usize, frames: usize, out_l: &mut [f32], out_r: &mut [f32])` ramps from the previous gains to the target over 256 frames.
- `limiter::Limiter::new(rate: u32, ceiling: f32)`, `process(&mut self, l: &mut [f32], r: &mut [f32])` — same algorithm as `mix.limit`.
- `render::Render` — pulls output blocks for a recipe and timeline without a device: `Render::new(stems: Arc<Stems>, recipe: &Recipe, timeline: &Timeline, out_rate: u32)`, `next(&mut self, frames: usize) -> (Vec<f32>, Vec<f32>)`, `position(&self) -> f64` (mix seconds of the next output frame as heard, corrected for Rubber Band's delay), `set_recipe(&mut self, &Recipe)`, `seek(&mut self, mix_seconds: f64)`.
- `Stems { rate: u32, tracks: [(Vec<f32>, Vec<f32>); 6], source: Option<(Vec<f32>, Vec<f32>)> }`, `Stems::load(song_folder: &Path, song: &serde_json::Value) -> Result<Stems, String>`.

- [ ] **Step 1: Write failing tests** (in each file's `#[cfg(test)]`): `timeline_matches_the_cli` (beat 22.25, bpm 120, 1 bar, tempo 1 → source_offset 20.0, clicks at 0.25/0.75/1.25/1.75, downbeat 2.25; tempo 0.8 divides times by 0.8); `no_tempo_no_count_in`; `stick_is_short_and_accent_is_louder`; `solo_wins_over_mute`; `level_changes_ramp_without_a_jump` (max sample-to-sample step after a 0→−∞ change on a DC stem ≤ 1/256 + ε); `limiter_holds_minus_one_dbfs`; `render_moves_pitch_by_the_key` (440 Hz sine stem, transpose +12 → FFT peak 880 ± 5 Hz after 1 s); `render_keeps_time_at_tempo` (tempo 0.8 → 1 s of output advances `position` by 0.8 s ± 0.02 after warm-up); `render_counts_in_only_from_the_top` (seek 0 → clicks present in the first downbeat seconds; seek 10 → no click energy).
- [ ] **Step 2: Run** `cd app/src-tauri && cargo test engine` — Expected: FAIL (missing items).
- [ ] **Step 3: Implement.** Rubber Band options: `ProcessRealTime | EngineFiner | PitchHighConsistency`; pitch scale `2^(k/12) / (out_rate/44100)`, time ratio `(out_rate/44100) / tempo` (from the spike). Count-in clicks are added to the output timeline before the limiter (not stretched); music before `beat` under the count is silent, as `with_count_in` does.
- [ ] **Step 4: Run** `cargo test` and `cargo clippy --all-targets` — Expected: all pass, no warnings. Commit "Live engine core".

### Task 3: Player and commands (Rust)

**Files:**
- Create: `app/src-tauri/src/engine/player.rs`, `app/src-tauri/src/playback.rs`, `app/src-tauri/src/mixes.rs`
- Modify: `app/src-tauri/src/lib.rs` (manage `playback::Playback`, register commands), `app/src-tauri/src/maker.rs` (retire `make_mixes`, `mix_args`, `MixChoice`; add song jobs), `app/src-tauri/src/song.rs` (VERSION 2)

**Interfaces:**
- Commands: `playback_open(folder: String, mix_id: String) -> Opened { duration: f64, timeline: Timeline }`; `playback_play()`, `playback_pause()`, `playback_seek(mix_seconds: f64)`, `playback_set_mix(recipe: Recipe) -> Timeline` (applies on the next block, keeps the song position: new mix time = old song time mapped through the new timeline); event `playback-position { mix_seconds: f64, playing: bool }` every ~16 ms while playing.
- `mixes_load(folder) -> Vec<Recipe>` (defaults when missing/corrupt; error naming the version when newer); `mixes_save(folder, mixes: Vec<Recipe>)` (atomic write, refuses when the file on disk is newer-format).
- Song jobs (all through `Maker::run_cli`, event `song-job-line`, refuse while another job runs): `song_refresh(folder)`, `song_retime(folder, start: Option<f64>, bpm: Option<f64>)`, `song_export(folder, mix_id) -> String` (path; then revealed with `open -R`), `song_garageband(folder, transpose: i32)` (`garageband <folder> -k N --band`). `delete_song(folder, library)` moves the folder to the Trash (`trash` crate), only when it's inside `library`.
- `player::Player` owns the cpal stream and the processing thread (ring buffer ~0.1 s), wraps `render::Render`; position = `Render::position` of the frame being played (count frames consumed by the callback).

- [ ] **Step 1: Write failing tests**: `mixes_file_round_trips_and_defaults_when_missing`; `a_newer_mixes_file_is_not_overwritten`; `set_mix_keeps_the_song_position` (pure function `remap(old: &Timeline, new: &Timeline, mix_seconds) -> f64`); `export_args`, `retime_args` (CLI argument lists); `delete_only_inside_the_library`; song.rs `opens_version_2`.
- [ ] **Step 2: Run** `cargo test` — Expected: FAIL.
- [ ] **Step 3: Implement.** The audio thread never locks a mutex shared with commands: commands go through an `rtrb` command queue to the processing thread.
- [ ] **Step 4: Run** `cargo test`, `cargo clippy --all-targets`. Commit "Player, mixes file and song jobs".

### Task 4: Player page on the engine (UI)

**Files:**
- Create: `app/ui/src/lib/playback.svelte.ts`, `app/ui/src/lib/mixes.ts`
- Modify: `app/ui/src/routes/+page.svelte` (no `<audio>`), `app/ui/src/lib/song.ts` (types: `Recipe`, `Timeline`; `forMix` takes the recipe's transpose), `app/ui/src/lib/fixture.ts`, `app/ui/src/routes/page.test.ts`
- Delete: `MixesPage.svelte`, `MixesCard.svelte`, `mixChoice.ts`, `mixVersions.ts` and their tests; `makeMixes`/`mixJob` in `maker.svelte.ts`

**Interfaces:**
- `playback` state: `{ opened: OpenedSong | null, mixes: Recipe[], current: string, timeline: Timeline | null, mixSeconds: number, duration: number, playing: boolean }`; `openSong(folder)`, `play()`, `pause()`, `seekSong(songSeconds)`, `chooseMix(id)`, `updateMix(recipe)` (sets locally, `playback_set_mix`, debounced `mixes_save` 300 ms).
- `mixes.ts`: `describe(recipe, s): string` ("guitar off, vocals −6 · −2 · 90%", "as recorded"), `newMixFrom(recipe, existing): Recipe` (id unique, name "<name> copy"), `PRESET_LEVELS` for "Start from".
- The page computes chords/count from `timeline` exactly as from a rendered `Mix` (`songTime`, `mixTime`, `countAt` take `{tempo, source_offset, count_in}`).

- [ ] **Step 1: Write failing tests** (page.test.ts with IPC mocks): `plays_through_the_engine` (Play → `playback_play`; a `playback-position` event moves the chord); `switching_mix_keeps_the_place` (`playback_set_mix` with the new recipe, no `playback_open`); `transposed_mix_shows_moved_chords` (recipe transpose −2 → key and chord names from `transpositions["-2"]`); `old_song_is_refreshed_first` (version 1 → `song_refresh` then `playback_open`); `no_runtime_old_song_explains` . mixes.test.ts: `describes_mixes`, `new_mix_copies_and_names_uniquely`.
- [ ] **Step 2: Run** `cd app/ui && npx vitest run` — Expected: new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `npx vitest run && npx svelte-check`. Commit "Player plays live mixes".

### Task 5: Mix list, Edit mode and mixer (UI)

**Files:**
- Create: `app/ui/src/lib/MixList.svelte`, `app/ui/src/lib/Mixer.svelte`
- Modify: `+page.svelte` (sidebar uses MixList; main area shows Mixer in edit mode), `i18n.svelte.ts`, tests

**Interfaces:** as mocked up (screens 9, 10): heading "Mixes" with Edit/Done (aria-pressed); play mode rows with `describe`; edit mode rows with name input (rename on input, saved), ⋯ menu (Duplicate, Export MP3…, Delete — not for the last remaining mix), drag to reorder, + New mix (copy of the selected); Mixer: key stepper with key name, tempo stepper with BPM, count-in segmented (disabled with reason without tempo), six rows level slider (−30…+6 dB) / M / S, "Start from" presets.

- [ ] **Step 1: Failing tests**: `edit_toggle_shows_mixer_of_the_playing_mix`; `rename_saves_without_rendering` (`mixes_save` called, no job command); `level_change_is_heard_at_once` (`playback_set_mix` with new level); `solo_and_mute`; `new_duplicate_delete_reorder`; `export_runs_a_job_and_reveals`; `count_in_disabled_without_tempo`.
- [ ] **Step 2–4:** run, implement, run (`npx vitest run && npx svelte-check`). Commit "Edit mode: mix list and live mixer".

### Task 6: Song editing, Library and release notes

**Files:**
- Create: `app/ui/src/lib/SongPanel.svelte`
- Modify: `+page.svelte` (Song… toolbar button), `Library.svelte` (Mixes column = recipe count; Make song = run without mixes), `library.rs` (count recipes from `mixes.json`), `i18n.svelte.ts`, `README.md`

**Interfaces:** screen 11: start (m:ss.s input, Set to playhead), BPM (input, Tap: average of the last 4 taps), Detect chords again (`song_retime` with no overrides), GarageBand (key stepper, Make project → `song_garageband`, list per key with Open / out of date + Make again), Delete song… (confirm, `delete_song`, back to Library). Retime runs in the background; on finish the page reloads the song file and keeps playing.

- [ ] **Step 1: Failing tests**: `set_start_to_playhead_retimes`; `tap_tempo_averages`; `garageband_outdated_offers_make_again`; `delete_song_confirms_and_returns_to_library`; Rust `library_counts_recipes`.
- [ ] **Step 2–4:** run, implement, run all suites (`uv run pytest -q`, `cargo test`, `npx vitest run`, `svelte-check`). Rebuild the debug app; manual check on a real song: play, edit levels/key/tempo live, rename, export, retime, GarageBand.
- [ ] **Step 5:** README (player and edit mode, song editing). Commit "Song editing and Library for live mixes". The app runs its own bundled Python code in the runtime (`PLAYALONG_CODE`), so the new CLI commands need no runtime release; nothing is pushed or published.
