mod song;

use std::path::PathBuf;

use serde::Serialize;
use tauri::{AppHandle, Manager};

use crate::song::OpenedSong;

/// Opens a song folder (or its `.playalong` file) and lets the web view play audio from that folder
/// only, through the asset protocol.
#[tauri::command]
fn open_song(app: AppHandle, path: String) -> Result<OpenedSong, String> {
    let opened = song::open(&PathBuf::from(path))?;
    app.asset_protocol_scope()
        .allow_directory(&opened.folder, true)
        .map_err(|e| format!("can't give the player access to {}: {e}", opened.folder.display()))?;
    Ok(opened)
}

/// A song to open at launch: `Playalong <folder> [--at SECONDS]`, where `--at` is a time in the song.
#[derive(Debug, Default, PartialEq, Serialize)]
struct Launch {
    path: Option<String>,
    at: Option<f64>,
}

fn parse_launch(args: impl IntoIterator<Item = String>) -> Launch {
    let mut launch = Launch::default();
    let mut args = args.into_iter();
    while let Some(arg) = args.next() {
        if arg == "--at" {
            launch.at = args.next().and_then(|v| v.parse().ok());
        } else if !arg.starts_with('-') {
            // Finder used to add a `-psn_…` process serial number; anything else dashed is ignored too.
            launch.path = Some(arg);
        }
    }
    launch
}

#[tauri::command]
fn launch_args() -> Launch {
    parse_launch(std::env::args().skip(1))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![open_song, launch_args])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn parse(args: &[&str]) -> Launch {
        parse_launch(args.iter().map(|a| a.to_string()))
    }

    #[test]
    fn a_folder_and_an_optional_song_time() {
        assert_eq!(parse(&[]), Launch::default());
        assert_eq!(parse(&["/lib/song"]), Launch { path: Some("/lib/song".into()), at: None });
        assert_eq!(parse(&["/lib/song", "--at", "95.5"]), Launch { path: Some("/lib/song".into()), at: Some(95.5) });
        assert_eq!(parse(&["-psn_0_123", "--at", "x"]), Launch::default());
    }
}
