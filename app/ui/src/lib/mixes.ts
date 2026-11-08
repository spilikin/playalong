// A song's mixes as recipes (app/src-tauri/src/engine/mixer.rs, the CLI's recipes.py): what the app plays live
// and edits in place. The engine answers each with its timeline; together they're the timing the page uses.

import type { Strings } from './i18n.svelte';
import type { CountIn, Mix } from './song';

export const STEMS = ['vocals', 'guitar', 'bass', 'drums', 'piano', 'other'] as const;
export type Stem = (typeof STEMS)[number];

export interface Recipe {
  id: string;
  name: string;
  levels: Record<string, number>;
  mute: string[];
  solo: string[];
  transpose: number;
  tempo: number;
  count_in: number;
}

export interface Timeline {
  tempo: number;
  source_offset: number;
  count_in: CountIn | null;
}

const flat = () => Object.fromEntries(STEMS.map((s) => [s, 0])) as Record<string, number>;
const recipe = (id: string, name: string, levels: Partial<Record<Stem, number>> = {}, mute: Stem[] = []): Recipe => ({
  id,
  name,
  levels: { ...flat(), ...levels },
  mute,
  solo: [],
  transpose: 0,
  tempo: 1,
  count_in: 1,
});

/** Every new song's mixes, as the CLI writes them. */
export const DEFAULT_MIXES: Recipe[] = [
  recipe('original', 'Original'),
  recipe('guide', 'Guide', { guitar: -15 }),
  recipe('no-guitar', 'No guitar', {}, ['guitar']),
];

const ALL_BUT = (...keep: Stem[]) => STEMS.filter((s) => !keep.includes(s));

/** Levels and mutes of the CLI's presets, for "Start from". */
const PRESETS: Record<string, { levels?: Partial<Record<Stem, number>>; mute?: Stem[] }> = {
  original: {},
  guide: { levels: { guitar: -15 } },
  'no-guitar': { mute: ['guitar'] },
  'vocals-only': { mute: ALL_BUT('vocals') },
  backing: { mute: ['vocals', 'guitar'] },
  'rhythm-section': { mute: ['vocals', 'guitar', 'piano', 'other'] },
  'drums-only': { mute: ALL_BUT('drums') },
  'guitar-only': { mute: ALL_BUT('guitar') },
};
export const PRESET_IDS = Object.keys(PRESETS);

export function presetLevels(preset: string): { levels: Record<string, number>; mute: string[] } {
  const p = PRESETS[preset] ?? {};
  return { levels: { ...flat(), ...p.levels }, mute: [...(p.mute ?? [])] };
}

/** The timing a playing mix has, in the shape the chord and count-in helpers take. */
export function liveMix(recipe: Recipe, timeline: Timeline): Mix {
  return {
    tempo: timeline.tempo,
    transpose: recipe.transpose,
    source_offset: timeline.source_offset,
    count_in: timeline.count_in,
  };
}

const signed = (n: number) => (n > 0 ? `+${n}` : n < 0 ? `−${-n}` : '0');

/** "vocals −6 dB, guitar off · −2 · 90%": what's different from the recording, in a line. */
export function describeMix(recipe: Recipe, s: Strings): string {
  const name = (stem: string) => s.stemNames[stem as Stem].toLowerCase();
  const sound = recipe.solo.length
    ? [`${s.only} ${STEMS.filter((st) => recipe.solo.includes(st)).map(name).join(', ')}`]
    : STEMS.flatMap((st) => {
        if (recipe.mute.includes(st)) return [`${name(st)} ${s.levelOff}`];
        const db = recipe.levels[st] ?? 0;
        return db ? [`${name(st)} ${signed(db)} dB`] : [];
      });
  const parts = [sound.join(', ') || s.asRecorded];
  if (recipe.transpose) parts.push(signed(recipe.transpose));
  if (recipe.tempo !== 1) parts.push(`${Math.round(recipe.tempo * 100)}%`);
  return parts.join(' · ');
}

/** A copy to change: named "<name> copy" (numbered when taken), with an id no other mix has. */
export function newMixFrom(from: Recipe, existing: Recipe[], s: Strings): Recipe {
  const names = new Set(existing.map((m) => m.name));
  const ids = new Set(existing.map((m) => m.id));
  const base = `${from.name} ${s.copySuffix}`;
  let name = base;
  for (let n = 2; names.has(name); n++) name = `${base} ${n}`;
  const stem = from.id.replace(/-copy(-\d+)?$/, '');
  let id = `${stem}-copy`;
  for (let n = 2; ids.has(id); n++) id = `${stem}-copy-${n}`;
  // Through JSON: the mix may be a Svelte state proxy, which structuredClone refuses.
  return { ...(JSON.parse(JSON.stringify(from)) as Recipe), id, name };
}
