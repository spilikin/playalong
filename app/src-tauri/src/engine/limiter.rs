//! Peaks held at a ceiling without touching anything quieter: the streaming form of the CLI's `mix.limit`.
//! The gain a sample needs is held low from LOOKAHEAD before a peak to HOLD after it, then smoothed over
//! LOOKAHEAD; around a peak every smoothed value is already at or below that peak's gain, so the ceiling
//! holds exactly. Output lags input by `delay()` frames.

use std::collections::VecDeque;

const LOOKAHEAD: f64 = 0.005;
const HOLD: f64 = 0.1;

pub struct Limiter {
    ceiling: f32,
    ahead: usize,
    hold: usize,
    half: usize,
    /// Audio waiting for its gain.
    audio: VecDeque<(f32, f32)>,
    /// (sample index, gain it needs), increasing: the minimum over the hold window at the front.
    minima: VecDeque<(u64, f32)>,
    /// Held gains waiting to be averaged.
    held: VecDeque<f32>,
    held_sum: f64,
    index: u64,
}

impl Limiter {
    pub fn new(rate: u32, ceiling: f32) -> Limiter {
        let ahead = ((LOOKAHEAD * rate as f64) as usize).max(1);
        let half = ahead / 2;
        let mut l = Limiter {
            ceiling,
            ahead,
            hold: (HOLD * rate as f64) as usize,
            half,
            audio: VecDeque::new(),
            minima: VecDeque::new(),
            held: VecDeque::new(),
            held_sum: 0.0,
            index: 0,
        };
        // Silence before the first sample needs no gain reduction.
        for _ in 0..l.delay() {
            l.audio.push_back((0.0, 0.0));
        }
        for _ in 0..half {
            l.held.push_back(1.0);
            l.held_sum += 1.0;
        }
        l
    }

    pub fn delay(&self) -> usize {
        self.ahead + self.half
    }

    pub fn process(&mut self, l: &mut [f32], r: &mut [f32]) {
        let window = self.hold + self.ahead + 1;
        for f in 0..l.len() {
            let peak = l[f].abs().max(r[f].abs());
            let need = if peak > self.ceiling { self.ceiling / peak } else { 1.0 };
            self.audio.push_back((l[f], r[f]));
            // Sliding minimum over the last `window` needs: the held gain for the sample `ahead` back.
            while self.minima.back().is_some_and(|&(_, v)| v >= need) {
                self.minima.pop_back();
            }
            self.minima.push_back((self.index, need));
            while self.minima.front().is_some_and(|&(i, _)| i + window as u64 <= self.index) {
                self.minima.pop_front();
            }
            self.index += 1;
            let held = self.minima.front().map_or(1.0, |&(_, v)| v);
            self.held.push_back(held);
            self.held_sum += held as f64;
            if self.held.len() > 2 * self.half + 1 {
                self.held_sum -= self.held.pop_front().unwrap() as f64;
            }
            // The sample in the middle of the averaging window, `delay()` behind the input.
            let middle = self.held[self.half.min(self.held.len() - 1)];
            let gain = ((self.held_sum / self.held.len() as f64) as f32).min(middle);
            let (al, ar) = self.audio.pop_front().unwrap();
            l[f] = al * gain;
            r[f] = ar * gain;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn limiter_holds_minus_one_dbfs_and_leaves_quiet_audio_alone() {
        let ceiling = 10f32.powf(-1.0 / 20.0);
        let rate = 44100;
        let sine: Vec<f32> = (0..rate).map(|i| 0.3 * (i as f32 * 0.0313).sin()).collect();
        let mut lim = Limiter::new(rate as u32, ceiling);
        let delay = lim.delay();
        let (mut l, mut r) = (sine.clone(), sine.clone());
        lim.process(&mut l, &mut r);
        for i in delay..rate {
            assert!((l[i] - sine[i - delay]).abs() < 1e-6);
        }

        let mut loud = sine.clone();
        loud[22050..24050].iter_mut().for_each(|v| *v *= 6.0);
        let mut lim = Limiter::new(rate as u32, ceiling);
        let (mut l, mut r) = (loud.clone(), loud.clone());
        lim.process(&mut l, &mut r);
        assert!(l.iter().fold(0f32, |m, v| m.max(v.abs())) <= ceiling + 1e-6);
        assert!((l[1000 + delay] - loud[1000]).abs() < 1e-6);
    }
}
