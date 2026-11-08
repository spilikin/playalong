//! A song playing through the Mac's audio output. A processing thread renders ahead into a ring buffer of
//! about a tenth of a second and owns the output stream; the device's callback only takes samples and
//! counts them, never locking anything. Commands reach the thread through a queue.

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering::Relaxed};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};

use super::mixer::Recipe;
use super::render::{Render, SongTiming};
use super::Stems;

const BLOCK: usize = 1024;
const REPORT_EVERY: Duration = Duration::from_millis(16);

pub enum Command {
    Play,
    Pause,
    Seek(f64),
    Mix(Recipe),
    Stop,
}

/// What the callback and the thread share; only atomics, so the callback never waits.
#[derive(Default)]
pub struct Shared {
    playing: AtomicBool,
    /// Frames the device has taken from the buffer.
    played: AtomicU64,
    /// Frames written before this one were made stale by a jump: the callback drops them unheard.
    stale_before: AtomicU64,
}

/// Frames over which output fades in and out (about 6 ms): pausing or jumping never cuts a waveform.
const FADE: f32 = 256.0;

/// The device side: takes whole stereo frames from the queue and fades on pause and jumps.
pub struct Output {
    consumer: rtrb::Consumer<f32>,
    gain: f32,
}

impl Output {
    pub fn new(consumer: rtrb::Consumer<f32>) -> Output {
        Output { consumer, gain: 0.0 }
    }

    fn take(&mut self, played: &mut u64) -> Option<(f32, f32)> {
        // Both samples of a frame or neither: the producer pushes them one at a time.
        if self.consumer.slots() < 2 {
            return None;
        }
        *played += 1;
        Some((self.consumer.pop().ok()?, self.consumer.pop().ok()?))
    }

    pub fn fill(&mut self, data: &mut [f32], channels: usize, shared: &Shared) {
        let stale = shared.stale_before.load(Relaxed);
        let playing = shared.playing.load(Relaxed);
        let mut played = shared.played.load(Relaxed);
        for frame in data.chunks_mut(channels) {
            // A jump: the old place fades out first, then whatever is left of it goes unheard.
            if played < stale && self.gain == 0.0 {
                while played < stale && self.take(&mut played).is_some() {}
            }
            let target = if playing && played >= stale { 1.0 } else { 0.0 };
            let sample = if self.gain == 0.0 && target == 0.0 { None } else { self.take(&mut played) };
            frame.iter_mut().for_each(|v| *v = 0.0);
            if let Some((l, r)) = sample {
                self.gain = if target > self.gain { (self.gain + 1.0 / FADE).min(1.0) } else { (self.gain - 1.0 / FADE).max(0.0) };
                frame[0] = l * self.gain;
                if channels > 1 {
                    frame[1] = r * self.gain;
                }
            }
        }
        shared.played.store(played, Relaxed);
    }
}

/// Play pressed at (or just before) the end starts the song again.
pub fn starts_over(now: f64, duration: f64) -> bool {
    now >= duration - 0.05
}

/// Mix seconds being heard: the position after the last frame written, minus what's still queued.
pub fn heard(written_position: f64, written: u64, played: u64, rate: u32) -> f64 {
    written_position - written.saturating_sub(played) as f64 / rate as f64
}

pub struct Player {
    commands: Mutex<rtrb::Producer<Command>>,
    thread: Option<JoinHandle<()>>,
    pub timing: SongTiming,
    pub duration: f64,
}

impl Player {
    /// Starts paused at the top of the song. `report` gets (mix seconds heard, playing) while it plays and
    /// once when it stops.
    pub fn start(
        stems: Arc<Stems>,
        timing: SongTiming,
        recipe: &Recipe,
        report: impl Fn(f64, bool) + Send + 'static,
    ) -> Result<Player, String> {
        let (tx, mut rx) = rtrb::RingBuffer::<Command>::new(64);
        let (ready_tx, ready_rx) = std::sync::mpsc::channel::<Result<f64, String>>();
        let recipe = recipe.clone();
        let thread = std::thread::Builder::new()
            .name("playalong-audio".into())
            .spawn(move || {
                let host = cpal::default_host();
                let Some(device) = host.default_output_device() else {
                    let _ = ready_tx.send(Err("No audio output found".into()));
                    return;
                };
                let config = match device.default_output_config() {
                    Ok(c) if c.sample_format() == cpal::SampleFormat::F32 => c,
                    Ok(c) => {
                        let _ = ready_tx.send(Err(format!("The audio output wants {:?} samples", c.sample_format())));
                        return;
                    }
                    Err(e) => {
                        let _ = ready_tx.send(Err(format!("can't use the audio output: {e}")));
                        return;
                    }
                };
                let rate = config.sample_rate().0;
                let channels = config.channels() as usize;
                let shared = Arc::new(Shared::default());
                let (mut producer, consumer) = rtrb::RingBuffer::<f32>::new(rate as usize / 10 * 2);
                let mut output = Output::new(consumer);
                let callback_shared = shared.clone();
                let stream = device.build_output_stream(
                    &config.into(),
                    move |data: &mut [f32], _| output.fill(data, channels, &callback_shared),
                    |e| eprintln!("audio output: {e}"),
                    None,
                );
                let started = stream.map_err(|e| e.to_string()).and_then(|s| s.play().map(|_| s).map_err(|e| e.to_string()));
                let stream = match started {
                    Ok(s) => s,
                    Err(e) => {
                        let _ = ready_tx.send(Err(format!("can't start the audio output: {e}")));
                        return;
                    }
                };
                let mut render = Render::new(stems, timing, &recipe, rate);
                let duration = render.duration();
                let _ = ready_tx.send(Ok(duration));

                let mut written: u64 = 0;
                let mut position = render.position();
                let mut last_report = Instant::now();
                loop {
                    while let Ok(command) = rx.pop() {
                        match command {
                            Command::Play => {
                                let played = shared.played.load(Relaxed).max(shared.stale_before.load(Relaxed));
                                if starts_over(heard(position, written, played, rate), duration) {
                                    render.seek(0.0);
                                    shared.stale_before.store(written, Relaxed);
                                    position = render.position();
                                }
                                shared.playing.store(true, Relaxed);
                            }
                            Command::Pause => shared.playing.store(false, Relaxed),
                            Command::Seek(mix) => {
                                render.seek(mix.clamp(0.0, duration));
                                shared.stale_before.store(written, Relaxed);
                                position = render.position();
                            }
                            Command::Mix(recipe) => {
                                render.set_recipe(&recipe);
                                position = render.position();
                            }
                            Command::Stop => {
                                drop(stream);
                                return;
                            }
                        }
                    }
                    let playing = shared.playing.load(Relaxed);
                    let played = shared.played.load(Relaxed).max(shared.stale_before.load(Relaxed));
                    let now = heard(position, written, played, rate);
                    if playing && now >= duration {
                        shared.playing.store(false, Relaxed);
                        report(duration, false);
                    } else if producer.slots() >= BLOCK * 2 && now < duration {
                        let (l, r) = render.next(BLOCK);
                        for (a, b) in l.into_iter().zip(r) {
                            let _ = producer.push(a);
                            let _ = producer.push(b);
                        }
                        written += BLOCK as u64;
                        position = render.position();
                        continue;
                    }
                    if playing && last_report.elapsed() >= REPORT_EVERY {
                        report(now, true);
                        last_report = Instant::now();
                    }
                    std::thread::sleep(Duration::from_millis(3));
                }
            })
            .map_err(|e| format!("can't start playback: {e}"))?;
        let duration = ready_rx.recv().map_err(|_| "Playback stopped while starting".to_string())??;
        Ok(Player { commands: Mutex::new(tx), thread: Some(thread), timing, duration })
    }

    pub fn send(&self, command: Command) {
        let _ = self.commands.lock().unwrap().push(command);
    }
}

impl Drop for Player {
    fn drop(&mut self) {
        self.send(Command::Stop);
        if let Some(t) = self.thread.take() {
            let _ = t.join();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn queue(frames: &[(f32, f32)]) -> (rtrb::Producer<f32>, Output) {
        let (mut p, c) = rtrb::RingBuffer::<f32>::new(8192);
        for &(l, r) in frames {
            p.push(l).unwrap();
            p.push(r).unwrap();
        }
        (p, Output::new(c))
    }

    fn steepest(x: &[f32]) -> f32 {
        x.windows(2).map(|w| (w[1] - w[0]).abs()).fold(0.0, f32::max)
    }

    #[test]
    fn never_takes_half_a_frame() {
        let (mut p, mut out) = queue(&[]);
        p.push(0.5).unwrap();
        let shared = Shared::default();
        shared.playing.store(true, Relaxed);
        let mut data = [9.0f32; 4];
        out.fill(&mut data, 2, &shared);
        assert_eq!(data, [0.0; 4]);
        p.push(0.25).unwrap();
        let mut data = [0.0f32; 2];
        for _ in 0..300 {
            out.fill(&mut data, 2, &shared);
        }
        assert_eq!(shared.played.load(Relaxed), 1, "the pair came out together");
    }

    #[test]
    fn pause_fades_out_instead_of_cutting() {
        let (_p, mut out) = queue(&vec![(1.0, 1.0); 2000]);
        let shared = Shared::default();
        shared.playing.store(true, Relaxed);
        let mut data = vec![0f32; 2 * 600];
        out.fill(&mut data, 2, &shared);
        shared.playing.store(false, Relaxed);
        let mut after = vec![0f32; 2 * 600];
        out.fill(&mut after, 2, &shared);
        let left: Vec<f32> = data.iter().chain(after.iter()).step_by(2).copied().collect();
        assert!(steepest(&left) <= 1.0 / 256.0 + 1e-6);
        assert_eq!(*left.last().unwrap(), 0.0);
        let taken = shared.played.load(Relaxed);
        out.fill(&mut after, 2, &shared);
        assert_eq!(shared.played.load(Relaxed), taken, "paused, nothing more is taken");
    }

    #[test]
    fn a_jump_fades_the_old_place_out_and_the_new_one_in() {
        let mut frames = vec![(1.0, 1.0); 1000];
        frames.extend(vec![(-1.0, -1.0); 1000]);
        let (_p, mut out) = queue(&frames);
        let shared = Shared::default();
        shared.playing.store(true, Relaxed);
        let mut data = vec![0f32; 2 * 400];
        out.fill(&mut data, 2, &shared);
        shared.stale_before.store(1000, Relaxed);
        let mut after = vec![0f32; 2 * 900];
        out.fill(&mut after, 2, &shared);
        let left: Vec<f32> = data.iter().chain(after.iter()).step_by(2).copied().collect();
        assert!(steepest(&left) <= 1.0 / 256.0 + 1e-6);
        assert!(*left.last().unwrap() < -0.99, "the new place is heard");
    }

    #[test]
    fn play_at_the_end_starts_over() {
        assert!(starts_over(180.0, 180.0) && !starts_over(100.0, 180.0));
    }

    #[test]
    fn what_is_heard_lags_what_is_written_by_the_queue() {
        assert_eq!(heard(10.0, 48_000, 43_200, 48_000), 9.9);
        assert_eq!(heard(10.0, 100, 200, 48_000), 10.0);
    }
}

#[cfg(test)]
mod device {
    use super::*;

    /// Plays a real song for a few seconds: `PLAYALONG_SMOKE_SONG=<song folder> cargo test -- --ignored`.
    #[test]
    #[ignore]
    fn plays_a_real_song() {
        let folder = std::path::PathBuf::from(std::env::var("PLAYALONG_SMOKE_SONG").unwrap());
        let song = crate::song::open(&folder).unwrap();
        let timing = SongTiming::from_song(&song.song);
        let mut recipe = crate::mixes::load(&song.folder).unwrap()[0].clone();
        let stems = Arc::new(Stems::load(&song.folder, &song.song).unwrap());
        let seen = Arc::new(Mutex::new(Vec::new()));
        let log = seen.clone();
        let player = Player::start(stems, timing, &recipe, move |m, p| log.lock().unwrap().push((m, p))).unwrap();
        player.send(Command::Seek(30.0));
        player.send(Command::Play);
        std::thread::sleep(Duration::from_secs(3));
        let at = seen.lock().unwrap().last().unwrap().0;
        assert!((at - 33.0).abs() < 0.3, "after 3 s at {at}");
        recipe.transpose = -2;
        recipe.tempo = 0.8;
        player.send(Command::Mix(recipe));
        std::thread::sleep(Duration::from_secs(2));
        player.send(Command::Seek(60.0));
        std::thread::sleep(Duration::from_millis(500));
        let at = seen.lock().unwrap().last().unwrap().0;
        assert!((at - 60.5).abs() < 0.3, "after the jump at {at}");
        println!("positions reported: {}", seen.lock().unwrap().len());
    }
}
