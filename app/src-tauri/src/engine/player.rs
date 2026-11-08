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
struct Shared {
    playing: AtomicBool,
    /// Frames the device has taken from the buffer.
    played: AtomicU64,
    /// Frames written before this one were made stale by a jump: the callback drops them unheard.
    stale_before: AtomicU64,
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
                let (mut producer, mut consumer) = rtrb::RingBuffer::<f32>::new(rate as usize / 10 * 2);
                let callback_shared = shared.clone();
                let stream = device.build_output_stream(
                    &config.into(),
                    move |data: &mut [f32], _| {
                        let s = &callback_shared;
                        let stale = s.stale_before.load(Relaxed);
                        let mut played = s.played.load(Relaxed);
                        while played < stale && consumer.pop().is_ok() && consumer.pop().is_ok() {
                            played += 1;
                        }
                        let playing = s.playing.load(Relaxed);
                        for frame in data.chunks_mut(channels) {
                            let (l, r) = if playing {
                                match (consumer.pop(), consumer.pop()) {
                                    (Ok(l), Ok(r)) => {
                                        played += 1;
                                        (l, r)
                                    }
                                    _ => (0.0, 0.0),
                                }
                            } else {
                                (0.0, 0.0)
                            };
                            frame[0] = l;
                            if channels > 1 {
                                frame[1] = r;
                            }
                            frame.iter_mut().skip(2).for_each(|v| *v = 0.0);
                        }
                        s.played.store(played, Relaxed);
                    },
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
                            Command::Play => shared.playing.store(true, Relaxed),
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
