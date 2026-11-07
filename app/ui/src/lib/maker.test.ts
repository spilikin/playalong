import { describe, expect, it } from 'vitest';
import { STRINGS } from './i18n.svelte';
import { addedLabel, isYouTube, keyShort, matches, megabytes, progressText, stepOf, transposeLabel } from './maker';

const s = STRINGS.en;

describe('setting up', () => {
  it('reports download progress per part in MB', () => {
    expect(progressText({ stage: 'model', done: 170e6, total: 341e6 }, s)).toBe('170 / 341 MB');
    expect(progressText({ stage: 'unpack', done: 0, total: 0 }, s)).toBe('Unpacking…');
    expect(megabytes(489_600_000)).toBe(490);
  });
});

describe('making a song', () => {
  it('tells links from files', () => {
    expect(isYouTube('https://youtu.be/x')).toBe(true);
    expect(isYouTube('  https://www.youtube.com/watch?v=a ')).toBe(true);
    expect(isYouTube('/Users/a/song.wav')).toBe(false);
  });

  it('follows the CLI through its five steps', () => {
    expect(stepOf([])).toBe(0);
    expect(stepOf(['Checking for a newer YouTube downloader', '1/5 Download', 'x', '3/5 Separate', '42%'])).toBe(3);
  });

  it('names the key change', () => {
    expect(transposeLabel(0, s)).toBe('original');
    expect(transposeLabel(-2, s)).toBe('−2');
    expect(transposeLabel(3, s)).toBe('+3');
  });
});

describe('library', () => {
  const song = { folder: '/m/kad', title: 'Kad izdzisīs', artist: 'Miks Galvanovskis', key: 'Bb minor', bpm: 79.9,
    mixes: 8, transposed: [-2], cover: null, added: 0 };

  it('writes keys the short way a chart does', () => {
    expect(keyShort('Bb minor')).toBe('B♭m');
    expect(keyShort('F# major')).toBe('F♯');
    expect(keyShort(null)).toBe('');
  });

  it('finds songs by title or artist', () => {
    expect(matches(song, '')).toBe(true);
    expect(matches(song, 'miks')).toBe(true);
    expect(matches(song, 'IZDZ')).toBe(true);
    expect(matches(song, 'bee gees')).toBe(false);
  });

  it('says today for songs made today, else the date', () => {
    const now = new Date(2026, 10, 7, 18, 0);
    expect(addedLabel(new Date(2026, 10, 7, 9, 0).getTime() / 1000, now, 'en', s)).toBe('Today');
    expect(addedLabel(new Date(2026, 10, 2, 9, 0).getTime() / 1000, now, 'en', s)).toBe('Nov 2');
  });
});
