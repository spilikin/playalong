// What the New mixes panel offers, and the choice it remembers: the last one made, for every song, since
// people tend to practise the same way (no guitar, a tone lower) from song to song.

import type { Strings } from './i18n.svelte';

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

/** Matches `MixChoice` in app/src-tauri/src/maker.rs. */
export interface MixChoice {
  presets: string[];
  /** The person's own mix: dB per instrument, null for off; left out = as recorded. */
  custom: Partial<Record<Stem, number | null>> | null;
  transpose: number;
  tempo: number;
  count_in: 0 | 1 | 2;
  garageband: boolean;
}

export const DEFAULT_CHOICE: MixChoice = {
  presets: ['guide', 'no-guitar', 'vocals-only'],
  custom: null,
  transpose: 0,
  tempo: 1,
  count_in: 1,
  garageband: false,
};

const KEY = 'playalong.mixChoice';

export function loadChoice(): MixChoice {
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) ?? 'null');
    return stored && typeof stored === 'object' ? { ...DEFAULT_CHOICE, ...stored } : { ...DEFAULT_CHOICE };
  } catch {
    return { ...DEFAULT_CHOICE };
  }
}

export function saveChoice(choice: MixChoice) {
  try {
    localStorage.setItem(KEY, JSON.stringify(choice));
  } catch {
    // Storage can be unavailable; the panel then starts from the defaults next time.
  }
}

export const mixCount = (choice: MixChoice) => choice.presets.length + (choice.custom ? 1 : 0);

export function mixSummary(choice: MixChoice, s: Strings): string {
  const extra = [
    choice.transpose ? (choice.transpose > 0 ? `+${choice.transpose}` : `−${-choice.transpose}`) : '',
    choice.tempo !== 1 ? `${Math.round(choice.tempo * 100)}%` : '',
  ]
    .filter(Boolean)
    .join(' ');
  const names = [...choice.presets.map((p) => s.mixNames[p]?.[0] ?? p), ...(choice.custom ? [s.myMix] : [])];
  return names.map((n) => (extra ? `${n} ${extra}` : n)).join(', ');
}
