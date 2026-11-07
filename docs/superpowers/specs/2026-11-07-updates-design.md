# Playalong updates: two channels

## Why

Playalong should work on a bandmate's Mac with nothing installed by hand: install the app once, and it
fetches everything it needs to make songs and keeps it current. The parts change at very different
speeds, so each updates on its own and nobody downloads 500 MB because YouTube changed something.

## The parts and their two channels

| part | contents | packed size | changes | comes from |
|---|---|---|---|---|
| **App** | Playalong.app *and the playalong Python code* | ~15 MB | every feature | channel 1: Tauri updater |
| **Runtime** | Python 3.12, third-party packages (PyTorch, numpy, pedalboard…), ffmpeg/ffprobe/deno + libs | ~150 MB | when dependencies change (months) | channel 2: `manifest.json` |
| **Model** | BS-RoFormer separation weights | ~340 MB | almost never | channel 2, a file of its own so runtime updates skip it |
| **Downloader** | yt-dlp + yt-dlp-ejs | ~3 MB | every few days | PyPI, where yt-dlp publishes its releases; no channel to maintain |

The one change from what is built today: **the playalong Python code moves out of the runtime and into
the app bundle** (it is ~300 KB of source). The app and the CLI that writes its song files then always
match, a code fix ships with an app update, and the runtime only changes when a dependency does.

## How each updates

Both channels live on GitHub Releases of `spilikin/playalong`. One rolling release, `updates`, holds the
two small JSON files the app polls; versioned releases hold the big files, uploaded once each.

- **App** – the Tauri updater plugin reads `updates/latest.json` (Tauri's own format: version, notes,
  URL of the `.app.tar.gz`, signature). Updates are signed with a minisign key the build Mac keeps;
  the public key is in the app. The app checks at launch and offers "Restart to update".
- **Runtime + model** – `updates/manifest.json` (what `runtime/package.py` writes now) names the
  newest runtime and model. The app installs into `~/Library/Application Support/dev.playalong/`, only
  downloads what changed, verifies sha256, unpacks into staging and swaps in whole (built:
  `app/src-tauri/src/runtime.rs`). Each app release states the runtime *series* it needs (bumped when
  the Python code needs a new dependency), so an old app never picks a runtime it can't drive.
- **Downloader** – not a channel: the app runs the runtime's `playalong update-downloader` (built), which
  installs the newest yt-dlp and yt-dlp-ejs from PyPI into the runtime's `downloader/` folder, ahead of
  the bundled ones. The app does this at most once a day before a YouTube download, and again when a
  download fails. A new runtime starts without it, since it brings a newer yt-dlp of its own.

## First run on a new Mac

1. Download Playalong from the GitHub release page, drag it to Applications.
2. The app finds no runtime and offers to set it up: ~490 MB (runtime + model), with progress.
3. From then on, updates happen in the background with a note in the toolbar.

## Decisions for you

1. **Apple notarisation.** Without an Apple Developer ID ($99/year) the *first* install from the
   browser says "Apple could not verify Playalong"; the user opens it once via right-click > Open or
   System Settings. Updates after that are not affected (the updater isn't a browser). Default:
   no Developer ID, and the README explains the right-click.

## Builder's calls

- Runtime versions stay date-based; runtime series is an integer in `runtime.json` and the manifest.
- The app's CLI code is run by the runtime's Python with the bundled source on `sys.path`, i.e.
  `bin/playalong` takes the code location from the app.
- UI for setup/progress and "make a song from a link" comes as a mockup before it is built.
- Publishing (push, releases, signing key creation) waits for an explicit go.

## Not in scope

Intel Macs, Windows, partial (delta) downloads, auto-updating the app without asking.
