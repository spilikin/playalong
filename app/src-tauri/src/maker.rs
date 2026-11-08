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

    fn is_stopped(&self) -> bool {
        self.stopped.load(Ordering::SeqCst)
    }

    /// Stop the song being made: the step running now ends, and no later step starts.
    pub fn cancel(&self) {
        self.stopped.store(true, Ordering::SeqCst);
        if let Some(pid) = *self.child.lock().unwrap() {
            runtime::stop(pid);
        }
    }

    /// One CLI run for the song being made (yt-dlp check, the song, a retry). Its pid is known to `cancel`
    /// for exactly as long as it runs; a Stop that lands just before it starts still ends it.
    fn run_cli(&self, runtime_dir: &Path, args: &[String], env: &[(&str, &Path)], line: impl FnMut(&str)) -> Result<(), String> {
        if self.is_stopped() {
            return Err("Stopped".into());
        }
        let started = |pid| {
            let mut child = self.child.lock().unwrap();
            *child = Some(pid);
            if self.is_stopped() {
                runtime::stop(pid);
            }
        };
        let result = runtime::run_cli(runtime_dir, args, env, started, line);
        *self.child.lock().unwrap() = None;
        result
    }
}

impl Drop for Busy<'_> {
    fn drop(&mut self) {
        *self.0.busy.lock().unwrap() = None;
    }
}

/// A new song: download, cover, instruments, chords and its default mixes, which play live.
pub fn cli_args(source: &str, library: &str) -> Vec<String> {
    ["-l", library, "run", source].map(String::from).to_vec()
}

/// The jobs a song can run in the background, as `playalong` arguments.
pub enum SongJob {
    Refresh,
    Retime { start: Option<f64>, bpm: Option<f64> },
    Export { mix: String },
    GarageBand { transpose: i32 },
}

impl SongJob {
    /// Values come from the web view; a mix id is checked so it can't be taken for an option.
    pub fn args(&self, folder: &str) -> Result<Vec<String>, String> {
        let mut args = vec![String::new(), folder.to_string()];
        match self {
            SongJob::Refresh => args[0] = "refresh".into(),
            SongJob::Retime { start, bpm } => {
                args[0] = "retime".into();
                if let Some(s) = start {
                    args.extend(["--start".into(), format!("{s:.2}")]);
                }
                if let Some(b) = bpm {
                    args.extend(["--bpm".into(), format!("{b:.1}")]);
                }
            }
            SongJob::Export { mix } => {
                let plain = mix.chars().all(|c| c.is_alphanumeric() || c == '-' || c == '_');
                if mix.is_empty() || mix.starts_with('-') || !plain {
                    return Err(format!("Not a mix id: {mix}"));
                }
                args[0] = "export".into();
                args.push(mix.clone());
            }
            SongJob::GarageBand { transpose } => {
                if !(-12..=12).contains(transpose) {
                    return Err("The key moves at most 12 semitones".into());
                }
                args[0] = "garageband".into();
                if *transpose != 0 {
                    args.extend(["-k".into(), transpose.to_string()]);
                }
                args.push("--band".into());
            }
        }
        Ok(args)
    }
}

/// The file `export` wrote, from its last line ("  <path>.mp3").
pub fn exported_file(line: &str) -> Option<PathBuf> {
    let path = line.trim();
    path.ends_with(".mp3").then(|| PathBuf::from(path))
}

/// Whether `folder` is a song inside `library` (and not the library itself): the only thing deleted.
pub fn inside_library(library: &Path, folder: &Path) -> bool {
    match (library.canonicalize(), folder.canonicalize()) {
        (Ok(lib), Ok(song)) => song != lib && song.starts_with(&lib),
        _ => false,
    }
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

/// `~/Library/Caches/dev.playalong`: bytecode, deno, yt-dlp and downloads in progress, all safe to delete.
fn cache(app: &AppHandle) -> Result<PathBuf, String> {
    app.path().app_cache_dir().map_err(|e| format!("can't find the app's cache folder: {e}"))
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
    let cache = cache(&app)?;
    tauri::async_runtime::spawn_blocking(move || {
        let maker = app.state::<Maker>();
        let _busy = maker.begin("setting up the runtime")?;
        let current = root.join("runtime");
        let manifest = runtime::fetch_manifest(runtime::MANIFEST_URL)?;
        let plan = runtime::plan(runtime::installed(&current).as_ref(), &manifest)?;
        let downloads = runtime::Downloads::new(&cache)?;
        let fetched = |stage: &'static str, archive: &runtime::Archive| -> Result<PathBuf, String> {
            let to = downloads.path().join(&archive.file);
            let total = archive.size;
            runtime::fetch(archive, &to, |done| {
                let _ = app.emit("runtime-progress", Progress { stage, done, total });
            })?;
            Ok(to)
        };
        let runtime_file = plan.runtime.as_ref().map(|a| fetched("runtime", a)).transpose()?;
        let model_file = plan.model.as_ref().map(|a| fetched("model", a)).transpose()?;
        let _ = app.emit("runtime-progress", Progress { stage: "unpack", done: 0, total: 0 });
        runtime::install(&root, runtime_file.as_deref(), model_file.as_deref())?;
        if runtime_file.is_some() {
            runtime::forget_bytecode(&cache);
        }
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
pub async fn make_song(app: AppHandle, source: String, library: String) -> Result<OpenedSong, String> {
    let root = root(&app)?;
    let code = code(&app)?;
    let cache = cache(&app)?;
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
        let env = [("PLAYALONG_CODE", code.as_path()), ("PLAYALONG_CACHE", cache.as_path())];
        let update_downloader = || {
            emit("Checking for a newer YouTube downloader");
            let _ = maker.run_cli(&runtime_dir, &["update-downloader".to_string()], &env, emit);
            let _ = std::fs::write(root.join(DOWNLOADER_STAMP), b"");
        };
        let youtube = is_url(&source);
        let mut updated = false;
        if youtube && needs_downloader_check(stamp_age(&root.join(DOWNLOADER_STAMP))) {
            update_downloader();
            updated = true;
        }
        let args = cli_args(&source, &library);
        let mut done = None;
        let mut run = || {
            maker.run_cli(&runtime_dir, &args, &env, |line| {
                if let Some(folder) = runtime::finished_folder(line) {
                    done = Some(folder);
                }
                emit(line);
            })
        };
        let mut result = run();
        if let Err(reason) = &result
            && !maker.is_stopped()
            && youtube
            && !updated
            && worth_new_downloader(reason)
        {
            emit(reason);
            update_downloader();
            result = run();
        }
        if maker.is_stopped() {
            return Err("Stopped".into());
        }
        result?;
        done.ok_or_else(|| "The runtime finished without a song".to_string())
    })
    .await
    .map_err(|e| e.to_string())??;
    crate::open_folder(&app, &folder.to_string_lossy())
}

#[derive(Clone, Serialize)]
struct JobLine {
    folder: String,
    line: String,
}

/// A job on a song, in the background; its output lines go out as `song-job-line`, and the last line is
/// returned (an export prints the file it wrote there).
async fn song_job(app: AppHandle, folder: String, job: SongJob, what: &'static str) -> Result<String, String> {
    let args = job.args(&folder)?;
    let root = root(&app)?;
    let code = code(&app)?;
    let cache = cache(&app)?;
    let handle = app.clone();
    tauri::async_runtime::spawn_blocking(move || -> Result<String, String> {
        let maker = handle.state::<Maker>();
        let _busy = maker.begin(what)?;
        maker.stopped.store(false, Ordering::SeqCst);
        let runtime_dir = root.join("runtime");
        if runtime::installed(&runtime_dir).is_none() {
            return Err("The audio tools aren't set up yet".into());
        }
        let env = [("PLAYALONG_CODE", code.as_path()), ("PLAYALONG_CACHE", cache.as_path())];
        let mut last = String::new();
        let result = maker.run_cli(&runtime_dir, &args, &env, |line| {
            last = line.to_string();
            let _ = handle.emit("song-job-line", JobLine { folder: folder.clone(), line: line.to_string() });
        });
        if maker.is_stopped() {
            return Err("Stopped".into());
        }
        result.map(|_| last)
    })
    .await
    .map_err(|e| e.to_string())?
}

/// A song from before live mixes: rendered mixes go, default mixes and a version 2 song file come.
#[tauri::command]
pub async fn song_refresh(app: AppHandle, folder: String) -> Result<OpenedSong, String> {
    song_job(app.clone(), folder.clone(), SongJob::Refresh, "bringing the song up to date").await?;
    crate::open_folder(&app, &folder)
}

/// A new start and/or tempo; chords and bars are found again.
#[tauri::command]
pub async fn song_retime(
    app: AppHandle,
    folder: String,
    start: Option<f64>,
    bpm: Option<f64>,
) -> Result<OpenedSong, String> {
    song_job(app.clone(), folder.clone(), SongJob::Retime { start, bpm }, "finding chords and bars").await?;
    crate::open_folder(&app, &folder)
}

/// One mix as an MP3, shown in Finder once it's written.
#[tauri::command]
pub async fn song_export(app: AppHandle, folder: String, mix: String) -> Result<String, String> {
    let last = song_job(app, folder, SongJob::Export { mix }, "exporting a mix").await?;
    let file = exported_file(&last).ok_or("The export didn't say where it wrote the file")?;
    let _ = std::process::Command::new("/usr/bin/open").arg("-R").arg(&file).status();
    Ok(file.to_string_lossy().into_owned())
}

#[tauri::command]
pub async fn song_garageband(app: AppHandle, folder: String, transpose: i32) -> Result<OpenedSong, String> {
    let job = SongJob::GarageBand { transpose };
    song_job(app.clone(), folder.clone(), job, "building the GarageBand project").await?;
    crate::open_folder(&app, &folder)
}

/// A song to the Trash; only a folder inside the library.
#[tauri::command]
pub fn delete_song(folder: String, library: String) -> Result<(), String> {
    if !inside_library(Path::new(&library), Path::new(&folder)) {
        return Err(format!("{folder} isn't a song in the library"));
    }
    trash::delete(&folder).map_err(|e| format!("can't move {folder} to the Trash: {e}"))
}

/// A song's GarageBand project, from the path the song file gives it; nothing outside the song folder.
pub fn project_path(folder: &str, project: &str) -> Result<PathBuf, String> {
    let root = Path::new(folder).canonicalize().map_err(|e| format!("can't find {folder}: {e}"))?;
    let path = root.join(project).canonicalize().map_err(|e| format!("can't find {project}: {e}"))?;
    if !path.starts_with(&root) || path.extension().is_none_or(|e| e != "band") || !path.is_dir() {
        return Err(format!("Not a GarageBand project of this song: {project}"));
    }
    Ok(path)
}

#[tauri::command]
pub fn open_in_garageband(folder: String, project: String) -> Result<(), String> {
    let path = project_path(&folder, &project)?;
    std::process::Command::new("/usr/bin/open")
        .args(["-a", "GarageBand"])
        .arg(path)
        .status()
        .map_err(|e| format!("can't open GarageBand: {e}"))?;
    Ok(())
}

#[tauri::command]
pub fn cancel_make(maker: State<'_, Maker>) {
    maker.cancel();
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
    fn a_new_song_is_run_without_rendering_mixes() {
        assert_eq!(cli_args("https://y/x", "/lib"), ["-l", "/lib", "run", "https://y/x"]);
    }

    #[test]
    fn song_jobs_become_cli_arguments() {
        assert_eq!(SongJob::Refresh.args("/s").unwrap(), ["refresh", "/s"]);
        let retime = SongJob::Retime { start: Some(12.345), bpm: Some(92.04) };
        assert_eq!(retime.args("/s").unwrap(), ["retime", "/s", "--start", "12.35", "--bpm", "92.0"]);
        assert_eq!(SongJob::Retime { start: None, bpm: None }.args("/s").unwrap(), ["retime", "/s"]);
        assert_eq!(SongJob::Export { mix: "band-2".into() }.args("/s").unwrap(), ["export", "/s", "band-2"]);
        assert!(SongJob::Export { mix: "--all".into() }.args("/s").is_err());
        let gb = SongJob::GarageBand { transpose: -2 };
        assert_eq!(gb.args("/s").unwrap(), ["garageband", "/s", "-k", "-2", "--band"]);
        assert_eq!(SongJob::GarageBand { transpose: 0 }.args("/s").unwrap(), ["garageband", "/s", "--band"]);
        assert!(SongJob::GarageBand { transpose: 13 }.args("/s").is_err());
        let line = "  /lib/s/exports/s - Guide.mp3";
        assert_eq!(exported_file(line), Some(PathBuf::from("/lib/s/exports/s - Guide.mp3")));
        assert_eq!(exported_file("Song file: /x.playalong"), None);
    }

    #[test]
    fn delete_only_inside_the_library() {
        let lib = tempfile::tempdir().unwrap();
        let song = lib.path().join("song");
        std::fs::create_dir(&song).unwrap();
        let elsewhere = tempfile::tempdir().unwrap();
        assert!(inside_library(lib.path(), &song));
        assert!(!inside_library(lib.path(), lib.path()));
        assert!(!inside_library(lib.path(), elsewhere.path()));
        assert!(!inside_library(lib.path(), &lib.path().join("missing")));
        assert!(!inside_library(lib.path(), &song.join("..").join("..")));
    }

    #[test]
    fn only_a_garageband_project_inside_the_song_is_opened() {
        let song = tempfile::tempdir().unwrap();
        let project = song.path().join("mixes/s - GarageBand 120 BPM.band");
        std::fs::create_dir_all(&project).unwrap();
        let folder = song.path().to_str().unwrap();
        assert_eq!(project_path(folder, "mixes/s - GarageBand 120 BPM.band").unwrap(), project.canonicalize().unwrap());
        assert!(project_path(folder, "../elsewhere.band").is_err());
        assert!(project_path(folder, "mixes").is_err());
        assert!(project_path(folder, "mixes/missing.band").is_err());
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

    fn sleeper(dir: &Path) {
        let bin = dir.join("bin");
        std::fs::create_dir_all(&bin).unwrap();
        let script = bin.join("playalong");
        std::fs::write(&script, "#!/bin/sh\necho started\nexec sleep 30\n").unwrap();
        std::fs::set_permissions(&script, std::os::unix::fs::PermissionsExt::from_mode(0o755)).unwrap();
    }

    #[test]
    fn after_stop_no_further_step_starts() {
        let dir = tempfile::tempdir().unwrap();
        sleeper(dir.path());
        let maker = Maker::default();
        maker.cancel();
        let mut lines = 0;
        assert_eq!(maker.run_cli(dir.path(), &[], &[], |_| lines += 1).unwrap_err(), "Stopped");
        assert_eq!(lines, 0);
    }

    #[test]
    fn stop_ends_whichever_step_is_running() {
        let dir = tempfile::tempdir().unwrap();
        sleeper(dir.path());
        let maker = Maker::default();
        let begun = std::time::Instant::now();
        std::thread::scope(|scope| {
            scope.spawn(|| {
                while maker.child.lock().unwrap().is_none() {
                    std::thread::sleep(Duration::from_millis(20));
                }
                maker.cancel();
            });
            assert!(maker.run_cli(dir.path(), &[], &[], |_| {}).is_err());
        });
        assert!(begun.elapsed().as_secs() < 10);
        assert!(maker.child.lock().unwrap().is_none(), "a finished step leaves no process id to stop");
    }
}
