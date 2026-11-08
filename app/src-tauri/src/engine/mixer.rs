//! A mix recipe applied to the stems: one stereo signal from six instruments (or the recording itself),
//! with level changes ramped so moving a slider never clicks.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use super::Stems;

pub const STEMS: [&str; 6] = ["vocals", "guitar", "bass", "drums", "piano", "other"];
/// The recording is the seventh track: an untouched mix plays it instead of the stems.
pub const SOURCE: usize = 6;
const RAMP: usize = 256;

/// A song's mix as kept in `mixes.json` (see the CLI's recipes.py).
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
pub struct Recipe {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub levels: BTreeMap<String, f64>,
    #[serde(default)]
    pub mute: Vec<String>,
    #[serde(default)]
    pub solo: Vec<String>,
    #[serde(default)]
    pub transpose: i32,
    #[serde(default = "one")]
    pub tempo: f64,
    #[serde(default = "one_bar")]
    pub count_in: u8,
}

fn one() -> f64 {
    1.0
}

fn one_bar() -> u8 {
    1
}

impl Recipe {
    /// Untouched: the stems never add back up to the recording exactly, so the recording plays.
    pub fn plays_source(&self) -> bool {
        self.mute.is_empty() && self.solo.is_empty() && self.levels.values().all(|db| *db == 0.0)
    }
}

/// Linear gain per track (six stems, then the recording). A muted instrument stays silent even when
/// soloed; with any soloed, only those sound.
pub fn gains(recipe: &Recipe, has_source: bool) -> [f32; 7] {
    let mut out = [0.0; 7];
    if recipe.plays_source() && has_source {
        out[SOURCE] = 1.0;
        return out;
    }
    for (i, stem) in STEMS.iter().enumerate() {
        let stem = stem.to_string();
        let silent = recipe.mute.contains(&stem) || (!recipe.solo.is_empty() && !recipe.solo.contains(&stem));
        if !silent {
            out[i] = 10f32.powf(*recipe.levels.get(&stem).unwrap_or(&0.0) as f32 / 20.0);
        }
    }
    out
}

pub struct Mixer {
    current: [f32; 7],
    target: [f32; 7],
}

impl Mixer {
    pub fn new(target: [f32; 7]) -> Mixer {
        Mixer { current: target, target }
    }

    pub fn set(&mut self, target: [f32; 7]) {
        self.target = target;
    }

    /// `frames` frames from source frame `from` (negative or past the end is silence) into `l` and `r`.
    pub fn block(&mut self, stems: &Stems, from: i64, frames: usize, l: &mut [f32], r: &mut [f32]) {
        l[..frames].fill(0.0);
        r[..frames].fill(0.0);
        for t in 0..7 {
            let Some((tl, tr)) = stems.track(t) else { continue };
            let (start, end) = (self.current[t], self.target[t]);
            if start == 0.0 && end == 0.0 {
                continue;
            }
            for f in 0..frames {
                let g = if f < RAMP { start + (end - start) * (f + 1) as f32 / RAMP as f32 } else { end };
                let i = from + f as i64;
                if i >= 0 && (i as usize) < tl.len() {
                    l[f] += tl[i as usize] * g;
                    r[f] += tr[i as usize] * g;
                }
            }
        }
        if frames >= RAMP {
            self.current = self.target;
        } else {
            for t in 0..7 {
                self.current[t] += (self.target[t] - self.current[t]) * frames as f32 / RAMP as f32;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn recipe() -> Recipe {
        Recipe {
            id: "m".into(),
            name: "M".into(),
            levels: STEMS.iter().map(|s| (s.to_string(), 0.0)).collect(),
            mute: vec![],
            solo: vec![],
            transpose: 0,
            tempo: 1.0,
            count_in: 1,
        }
    }

    #[test]
    fn untouched_plays_the_recording_and_mute_beats_solo() {
        assert_eq!(gains(&recipe(), true)[SOURCE], 1.0);
        assert_eq!(gains(&recipe(), false)[0], 1.0);
        let mut r = recipe();
        r.levels.insert("vocals".into(), -6.0);
        r.mute = vec!["guitar".into()];
        r.solo = vec!["vocals".into(), "guitar".into()];
        let g = gains(&r, true);
        assert!((g[0] - 0.501).abs() < 1e-3);
        assert_eq!(&g[1..], &[0.0; 6]);
    }

    #[test]
    fn level_changes_ramp_without_a_jump() {
        let dc = vec![1.0f32; 2048];
        let stems = Stems::from_tracks(44100, vec![(dc.clone(), dc.clone())], None);
        let mut m = Mixer::new([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]);
        let (mut l, mut r) = (vec![0f32; 512], vec![0f32; 512]);
        m.block(&stems, 0, 512, &mut l, &mut r);
        m.set([0.0; 7]);
        m.block(&stems, 512, 512, &mut l, &mut r);
        let steepest = l.windows(2).map(|w| (w[1] - w[0]).abs()).fold(0f32, f32::max);
        assert!(steepest <= 1.0 / 256.0 + 1e-6, "{steepest}");
        assert_eq!(l[511], 0.0);
    }
}
