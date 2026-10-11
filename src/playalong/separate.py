import contextlib
import sys
import warnings
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

MODEL = "roformer-model-bs-roformer-sw-by-jarredou"
STEMS = ("bass", "drums", "other", "vocals", "guitar", "piano")
SAMPLE_RATE = 44100  # the model was trained on 44.1 kHz audio and does no resampling itself


def default_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    # bs-roformer-infer's own CLI refuses MPS, but calling demix_track directly works
    # and matches CPU output while running roughly twice as fast on Apple Silicon.
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


# bs-roformer-infer trips these on every run, none of them about our use: the model's constructor
# calls stft without a window only to count frequency bins (separation itself uses Hann), and the
# rest are deprecations in its CUDA-only code paths.
LIBRARY_WARNINGS = (
    (UserWarning, r"A window was not provided"),
    (FutureWarning, r"`torch\.cuda\.amp\.autocast\(args\.\.\.\)` is deprecated"),
    (UserWarning, r"CUDA is not available or torch_xla is imported"),
    (FutureWarning, r"`torch\.backends\.cuda\.sdp_kernel\(\)` is deprecated"),
)


@contextlib.contextmanager
def quiet_library_warnings():
    with warnings.catch_warnings():
        for category, message in LIBRARY_WARNINGS:
            warnings.filterwarnings("ignore", message=message, category=category)
        yield


class clean_progress:
    """Passes output through, clearing the rest of the line after each carriage-return redraw.

    demix_track redraws its "time remaining" line with a bare \r, so a shorter line leaves the end
    of the longer one behind ("0.00 secondsss").
    """

    def __init__(self, stream):
        self.stream = stream

    def write(self, text: str) -> int:
        if text.startswith("\r"):
            text += "\x1b[K"
        return self.stream.write(text)

    def flush(self) -> None:
        self.stream.flush()


def _load_model(device: str):
    import yaml
    from bs_roformer import ensure_model_assets, get_model_from_config
    from bs_roformer.inference import SafeLoaderWithTuple
    from ml_collections import ConfigDict

    checkpoint, config_path = ensure_model_assets(MODEL)
    with open(config_path) as f:
        config = ConfigDict(yaml.load(f, Loader=SafeLoaderWithTuple))
    model = get_model_from_config("bs_roformer", config)
    model.load_state_dict(torch.load(checkpoint, map_location="cpu"))
    return model.to(device).eval(), config


def separate(track_dir: Path, device: str | None = None, force: bool = False) -> Path:
    """Split source.wav into per-instrument stems under track_dir/stems."""
    stems_dir = track_dir / "stems"
    if not force and all((stems_dir / f"{s}.wav").exists() for s in STEMS):
        print(f"Stems already present: {stems_dir}")
        return stems_dir

    from bs_roformer import demix_track

    mix, sr = sf.read(track_dir / "source.wav", dtype="float32", always_2d=True)
    if sr != SAMPLE_RATE:
        raise ValueError(f"source.wav is {sr} Hz, expected {SAMPLE_RATE}; re-import the track")
    if mix.shape[1] == 1:
        mix = np.repeat(mix, 2, axis=1)

    device = device or default_device()
    output = clean_progress(sys.stdout) if sys.stdout.isatty() else sys.stdout
    with quiet_library_warnings(), contextlib.redirect_stdout(output):
        model, config = _load_model(device)
        stems, _ = demix_track(config, model, torch.from_numpy(mix.T.copy()), torch.device(device))

    stems_dir.mkdir(exist_ok=True)
    for name, audio in stems.items():
        # Float WAV keeps peaks above 0 dBFS intact until the final mix is normalized.
        sf.write(stems_dir / f"{name}.wav", audio.T, sr, subtype="FLOAT")
    return stems_dir
