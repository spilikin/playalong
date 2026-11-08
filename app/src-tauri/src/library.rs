//! The songs in a library folder: one row per song folder holding a `.playalong` file.

use std::path::{Path, PathBuf};
use std::time::UNIX_EPOCH;

use serde::Serialize;
use serde_json::Value;

use crate::song;

#[derive(Debug, Serialize, PartialEq)]
pub struct LibrarySong {
    pub folder: PathBuf,
    pub title: String,
    pub artist: Option<String>,
    pub key: Option<String>,
    pub bpm: Option<f64>,
    pub mixes: usize,
    /// Semitones of the transposed mixes, e.g. [-2]; empty when all are in the original key.
    pub transposed: Vec<i64>,
    pub cover: Option<PathBuf>,
    /// When the song file was made, seconds since 1970; newest songs come first.
    pub added: u64,
}

fn row(folder: &Path) -> Option<LibrarySong> {
    let file = song::locate(folder).ok()?;
    let data: Value = serde_json::from_str(&std::fs::read_to_string(&file).ok()?).ok()?;
    if data.get("format").and_then(Value::as_str) != Some(song::FORMAT) {
        return None;
    }
    let text = |key: &str| data.get(key).and_then(Value::as_str).map(String::from);
    // The song's mixes (defaults without a file); a newer app's file still lists the song, without counts.
    let mixes = crate::mixes::load(folder).unwrap_or_default();
    let mut transposed: Vec<i64> = mixes.iter().map(|m| m.transpose as i64).filter(|&t| t != 0).collect();
    transposed.sort_unstable();
    transposed.dedup();
    let meta = std::fs::metadata(&file).ok()?;
    let added = meta.created().or_else(|_| meta.modified()).ok()?;
    Some(LibrarySong {
        folder: folder.to_path_buf(),
        title: text("title").unwrap_or_else(|| folder.file_name().unwrap_or_default().to_string_lossy().into()),
        artist: text("artist"),
        key: text("key"),
        bpm: data.pointer("/tempo/bpm").and_then(Value::as_f64),
        mixes: mixes.len(),
        transposed,
        cover: data.pointer("/cover/file").and_then(Value::as_str).map(|f| folder.join(f)),
        added: added.duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0),
    })
}

/// Every song in `library`, newest first; a missing library is an empty one.
pub fn list(library: &Path) -> Vec<LibrarySong> {
    let Ok(entries) = std::fs::read_dir(library) else { return vec![] };
    let mut songs: Vec<LibrarySong> =
        entries.flatten().map(|e| e.path()).filter(|p| p.is_dir()).filter_map(|p| row(&p)).collect();
    songs.sort_by(|a, b| b.added.cmp(&a.added).then_with(|| a.title.cmp(&b.title)));
    songs
}

#[cfg(test)]
mod tests {
    use super::*;

    fn song(library: &Path, name: &str, json: &str) -> PathBuf {
        let folder = library.join(name);
        std::fs::create_dir_all(&folder).unwrap();
        std::fs::write(folder.join(format!("{name}.playalong")), json).unwrap();
        folder
    }

    #[test]
    fn lists_each_song_with_what_the_table_shows() {
        let dir = tempfile::tempdir().unwrap();
        let folder = song(
            dir.path(),
            "kad",
            r#"{"format": "playalong-song", "version": 2, "title": "Kad izdzisīs", "artist": "Miks",
                "key": "Bb minor", "tempo": {"bpm": 79.9}, "cover": {"file": "cover.jpg"}}"#,
        );
        let mut mixes = crate::mixes::defaults();
        mixes[1].transpose = -2;
        let mut lower = mixes[2].clone();
        lower.id = "lower".into();
        lower.transpose = -2;
        mixes.push(lower);
        crate::mixes::save(&folder, &mixes).unwrap();
        std::fs::create_dir_all(dir.path().join("not-a-song")).unwrap();
        std::fs::write(dir.path().join("stray.txt"), "x").unwrap();
        let songs = list(dir.path());
        assert_eq!(songs.len(), 1);
        let s = &songs[0];
        assert_eq!((s.title.as_str(), s.artist.as_deref(), s.key.as_deref()), ("Kad izdzisīs", Some("Miks"), Some("Bb minor")));
        assert_eq!((s.bpm, s.mixes, s.transposed.clone()), (Some(79.9), 4, vec![-2]));
        assert_eq!(s.cover, Some(folder.join("cover.jpg")));
        assert!(s.added > 0);
    }

    #[test]
    fn a_missing_library_or_odd_files_are_no_songs() {
        let dir = tempfile::tempdir().unwrap();
        assert!(list(&dir.path().join("nope")).is_empty());
        song(dir.path(), "other", r#"{"format": "something-else"}"#);
        song(dir.path(), "broken", "{not json");
        let bare = song(dir.path(), "bare", r#"{"format": "playalong-song", "version": 1}"#);
        let songs = list(dir.path());
        assert_eq!(songs.len(), 1);
        // Without a mixes file a song has the default three.
        assert_eq!((songs[0].title.as_str(), songs[0].mixes), ("bare", 3));
        assert_eq!(songs[0].folder, bare);
    }
}
