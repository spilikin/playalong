//! Finding and checking a song's `.playalong` file, written by the playalong CLI.

use std::path::{Path, PathBuf};

use serde::Serialize;
use serde_json::Value;

pub const FORMAT: &str = "playalong-song";
/// The newest song file version this app understands.
pub const VERSION: u64 = 1;
const SUFFIX: &str = "playalong";

#[derive(Debug, Serialize)]
pub struct OpenedSong {
    /// The song's folder; every path inside the song file is relative to it.
    pub folder: PathBuf,
    pub file: PathBuf,
    /// Passed through as written; the UI reads the fields it needs (see the CLI's song.py).
    pub song: Value,
}

/// `path` is a song folder or a `.playalong` file in one.
pub fn locate(path: &Path) -> Result<PathBuf, String> {
    if path.is_file() {
        return if path.extension().is_some_and(|e| e == SUFFIX) {
            Ok(path.to_path_buf())
        } else {
            Err(format!("{} is not a song file (.{SUFFIX})", path.display()))
        };
    }
    if !path.is_dir() {
        return Err(format!("{} doesn't exist", path.display()));
    }
    // The CLI names the file after its folder; any other one will do if that's missing.
    if let Some(name) = path.file_name() {
        let named = path.join(format!("{}.{SUFFIX}", name.to_string_lossy()));
        if named.is_file() {
            return Ok(named);
        }
    }
    let mut found: Vec<PathBuf> = std::fs::read_dir(path)
        .map_err(|e| format!("can't read {}: {e}", path.display()))?
        .flatten()
        .map(|entry| entry.path())
        .filter(|p| p.is_file() && p.extension().is_some_and(|e| e == SUFFIX))
        .collect();
    found.sort();
    found.into_iter().next().ok_or_else(|| {
        format!("No song file in {}. Run `playalong chords` on this folder to create one.", path.display())
    })
}

pub fn open(path: &Path) -> Result<OpenedSong, String> {
    let file = locate(path)?;
    let text = std::fs::read_to_string(&file).map_err(|e| format!("can't read {}: {e}", file.display()))?;
    let song: Value = serde_json::from_str(&text).map_err(|e| format!("{} is not valid JSON: {e}", file.display()))?;
    if song.get("format").and_then(Value::as_str) != Some(FORMAT) {
        return Err(format!("{} is not a playalong song file", file.display()));
    }
    let version = song.get("version").and_then(Value::as_u64).unwrap_or(0);
    if version > VERSION {
        return Err(format!("{} is song file version {version}; this app reads up to {VERSION}. Update the app.", file.display()));
    }
    let folder = file.parent().map(Path::to_path_buf).unwrap_or_default();
    Ok(OpenedSong { folder, file, song })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn song_dir(name: &str, body: &str) -> (tempfile::TempDir, PathBuf) {
        let root = tempfile::tempdir().unwrap();
        let dir = root.path().join(name);
        std::fs::create_dir(&dir).unwrap();
        std::fs::write(dir.join(format!("{name}.playalong")), body).unwrap();
        (root, dir)
    }

    const SONG: &str = r#"{"format": "playalong-song", "version": 1, "title": "Song"}"#;

    #[test]
    fn opens_a_folder_or_its_song_file() {
        let (_root, dir) = song_dir("artist-song", SONG);
        let from_folder = open(&dir).unwrap();
        assert_eq!(from_folder.folder, dir);
        assert_eq!(from_folder.song["title"], "Song");
        let from_file = open(&dir.join("artist-song.playalong")).unwrap();
        assert_eq!(from_file.file, from_folder.file);
    }

    #[test]
    fn a_folder_without_its_named_file_uses_any_song_file() {
        let root = tempfile::tempdir().unwrap();
        std::fs::write(root.path().join("renamed.playalong"), SONG).unwrap();
        assert!(open(root.path()).unwrap().file.ends_with("renamed.playalong"));
    }

    #[test]
    fn says_what_to_do_when_there_is_no_song_file() {
        let root = tempfile::tempdir().unwrap();
        let err = open(root.path()).unwrap_err();
        assert!(err.contains("playalong chords"), "{err}");
    }

    #[test]
    fn rejects_other_files_and_newer_versions() {
        let (_root, dir) = song_dir("a", r#"{"title": "x"}"#);
        assert!(open(&dir).unwrap_err().contains("not a playalong song file"));
        let (_root, dir) = song_dir("b", r#"{"format": "playalong-song", "version": 2}"#);
        assert!(open(&dir).unwrap_err().contains("Update the app"));
        let (_root, dir) = song_dir("c", "not json");
        assert!(open(&dir).unwrap_err().contains("not valid JSON"));
        let plain = dir.join("notes.txt");
        std::fs::write(&plain, "hi").unwrap();
        assert!(open(&plain).unwrap_err().contains("not a song file"));
    }
}
