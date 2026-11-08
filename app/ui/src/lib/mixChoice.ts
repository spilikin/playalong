// What the Mixes page offers and remembers: the rows ticked last time, your own instrument levels, the
// count-in and the GarageBand stems, for every song. Key and tempo come from the mix that's playing.

import type { Strings } from './i18n.svelte';
import type { Mix } from './song';

export const PRESETS = [
  'original',
  'guide',
  'no-guitar',
  'vocals-only',
  'backing',
  'rhythm-section',
  'drums-only',
  'guitar-only',
] as const;
export const STEMS = ['vocals', 'guitar', 'bass', 'drums', 'piano', 'other'] as const;
export type Stem = (typeof STEMS)[number];
export type Levels = Record<Stem, number | null>;
/** The file name of your own mix, as the CLI writes it. */
export const MY_MIX = 'my-mix';

export interface Picks {
  presets: string[];
  myMix: boolean;
  /** dB per instrument for My mix, null for off; kept while My mix isn't ticked. */
  levels: Levels;
  count_in: 0 | 1 | 2;
  garageband: boolean;
}

/** Matches `MixChoice` in app/src-tauri/src/maker.rs. */
export interface MixChoice {
  presets: string[];
  custom: Levels | null;
  transpose: number;
  tempo: number;
  count_in: 0 | 1 | 2;
  garageband: boolean;
}

export interface Made {
  mixes: Map<string, Mix>;
  /** The GarageBand project of this key, relative to the song folder. */
  garageband: string | null;
}

export const DEFAULT_PICKS: Picks = {
  presets: ['guide', 'no-guitar', 'vocals-only'],
  myMix: false,
  levels: { vocals: 0, guitar: 0, bass: 0, drums: 0, piano: 0, other: 0 },
  count_in: 1,
  garageband: false,
};

const KEY = 'playalong.mixPicks';

export function loadPicks(): Picks {
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) ?? 'null');
    if (!stored || typeof stored !== 'object') return structuredClone(DEFAULT_PICKS);
    return {
      ...structuredClone(DEFAULT_PICKS),
      ...stored,
      levels: { ...DEFAULT_PICKS.levels, ...stored.levels },
    };
  } catch {
    return structuredClone(DEFAULT_PICKS);
  }
}

export function savePicks(picks: Picks) {
  try {
    localStorage.setItem(KEY, JSON.stringify(picks));
  } catch {
    // Storage can be unavailable; the page then starts from the defaults next time.
  }
}

/** Names of what Make would make in this version: the ticked rows it doesn't have yet. */
export function toMake(picks: Picks, made: Made, s: Strings): string[] {
  return [
    ...picks.presets.filter((p) => !made.mixes.has(p)).map((p) => s.mixNames[p]?.[0] ?? p),
    ...(picks.myMix && !made.mixes.has(MY_MIX) ? [s.myMix] : []),
    ...(picks.garageband && !made.garageband ? [s.garageBandProject] : []),
  ];
}

export function toChoice(picks: Picks, made: Made, transpose: number, tempo: number): MixChoice {
  return {
    presets: PRESETS.filter((p) => picks.presets.includes(p) && !made.mixes.has(p)),
    custom: picks.myMix && !made.mixes.has(MY_MIX) ? { ...picks.levels } : null,
    transpose,
    tempo,
    count_in: picks.count_in,
    garageband: picks.garageband && !made.garageband,
  };
}
