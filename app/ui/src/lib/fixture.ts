import type { Mix, OpenedSong, Song } from './song';

export const counted: Mix = {
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

export const song: Song = {
  format: 'playalong-song',
  version: 1,
  title: 'Kad izdzisīs',
  artist: 'Miks Galvanovskis',
  key: 'Bb minor',
  tempo: { bpm: 120, confidence: 0.6, source: 'detected', beats_per_bar: 4 },
  song_start: { seconds: 21.9, source: 'stems' },
  beats: [22.25, 22.75, 23.25, 23.75, 24.25, 24.75, 25.25, 25.75, 26.25],
  bars: [22.25, 24.25],
  chords: [
    { start: 22.25, end: 23.25, name: 'Bbm', root: 'Bb', quality: 'minor' },
    { start: 23.25, end: 26.25, name: 'Ab', root: 'Ab', quality: 'major' },
  ],
  chord_shapes: {
    Bbm: { frets: [-1, 1, 3, 3, 2, 1], fingers: [0, 1, 3, 4, 2, 1], barre: { fret: 1, strings: [1, 5] } },
    Ab: { frets: [4, 6, 6, 5, 4, 4], fingers: [1, 3, 4, 2, 1, 1], barre: { fret: 4, strings: [0, 5] } },
  },
  mixes: [
    { ...counted, file: 'mixes/s - backing.mp3', name: 'backing' },
    { ...counted, file: 'mixes/s - guide.mp3', name: 'guide' },
    counted,
    { ...counted, file: 'mixes/s - original.mp3', name: 'original' },
    { ...counted, file: 'mixes/s - vocals-only.mp3', name: 'vocals-only' },
  ],
  cover: { file: 'cover.jpg', source: 'itunes', album: 'Tā Mana Dzīve' },
  audio: { file: 'source.wav', sample_rate: 44100, duration: 30 },
};

export const opened: OpenedSong = { folder: '/lib/kad-izdzisis', file: '/lib/kad-izdzisis/kad-izdzisis.playalong', song };
