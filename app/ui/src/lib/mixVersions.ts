// A song's mixes come in versions: one set per key and tempo. The Mixes page shows one version at a time,
// what it already has and what's left to make.

import type { Mix, Song } from "./song";

const SHARPS = [
  "C",
  "C#",
  "D",
  "D#",
  "E",
  "F",
  "F#",
  "G",
  "G#",
  "A",
  "A#",
  "B",
];
const FLATS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"];
// As in src/playalong/chords.py: these keys are written with flats, the rest with sharps.
const FLAT_KEYS = new Set([
  "F major",
  "Bb major",
  "Eb major",
  "Ab major",
  "Db major",
  "Gb major",
  "D minor",
  "G minor",
  "C minor",
  "F minor",
  "Bb minor",
  "Eb minor",
]);

/** "Bb minor" moved by semitones, spelled as the CLI spells the chords of a transposed mix. */
export function transposeKey(key: string, semitones: number): string {
  const [tonic, mode] = key.split(" ");
  const from = Math.max(SHARPS.indexOf(tonic), FLATS.indexOf(tonic));
  const pitch = (((from + semitones) % 12) + 12) % 12;
  return `${FLAT_KEYS.has(`${FLATS[pitch]} ${mode}`) ? FLATS[pitch] : SHARPS[pitch]} ${mode}`;
}

export interface Version {
  transpose: number;
  tempo: number;
  mixes: number;
  garageband: boolean;
}

const gbKeys = (song: Song) =>
  new Set((song.garagebands ?? []).map((g) => g.transpose));

/** The versions the song has, the original key at full tempo first. GarageBand stems keep the song's
 * tempo, so they belong to the full-tempo version of their key. */
export function versionsOf(song: Song): Version[] {
  const found = new Map<string, Version>();
  const add = (transpose: number, tempo: number) => {
    const id = `${transpose}@${tempo}`;
    if (!found.has(id))
      found.set(id, { transpose, tempo, mixes: 0, garageband: false });
    return found.get(id)!;
  };
  for (const m of song.mixes) add(m.transpose ?? 0, m.tempo).mixes++;
  for (const t of gbKeys(song)) add(t, 1).garageband = true;
  const rank = (v: Version) => [
    v.transpose === 0 ? 0 : 1,
    Math.abs(v.transpose),
    v.transpose,
    -v.tempo,
  ];
  return [...found.values()].sort((a, b) => {
    const [ra, rb] = [rank(a), rank(b)];
    return ra.map((x, i) => x - rb[i]).find((d) => d !== 0) ?? 0;
  });
}

/** What one version has: its mixes by name, and whether its key has GarageBand stems. */
export function madeIn(
  song: Song,
  transpose: number,
  tempo: number,
): { mixes: Map<string, Mix>; garageband: boolean } {
  const mixes = new Map(
    song.mixes
      .filter((m) => (m.transpose ?? 0) === transpose && m.tempo === tempo)
      .map((m) => [m.name, m]),
  );
  return { mixes, garageband: gbKeys(song).has(transpose) };
}
