//! The portable runtime that makes songs: finding it, updating it from GitHub Releases, and running it.
//!
//! The CLI's runtime/package.py publishes a runtime archive per version and the separation model on its
//! own, and points at both from one `manifest.json`. An update downloads only what changed, checks each
//! archive's sha256, unpacks into a staging folder and swaps it in whole, so a broken download never
//! replaces a working runtime.

use std::fs;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

pub const MANIFEST_URL: &str = "https://github.com/spilikin/playalong/releases/download/updates/manifest.json";
/// The runtime series this app's Python code runs on (runtime/build.py's SERIES).
pub const RUNTIME_SERIES: u64 = 1;
const MANIFEST_FORMAT: &str = "playalong-runtime-manifest";
const MANIFEST_VERSION: u64 = 1;
const MODELS: &str = "models";
const STAGING: &str = "runtime.staging";
const RETIRED: &str = "runtime.old";

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
pub struct Archive {
    pub file: String,
    pub url: String,
    pub size: u64,
    pub sha256: String,
    pub unpacked_size: u64,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
pub struct RuntimeEntry {
    pub version: String,
    #[serde(default = "first_series")]
    pub series: u64,
    pub commit: String,
    #[serde(flatten)]
    pub archive: Archive,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
pub struct ModelEntry {
    pub name: String,
    #[serde(flatten)]
    pub archive: Archive,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
pub struct Manifest {
    pub format: String,
    pub version: u64,
    pub runtime: RuntimeEntry,
    pub model: ModelEntry,
}

impl Manifest {
    pub fn parse(text: &str) -> Result<Manifest, String> {
        let manifest: Manifest =
            serde_json::from_str(text).map_err(|e| format!("the runtime manifest is not readable: {e}"))?;
        if manifest.format != MANIFEST_FORMAT {
            return Err("the runtime manifest is not a playalong manifest".into());
        }
        if manifest.version > MANIFEST_VERSION {
            return Err("the runtime needs a newer Playalong app; update the app".into());
        }
        Ok(manifest)
    }
}

fn first_series() -> u64 {
    1
}

/// What is installed: the runtime's version and which model sits in it.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Installed {
    pub version: String,
    pub series: u64,
    pub commit: String,
    pub model: Option<String>,
}

pub fn installed(dir: &Path) -> Option<Installed> {
    let info: serde_json::Value = serde_json::from_str(&fs::read_to_string(dir.join("runtime.json")).ok()?).ok()?;
    let model = fs::read_dir(dir.join(MODELS))
        .ok()?
        .flatten()
        .find(|e| e.path().is_dir())
        .map(|e| e.file_name().to_string_lossy().into_owned());
    Some(Installed {
        version: info.get("version")?.as_str()?.to_string(),
        series: info.get("series").and_then(|v| v.as_u64()).unwrap_or(1),
        commit: info.get("commit")?.as_str()?.to_string(),
        model,
    })
}

/// The downloads that bring `installed` up to `manifest`: nothing when it matches.
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct Plan {
    pub runtime: Option<Archive>,
    pub model: Option<Archive>,
    pub version: String,
}

impl Plan {
    pub fn download_size(&self) -> u64 {
        self.runtime.iter().chain(self.model.iter()).map(|a| a.size).sum()
    }
}

pub fn plan(installed: Option<&Installed>, manifest: &Manifest) -> Result<Plan, String> {
    if manifest.runtime.series > RUNTIME_SERIES {
        return Err("This runtime needs a newer Playalong; update the app first".into());
    }
    let runtime_current = installed
        .is_some_and(|i| i.version == manifest.runtime.version && i.series == RUNTIME_SERIES);
    let model_current = installed.is_some_and(|i| i.model.as_deref() == Some(manifest.model.name.as_str()));
    Ok(Plan {
        runtime: (!runtime_current).then(|| manifest.runtime.archive.clone()),
        model: (!model_current).then(|| manifest.model.archive.clone()),
        version: manifest.runtime.version.clone(),
    })
}

/// Copy `from` into `to`, checking its sha256 and reporting bytes done as it goes.
pub fn download(
    mut from: impl Read,
    to: &Path,
    sha256: &str,
    mut progress: impl FnMut(u64),
) -> Result<(), String> {
    let mut out = fs::File::create(to).map_err(|e| format!("can't write {}: {e}", to.display()))?;
    let mut hasher = Sha256::new();
    let mut buf = vec![0u8; 1 << 20];
    let mut done = 0u64;
    loop {
        let n = from.read(&mut buf).map_err(|e| format!("download interrupted: {e}"))?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
        out.write_all(&buf[..n]).map_err(|e| format!("can't write {}: {e}", to.display()))?;
        done += n as u64;
        progress(done);
    }
    let digest: String = hasher.finalize().iter().map(|b| format!("{b:02x}")).collect();
    if digest != sha256 {
        let _ = fs::remove_file(to);
        return Err("the download is damaged (checksum mismatch); try again".into());
    }
    Ok(())
}

pub fn unpack(archive: &Path, into: &Path) -> Result<(), String> {
    let file = fs::File::open(archive).map_err(|e| format!("can't open {}: {e}", archive.display()))?;
    let decoder = zstd::Decoder::new(file).map_err(|e| format!("can't read {}: {e}", archive.display()))?;
    let mut tar = tar::Archive::new(decoder);
    tar.set_preserve_permissions(true);
    // `unpack` refuses entries that would land outside `into`.
    tar.unpack(into).map_err(|e| format!("can't unpack {}: {e}", archive.display()))
}

/// Put the downloaded archives in place under `root` (the folder holding `runtime/`).
///
/// A new runtime is unpacked into a staging folder, takes over the installed model unless a new one came
/// too, and replaces the old runtime by renaming, so `runtime/` is always a complete runtime.
pub fn install(root: &Path, runtime: Option<&Path>, model: Option<&Path>) -> Result<(), String> {
    let current = root.join("runtime");
    let staging = root.join(STAGING);
    let retired = root.join(RETIRED);
    for leftover in [&staging, &retired] {
        if leftover.exists() {
            fs::remove_dir_all(leftover).map_err(|e| format!("can't clear {}: {e}", leftover.display()))?;
        }
    }
    let Some(runtime) = runtime else {
        if let Some(model) = model {
            install_model(&current, model)?;
        }
        return Ok(());
    };

    fs::create_dir_all(&staging).map_err(|e| format!("can't create {}: {e}", staging.display()))?;
    unpack(runtime, &staging)?;
    match model {
        Some(model) => install_model(&staging, model)?,
        None => {
            let old_models = current.join(MODELS);
            if old_models.is_dir() {
                fs::rename(&old_models, staging.join(MODELS))
                    .map_err(|e| format!("can't keep the installed model: {e}"))?;
            }
        }
    }
    if current.exists() {
        fs::rename(&current, &retired).map_err(|e| format!("can't replace the old runtime: {e}"))?;
    }
    fs::rename(&staging, &current).map_err(|e| format!("can't put the new runtime in place: {e}"))?;
    let _ = fs::remove_dir_all(&retired);
    Ok(())
}

fn install_model(runtime: &Path, model: &Path) -> Result<(), String> {
    let models = runtime.join(MODELS);
    let fresh = runtime.join("models.new");
    let _ = fs::remove_dir_all(&fresh);
    fs::create_dir_all(&fresh).map_err(|e| format!("can't create {}: {e}", fresh.display()))?;
    // The model archive holds `models/<name>/...`.
    unpack(model, &fresh)?;
    if models.exists() {
        fs::remove_dir_all(&models).map_err(|e| format!("can't remove the old model: {e}"))?;
    }
    fs::rename(fresh.join(MODELS), &models).map_err(|e| format!("can't put the model in place: {e}"))?;
    let _ = fs::remove_dir_all(&fresh);
    Ok(())
}

pub fn fetch_manifest(url: &str) -> Result<Manifest, String> {
    let response = reqwest::blocking::get(url)
        .and_then(|r| r.error_for_status())
        .map_err(|e| format!("can't reach the runtime download: {e}"))?;
    Manifest::parse(&response.text().map_err(|e| format!("can't read the runtime manifest: {e}"))?)
}

pub fn fetch(archive: &Archive, to: &Path, progress: impl FnMut(u64)) -> Result<(), String> {
    let response = reqwest::blocking::Client::builder()
        .timeout(None)
        .build()
        .and_then(|c| c.get(&archive.url).send())
        .and_then(|r| r.error_for_status())
        .map_err(|e| format!("can't download {}: {e}", archive.file))?;
    download(response, to, &archive.sha256, progress)
}

/// Run `bin/playalong` from the runtime, passing each line it prints (progress bars split on `\r`).
pub fn run_cli(
    runtime: &Path,
    args: &[String],
    env: &[(&str, &Path)],
    mut line: impl FnMut(&str),
) -> Result<(), String> {
    let mut child = Command::new(runtime.join("bin").join("playalong"))
        .args(args)
        .envs(env.iter().map(|(k, v)| (*k, *v)))
        .env("PYTHONUNBUFFERED", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("can't start the runtime: {e}"))?;
    let stderr = child.stderr.take().expect("piped");
    let errors = std::thread::spawn(move || {
        let mut text = String::new();
        let _ = BufReader::new(stderr).read_to_string(&mut text);
        text
    });
    let mut reader = BufReader::new(child.stdout.take().expect("piped"));
    let mut chunk = Vec::new();
    while reader.read_until(b'\n', &mut chunk).map_err(|e| e.to_string())? > 0 {
        for part in String::from_utf8_lossy(&chunk).split('\r') {
            let part = part.trim_end();
            if !part.is_empty() {
                line(part);
            }
        }
        chunk.clear();
    }
    let status = child.wait().map_err(|e| e.to_string())?;
    let errors = errors.join().unwrap_or_default();
    if status.success() {
        return Ok(());
    }
    // The CLI ends with a one-line reason (SystemExit); a traceback's last line says the most.
    let reason = errors.lines().rev().find(|l| !l.trim().is_empty()).unwrap_or("the runtime stopped");
    Err(reason.trim().to_string())
}

/// The song folder `playalong run` finished, from its closing "Done: <folder>" line.
pub fn finished_folder(line: &str) -> Option<PathBuf> {
    line.strip_prefix("Done: ").map(PathBuf::from)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn archive(file: &str, size: u64) -> Archive {
        Archive { file: file.into(), url: format!("https://x/{file}"), size, sha256: "00".into(), unpacked_size: 1 }
    }

    fn manifest(version: &str, model: &str) -> Manifest {
        Manifest {
            format: MANIFEST_FORMAT.into(),
            version: 1,
            runtime: RuntimeEntry {
                version: version.into(),
                series: RUNTIME_SERIES,
                commit: "abc".into(),
                archive: archive("rt", 150),
            },
            model: ModelEntry { name: model.into(), archive: archive("model", 340) },
        }
    }

    fn installed_as(version: &str, model: Option<&str>) -> Installed {
        Installed { version: version.into(), series: RUNTIME_SERIES, commit: "abc".into(), model: model.map(String::from) }
    }

    #[test]
    fn a_first_install_fetches_both_an_update_only_what_changed() {
        let m = manifest("2026.11.07", "sw");
        assert_eq!(plan(None, &m).unwrap().download_size(), 490);
        let same = installed_as("2026.11.07", Some("sw"));
        assert_eq!(plan(Some(&same), &m).unwrap().download_size(), 0);
        let older = installed_as("2026.10.01", Some("sw"));
        let p = plan(Some(&older), &m).unwrap();
        assert_eq!((p.runtime.is_some(), p.model.is_none()), (true, true));
        let other_model = installed_as("2026.11.07", Some("old"));
        let p = plan(Some(&other_model), &m).unwrap();
        assert_eq!((p.runtime.is_none(), p.model.is_some()), (true, true));
    }

    #[test]
    fn a_newer_series_asks_for_an_app_update() {
        let mut m = manifest("2026.11.07", "sw");
        m.runtime.series = RUNTIME_SERIES + 1;
        assert!(plan(None, &m).unwrap_err().contains("newer Playalong"));
    }

    #[test]
    fn an_older_series_is_replaced() {
        let m = manifest("2026.11.07", "sw");
        let mut old = installed_as("2026.11.07", Some("sw"));
        old.series = RUNTIME_SERIES - 1;
        assert!(plan(Some(&old), &m).unwrap().runtime.is_some());
    }

    #[test]
    fn leftover_staging_is_cleared() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        fs::create_dir_all(root.join(STAGING)).unwrap();
        fs::write(root.join(STAGING).join("junk"), "x").unwrap();
        let rt = tar_zst(root, "rt", &[("runtime.json", r#"{"version":"1","commit":"abc"}"#)]);
        install(root, Some(&rt), None).unwrap();
        assert!(!root.join(STAGING).exists());
        assert!(!root.join("runtime").join("junk").exists());
    }

    #[test]
    fn manifests_are_checked() {
        let text = serde_json::to_string(&manifest("1", "sw")).unwrap();
        assert_eq!(Manifest::parse(&text).unwrap().runtime.version, "1");
        assert!(Manifest::parse(&text.replace(MANIFEST_FORMAT, "other")).is_err());
        assert!(Manifest::parse(&text.replace("\"version\":1,", "\"version\":2,")).unwrap_err().contains("newer"));
    }

    #[test]
    fn a_download_must_match_its_checksum() {
        let dir = tempfile::tempdir().unwrap();
        let to = dir.path().join("a");
        // sha256 of "abc"
        let good = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
        let mut seen = 0;
        download(&b"abc"[..], &to, good, |n| seen = n).unwrap();
        assert_eq!((fs::read(&to).unwrap(), seen), (b"abc".to_vec(), 3));
        assert!(download(&b"abd"[..], &to, good, |_| {}).unwrap_err().contains("damaged"));
        assert!(!to.exists());
    }

    /// A tar.zst of `files` (path, contents), as runtime/package.py writes them.
    fn tar_zst(dir: &Path, name: &str, files: &[(&str, &str)]) -> PathBuf {
        let path = dir.join(name);
        let encoder = zstd::Encoder::new(fs::File::create(&path).unwrap(), 3).unwrap().auto_finish();
        let mut tar = tar::Builder::new(encoder);
        for (file, text) in files {
            let mut header = tar::Header::new_gnu();
            header.set_size(text.len() as u64);
            header.set_mode(0o755);
            header.set_cksum();
            tar.append_data(&mut header, file, text.as_bytes()).unwrap();
        }
        tar.into_inner().unwrap();
        path
    }

    #[test]
    fn installing_puts_a_whole_runtime_in_place_and_keeps_the_model() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        let rt1 = tar_zst(root, "rt1", &[("runtime.json", r#"{"version":"1","commit":"abc"}"#), ("bin/playalong", "v1")]);
        let model = tar_zst(root, "m", &[("models/sw/weights.ckpt", "w")]);
        install(root, Some(&rt1), Some(&model)).unwrap();
        let current = root.join("runtime");
        assert_eq!(installed(&current), Some(installed_as("1", Some("sw"))));
        let mode = fs::metadata(current.join("bin/playalong")).unwrap();
        assert_eq!(std::os::unix::fs::PermissionsExt::mode(&mode.permissions()) & 0o111, 0o111);

        let rt2 = tar_zst(root, "rt2", &[("runtime.json", r#"{"version":"2","commit":"abc"}"#), ("bin/playalong", "v2")]);
        install(root, Some(&rt2), None).unwrap();
        assert_eq!(installed(&current), Some(installed_as("2", Some("sw"))));
        assert_eq!(fs::read_to_string(current.join("models/sw/weights.ckpt")).unwrap(), "w");
        assert!(!root.join(STAGING).exists() && !root.join(RETIRED).exists());
    }

    #[test]
    fn a_broken_archive_leaves_the_installed_runtime_alone() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        let rt1 = tar_zst(root, "rt1", &[("runtime.json", r#"{"version":"1","commit":"abc"}"#)]);
        let model = tar_zst(root, "m", &[("models/sw/w", "w")]);
        install(root, Some(&rt1), Some(&model)).unwrap();
        let broken = root.join("broken");
        fs::write(&broken, b"not zstd").unwrap();
        assert!(install(root, Some(&broken), None).is_err());
        assert_eq!(installed(&root.join("runtime")), Some(installed_as("1", Some("sw"))));
    }

    #[test]
    fn the_cli_runs_with_its_lines_passed_on_and_its_reason_when_it_fails() {
        let dir = tempfile::tempdir().unwrap();
        let bin = dir.path().join("bin");
        fs::create_dir_all(&bin).unwrap();
        let script = bin.join("playalong");
        fs::write(&script, "#!/bin/sh\nprintf 'one\\n10%%\\r20%%\\nDone: /lib/song\\n'\n[ \"$1\" = fail ] && { echo 'Traceback' >&2; echo 'No such video' >&2; exit 1; }\nexit 0\n").unwrap();
        fs::set_permissions(&script, std::os::unix::fs::PermissionsExt::from_mode(0o755)).unwrap();
        let mut lines = vec![];
        run_cli(dir.path(), &["ok".into()], &[], |l| lines.push(l.to_string())).unwrap();
        assert_eq!(lines, ["one", "10%", "20%", "Done: /lib/song"]);
        assert_eq!(finished_folder(&lines[3]), Some(PathBuf::from("/lib/song")));
        assert_eq!(run_cli(dir.path(), &["fail".into()], &[], |_| {}).unwrap_err(), "No such video");
    }
}
