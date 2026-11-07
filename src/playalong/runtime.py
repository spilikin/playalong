"""The portable runtime (see runtime/build.py) and updating its YouTube downloader on its own.

YouTube changes often and yt-dlp follows within days, so the runtime keeps a `downloader/` folder ahead
of its own packages on the import path: newer yt-dlp and yt-dlp-ejs go there, without a new runtime.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

RUNTIME_ENV = "PLAYALONG_RUNTIME"  # set by the runtime's bin/playalong to the runtime folder
DOWNLOADER = "downloader"
PACKAGES = ("yt-dlp", "yt-dlp-ejs")
VERSION = "import yt_dlp, yt_dlp_ejs; print(yt_dlp.version.__version__)"


def runtime_dir() -> Path | None:
    value = os.environ.get(RUNTIME_ENV)
    return Path(value) if value else None


def _version(path: Path | None) -> str:
    code = (f"import sys; sys.path.insert(0, {str(path)!r}); " if path else "") + VERSION
    result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
    return result.stdout.strip() or "unknown"


def update_downloader() -> None:
    runtime = runtime_dir()
    if runtime is None:
        raise SystemExit("Not running from the portable runtime; in the project, update with\n"
                         "  uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs && uv sync")
    target = runtime / DOWNLOADER
    before = _version(target if target.is_dir() else None)
    # Installed next to the old one and swapped in whole, so a failed update leaves the working one alone.
    with tempfile.TemporaryDirectory(dir=runtime, prefix=".downloader-") as tmp:
        fresh = Path(tmp) / DOWNLOADER
        subprocess.run([sys.executable, "-I", "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                        "--no-deps", "--upgrade", "--target", str(fresh), *PACKAGES], check=True)
        old = Path(tmp) / "old"
        if target.exists():
            target.rename(old)
        fresh.rename(target)
    after = _version(target)
    print(f"yt-dlp {before} → {after}" if after != before else f"yt-dlp {after} is the newest")

