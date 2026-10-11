import argparse
import sys
from pathlib import Path

from playalong.mix import MAIN_PRESETS, PRESET_HELP, PRESETS, make_mixes, parse_gain


def _ingest(source: str, library: Path) -> Path:
    from playalong.download import fetch, import_file

    path = Path(source).expanduser()
    if path.is_file():
        return import_file(path, library)
    if path.is_dir() and (path / "source.wav").exists():
        return path
    return fetch(source, library)


def _update_song(track_dir: Path, chords=None) -> None:
    from playalong.song import write_song

    print(f"Song file: {write_song(track_dir, chords)}")


def _summary(track_dir: Path) -> None:
    from playalong.song import read_song, song_path

    song = read_song(track_dir) or {}
    print(f"\nDone: {track_dir}")
    print(f"  song file    {song_path(track_dir).name}  (open this folder in the player)")
    print(f"  mixes        {len(song.get('mixes', []))} in mixes/")
    print(f"  stems        {len(song.get('stems', {}))} in stems/")
    if song.get("cover"):
        print(f"  cover        {song['cover']['album'] or 'video thumbnail'}")
    if song.get("chords"):
        print(f"  chords       {song.get('key')}, chord sheet in chords.html")
    if song.get("garageband"):
        print(f"  GarageBand   {song['garageband']['folder']}/")


def _detect_chords(track_dir: Path, start: float | None, bpm: float | None):
    from playalong.chords import track_chords

    try:
        return track_chords(track_dir, start, bpm)
    except ValueError as e:
        print(f"No chords: {e}")
        return None


def _presets(args: argparse.Namespace) -> list[str]:
    """The four main mixes unless told which (--all for every preset). A custom mix (-g) replaces the
    presets unless some are named too."""
    if args.gain:
        return args.preset or []
    if args.preset:
        return args.preset
    return list(PRESETS) if args.all else MAIN_PRESETS


def _mix(args: argparse.Namespace, track_dir: Path) -> None:
    presets = _presets(args)
    custom = dict(parse_gain(g) for g in args.gain) if args.gain else None
    if not 0.5 <= args.tempo <= 2.0:
        raise SystemExit("--tempo must be between 0.5 and 2.0")
    if args.bpm is not None and not 30 <= args.bpm <= 300:
        raise SystemExit("--bpm must be between 30 and 300")
    print(f"Writing mixes for {track_dir.name}:")
    start = 0.0 if args.no_trim else args.start
    try:
        make_mixes(track_dir, presets, custom, args.name, args.format, args.tempo, start, args.count_in, args.bpm)
    except ValueError as e:
        raise SystemExit(str(e)) from e
    if args.garageband:
        from playalong.garageband import export_stems

        export_stems(track_dir, start, args.bpm)


def _add_mix_options(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("mix options")
    g.add_argument("-p", "--preset", action="append", choices=sorted(PRESETS),
                   help=f"preset to render (repeatable; default: {', '.join(MAIN_PRESETS)})")
    g.add_argument("--all", action="store_true", help="render every preset")
    g.add_argument("-g", "--gain", action="append", metavar="STEM=DB|off",
                   help="custom mix, e.g. -g guitar=-12 -g vocals=off (repeatable)")
    g.add_argument("--name", default="custom", help="file label for the custom mix")
    g.add_argument("-f", "--format", choices=["mp3", "wav", "flac"], default="mp3")
    g.add_argument("-t", "--tempo", type=float, default=1.0,
                   help="playback speed, pitch preserved (e.g. 0.8 for practice)")
    count = g.add_mutually_exclusive_group()
    count.add_argument("-c", "--count-in", type=int, default=1, choices=[1, 2], metavar="BARS",
                       help="bars of drumstick clicks before the song, at its tempo: 1 or 2 (default: 1)")
    count.add_argument("--no-count-in", dest="count_in", action="store_const", const=0,
                       help="start straight into the song")
    g.add_argument("--bpm", type=float,
                   help="the song's tempo for --count-in, if detection gets it wrong (saved for the track)")
    g.add_argument("--garageband", action="store_true",
                   help="also write the stems for a GarageBand project (no count-in, no tempo change)")
    trim = g.add_mutually_exclusive_group()
    trim.add_argument("-s", "--start", type=float, metavar="SECONDS",
                      help="where the song starts, overriding intro detection")
    trim.add_argument("--no-trim", action="store_true", help="keep the video intro")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="playalong", description="Turn songs into guitar playalong tracks.")
    parser.add_argument("-l", "--library", type=Path, default=Path("library"),
                        help="where tracks are stored (default: ./library)")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="everything in one go: download/import, cover, separate, mixes, chords, song file")
    run.add_argument("source", help="YouTube URL, audio file, or existing track directory")
    run.add_argument("--device", help="torch device: cuda, mps or cpu (default: best available)")
    _add_mix_options(run)

    dl = sub.add_parser("download", help="download or import audio only")
    dl.add_argument("source", help="YouTube URL or audio file")

    sep = sub.add_parser("separate", help="split a track into stems")
    sep.add_argument("track", type=Path, help="track directory")
    sep.add_argument("--device")
    sep.add_argument("--force", action="store_true", help="re-run even if stems exist")

    mix = sub.add_parser("mix", help="render playalong mixes from existing stems")
    mix.add_argument("track", type=Path, help="track directory")
    _add_mix_options(mix)

    ch = sub.add_parser("chords", help="detect the chords (writes chords.html, chords.txt and chords.lab)")
    ch.add_argument("track", type=Path, help="track directory")
    ch.add_argument("--bpm", type=float, help="the song's tempo, if detection gets it wrong (saved for the track)")
    ch_trim = ch.add_mutually_exclusive_group()
    ch_trim.add_argument("-s", "--start", type=float, metavar="SECONDS",
                         help="where the song starts, overriding intro detection")
    ch_trim.add_argument("--no-trim", action="store_true", help="include the video intro")

    cov = sub.add_parser("cover", help="fetch the album cover (cover.jpg)")
    cov.add_argument("track", type=Path, help="track directory")
    cov.add_argument("-q", "--query", help='search for this instead of the guess from the title, e.g. "Artist Song"')
    cov.add_argument("--force", action="store_true", help="replace the cover the track has")

    sub.add_parser("presets", help="list mix presets")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.command == "presets":
        for name in PRESETS:
            print(f"{name:16} {PRESET_HELP[name]}")
        return

    from playalong.cover import fetch_cover

    if args.command == "cover":
        fetch_cover(args.track, args.query, force=args.force or bool(args.query))
        _update_song(args.track)
        return

    if args.command == "download":
        track_dir = _ingest(args.source, args.library)
        print(track_dir)
        fetch_cover(track_dir)
        _update_song(track_dir)
        return

    if args.command == "chords":
        from playalong.chords import format_chart, track_chords

        try:
            result = track_chords(args.track, 0.0 if args.no_trim else args.start, args.bpm)
        except ValueError as e:
            raise SystemExit(str(e)) from e
        print(format_chart(result), end="")
        print(f"Saved to {args.track / 'chords.html'} (chord sheet), chords.txt and chords.lab")
        _update_song(args.track, result)
        return

    if args.command == "mix":
        _mix(args, args.track)
        _update_song(args.track)
        return

    from playalong.separate import separate

    if args.command == "separate":
        separate(args.track, args.device, args.force)
        _update_song(args.track)
        return

    # run: everything from a link (or file) to a song the player can open; finished steps are skipped.
    print("1/5 Download")
    track_dir = _ingest(args.source, args.library)
    print("2/5 Cover")
    fetch_cover(track_dir)
    print("3/5 Separate")
    separate(track_dir, args.device)
    print("4/5 Mix")
    _mix(args, track_dir)
    print("5/5 Chords")
    chords = _detect_chords(track_dir, 0.0 if args.no_trim else args.start, args.bpm)
    _update_song(track_dir, chords)
    _summary(track_dir)


if __name__ == "__main__":
    sys.exit(main())
