//! Commands the UI uses to set up the runtime and make songs with it.
//!
//! The work runs on blocking threads and reports through events (`runtime-progress`, `make-song-line`).
//! Installing and making a song exclude each other: a song made while its runtime is being swapped out
//! would fail halfway.

use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, SystemTime};

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State};

use crate::runtime::{self, Installed, Plan};
use crate::song::OpenedSong;

const DOWNLOADER_STAMP: &str = "downloader-checked";
const DOWNLOADER_EVERY: Duration = Duration::from_secs(24 * 60 * 60);

#[derive(Default)]
pub struct Maker {
    busy: Mutex<Option<String>>,
    /// The CLI making a song right now, and whether the user stopped it.
    child: Mutex<Option<u32>>,
    stopped: AtomicBool,
}

/// Held while one long job runs; dropping it frees the maker.
pub struct Busy<'a>(&'a Maker);

impl Maker {
    pub fn begin(&self, what: &str) -> Result<Busy<'_>, String> {
        let mut busy = self.busy.lock().unwrap();
        if let Some(running) = busy.as_ref() {
            return Err(format!("Busy: {running}"));
        }
        *busy = Some(what.to_string());
        Ok(Busy(self))
    }

    fn running(&self) -> bool {
        self.busy.lock().unwrap().is_some()
    }
}

impl Drop for Busy<'_> {
    fn drop(&mut self) {
        *self.0.busy.lock().unwrap() = None;
    }
}

pub fn cli_args(source: &str, library: &str, transpose: i32) -> Vec<String> {
    let mut args = vec!["-l".to_string(), library.to_string(), "run".to_string(), source.to_string()];
    if transpose != 0 {
        args.extend(["-k".to_string(), transpose.to_string()]);
    }
    args
}

pub fn is_url(source: &str) -> bool {
    source.starts_with("http://") || source.starts_with("https://")
}

/// yt-dlp is refreshed at most once a day, and never if the last check can't be read as a time.
pub fn needs_downloader_check(age: Option<Duration>) -> bool {
    age.is_none_or(|a| a >= DOWNLOADER_EVERY)
}

/// A failed download worth retrying with a newer yt-dlp: not one that only needs a login.
pub fn worth_new_downloader(reason: &str) -> bool {
    let reason = reason.to_lowercase();
    !["sign in", "signed-in", "login", "cookies"].iter().any(|w| reason.contains(w))
}

fn root(app: &AppHandle) -> Result<PathBuf, String> {
    app.path().app_data_dir().map_err(|e| format!("can't find the app's data folder: {e}"))
}

fn code(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app.path().resource_dir().map_err(|e| format!("can't find the app's resources: {e}"))?.join("python"))
}

#[derive(Serialize)]
pub struct Status {
    installed: Option<Installed>,
    busy: bool,
}

#[tauri::command]
pub fn runtime_status(app: AppHandle, maker: State<'_, Maker>) -> Result<Status, String> {
    Ok(Status { installed: runtime::installed(&root(&app)?.join("runtime")), busy: maker.running() })
}

#[derive(Serialize)]
pub struct Check {
    plan: Plan,
    download_size: u64,
}

#[tauri::command]
pub async fn runtime_check(app: AppHandle) -> Result<Check, String> {
    let dir = root(&app)?.join("runtime");
    tauri::async_runtime::spawn_blocking(move || {
        let manifest = runtime::fetch_manifest(runtime::MANIFEST_URL)?;
        let plan = runtime::plan(runtime::installed(&dir).as_ref(), &manifest)?;
        Ok(Check { download_size: plan.download_size(), plan })
    })
    .await
    .map_err(|e| e.to_string())?
}

#[derive(Clone, Serialize)]
struct Progress {
    stage: &'static str,
    done: u64,
    total: u64,
}

#[tauri::command]
pub async fn runtime_install(app: AppHandle) -> Result<Option<Installed>, String> {
    let root = root(&app)?;
    tauri::async_runtime::spawn_blocking(move || {
        let maker = app.state::<Maker>();
        let _busy = maker.begin("setting up the runtime")?;
        let current = root.join("runtime");
        let manifest = runtime::fetch_manifest(runtime::MANIFEST_URL)?;
        let plan = runtime::plan(runtime::installed(&current).as_ref(), &manifest)?;
        let downloads = root.join("downloads");
        std::fs::create_dir_all(&downloads).map_err(|e| format!("can't create {}: {e}", downloads.display()))?;
        let fetched = |stage: &'static str, archive: &runtime::Archive| -> Result<PathBuf, String> {
            let to = downloads.join(&archive.file);
            let total = archive.size;
            runtime::fetch(archive, &to, |done| {
                let _ = app.emit("runtime-progress", Progress { stage, done, total });
            })?;
            Ok(to)
        };
        let runtime_file = plan.runtime.as_ref().map(|a| fetched("runtime", a)).transpose()?;
        let model_file = plan.model.as_ref().map(|a| fetched("model", a)).transpose()?;
        let _ = app.emit("runtime-progress", Progress { stage: "unpack", done: 0, total: 0 });
        let result = runtime::install(&root, runtime_file.as_deref(), model_file.as_deref());
        let _ = std::fs::remove_dir_all(&downloads);
        result?;
        Ok(runtime::installed(&current))
    })
    .await
    .map_err(|e| e.to_string())?
}

fn stamp_age(path: &Path) -> Option<Duration> {
    SystemTime::now().duration_since(std::fs::metadata(path).ok()?.modified().ok()?).ok()
}

#[derive(Clone, Serialize)]
struct Line {
    line: String,
}

#[tauri::command]
pub async fn make_song(app: AppHandle, source: String, library: String, transpose: i32) -> Result<OpenedSong, String> {
    let root = root(&app)?;
    let code = code(&app)?;
    let handle = app.clone();
    let folder = tauri::async_runtime::spawn_blocking(move || -> Result<PathBuf, String> {
        let maker = handle.state::<Maker>();
        let _busy = maker.begin("making a song")?;
        maker.stopped.store(false, Ordering::SeqCst);
        let runtime_dir = root.join("runtime");
        if runtime::installed(&runtime_dir).is_none() {
            return Err("The runtime isn't set up yet".into());
        }
        let emit = |line: &str| {
            let _ = handle.emit("make-song-line", Line { line: line.to_string() });
        };
        let env = [("PLAYALONG_CODE", code.as_path())];
        let update_downloader = || {
            emit("Checking for a newer YouTube downloader");
            let _ = runtime::run_cli(&runtime_dir, &["update-downloader".to_string()], &env, |_| {}, emit);
            let _ = std::fs::write(root.join(DOWNLOADER_STAMP), b"");
        };
        let youtube = is_url(&source);
        let mut updated = false;
        if youtube && needs_downloader_check(stamp_age(&root.join(DOWNLOADER_STAMP))) {
            update_downloader();
            updated = true;
        }
        let args = cli_args(&source, &library, transpose);
        let mut done = None;
        let mut run = || {
            let started = |pid| *maker.child.lock().unwrap() = Some(pid);
            runtime::run_cli(&runtime_dir, &args, &env, started, |line| {
                if let Some(folder) = runtime::finished_folder(line) {
                    done = Some(folder);
                }
                emit(line);
            })
        };
        let mut result = run();
        let stopped = || maker.stopped.load(Ordering::SeqCst);
        if let Err(reason) = &result
            && !stopped()
            && youtube
            && !updated
            && worth_new_downloader(reason)
        {
            emit(reason);
            update_downloader();
            result = run();
        }
        *maker.child.lock().unwrap() = None;
        if stopped() {
            return Err("Stopped".into());
        }
        result?;
        done.ok_or_else(|| "The runtime finished without a song".to_string())
    })
    .await
    .map_err(|e| e.to_string())??;
    crate::open_folder(&app, &folder.to_string_lossy())
}

#[tauri::command]
pub fn cancel_make(maker: State<'_, Maker>) {
    maker.stopped.store(true, Ordering::SeqCst);
    if let Some(pid) = *maker.child.lock().unwrap() {
        runtime::stop(pid);
    }
}

/// `~/Music/Playalong`, where the app keeps the songs it makes.
#[tauri::command]
pub fn default_library(app: AppHandle) -> Result<String, String> {
    let music = app.path().audio_dir().map_err(|e| format!("can't find the Music folder: {e}"))?;
    Ok(music.join("Playalong").to_string_lossy().into_owned())
}

/// The library's songs, with their covers made readable for the web view.
#[tauri::command]
pub fn list_library(app: AppHandle, library: String) -> Vec<crate::library::LibrarySong> {
    let library = PathBuf::from(library);
    let _ = app.asset_protocol_scope().allow_directory(&library, true);
    crate::library::list(&library)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_cli_gets_the_library_source_and_transposition() {
        assert_eq!(cli_args("https://y/x", "/lib", -2), ["-l", "/lib", "run", "https://y/x", "-k", "-2"]);
        assert_eq!(cli_args("/a.wav", "/lib", 0), ["-l", "/lib", "run", "/a.wav"]);
    }

    #[test]
    fn the_downloader_is_checked_once_a_day() {
        assert!(needs_downloader_check(None));
        assert!(!needs_downloader_check(Some(Duration::from_secs(3600))));
        assert!(needs_downloader_check(Some(DOWNLOADER_EVERY)));
    }

    #[test]
    fn a_login_problem_is_not_a_downloader_problem() {
        assert!(worth_new_downloader("ERROR: [youtube] x: Requested format is not available"));
        assert!(!worth_new_downloader("YouTube wants a signed-in account for this video"));
        assert!(is_url("https://youtu.be/x") && !is_url("/Users/a/song.wav"));
    }

    #[test]
    fn making_a_song_waits_for_the_install() {
        let maker = Maker::default();
        let install = maker.begin("setting up the runtime").unwrap();
        assert_eq!(maker.begin("making a song").err().unwrap(), "Busy: setting up the runtime");
        drop(install);
        assert!(maker.begin("making a song").is_ok());
    }
}
