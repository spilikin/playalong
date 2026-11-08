// The song file the playalong CLI writes (`<track>/<track>.playalong`), and the timing that ties a
// playing mix to the song's beats and chords. Song times are seconds in the track's source.wav;
// mix times are seconds of the mix as it plays (count-in included, at its tempo).

export interface CountClick {
  time: number;
  accent: boolean;
  count: number;
}

export interface CountIn {
  bars: number;
  clicks: CountClick[];
  downbeat: number;
}

/** How a playing mix lines up with the song (see liveMix in mixes.ts). */
export interface Mix {
  tempo: number;
  /** Semitones the mix is moved by. */
  transpose?: number;
  /** Song time at the start of the mix; null falls back to the song start. */
  source_offset: number | null;
  count_in: CountIn | null;
}

export interface ChordSpan {
  start: number;
  end: number;
  name: string;
  root: string | null;
  quality: 'major' | 'minor' | null;
}

export interface Shape {
  /** Low E to high e; -1 muted, 0 open. */
  frets: number[];
  fingers: number[];
  barre: { fret: number; strings: [number, number] } | null;
}

export interface Song {
  format: string;
  version: number;
  title: string;
  artist: string | null;
  key: string | null;
  tempo: {
    bpm: number;
    confidence: number | null;
    source: string | null;
    beats_per_bar: number;
    /** The beat the count-in leads into (song file version 2). */
    beat?: number | null;
  } | null;
  song_start: { seconds: number; source: string | null } | null;
  beats: number[];
  bars: number[];
  chords: ChordSpan[] | null;
  chord_shapes: Record<string, Shape>;
  /** For every other key ("-12"…"+12"): the key and every chord name moved, with shapes in chord_shapes. */
  transpositions?: Record<string, { key: string; chords: Record<string, string> }>;
  /** GarageBand stems, one folder per key they were made in, the project built from them, and whether a
   * later change of start or tempo left that project behind. */
  garagebands?: { folder: string; bpm: number | null; transpose: number; project?: string; outdated?: boolean }[];
  audio: { file: string; sample_rate: number; duration: number } | null;
  /** Missing in song files written before the CLI fetched covers. */
  cover?: { file: string; source: string | null; album: string | null } | null;
}

export interface OpenedSong {
  folder: string;
  file: string;
  song: Song;
}

const signed = (n: number) => (n > 0 ? `+${n}` : String(n));

/** The song as heard in `mix`: a transposed mix gets the key and chord names moved with it. */
export function forMix(song: Song, mix: Mix | undefined): Song {
  const moved = mix?.transpose ? song.transpositions?.[signed(mix.transpose)] : undefined;
  if (!moved) return song;
  const rename = (name: string) => moved.chords[name] ?? name;
  return {
    ...song,
    key: moved.key,
    chords:
      song.chords?.map((c) => {
        if (c.name === 'N') return c;
        const name = rename(c.name);
        return { ...c, name, root: c.quality === 'minor' ? name.slice(0, -1) : name };
      }) ?? null,
  };
}

function offset(mix: Mix, song: Song): number {
  return mix.source_offset ?? song.song_start?.seconds ?? 0;
}

export function songTime(mix: Mix, mixSeconds: number, song: Song): number {
  return offset(mix, song) + mixSeconds * mix.tempo;
}

export function mixTime(mix: Mix, songSeconds: number, song: Song): number {
  return (songSeconds - offset(mix, song)) / mix.tempo;
}

/** The last index whose time is at or before `t`, or -1. */
export function indexAt(times: number[], t: number): number {
  let lo = 0;
  let hi = times.length - 1;
  let found = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= t) {
      found = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return found;
}

export function chordIndexAt(chords: ChordSpan[], t: number): number {
  const i = indexAt(
    chords.map((c) => c.start),
    t,
  );
  return i >= 0 && t < chords[i].end ? i : -1;
}

export type CountState =
  | { phase: 'ready' }
  | { phase: 'count'; count: number; accent: boolean; index: number }
  | { phase: 'song' };

/** Where a mix is relative to its count-in: before the first click, on a numbered click, or in the song. */
export function countAt(mix: Mix, mixSeconds: number): CountState {
  const count = mix.count_in;
  if (!count || mixSeconds >= count.downbeat) return { phase: 'song' };
  const index = indexAt(
    count.clicks.map((c) => c.time),
    mixSeconds,
  );
  if (index < 0) return { phase: 'ready' };
  const click = count.clicks[index];
  return { phase: 'count', count: click.count, accent: click.accent, index };
}

export interface BeatCell {
  time: number;
  /** The chord's name on the beat where it starts, else empty. */
  label: string;
  /** A chord carried over from the previous bar, named again on its first beat. */
  carried: boolean;
}

export interface SheetBar {
  start: number;
  cells: BeatCell[];
  /** Chords sounding in the bar, in order, without "N". */
  chords: string[];
}

export function sheetBars(song: Song): SheetBar[] {
  const chords = song.chords ?? [];
  const nameAt = (t: number) => {
    const i = chordIndexAt(chords, t + 1e-6);
    return i >= 0 ? chords[i].name : 'N';
  };
  const perBar = song.tempo?.beats_per_bar ?? 4;
  let previous: string | null = null;
  return song.bars.map((start) => {
    const first = indexAt(song.beats, start + 1e-6);
    const times = song.beats.slice(first, first + perBar);
    const cells: BeatCell[] = [];
    const inBar: string[] = [];
    times.forEach((time, i) => {
      const name = nameAt(time);
      const starts = i === 0 || name !== nameAt(times[i - 1]);
      cells.push({ time, label: starts ? (name === 'N' ? 'N.C.' : name) : '', carried: i === 0 && name === previous });
      if (starts && name !== 'N' && !inBar.includes(name)) inBar.push(name);
      previous = name;
    });
    return { start, cells, chords: inBar };
  });
}

/** The next `count` chords after the one sounding at `t` (or from the start, before the song), without
 * no-chord stretches or a chord repeating itself across one. */
export function upcoming(chords: ChordSpan[], t: number, count: number): string[] {
  const out: string[] = [];
  let last = chords[chordIndexAt(chords, t)]?.name;
  for (const c of chords) {
    if (c.start <= t || c.name === 'N' || c.name === last) continue;
    out.push(c.name);
    last = c.name;
    if (out.length === count) break;
  }
  return out;
}

/** "Bbm" as a chart writes it: "B♭m"; "N" is no chord. */
export function chordLabel(name: string): string {
  if (name === 'N') return 'N.C.';
  return name.replace(/^([A-G])b/, '$1♭').replace('#', '♯');
}
