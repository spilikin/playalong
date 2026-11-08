// What the app knows about its audio tools, its library and the song being made, shared by the start
// screens, the Library and the player's sidebar: a song keeps being made while another one plays.

import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import type { OpenedSong } from './song';
import type { Check, Installed, LibrarySong, Progress } from './maker';
import type { MixChoice } from './mixChoice';

export interface Job {
  source: string;
  lines: string[];
  running: boolean;
  error: string;
  /** The finished song, until it's opened. */
  made: OpenedSong | null;
}

/** Mixes being made for a song, in the background while it plays. */
export interface MixJob {
  folder: string;
  count: number;
  lines: string[];
  running: boolean;
  error: string;
  /** The song with its new mixes, until the player has taken it. */
  made: OpenedSong | null;
}

// Enough of the CLI's output to see where it is; the whole log would only grow.
const KEEP_LINES = 200;

export const maker = $state({
  ready: false,
  installed: null as Installed | null,
  check: null as Check | null,
  installing: false,
  progress: {} as Partial<Record<Progress['stage'], Progress>>,
  library: '',
  songs: [] as LibrarySong[],
  job: null as Job | null,
  mixJob: null as MixJob | null,
  /** An audio file dropped on the Library, waiting in the link field. */
  draft: '',
  error: '',
});

let listening = false;

async function listenOnce() {
  if (listening) return;
  listening = true;
  await listen<Progress>('runtime-progress', (e) => {
    maker.progress[e.payload.stage] = e.payload;
  });
  await listen<{ line: string }>('make-song-line', (e) => {
    const job = maker.job;
    if (!job) return;
    // A progress bar redraws its line; keep only its latest state.
    const last = job.lines.at(-1);
    if (last && /\d%|remaining/.test(last) && /\d%|remaining/.test(e.payload.line)) job.lines.pop();
    job.lines.push(e.payload.line);
    if (job.lines.length > KEEP_LINES) job.lines.splice(0, job.lines.length - KEEP_LINES);
  });
  await listen<{ line: string }>('make-mixes-line', (e) => {
    const job = maker.mixJob;
    if (!job) return;
    job.lines.push(e.payload.line);
    if (job.lines.length > KEEP_LINES) job.lines.splice(0, job.lines.length - KEEP_LINES);
  });
}

export async function refreshLibrary() {
  if (!maker.library) return;
  maker.songs = (await invoke<LibrarySong[] | null>('list_library', { library: maker.library }).catch(() => null)) ?? [];
}

/** What's installed, the library, and (in the background) whether the tools have an update. */
export async function startMaker() {
  await listenOnce().catch(() => {});
  try {
    const status = await invoke<{ installed: Installed | null; busy: boolean } | null>('runtime_status');
    maker.installed = status?.installed ?? null;
    maker.library = (await invoke<string | null>('default_library')) ?? '';
    await refreshLibrary();
  } catch (e) {
    maker.error = String(e);
  }
  maker.ready = true;
  // Offline is fine: the app plays songs without it, and setting up says what went wrong.
  maker.check = await invoke<Check>('runtime_check').catch(() => null);
}

export async function installTools() {
  maker.installing = true;
  maker.progress = {};
  maker.error = '';
  try {
    maker.installed = await invoke<Installed | null>('runtime_install');
    maker.check = await invoke<Check>('runtime_check').catch(() => null);
  } catch (e) {
    maker.error = String(e);
  } finally {
    maker.installing = false;
  }
}

export async function makeSong(source: string) {
  maker.job = { source: source.trim(), lines: [], running: true, error: '', made: null };
  const job = maker.job;
  try {
    job.made = await invoke<OpenedSong>('make_song', { source: job.source, library: maker.library });
  } catch (e) {
    job.error = String(e);
  } finally {
    job.running = false;
    await refreshLibrary();
  }
}

export async function stopSong() {
  await invoke('cancel_make').catch(() => {});
}

export function clearJob() {
  maker.job = null;
}

export async function makeMixes(folder: string, choice: MixChoice, count: number) {
  maker.mixJob = { folder, count, lines: [], running: true, error: '', made: null };
  const job = maker.mixJob;
  try {
    job.made = await invoke<OpenedSong>('make_mixes', { folder, choice });
  } catch (e) {
    job.error = String(e);
  } finally {
    job.running = false;
    await refreshLibrary();
  }
}

export function clearMixJob() {
  maker.mixJob = null;
}

/** Mix files written so far: the CLI prints each one's path as it's done. */
export const mixesWritten = (lines: string[]) => lines.filter((l) => /^ {2}\//.test(l)).length;
