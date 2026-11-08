//! Turns a recipe into audio, block by block, without a device: what the player plays and what the tests
//! listen to. Mixing happens at the stems' rate; Rubber Band then moves key and tempo and also converts to
//! the device's rate; the count-in clicks are added on the mix's own timeline (so they stay crisp at any
//! key or tempo), and the limiter comes last.

use std::sync::Arc;

use rubberband_sys::*;

use super::limiter::Limiter;
use super::mixer::{gains, Mixer, Recipe};
use super::timeline::{stick, Timeline};
use super::Stems;

const CEILING: f32 = 0.891_250_9; // -1 dBFS, as the CLI's mixes and exports
const FADE_IN: f64 = 0.03; // seconds, where the intro is cut, so the cut doesn't click
const MAX_BLOCK: usize = 4096;

/// What the song file says about timing.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct SongTiming {
    pub start: f64,
    pub beat: Option<f64>,
    pub bpm: Option<f64>,
}

impl SongTiming {
    pub fn from_song(song: &serde_json::Value) -> SongTiming {
        SongTiming {
            start: song.pointer("/song_start/seconds").and_then(|v| v.as_f64()).unwrap_or(0.0),
            beat: song.pointer("/tempo/beat").and_then(|v| v.as_f64()),
            bpm: song.pointer("/tempo/bpm").and_then(|v| v.as_f64()),
        }
    }

    pub fn timeline(&self, recipe: &Recipe) -> Timeline {
        Timeline::new(self.start, self.beat, self.bpm, recipe.count_in, recipe.tempo)
    }
}

struct Stretcher(RubberBandState);

// The state is only ever used from the thread that owns the Render.
unsafe impl Send for Stretcher {}

impl Stretcher {
    fn new(rate: u32) -> Stretcher {
        let options = RubberBandOption_RubberBandOptionProcessRealTime
            | RubberBandOption_RubberBandOptionEngineFiner
            | RubberBandOption_RubberBandOptionPitchHighConsistency;
        let state = unsafe { rubberband_new(rate, 2, options as i32, 1.0, 1.0) };
        unsafe { rubberband_set_max_process_size(state, MAX_BLOCK as u32) };
        Stretcher(state)
    }

    /// Key and tempo, and the step from the stems' rate to the device's: Rubber Band resamples as it goes.
    fn set(&self, transpose: i32, tempo: f64, rates: f64) {
        unsafe {
            rubberband_set_pitch_scale(self.0, 2f64.powf(transpose as f64 / 12.0) / rates);
            rubberband_set_time_ratio(self.0, rates / tempo);
        }
    }
}

impl Drop for Stretcher {
    fn drop(&mut self) {
        unsafe { rubberband_delete(self.0) };
    }
}

pub struct Render {
    stems: Arc<Stems>,
    timing: SongTiming,
    recipe: Recipe,
    timeline: Timeline,
    out_rate: u32,
    stretcher: Stretcher,
    mixer: Mixer,
    limiter: Limiter,
    clicks: [Vec<f32>; 2],
    /// Next stems frame to feed Rubber Band.
    src: i64,
    /// Mix frame (at the device's rate) of the next frame going into the limiter.
    out_frame: i64,
    buf: [Vec<f32>; 4],
}

impl Render {
    pub fn new(stems: Arc<Stems>, timing: SongTiming, recipe: &Recipe, out_rate: u32) -> Render {
        let timeline = timing.timeline(recipe);
        let mut r = Render {
            mixer: Mixer::new(gains(recipe, stems.has_source())),
            stretcher: Stretcher::new(stems.rate),
            limiter: Limiter::new(out_rate, CEILING),
            clicks: [stick(out_rate, false), stick(out_rate, true)],
            stems,
            timing,
            recipe: recipe.clone(),
            timeline,
            out_rate,
            src: 0,
            out_frame: 0,
            buf: std::array::from_fn(|_| vec![0.0; MAX_BLOCK]),
        };
        r.seek(0.0);
        r
    }

    pub fn timeline(&self) -> &Timeline {
        &self.timeline
    }

    /// Mix seconds of the song's end, for the page's scrubber.
    pub fn duration(&self) -> f64 {
        self.timeline.mix_time(self.stems.len() as f64 / self.stems.rate as f64).max(0.0)
    }

    /// Mix seconds of the next frame `next` returns.
    pub fn position(&self) -> f64 {
        (self.out_frame - self.limiter.delay() as i64) as f64 / self.out_rate as f64
    }

    fn rates(&self) -> f64 {
        self.out_rate as f64 / self.stems.rate as f64
    }

    /// A changed mix plays on from the same place in the song: its levels ramp, its key and tempo follow.
    pub fn set_recipe(&mut self, recipe: &Recipe) {
        let song = self.timeline.song_time(self.out_frame as f64 / self.out_rate as f64);
        self.recipe = recipe.clone();
        self.timeline = self.timing.timeline(recipe);
        self.out_frame = (self.timeline.mix_time(song) * self.out_rate as f64).round() as i64;
        self.mixer.set(gains(recipe, self.stems.has_source()));
        self.stretcher.set(recipe.transpose, recipe.tempo, self.rates());
    }

    pub fn seek(&mut self, mix_seconds: f64) {
        self.out_frame = (mix_seconds * self.out_rate as f64).round() as i64;
        self.src = (self.timeline.song_time(mix_seconds) * self.stems.rate as f64).round() as i64;
        unsafe { rubberband_reset(self.stretcher.0) };
        self.stretcher.set(self.recipe.transpose, self.recipe.tempo, self.rates());
        // Rubber Band's real-time engine pads its own start, so its first output already lines up with the
        // first input; only the limiter's delay is accounted for, in `position`.
        self.limiter = Limiter::new(self.out_rate, CEILING);
    }

    fn feed(&mut self) {
        let need = (unsafe { rubberband_get_samples_required(self.stretcher.0) } as usize).clamp(256, MAX_BLOCK);
        let [l, r, _, _] = &mut self.buf;
        self.mixer.block(&self.stems, self.src, need, l, r);
        // Nothing before the song proper (the video intro), faded in where it's cut.
        let rate = self.stems.rate as f64;
        let cut = (self.timeline.music_from() * rate).round() as i64;
        let fade = (FADE_IN * rate) as i64;
        for f in 0..need {
            let i = self.src + f as i64;
            let g = if i < cut { 0.0 } else if i < cut + fade { (i - cut) as f32 / fade as f32 } else { 1.0 };
            l[f] *= g;
            r[f] *= g;
        }
        let ptrs = [l.as_ptr(), r.as_ptr()];
        unsafe { rubberband_process(self.stretcher.0, ptrs.as_ptr(), need as u32, 0) };
        self.src += need as i64;
    }

    pub fn next(&mut self, frames: usize) -> (Vec<f32>, Vec<f32>) {
        let (mut out_l, mut out_r) = (Vec::with_capacity(frames), Vec::with_capacity(frames));
        while out_l.len() < frames {
            while unsafe { rubberband_available(self.stretcher.0) } <= 0 {
                self.feed();
            }
            let available = unsafe { rubberband_available(self.stretcher.0) } as usize;
            let n = available.min(frames - out_l.len()).min(MAX_BLOCK);
            let [_, _, l, r] = &mut self.buf;
            let ptrs = [l.as_mut_ptr(), r.as_mut_ptr()];
            let got = unsafe { rubberband_retrieve(self.stretcher.0, ptrs.as_ptr(), n as u32) } as usize;
            self.add_clicks(got);
            let [_, _, l, r] = &mut self.buf;
            self.limiter.process(&mut l[..got], &mut r[..got]);
            out_l.extend_from_slice(&l[..got]);
            out_r.extend_from_slice(&r[..got]);
            self.out_frame += got as i64;
        }
        (out_l, out_r)
    }

    /// The count-in's clicks that fall in the next `frames` frames; only reached when playing from the top,
    /// since they all sit before the downbeat.
    fn add_clicks(&mut self, frames: usize) {
        let Some(count) = &self.timeline.count_in else { return };
        let (from, to) = (self.out_frame, self.out_frame + frames as i64);
        let [_, _, l, r] = &mut self.buf;
        for click in &count.clicks {
            let sound = &self.clicks[click.accent as usize];
            let at = (click.time * self.out_rate as f64).round() as i64;
            for (k, s) in sound.iter().enumerate() {
                let i = at + k as i64;
                if i >= from && i < to {
                    l[(i - from) as usize] += s;
                    r[(i - from) as usize] += s;
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::engine::mixer::STEMS;

    fn recipe(transpose: i32, tempo: f64, count_in: u8) -> Recipe {
        Recipe {
            id: "m".into(),
            name: "M".into(),
            levels: STEMS.iter().map(|s| (s.to_string(), 0.0)).collect(),
            mute: vec![],
            solo: vec![],
            transpose,
            tempo,
            count_in,
        }
    }

    fn mono(samples: Vec<f32>) -> Arc<Stems> {
        Arc::new(Stems::from_tracks(44100, vec![(samples.clone(), samples)], None))
    }

    fn crossings_per_second(x: &[f32], rate: f64) -> f64 {
        x.windows(2).filter(|w| (w[0] < 0.0) != (w[1] < 0.0)).count() as f64 / 2.0 / (x.len() as f64 / rate)
    }

    #[test]
    fn render_moves_pitch_by_the_key() {
        let sine: Vec<f32> = (0..44100 * 6).map(|i| 0.3 * (2.0 * std::f32::consts::PI * 440.0 * i as f32 / 44100.0).sin()).collect();
        let timing = SongTiming { start: 0.0, beat: None, bpm: None };
        let mut r = Render::new(mono(sine), timing, &recipe(12, 1.0, 0), 44100);
        r.next(44100);
        let (l, _) = r.next(44100 * 2);
        let hz = crossings_per_second(&l, 44100.0);
        assert!((hz - 880.0).abs() < 5.0, "{hz}");
    }

    #[test]
    fn render_keeps_sync_at_another_tempo_key_and_device_rate() {
        let mut stem = vec![0f32; 44100 * 8];
        for i in 0..441 {
            stem[3 * 44100 + i] = 0.5 * (2.0 * std::f32::consts::PI * 1000.0 * i as f32 / 44100.0).sin();
        }
        let timing = SongTiming { start: 0.0, beat: None, bpm: None };
        let mut r = Render::new(mono(stem), timing, &recipe(2, 0.8, 0), 48000);
        let start = r.position();
        let (l, _) = r.next(48000 * 5);
        let first = l.iter().position(|v| v.abs() > 0.05).expect("the burst comes out");
        let heard = start + first as f64 / 48000.0;
        assert!((heard - 3.0 / 0.8).abs() < 0.05, "heard at {heard}");
    }

    #[test]
    fn render_counts_in_only_from_the_top() {
        let silence = vec![0f32; 44100 * 20];
        let timing = SongTiming { start: 0.0, beat: Some(4.0), bpm: Some(120.0) };
        let mut r = Render::new(mono(silence), timing, &recipe(0, 1.0, 1), 44100);
        let downbeat = r.timeline().count_in.as_ref().unwrap().downbeat;
        let (l, _) = r.next((downbeat * 44100.0) as usize);
        assert!(l.iter().any(|v| v.abs() > 0.3), "clicks from the top");
        r.seek(6.0);
        let (l, _) = r.next(44100);
        assert!(l.iter().all(|v| v.abs() < 1e-3), "no clicks after a jump");
    }

    #[test]
    fn a_changed_mix_keeps_the_place_in_the_song() {
        let timing = SongTiming { start: 0.0, beat: Some(4.0), bpm: Some(120.0) };
        let mut r = Render::new(mono(vec![0f32; 44100 * 30]), timing, &recipe(0, 1.0, 1), 44100);
        r.seek(10.0);
        let song = r.timeline().song_time(r.position());
        r.set_recipe(&recipe(-2, 0.5, 2));
        assert!((r.timeline().song_time(r.position()) - song).abs() < 0.01);
    }
}

