# Live mixes, song bundles and edit mode

## Intent

Today a mix is a rendered file: changing a level, key or tempo means waiting for a new file, and the
player shows whatever files exist. That made the Mixes page confusing (which mixes exist, which key
needs everything rendered again) and every change slow. The goal is that a mix is something you
shape while the song plays: change a level, mute the guitar, drop the key by two, slow to 85%, and
hear it at once. Files are only made when one is needed outside the app.

A throwaway test (scratchpad `livespike`, 2026-11-08) proved the core: the six stems of a 4-minute
song load in 1 s into 504 MB, are mixed live, run through Rubber Band's real-time mode (R3 "finer"
engine) for key and tempo, and play through CoreAudio at 20–30 % of one Apple Silicon core with no
dropouts and under a quarter of a second from a change to hearing it. The user listened and approved
the sound.

## The workflow (decided by the user)

1. **Add new song** (Library): a YouTube link or audio file is downloaded and split into instruments.
   That makes the song's *bundle*: the six stems, the chords, the cover, the song file. No mix files.
2. **Mixes are recipes**, all configurable. Every new song gets three defaults: **Original, Guide,
   No guitar**. The user can add their own mixes, edit any mix in place, rename one without anything
   being downloaded or rendered again, duplicate and delete.
3. **Playback is live**: the app mixes the stems at the mix's levels, applies its key, tempo and
   count-in, and plays the result. Key and tempo are live too.
4. **Edit mode** is a toggle in the left bar (where the mix list is), not a button in the toolbar.
   **Song editing** (global) and **mix editing** are clearly separate.
5. **Existing songs start fresh**: their rendered mix files are deleted and they get the three
   defaults.

## Goals

- Every change to a mix is heard immediately while the song keeps playing, in the place it plays.
- It's always clear which mix is playing, which one is being edited, and that edits apply to it.
- Rename, new, duplicate and delete are instant.
- Chords, bars, count-in numbers and the playhead stay in sync at any tempo and key.
- Files appear only on request: an MP3 export of a mix, or the GarageBand project.

## Non-goals

- Editing title, artist or cover (the user said no).
- Effects, EQ, panning, automation, per-section levels.
- Playing several songs at once, or mixes from different songs.
- Windows, Linux or Intel Macs (the app and runtime are Apple Silicon only).

## Anti-goals

- A slow or glitchy player: dropouts, clicks when changing a level, a lag the user notices. The live
  engine must stay well inside real time; levels change with a short ramp, not a jump.
- Edits that silently go somewhere else than the user thinks (editing a mix that isn't the one
  playing, or an edit being lost on switching).
- Losing the user's mixes when the CLI rewrites the song file.

## What's decided

### Mix recipe

A mix has: a name; per instrument (vocals, guitar, bass, drums, piano, other) a level in dB and a
mute flag, and per mix one optional solo set (the mixer's solo buttons); key change in semitones
(−12…+12); tempo in percent (50…150, as today's CLI range allows); count-in (off, 1 bar, 2 bars).
The defaults are today's presets expressed as levels: Original = all at 0 dB; Guide = guitar −15 dB;
No guitar = guitar muted; all at key 0, tempo 100 %, count-in 1 bar.

### Where mixes live

In the bundle, in a file of their own that the app writes and the CLI only reads and adds to
(**builder's call** on the name and format, e.g. `mixes.json` with a format name and version like the
song file). Not inside `<song>.playalong`, because the CLI rebuilds that file from what's on disk and
would drop them. Order in the file is the order in the list.

### Live engine (the user's call: Rust, live key and tempo)

In the app's Rust side. From the test: stems are read into memory as float; each block, the six are
summed with their levels into one stereo signal; that goes through Rubber Band real-time (R3 engine,
pitch-high-consistency) whose pitch scale and time ratio follow the mix's key and tempo; count-in
clicks are added; the result goes to CoreAudio via `cpal` through a small ring buffer filled by a
processing thread (the test's ~0.1 s). Rubber Band also covers the difference when the output device
runs at another rate than 44.1 kHz (pitch and time ratio scaled by the rate ratio, as in the test).
Rubber Band comes in through the `rubberband-sys` crate, which builds it from source (GPL-2.0-or-later,
fine under the project's GPL-3.0-or-later).

The engine reports the **song position** (source time, corrected for the buffering and Rubber Band's
delay) many times a second; the page draws chords, bars, count-in and the playhead from it. Play,
pause, seek and the mix's settings are commands from the page. Changing mix (or editing one) never
restarts playback: the engine takes the new settings on the next block.

Count-in plays **only from the top of the song** (the user's call), as today: before the song's first
downbeat when playback starts at the beginning; pausing, resuming or jumping continues straight away.
The clicks are the ones the CLI makes today (`countin.py`: two synthesized stick sounds, accent on the
one, "ONE . TWO . one two three four" for two bars) at the song's tempo times the mix's tempo, before
the song's first downbeat; the song itself starts where the song file says it starts (intro cut).
The page's count-in numbers follow the engine's position as today. **Builder's call:** port the click
synthesis to Rust, or have the CLI write the two click sounds into the bundle.

Loudness (**my call**, from the builder check): a live mix can't be normalized ahead like today's files,
so the engine ends in a gentle limiter with a ceiling just under full scale (−1 dBFS, as the CLI's mixes
use): nothing clips, and switching mixes never jumps in level. MP3 exports go through the same limiter
so a file sounds like what was heard. Level changes ramp over a few milliseconds.

### Chords in another key

The page shows chords, key and shapes moved with the mix's key, as today. Since any mix can now be at
any key, the song file carries the transposition for **every** key −12…+12 (key name, every chord name
moved, and the finger shapes of all moved chords), built by the CLI with the existing rules
(`transpose_key`, `transpose_chord`, `_shape`). The page looks them up as today.

### Edit mode and song editing (layout to be mocked up and approved before building)

- **Play mode** (default): the left bar lists the mixes; clicking one plays it, keeping the place in
  the song (as today).
- **Edit toggle** at the top of the mix list (iOS/Reminders-style "Edit" ↔ "Done"). While on:
  - the list shows each mix with a rename field and a ⋯ menu (duplicate, delete), and **+ New mix**
    (a copy of the selected mix, named so the user renames it);
  - the main area shows the **mixer of the selected mix**: one row per instrument with level, mute and
    solo, and the mix's key, tempo and count-in. The song keeps playing and every change is heard at
    once and saved at once (no Save button);
  - the mix being edited is the one playing.
- **Song editing** is reached separately from mix editing (**Song…** in the toolbar, as mocked up) and
  ships **together with live mixes** (the user's call). It covers: where the song starts (typed, or
  "Set to playhead"), BPM (typed, or tapped), re-detecting chords, building the GarageBand project
  (key chosen there), and deleting the song. No title, artist or cover editing. Changing the start or
  the BPM re-detects chords and bars in the background through the CLI (`chords --start/--bpm`, about
  20 s); the player keeps playing and takes the new timing when it's done. GarageBand projects made
  before such a change are marked out of date, with Make again.
- **Export**: from a mix's ⋯ menu, an MP3 of that mix as it's set, rendered by the CLI with the same
  quality as today's mixes (offline Rubber Band), saved in the bundle (**builder's call** on the folder,
  e.g. `exports/`) and shown in Finder.

### CLI

- `run` (and the app's Add new song): download, cover, separate, chords, song file, and the three
  default mixes; no mix files.
- Rendering stays available for export: a command that renders one mix recipe of a bundle to MP3 with
  today's quality (offline Rubber Band, count-in, intro cut). **Builder's call** whether `mix` changes to
  take a recipe or a new `export` command is added; the README follows.
- `garageband` and `--band` stay as they are.
- A one-off clean-up for existing songs: delete rendered mix files (`mixes/*.mp3|wav|flac`,
  `mixes/mixes.json`), keep stems, chords, cover and GarageBand folders and projects, add the three
  default mixes. The app runs it when it opens a song that still has rendered mixes (**builder's call**:
  ask first or just do it; deleting is cheap to redo since mixes can be exported again).

## Constraints

- Apple Silicon, macOS; the app stays a Tauri 2 + Svelte 5 app with the Rust side doing the audio.
- No AI attribution anywhere; comments explain why, not what (project rules).
- Mockups before UI is built (the user's standing rule); the edit-mode layout above is a description,
  not yet approved.
- The portable runtime (Python) still does download, separation, chords, GarageBand and exports; the
  app only needs the runtime for those, not for playing.
- The song file stays readable by older players where cheap (additive fields), but the app may require
  the new mixes file.

## Calls I made (the user can overrule)

- The −1 dBFS limiter on live playback and exports.
- Start entry by typing or "Set to playhead"; BPM by typing or tapping.
- Existing songs keep stems, chords, cover and GarageBand material; only rendered mixes go.
- Mixes in their own bundle file, not in the song file.
- Song file carries chord transpositions for every key.

## Left to the builder

The exact mixes-file format; the engine's threading and buffer sizes (the test's values worked); how
level changes are ramped; how the page and engine talk (Tauri commands and events); click synthesis
location; export command shape and folder; whether the clean-up asks; how the Mixes page from the
previous iteration is retired (it is replaced by edit mode).
