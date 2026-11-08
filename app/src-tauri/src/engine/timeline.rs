//! Where things sit in a mix as it plays: the song time at its start, its tempo, and the count-in clicks.
//! The same numbers a rendered mix carried (`countin.count_timing` in the CLI), so the page's chords,
//! bars and count-in follow a live mix exactly as they followed a file.

use serde::Serialize;

pub const LEAD: f64 = 0.25;
pub const BEATS_PER_BAR: u32 = 4;
const CLICK_SECONDS: f64 = 0.03;
const CLICK_LEVEL: f32 = 0.6;

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Click {
    pub time: f64,
    pub accent: bool,
    pub count: u32,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct CountIn {
    pub bars: u8,
    pub clicks: Vec<Click>,
    pub downbeat: f64,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Timeline {
    pub tempo: f64,
    pub source_offset: f64,
    pub count_in: Option<CountIn>,
    /// Song time before which nothing plays: the video intro.
    #[serde(skip)]
    pub start: f64,
}

/// (beat, accented) per click; two bars count "ONE . TWO . one two three four".
fn clicks(bars: u8) -> Vec<(u32, bool)> {
    match bars {
        2 => vec![(0, true), (2, true), (4, true), (5, false), (6, false), (7, false)],
        _ => vec![(0, true), (1, false), (2, false), (3, false)],
    }
}

impl Timeline {
    /// `beat` is the beat the count-in leads into and `bpm` the song's tempo; without either there's no count-in.
    pub fn new(start: f64, beat: Option<f64>, bpm: Option<f64>, count_in: u8, tempo: f64) -> Timeline {
        let (Some(beat), Some(bpm), 1..=2) = (beat, bpm, count_in) else {
            return Timeline { tempo, source_offset: start, count_in: None, start };
        };
        let period = 60.0 / bpm;
        let counts = clicks(count_in)
            .into_iter()
            .map(|(b, accent)| {
                let count = if count_in == 2 && b < BEATS_PER_BAR { b / 2 + 1 } else { b % BEATS_PER_BAR + 1 };
                Click { time: (LEAD + b as f64 * period) / tempo, accent, count }
            })
            .collect();
        let count_seconds = LEAD + (BEATS_PER_BAR * count_in as u32) as f64 * period;
        Timeline {
            tempo,
            source_offset: beat - count_seconds,
            count_in: Some(CountIn { bars: count_in, clicks: counts, downbeat: count_seconds / tempo }),
            start,
        }
    }

    pub fn song_time(&self, mix_seconds: f64) -> f64 {
        self.source_offset + mix_seconds * self.tempo
    }

    pub fn mix_time(&self, song_seconds: f64) -> f64 {
        (song_seconds - self.source_offset) / self.tempo
    }

    /// Where the music starts: after the intro, and not before the mix's own start.
    pub fn music_from(&self) -> f64 {
        self.start.max(self.source_offset)
    }
}

/// Two sticks struck together, as the CLI's count-in: a noise crack and a short woody ring, the accent
/// higher and louder.
pub fn stick(rate: u32, accent: bool) -> Vec<f32> {
    let n = ((CLICK_SECONDS * rate as f64) as usize).max(1);
    let mut seed: u32 = 0x9E37_79B9;
    let mut noise = || {
        seed ^= seed << 13;
        seed ^= seed >> 17;
        seed ^= seed << 5;
        seed as f64 / u32::MAX as f64 * 2.0 - 1.0
    };
    let keep = if accent { 0.8 } else { 0.65 };
    let ring = if accent { 2400.0 } else { 1800.0 };
    let (mut crack, mut previous) = (0.0, noise());
    let mut out: Vec<f64> = (0..n)
        .map(|i| {
            let t = i as f64 / rate as f64;
            let now = noise();
            crack = keep * (crack + now - previous);
            previous = now;
            0.6 * crack * (-t / 0.004).exp() + (2.0 * std::f64::consts::PI * ring * t).sin() * (-t / 0.012).exp()
        })
        .collect();
    let peak = out.iter().fold(0.0f64, |m, v| m.max(v.abs()));
    let level = if accent { 1.0 } else { 0.7 } * CLICK_LEVEL as f64 / peak;
    out.iter_mut().for_each(|v| *v *= level);
    out.into_iter().map(|v| v as f32).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn timeline_matches_the_cli() {
        let t = Timeline::new(21.9, Some(22.25), Some(120.0), 1, 1.0);
        assert!((t.source_offset - 20.0).abs() < 1e-9);
        let count = t.count_in.as_ref().unwrap();
        let times: Vec<f64> = count.clicks.iter().map(|c| c.time).collect();
        assert_eq!(times, [0.25, 0.75, 1.25, 1.75]);
        assert_eq!(count.clicks.iter().map(|c| c.count).collect::<Vec<_>>(), [1, 2, 3, 4]);
        assert!((count.downbeat - 2.25).abs() < 1e-9);
        let slow = Timeline::new(21.9, Some(22.25), Some(120.0), 1, 0.8);
        assert!((slow.count_in.unwrap().clicks[1].time - 0.75 / 0.8).abs() < 1e-9);
        let two = Timeline::new(0.0, Some(10.0), Some(120.0), 2, 1.0);
        assert_eq!(two.count_in.unwrap().clicks.iter().map(|c| c.count).collect::<Vec<_>>(), [1, 2, 1, 2, 3, 4]);
        assert!((t.song_time(t.mix_time(30.0)) - 30.0).abs() < 1e-9);
    }

    #[test]
    fn no_tempo_no_count_in() {
        let t = Timeline::new(3.0, None, None, 1, 1.0);
        assert_eq!((t.source_offset, t.count_in), (3.0, None));
        assert_eq!(Timeline::new(3.0, Some(4.0), Some(100.0), 0, 1.0).count_in, None);
    }

    #[test]
    fn stick_is_short_and_accent_is_louder() {
        let (accent, plain) = (stick(44100, true), stick(44100, false));
        assert_eq!(accent.len(), 1323);
        let peak = |v: &[f32]| v.iter().fold(0f32, |m, x| m.max(x.abs()));
        assert!((peak(&accent) - 0.6).abs() < 1e-4 && (peak(&plain) - 0.42).abs() < 1e-4);
    }
}
