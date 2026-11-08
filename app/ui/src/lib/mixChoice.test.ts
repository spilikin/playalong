import { beforeEach, describe, expect, it } from 'vitest';
import { STRINGS } from './i18n.svelte';
import { DEFAULT_CHOICE, loadChoice, makeLabel, mixCount, mixSummary, saveChoice, type MixChoice } from './mixChoice';

const s = STRINGS.en;

describe('mix choices', () => {
  beforeEach(() => localStorage.clear());

  it('starts from the main practice mixes, then remembers the last choice for every song', () => {
    expect(loadChoice()).toEqual(DEFAULT_CHOICE);
    const mine: MixChoice = { ...DEFAULT_CHOICE, presets: ['backing'], transpose: -2, count_in: 2 };
    saveChoice(mine);
    expect(loadChoice()).toEqual(mine);
  });

  it('falls back to the defaults when what is stored is unreadable or from an older app', () => {
    localStorage.setItem('playalong.mixChoice', '{oops');
    expect(loadChoice()).toEqual(DEFAULT_CHOICE);
    localStorage.setItem('playalong.mixChoice', JSON.stringify({ presets: ['guide'] }));
    expect(loadChoice()).toEqual({ ...DEFAULT_CHOICE, presets: ['guide'] });
  });

  it('says what will be made', () => {
    const c: MixChoice = { ...DEFAULT_CHOICE, presets: ['guide', 'no-guitar'], custom: { guitar: -12 }, transpose: -2 };
    expect(mixCount(c)).toBe(3);
    expect(mixSummary(c, s)).toBe('Guide −2, No guitar −2, My mix −2');
    expect(mixSummary({ ...c, transpose: 0, tempo: 0.8, custom: null }, s)).toBe('Guide 80%, No guitar 80%');
  });

  it('makes GarageBand stems on their own too, in the chosen key', () => {
    const only: MixChoice = { ...DEFAULT_CHOICE, presets: [], garageband: true, transpose: -2 };
    expect(mixCount(only)).toBe(1);
    expect(mixSummary(only, s)).toBe('GarageBand stems −2');
    expect(makeLabel(only, s)).toBe('Make GarageBand stems');
    expect(makeLabel({ ...only, presets: ['guide'] }, s)).toBe('Make 1 mix + GarageBand');
    expect(makeLabel({ ...only, presets: ['guide', 'backing'], garageband: false }, s)).toBe('Make 2 mixes');
  });
});
