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

/** The CLI's step (1–5) from its "N/5 …" lines; 0 before the first. */
export function stepOf(lines: string[]): number {
  for (let i = lines.length - 1; i >= 0; i--) {
    const m = /^([1-5])\/5 /.exec(lines[i]);
    if (m) return Number(m[1]);
  }
  return 0;
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
