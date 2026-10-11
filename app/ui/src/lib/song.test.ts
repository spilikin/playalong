import { describe, expect, it } from 'vitest';
import {
  chordLabel,
  countAt,
  defaultMix,
  groupMixes,
  indexAt,
  mixLabel,
  mixTime,
  sheetBars,
  songTime,
  upcoming,
  type ChordSpan,
  type Mix,
  type Song,
} from './song';

const counted: Mix = {
  file: 'mixes/s - no-guitar.mp3',
  name: 'no-guitar',
  tempo: 1,
  source_offset: 20,
  count_in: {
    bars: 1,
    clicks: [0.25, 0.75, 1.25, 1.75].map((time, i) => ({ time, accent: i === 0, count: i + 1 })),
    downbeat: 2.25,
  },
};
const slow: Mix = { ...counted, file: 'mixes/s - backing @80%.mp3', name: 'backing', tempo: 0.8 };
const old: Mix = { file: 'mixes/s - guide.mp3', name: 'guide', tempo: 1, source_offset: null, count_in: null };

const song = {
  format: 'playalong-song',
  version: 1,
  title: 'S',
  artist: null,
  key: 'C major',
  tempo: { bpm: 120, confidence: 0.6, source: 'detected', beats_per_bar: 4 },
  song_start: { seconds: 21.9, source: 'stems' },
  beats: [21.75, 22.25, 22.75, 23.25, 23.75, 24.25, 24.75, 25.25, 25.75, 26.25],
  bars: [22.25, 24.25],
  chords: [
    { start: 21.75, end: 22.25, name: 'N', root: null, quality: null },
    { start: 22.25, end: 23.25, name: 'C', root: 'C', quality: 'major' },
    { start: 23.25, end: 26.25, name: 'Am', root: 'A', quality: 'minor' },
  ],
  chord_shapes: {},
  mixes: [old, slow, counted],
  audio: null,
} as unknown as Song;

describe('timing', () => {
  it('maps mix time to song time through the offset and tempo, and back', () => {
    expect(songTime(counted, 2.25, song)).toBeCloseTo(22.25);
    expect(songTime(slow, 2.5, song)).toBeCloseTo(22);
    expect(mixTime(slow, 22, song)).toBeCloseTo(2.5);
  });

  it('falls back to the song start for mixes rendered before timing was recorded', () => {
    expect(songTime(old, 1, song)).toBeCloseTo(22.9);
  });

  it('finds the last item at or before a time', () => {
    expect(indexAt([1, 2, 3], 0.5)).toBe(-1);
    expect(indexAt([1, 2, 3], 2)).toBe(1);
    expect(indexAt([1, 2, 3], 9)).toBe(2);
  });
});

describe('count-in', () => {
  it('shows each number from its click until the next, then the song takes over', () => {
    expect(countAt(counted, 0.1)).toEqual({ phase: 'ready' });
    expect(countAt(counted, 0.3)).toEqual({ phase: 'count', count: 1, accent: true, index: 0 });
    expect(countAt(counted, 1.8)).toEqual({ phase: 'count', count: 4, accent: false, index: 3 });
    expect(countAt(counted, 2.25)).toEqual({ phase: 'song' });
  });

  it('a mix without a count-in is always in the song', () => {
    expect(countAt(old, 0)).toEqual({ phase: 'song' });
  });
});

describe('mixes', () => {
  it('opens the full-speed guide mix first', () => {
    const guide = { ...counted, file: 'mixes/s - guide.mp3', name: 'guide' };
    const slowGuide = { ...guide, file: 'mixes/s - guide @80%.mp3', tempo: 0.8 };
    expect(defaultMix([counted, slowGuide, guide])).toBe(guide);
    expect(defaultMix([counted, slow])).toBe(counted);
    expect(defaultMix([old])).toBe(old);
  });

  it('labels mixes for the picker', () => {
    expect(mixLabel(counted)).toBe('No guitar');
    expect(mixLabel(slow)).toBe('Backing · 80%');
    expect(mixLabel({ ...old, file: 'mixes/s - guide.wav' })).toBe('Guide · WAV');
  });

  it('puts the four main mixes first, one each at full speed, and the rest after', () => {
    const mix = (name: string, rest = '') => ({ ...counted, file: `mixes/s - ${name}${rest}.mp3`, name });
    const guideWav = { ...mix('guide'), file: 'mixes/s - guide.wav' };
    const slowOriginal = { ...mix('original', ' @80%'), tempo: 0.8 };
    const { main, more } = groupMixes([
      mix('backing'), guideWav, mix('vocals-only'), slowOriginal, mix('guide'), mix('original'),
    ]);
    expect(main.map((m) => m.file)).toEqual([
      'mixes/s - original.mp3', 'mixes/s - guide.mp3', 'mixes/s - vocals-only.mp3',
    ]);
    expect(more.map((m) => m.file)).toEqual(['mixes/s - backing.mp3', 'mixes/s - guide.wav', 'mixes/s - original @80%.mp3']);
  });
});

describe('sheet', () => {
  it('splits the song into bars of beat cells naming chords where they start', () => {
    const bars = sheetBars(song);
    expect(bars.map((b) => b.start)).toEqual([22.25, 24.25]);
    expect(bars[0].cells.map((c) => c.label)).toEqual(['C', '', 'Am', '']);
    expect(bars[1].cells.map((c) => c.label)).toEqual(['Am', '', '', '']);
    expect(bars[1].cells[0].carried).toBe(true);
    expect(bars[0].chords).toEqual(['C', 'Am']);
    expect(bars[1].cells.map((c) => c.time)).toEqual([24.25, 24.75, 25.25, 25.75]);
  });
});

describe('chord row', () => {
  const spans = (names: string[]) =>
    names.map((name, i) => ({ start: i, end: i + 1, name, root: null, quality: null }) as ChordSpan);

  it('lists the chords after the current one, skipping no-chord and repeats', () => {
    const chords = spans(['C', 'G', 'N', 'G', 'Am', 'F', 'C', 'G']);
    expect(upcoming(chords, 0.5, 4)).toEqual(['G', 'Am', 'F', 'C']);
    expect(upcoming(chords, 6.5, 4)).toEqual(['G']);
  });

  it('before the song starts, the first chords are what is coming', () => {
    expect(upcoming(spans(['C', 'G']), -3, 4)).toEqual(['C', 'G']);
  });

  it('writes flats and sharps the way a chart does', () => {
    expect(chordLabel('Bbm')).toBe('B♭m');
    expect(chordLabel('F#')).toBe('F♯');
    expect(chordLabel('Gb')).toBe('G♭');
    expect(chordLabel('N')).toBe('N.C.');
  });
});
