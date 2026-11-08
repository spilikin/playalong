//! Commands the player page uses to play a song live: open it with one of its mixes, play, pause, jump,
//! and change the mix while it plays. Position comes back as `playback-position` events.

use std::path::Path;
use std::sync::{Arc, Mutex};

use serde::Serialize;
use tauri::{AppHandle, Emitter, State};

use crate::engine::mixer::Recipe;
use crate::engine::player::{retire, Command, Player};
use crate::engine::render::SongTiming;
use crate::engine::timeline::Timeline;
use crate::engine::Stems;

#[derive(Default)]
pub struct Playback(Mutex<Option<Player>>);

#[derive(Serialize)]
pub struct Opened {
    duration: f64,
    timeline: Timeline,
    mixes: Vec<Recipe>,
    current: String,
}

#[derive(Clone, Serialize)]
struct Position {
    mix_seconds: f64,
    playing: bool,
}

/// The song's stems into memory (about half a gigabyte for four minutes, a second or so) and its mixes;
/// `mix` picks one by id, else the first. Whatever played before stops.
#[tauri::command]
pub async fn playback_open(
    app: AppHandle,
    playback: State<'_, Playback>,
    folder: String,
    mix: Option<String>,
) -> Result<Opened, String> {
    // Taken out before it's stopped, so no other command waits on the lock meanwhile.
    let old = playback.0.lock().unwrap().take();
    retire(old);
    let handle = app.clone();
    let (player, opened) = tauri::async_runtime::spawn_blocking(move || -> Result<(Player, Opened), String> {
        let song = crate::song::open(Path::new(&folder))?;
        let mixes = crate::mixes::load(&song.folder)?;
        let recipe = mix.and_then(|id| mixes.iter().find(|m| m.id == id).cloned()).unwrap_or_else(|| mixes[0].clone());
        let timing = SongTiming::from_song(&song.song);
        let stems = Arc::new(Stems::load(&song.folder, &song.song)?);
        let player = Player::start(stems, timing, &recipe, move |mix_seconds, playing| {
            let _ = handle.emit("playback-position", Position { mix_seconds, playing });
        })?;
        let opened = Opened { duration: player.duration, timeline: timing.timeline(&recipe), current: recipe.id.clone(), mixes };
        Ok((player, opened))
    })
    .await
    .map_err(|e| e.to_string())??;
    *playback.0.lock().unwrap() = Some(player);
    Ok(opened)
}

fn send(playback: &Playback, command: Command) -> Result<(), String> {
    match playback.0.lock().unwrap().as_ref() {
        Some(player) => {
            player.send(command);
            Ok(())
        }
        None => Err("No song is open".into()),
    }
}

#[tauri::command]
pub fn playback_play(playback: State<'_, Playback>) -> Result<(), String> {
    send(&playback, Command::Play)
}

#[tauri::command]
pub fn playback_pause(playback: State<'_, Playback>) -> Result<(), String> {
    send(&playback, Command::Pause)
}

#[tauri::command]
pub fn playback_seek(playback: State<'_, Playback>, mix_seconds: f64) -> Result<(), String> {
    send(&playback, Command::Seek(mix_seconds))
}

/// The mix playing changes (another one chosen, or this one edited) without stopping; returns its timeline.
#[tauri::command]
pub fn playback_set_mix(playback: State<'_, Playback>, recipe: Recipe) -> Result<Timeline, String> {
    let guard = playback.0.lock().unwrap();
    let player = guard.as_ref().ok_or("No song is open")?;
    let timeline = player.timing.timeline(&recipe);
    player.send(Command::Mix(recipe));
    Ok(timeline)
}

/// Back to the Library: the stems leave memory.
#[tauri::command]
pub fn playback_close(playback: State<'_, Playback>) {
    let old = playback.0.lock().unwrap().take();
    retire(old);
}
