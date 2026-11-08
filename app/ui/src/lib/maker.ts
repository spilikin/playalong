// Making songs in the app: what the Rust side reports (see app/src-tauri/src/maker.rs and library.rs),
// and the small bits of wording the setup, Library and progress screens build from it.

import type { Lang, Strings } from './i18n.svelte';

export interface Installed {
  version: string;
  series: number;
  commit: string;
  model: string | null;
}

export interface Archive {
  file: string;
  size: number;
}

export interface Check {
  plan: { runtime: Archive | null; model: Archive | null; version: string };
  download_size: number;
}

export interface Progress {
  stage: 'runtime' | 'model' | 'unpack';
  done: number;
  total: number;
}

export interface LibrarySong {
  folder: string;
  title: string;
  artist: string | null;
  key: string | null;
  bpm: number | null;
  mixes: number;
  /** Semitones of the transposed mixes, e.g. [-2]. */
  transposed: number[];
  cover: string | null;
  /** Seconds since 1970. */
  added: number;
}

export const megabytes = (bytes: number) => Math.round(bytes / 1e6);

export function progressText(p: Progress, s: Strings): string {
  if (p.stage === 'unpack') return s.unpacking;
  return `${megabytes(p.done)} / ${megabytes(p.total)} MB`;
}

export const isYouTube = (source: string) => /^https?:\/\//.test(source.trim());

/** The CLI's step (1–4) from its "N/4 …" lines; 0 before the first. */
export function stepOf(lines: string[]): number {
  for (let i = lines.length - 1; i >= 0; i--) {
    const m = /^([1-4])\/4 /.exec(lines[i]);
    if (m) return Number(m[1]);
  }
  return 0;
}

export interface SongProgress {
  /** The CLI's step, 1–5; 0 before the first. */
  step: number;
  /** How far into this step, 0–1, or null while it can't tell (loading the model, say). */
  share: number | null;
  /** Seconds left in this step, when it says. */
  left: number | null;
  /** The whole song, 0–1. */
  overall: number;
}

// Roughly how the time splits for a typical song on Apple Silicon: splitting into instruments dominates.
const STEP_WEIGHTS = [0.1, 0.02, 0.8, 0.08];

const lastNumber = (lines: string[], pattern: RegExp) => {
  for (let i = lines.length - 1; i >= 0; i--) {
    const m = pattern.exec(lines[i]);
    if (m) return Number(m[1]);
  }
  return null;
};

/** Where `playalong run` is, from what it has printed: its steps, yt-dlp's percentages, the separation's
 * own time estimate, and the mix files as they're written. */
export function progressOf(lines: string[]): SongProgress {
  const step = stepOf(lines);
  const since = lines.slice(lines.findLastIndex((l) => /^[1-4]\/4 /.test(l)) + 1);
  let share: number | null = null;
  let left: number | null = null;
  if (step === 1) {
    const percent = lastNumber(since, /^\[download\]\s+([\d.]+)%/);
    share = percent === null ? null : percent / 100;
  } else if (step === 3) {
    const total = lastNumber(since, /Estimated total processing time for this track: ([\d.]+) seconds/);
    if (total) {
      left = lastNumber(since, /Estimated time remaining: ([\d.]+) seconds/) ?? total;
      share = Math.min(1, Math.max(0, 1 - left / total));
    }
  }
  const before = STEP_WEIGHTS.slice(0, Math.max(step - 1, 0)).reduce((a, b) => a + b, 0);
  const overall = step ? before + STEP_WEIGHTS[step - 1] * (share ?? 0) : 0;
  return { step, share, left, overall };
}

export function timeLeft(seconds: number, s: Strings): string {
  return seconds < 60 ? s.underAMinute : s.minutesLeft(Math.round(seconds / 60));
}

export function transposeLabel(semitones: number, s: Strings): string {
  if (!semitones) return s.originalKey;
  return semitones > 0 ? `+${semitones}` : `−${-semitones}`;
}

/** "Bb minor" as a chart writes it: "B♭m". */
export function keyShort(key: string | null): string {
  if (!key) return '';
  const [tonic, mode] = key.split(' ');
  return tonic.replace(/^([A-G])b/, '$1♭').replace('#', '♯') + (mode === 'minor' ? 'm' : '');
}

export function matches(song: LibrarySong, query: string): boolean {
  const q = query.trim().toLowerCase();
  return !q || [song.title, song.artist ?? ''].some((t) => t.toLowerCase().includes(q));
}

export function addedLabel(seconds: number, now: Date, lang: Lang, s: Strings): string {
  const when = new Date(seconds * 1000);
  if (when.toDateString() === now.toDateString()) return s.today;
  return new Intl.DateTimeFormat(lang === 'lv' ? 'lv' : 'en-US', { month: 'short', day: 'numeric' }).format(when);
}

/** What the sidebar's Library section shows: every song, the last week's, or the one being made. */
export type Shelf = 'all' | 'recent' | 'making';
/** What the main area shows: a Library shelf, the playing mix, or the song's own settings. */
export type Place = Shelf | 'player' | 'song';
const WEEK = 7 * 24 * 60 * 60;

export function shownSongs(songs: LibrarySong[], shelf: Shelf, query: string, now: number): LibrarySong[] {
  return songs.filter((song) => (shelf !== 'recent' || now - song.added <= WEEK) && matches(song, query));
}
