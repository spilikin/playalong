// The song playing live (app/src-tauri/src/playback.rs): its mixes, which one plays, and where it is. The
// engine reports the position; the page draws chords, bars and the count-in from it.

import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import type { Recipe, Timeline } from './mixes';

interface Opened {
  duration: number;
  timeline: Timeline;
  mixes: Recipe[];
  current: string;
}

export const playback = $state({
  folder: '',
  mixes: [] as Recipe[],
  current: '',
  timeline: null as Timeline | null,
  mixSeconds: 0,
  duration: 0,
  playing: false,
});

let unlisten: (() => void) | undefined;
let saving: ReturnType<typeof setTimeout> | undefined;
const SAVE_AFTER = 300;

/** Follows the engine's reports for the song being opened; one listener at a time. */
async function follow() {
  unlisten?.();
  unlisten = await listen<{ mix_seconds: number; playing: boolean }>('playback-position', (e) => {
    playback.mixSeconds = e.payload.mix_seconds;
    playback.playing = e.payload.playing;
  });
}

export const currentMix = (): Recipe | undefined => playback.mixes.find((m) => m.id === playback.current);

/** Loads the song's stems into the engine; whatever played before stops. */
export async function openPlayback(folder: string, mix: string | null = null) {
  await follow().catch(() => {});
  const opened = await invoke<Opened>('playback_open', { folder, mix });
  Object.assign(playback, {
    folder,
    mixes: opened.mixes,
    current: opened.current,
    timeline: opened.timeline,
    duration: opened.duration,
    mixSeconds: 0,
    playing: false,
  });
}

export async function closePlayback() {
  playback.playing = false;
  playback.folder = '';
  await invoke('playback_close').catch(() => {});
}

export async function play() {
  playback.playing = true;
  await invoke('playback_play');
}

export async function pause() {
  playback.playing = false;
  await invoke('playback_pause');
}

export async function seek(mixSeconds: number) {
  playback.mixSeconds = Math.min(Math.max(0, mixSeconds), playback.duration || mixSeconds);
  await invoke('playback_seek', { mixSeconds: playback.mixSeconds });
}

/** Tells the engine, and moves the shown position to the same place in the song in the new mix's time, so
 * the chords don't jump until the engine's next report. */
async function apply(recipe: Recipe) {
  const old = playback.timeline;
  const timeline = await invoke<Timeline>('playback_set_mix', { recipe: $state.snapshot(recipe) });
  if (old) playback.mixSeconds = (old.source_offset + playback.mixSeconds * old.tempo - timeline.source_offset) / timeline.tempo;
  playback.timeline = timeline;
}

export async function chooseMix(id: string) {
  const recipe = playback.mixes.find((m) => m.id === id);
  if (!recipe || id === playback.current) return;
  playback.current = id;
  await apply(recipe);
}

/** The song's mixes as they are now, written shortly after the last change rather than on every slider step. */
export function saveMixes() {
  clearTimeout(saving);
  const folder = playback.folder;
  const mixes = $state.snapshot(playback.mixes);
  saving = setTimeout(() => void invoke('mixes_save', { folder, mixes }).catch(() => {}), SAVE_AFTER);
}

/** A mix changed in place: heard at once if it's the one playing, and kept. */
export async function updateMix(recipe: Recipe) {
  playback.mixes = playback.mixes.map((m) => (m.id === recipe.id ? recipe : m));
  saveMixes();
  if (recipe.id === playback.current) await apply(recipe);
}
