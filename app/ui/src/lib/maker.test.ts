import { describe, expect, it } from 'vitest';
import { STRINGS } from './i18n.svelte';
import {
  addedLabel,
  isYouTube,
  keyShort,
  matches,
  shownSongs,
  megabytes,
  progressOf,
  progressText,
  stepOf,
  timeLeft,
  transposeLabel,
} from './maker';

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

  it('follows the CLI through its four steps', () => {
    expect(stepOf([])).toBe(0);
    expect(stepOf(['Checking for a newer YouTube downloader', '1/4 Download', 'x', '3/4 Separate', '42%'])).toBe(3);
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

describe('progress while making a song', () => {
  it('follows the download percentage', () => {
    const p = progressOf(['1/4 Download', '[download]   0.0% of 3.52MiB', '[download]  45.5% of 3.52MiB at 2MiB/s']);
    expect(p).toMatchObject({ step: 1, share: 0.455 });
  });

  it('follows the separation by its own time estimate, once the model is loaded', () => {
    const lines = ['1/4 Download', '2/4 Cover', '3/4 Separate'];
    expect(progressOf(lines)).toMatchObject({ step: 3, share: null, left: null });
    lines.push('Estimated total processing time for this track: 200.00 seconds');
    expect(progressOf(lines)).toMatchObject({ step: 3, share: 0, left: 200 });
    lines.push('Estimated time remaining: 150.00 seconds');
    expect(progressOf(lines)).toMatchObject({ step: 3, share: 0.25, left: 150 });
  });

  it('adds up to one bar for the whole song, weighted by how long each step takes', () => {
    expect(progressOf([]).overall).toBe(0);
    const halfway = progressOf(['1/4 Download', '2/4 Cover', '3/4 Separate',
      'Estimated total processing time for this track: 100 seconds', 'Estimated time remaining: 50 seconds']).overall;
    expect(halfway).toBeGreaterThan(0.3);
    expect(halfway).toBeLessThan(0.6);
    expect(progressOf(['4/4 Chords']).overall).toBeGreaterThan(0.9);
    expect(stepOf(['3/5 Separate'])).toBe(0); // an older CLI's lines aren't misread
  });

  it('says the time left in words', () => {
    expect(timeLeft(150, s)).toBe('about 3 min left');
    expect(timeLeft(40, s)).toBe('less than a minute left');
  });
});

describe('library shelves', () => {
  const song = (title: string, daysAgo: number) => ({
    folder: `/m/${title}`, title, artist: 'Band', key: null, bpm: null, mixes: 3, transposed: [], cover: null,
    added: 1_800_000_000 - daysAgo * 86400,
  });
  const songs = [song('Fresh', 1), song('Week old', 6), song('Old', 30)];
  const now = 1_800_000_000;

  it('shows all songs, or the ones added in the last week, narrowed by the search', () => {
    expect(shownSongs(songs, 'all', '', now).map((x) => x.title)).toEqual(['Fresh', 'Week old', 'Old']);
    expect(shownSongs(songs, 'recent', '', now).map((x) => x.title)).toEqual(['Fresh', 'Week old']);
    expect(shownSongs(songs, 'recent', 'fre', now).map((x) => x.title)).toEqual(['Fresh']);
  });
});
