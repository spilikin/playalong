import { describe, expect, it } from "vitest";
import { song as fixture } from "./fixture";
import type { Mix, Song } from "./song";
import { madeIn, transposeKey, versionsOf } from "./mixVersions";

const mix = (name: string, transpose = 0, tempo = 1): Mix => ({
  file: `mixes/s - ${name}.mp3`,
  name,
  tempo,
  transpose,
  source_offset: 0,
  count_in: null,
});

const song: Song = {
  ...fixture,
  mixes: [
    mix("original"),
    mix("guide"),
    mix("guide", -2),
    mix("no-guitar", -2),
    mix("backing", 0, 0.8),
  ],
  garagebands: [
    { folder: "mixes/s - GarageBand 120 BPM", bpm: 120, transpose: 0 },
  ],
};

describe("versions of a song", () => {
  it("spells a moved key the way the chords are spelled", () => {
    expect(transposeKey("Bb minor", -2)).toBe("G# minor");
    expect(transposeKey("Ab major", -2)).toBe("Gb major");
    expect(transposeKey("C major", 1)).toBe("Db major");
    expect(transposeKey("A minor", 12)).toBe("A minor");
  });

  it("lists each key and tempo the song has, the original first", () => {
    expect(versionsOf(song)).toEqual([
      { transpose: 0, tempo: 1, mixes: 2, garageband: true },
      { transpose: 0, tempo: 0.8, mixes: 1, garageband: false },
      { transpose: -2, tempo: 1, mixes: 2, garageband: false },
    ]);
  });

  it("tells which mixes and stems a version already has", () => {
    const made = madeIn(song, -2, 1);
    expect([...made.mixes.keys()]).toEqual(["guide", "no-guitar"]);
    expect(made.garageband).toBe(false);
    expect(madeIn(song, 0, 0.8).garageband).toBe(true);
  });
});
