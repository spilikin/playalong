//! A song's mixes, as the app edits them: `mixes.json` next to the song file (see the CLI's recipes.py).

use std::path::Path;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::engine::mixer::{Recipe, STEMS};

pub const FILE: &str = "mixes.json";
const FORMAT: &str = "playalong-mixes";
const VERSION: u64 = 1;

#[derive(Serialize, Deserialize)]
struct Stored {
    format: String,
    version: u64,
    mixes: Vec<Recipe>,
}

fn recipe(id: &str, name: &str, guitar: f64, mute: &[&str]) -> Recipe {
    let mut levels: std::collections::BTreeMap<String, f64> = STEMS.iter().map(|s| (s.to_string(), 0.0)).collect();
    levels.insert("guitar".into(), guitar);
    Recipe {
        id: id.into(),
        name: name.into(),
        levels,
        mute: mute.iter().map(|s| s.to_string()).collect(),
        solo: vec![],
        transpose: 0,
        tempo: 1.0,
        count_in: 1,
    }
}

/// Every new song's mixes, as the CLI writes them.
pub fn defaults() -> Vec<Recipe> {
    vec![recipe("original", "Original", 0.0, &[]), recipe("guide", "Guide", -15.0, &[]), recipe("no-guitar", "No guitar", 0.0, &["guitar"])]
}

fn stored_version(folder: &Path) -> Option<u64> {
    let text = std::fs::read_to_string(folder.join(FILE)).ok()?;
    let value: Value = serde_json::from_str(&text).ok()?;
    (value.get("format")?.as_str()? == FORMAT).then(|| value.get("version")?.as_u64())?
}

/// The song's mixes; the defaults when there's no file yet or it can't be read.
pub fn load(folder: &Path) -> Result<Vec<Recipe>, String> {
    if stored_version(folder).is_some_and(|v| v > VERSION) {
        return Err("These mixes were saved by a newer Playalong; update the app to use them".into());
    }
    let stored = std::fs::read_to_string(folder.join(FILE)).ok().and_then(|t| serde_json::from_str::<Stored>(&t).ok());
    Ok(match stored {
        Some(s) if s.format == FORMAT && !s.mixes.is_empty() => s.mixes,
        _ => defaults(),
    })
}

/// Written whole and renamed into place, so a crash never leaves half a file; a newer app's file stays.
pub fn save(folder: &Path, mixes: &[Recipe]) -> Result<(), String> {
    if stored_version(folder).is_some_and(|v| v > VERSION) {
        return Err("These mixes were saved by a newer Playalong; update the app to change them".into());
    }
    let body = serde_json::to_string_pretty(&Stored { format: FORMAT.into(), version: VERSION, mixes: mixes.to_vec() })
        .map_err(|e| e.to_string())?;
    let tmp = folder.join(".mixes.json.tmp");
    std::fs::write(&tmp, body).map_err(|e| format!("can't save the mixes: {e}"))?;
    std::fs::rename(&tmp, folder.join(FILE)).map_err(|e| format!("can't save the mixes: {e}"))
}

#[tauri::command]
pub fn mixes_load(folder: String) -> Result<Vec<Recipe>, String> {
    load(Path::new(&folder))
}

#[tauri::command]
pub fn mixes_save(folder: String, mixes: Vec<Recipe>) -> Result<(), String> {
    save(Path::new(&folder), &mixes)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_or_unreadable_gives_the_defaults() {
        let dir = tempfile::tempdir().unwrap();
        let names: Vec<String> = load(dir.path()).unwrap().into_iter().map(|m| m.name).collect();
        assert_eq!(names, ["Original", "Guide", "No guitar"]);
        std::fs::write(dir.path().join(FILE), "{oops").unwrap();
        assert_eq!(load(dir.path()).unwrap().len(), 3);
        let guide = &defaults()[1];
        assert_eq!(guide.levels["guitar"], -15.0);
        assert_eq!(defaults()[2].mute, ["guitar"]);
    }

    #[test]
    fn mixes_round_trip_in_the_clis_format() {
        let dir = tempfile::tempdir().unwrap();
        let mut mine = defaults();
        mine[1].name = "Band −2".into();
        mine[1].transpose = -2;
        save(dir.path(), &mine).unwrap();
        assert_eq!(load(dir.path()).unwrap(), mine);
        let stored: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(dir.path().join(FILE)).unwrap()).unwrap();
        assert_eq!((stored["format"].as_str(), stored["version"].as_u64()), (Some("playalong-mixes"), Some(1)));
    }

    #[test]
    fn a_newer_mixes_file_is_not_read_or_overwritten() {
        let dir: &Path = &tempfile::tempdir().unwrap().keep();
        let newer = r#"{"format": "playalong-mixes", "version": 2, "mixes": []}"#;
        std::fs::write(dir.join(FILE), newer).unwrap();
        assert!(load(dir).unwrap_err().contains("newer"));
        assert!(save(dir, &defaults()).is_err());
        assert_eq!(std::fs::read_to_string(dir.join(FILE)).unwrap(), newer);
    }
}
