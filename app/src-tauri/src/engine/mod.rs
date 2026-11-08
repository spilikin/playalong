//! Live playback of a song's mixes: its stems in memory, mixed by a recipe, moved in key and tempo by
//! Rubber Band's real-time engine, with the count-in on top and a limiter at the end.

pub mod limiter;
pub mod mixer;
pub mod player;
pub mod render;
pub mod timeline;

use std::path::Path;

use serde_json::Value;

type Track = (Vec<f32>, Vec<f32>);

/// The six stems (in `mixer::STEMS` order; a missing one is silence) and the recording, at one rate.
pub struct Stems {
    pub rate: u32,
    tracks: Vec<Option<Track>>,
    source: Option<Track>,
}

impl Stems {
    #[cfg(test)]
    pub fn from_tracks(rate: u32, tracks: Vec<Track>, source: Option<Track>) -> Stems {
        let mut tracks: Vec<Option<Track>> = tracks.into_iter().map(Some).collect();
        tracks.resize_with(6, || None);
        Stems { rate, tracks, source }
    }

    /// Track `i`: a stem, or `mixer::SOURCE` for the recording.
    pub fn track(&self, i: usize) -> Option<(&[f32], &[f32])> {
        let t = if i == mixer::SOURCE { self.source.as_ref() } else { self.tracks.get(i)?.as_ref() };
        t.map(|(l, r)| (l.as_slice(), r.as_slice()))
    }

    pub fn len(&self) -> usize {
        self.tracks.iter().flatten().chain(self.source.iter()).map(|t| t.0.len()).max().unwrap_or(0)
    }

    pub fn has_source(&self) -> bool {
        self.source.is_some()
    }

    /// The stems and recording a song file names, relative to its folder.
    pub fn load(folder: &Path, song: &Value) -> Result<Stems, String> {
        let stems = song.get("stems").and_then(Value::as_object).ok_or("This song has no instruments yet")?;
        let mut rate = None;
        let mut read = |rel: &str| -> Result<Track, String> {
            let (track, r) = read_wav(&folder.join(rel))?;
            if *rate.get_or_insert(r) != r {
                return Err(format!("{rel} is at {r} Hz, the other stems aren't"));
            }
            Ok(track)
        };
        let mut tracks = Vec::new();
        for name in mixer::STEMS {
            tracks.push(match stems.get(name).and_then(Value::as_str) {
                Some(rel) => Some(read(rel)?),
                None => None,
            });
        }
        let source = song.pointer("/audio/file").and_then(Value::as_str).and_then(|rel| read(rel).ok());
        Ok(Stems { rate: rate.ok_or("This song has no instruments yet")?, tracks, source })
    }
}

fn read_wav(path: &Path) -> Result<(Track, u32), String> {
    let mut reader = hound::WavReader::open(path).map_err(|e| format!("can't read {}: {e}", path.display()))?;
    let spec = reader.spec();
    let samples: Vec<f32> = match spec.sample_format {
        hound::SampleFormat::Float => reader.samples::<f32>().collect::<Result<_, _>>(),
        hound::SampleFormat::Int => {
            let scale = 1.0 / (1i64 << (spec.bits_per_sample - 1)) as f32;
            reader.samples::<i32>().map(|s| s.map(|v| v as f32 * scale)).collect()
        }
    }
    .map_err(|e| format!("can't read {}: {e}", path.display()))?;
    let channels = spec.channels as usize;
    let left: Vec<f32> = samples.iter().step_by(channels).copied().collect();
    let right = if channels > 1 { samples.iter().skip(1).step_by(channels).copied().collect() } else { left.clone() };
    Ok(((left, right), spec.sample_rate))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loads_the_stems_and_recording_a_song_names() {
        let dir = tempfile::tempdir().unwrap();
        let spec = |format, bits| hound::WavSpec { channels: 2, sample_rate: 44100, bits_per_sample: bits, sample_format: format };
        std::fs::create_dir(dir.path().join("stems")).unwrap();
        let mut w = hound::WavWriter::create(dir.path().join("stems/bass.wav"), spec(hound::SampleFormat::Float, 32)).unwrap();
        for v in [0.5f32, -0.5, 0.25, -0.25] {
            w.write_sample(v).unwrap();
        }
        w.finalize().unwrap();
        let mut w = hound::WavWriter::create(dir.path().join("source.wav"), spec(hound::SampleFormat::Int, 16)).unwrap();
        for v in [16384i16, -16384] {
            w.write_sample(v).unwrap();
        }
        w.finalize().unwrap();
        let song = serde_json::json!({"stems": {"bass": "stems/bass.wav"}, "audio": {"file": "source.wav"}});
        let stems = Stems::load(dir.path(), &song).unwrap();
        let (l, r) = stems.track(2).unwrap();
        assert_eq!((l, r), (&[0.5, 0.25][..], &[-0.5, -0.25][..]));
        assert!(stems.track(0).is_none() && stems.has_source());
        assert_eq!(stems.track(mixer::SOURCE).unwrap().0, &[0.5]);
        assert!(Stems::load(dir.path(), &serde_json::json!({"stems": {}})).is_err());
    }
}
