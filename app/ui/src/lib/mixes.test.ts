import { describe, expect, it } from 'vitest';
import { STRINGS } from './i18n.svelte';
import { DEFAULT_MIXES, describeMix, liveMix, newMixFrom, presetLevels, type Recipe } from './mixes';

const s = STRINGS.en;
const [original, guide, noGuitar] = DEFAULT_MIXES;

describe('mixes', () => {
  it('describes a mix in a line', () => {
    expect(describeMix(original, s)).toBe('as recorded');
    expect(describeMix(guide, s)).toBe('guitar −15 dB');
    expect(describeMix(noGuitar, s)).toBe('guitar off');
    const band: Recipe = {
      ...noGuitar,
      levels: { ...noGuitar.levels, vocals: -6 },
      transpose: -2,
      tempo: 0.9,
    };
    expect(describeMix(band, s)).toBe('vocals −6 dB, guitar off · −2 · 90%');
    expect(describeMix({ ...original, solo: ['drums', 'bass'] }, s)).toBe('only bass, drums');
  });

  it('copies a mix as a new one with a name and id of its own', () => {
    const copy = newMixFrom(guide, DEFAULT_MIXES, s);
    expect(copy).toMatchObject({ name: 'Guide copy', levels: guide.levels });
    expect(DEFAULT_MIXES.map((m) => m.id)).not.toContain(copy.id);
    const again = newMixFrom(guide, [...DEFAULT_MIXES, copy], s);
    expect(again.name).toBe('Guide copy 2');
    expect(again.id).not.toBe(copy.id);
  });

  it('plays on the timeline the engine gives it', () => {
    const timeline = { tempo: 0.8, source_offset: 20, count_in: null };
    expect(liveMix({ ...guide, transpose: -2 }, timeline)).toEqual({
      tempo: 0.8,
      transpose: -2,
      source_offset: 20,
      count_in: null,
    });
  });

  it('starts from a preset by its levels', () => {
    expect(presetLevels('vocals-only')).toEqual({
      levels: { vocals: 0, guitar: 0, bass: 0, drums: 0, piano: 0, other: 0 },
      mute: ['guitar', 'bass', 'drums', 'piano', 'other'],
    });
    expect(presetLevels('guide').levels.guitar).toBe(-15);
  });
});
