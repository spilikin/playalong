import { beforeEach, describe, expect, it } from 'vitest';
import { STRINGS } from './i18n.svelte';
import { DEFAULT_PICKS, loadPicks, savePicks, toChoice, toMake, type Picks } from './mixChoice';

const s = STRINGS.en;
const nothingMade = { mixes: new Map(), garageband: null };

describe('what the Mixes page remembers', () => {
  beforeEach(() => localStorage.clear());

  it('starts from the main practice mixes, then remembers the last picks for every song', () => {
    expect(loadPicks()).toEqual(DEFAULT_PICKS);
    const mine: Picks = {
      ...DEFAULT_PICKS,
      presets: ['backing'],
      count_in: 2,
      garageband: true,
    };
    savePicks(mine);
    expect(loadPicks()).toEqual(mine);
  });

  it('falls back to the defaults when what is stored is unreadable or from an older app', () => {
    localStorage.setItem('playalong.mixPicks', '{oops');
    expect(loadPicks()).toEqual(DEFAULT_PICKS);
    localStorage.setItem('playalong.mixPicks', JSON.stringify({ presets: ['guide'] }));
    expect(loadPicks()).toEqual({ ...DEFAULT_PICKS, presets: ['guide'] });
  });
});

describe('what gets made', () => {
  const picks: Picks = {
    ...DEFAULT_PICKS,
    presets: ['guide', 'vocals-only'],
    myMix: true,
    garageband: true,
  };

  it('leaves out what the version already has', () => {
    const made = { mixes: new Map([['guide', {} as never]]), garageband: 'mixes/x.band' };
    expect(toMake(picks, made, s)).toEqual(['Vocals only', 'My mix']);
    const choice = toChoice(picks, made, -2, 0.9);
    expect(choice).toMatchObject({
      presets: ['vocals-only'],
      transpose: -2,
      tempo: 0.9,
      garageband: false,
    });
    expect(choice.custom).toEqual(DEFAULT_PICKS.levels);
  });

  it('makes GarageBand stems alone too', () => {
    const only: Picks = {
      ...DEFAULT_PICKS,
      presets: [],
      myMix: false,
      garageband: true,
    };
    expect(toMake(only, nothingMade, s)).toEqual(['GarageBand project']);
    expect(toChoice(only, nothingMade, 0, 1)).toMatchObject({
      presets: [],
      custom: null,
      garageband: true,
    });
  });
});
