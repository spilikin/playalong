"""Build `dist/Playalong Runtime/`: everything the playalong CLI needs, in one folder another Mac can use as is.

    uv run python runtime/build.py [--out DIR]

The folder holds a standalone Python with the project and its packages installed, the separation model,
and ffmpeg, ffprobe and deno with the Homebrew libraries they load, rewired to load from the folder.
`bin/playalong` runs the CLI from it. Apple Silicon only, like the Python and libraries it copies.

Needs on the building Mac: uv, Homebrew's ffmpeg and deno, the model in the bs-roformer cache (one
`playalong separate` run fetches it), and Xcode's command-line tools (otool, install_name_tool, codesign).
"""

import argparse
import datetime
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "Playalong Runtime"
# Bumped when the playalong code needs a dependency older runtimes lack; the app asks for its series.
SERIES = 1
TOOLS = ("ffmpeg", "ffprobe", "deno")
SYSTEM = ("/usr/lib/", "/System/")

LAUNCHER = """#!/bin/sh
# Runs the playalong CLI from this runtime, whatever is (or isn't) installed on the Mac.
here="$(cd "$(dirname "$0")/.." && pwd -P)"
export PATH="$here/bin:$PATH"
export BS_ROFORMER_MODELS_PATH="$here/models"
export PLAYALONG_RUNTIME="$here"
# Import order: a newer yt-dlp from `playalong update-downloader`, then the app's own playalong code
# (PLAYALONG_CODE, set by the app so its song files and the CLI always match), then the runtime's.
exec "$here/python/bin/python3" -I -c '
import os, sys
code = os.environ.get("PLAYALONG_CODE")
# Bytecode goes to the runtime, never next to the code: the app bundle has to stay as it was signed.
sys.pycache_prefix = os.path.join(os.environ["PLAYALONG_RUNTIME"], "pycache")
sys.path[0:0] = [os.path.join(os.environ["PLAYALONG_RUNTIME"], "downloader"), *([code] if code else [])]
sys.argv[0] = "playalong"
from playalong import main
main()' "$@"
"""


def run(*cmd, **kwargs) -> str:
    return subprocess.run([str(c) for c in cmd], check=True, text=True, capture_output=True, **kwargs).stdout


def _python(dest: Path) -> None:
    # The venv this script runs in sits on a uv-managed CPython (python-build-standalone), which is
    # relocatable: copy the whole install and put the packages straight into it.
    base = Path(sys.base_prefix)
    print(f"Python {platform.python_version()} from {base}")
    shutil.copytree(base, dest, symlinks=True)
    python = dest / "bin" / "python3"
    with tempfile.TemporaryDirectory() as tmp:
        reqs = Path(tmp) / "requirements.txt"
        run("uv", "export", "--frozen", "--no-dev", "--no-emit-project", "-o", reqs, cwd=ROOT)
        print("Packages")
        run("uv", "pip", "install", "--python", python, "--break-system-packages", "--require-hashes", "-r", reqs)
    run("uv", "pip", "install", "--python", python, "--break-system-packages", "--no-deps", "--reinstall-package",
        "playalong", ROOT)
    # Console scripts carry this build's absolute path in their shebang; bin/playalong replaces them.
    for script in (dest / "bin").iterdir():
        if script.is_file() and not script.name.startswith("python") and script.read_bytes()[:2] == b"#!":
            script.unlink()


def _deps(binary: Path) -> list[tuple[str, Path]]:
    """The non-system libraries `binary` loads: as written in it, and where that file is."""
    out = []
    lines = run("otool", "-L", binary).splitlines()[1:]
    rpaths = _rpaths(binary)
    for line in lines:
        ref = line.strip().split(" (")[0]
        if ref.startswith(SYSTEM) or Path(ref).name == binary.name:
            continue
        out.append((ref, _resolve(ref, binary, rpaths)))
    return out


def _rpaths(binary: Path) -> list[str]:
    lines = run("otool", "-l", binary).splitlines()
    return [lines[i + 2].split()[1] for i, line in enumerate(lines) if "LC_RPATH" in line]


def _resolve(ref: str, binary: Path, rpaths: list[str]) -> Path:
    loader = str(binary.resolve().parent)
    if ref.startswith("@loader_path/"):
        return Path(loader, ref.removeprefix("@loader_path/")).resolve()
    if ref.startswith("@rpath/"):
        for rpath in rpaths:
            candidate = Path(rpath.replace("@loader_path", loader), ref.removeprefix("@rpath/"))
            if candidate.exists():
                return candidate.resolve()
        raise FileNotFoundError(f"{ref} (needed by {binary}) not found in {rpaths}")
    return Path(ref).resolve()


def _tools(bin_dir: Path, lib_dir: Path) -> None:
    """Copy the tools and every library they need, pointing each reference into lib/."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    lib_dir.mkdir(exist_ok=True)
    todo = []
    for tool in TOOLS:
        found = shutil.which(tool)
        if not found:
            raise SystemExit(f"{tool} not found; brew install {tool}")
        src = Path(found).resolve()
        print(f"{tool} from {src}")
        todo.append((src, bin_dir / tool))

    copied: dict[Path, Path] = {}
    while todo:
        src, dest = todo.pop()
        shutil.copy2(src, dest)
        dest.chmod(0o755)
        copied[src] = dest
        changes = []
        for ref, lib in _deps(src):
            target = lib_dir / lib.name
            if lib not in copied and all(lib != s for s, _ in todo):
                todo.append((lib, target))
            changes += ["-change", ref, f"@rpath/{lib.name}"]
        args = changes[:]
        if dest.parent == lib_dir:
            args += ["-id", f"@rpath/{dest.name}"]
        for rpath in _rpaths(dest):
            args += ["-delete_rpath", rpath]
        args += ["-add_rpath", "@loader_path" if dest.parent == lib_dir else "@executable_path/../lib"]
        run("install_name_tool", *args, dest)
    # Rewriting load commands breaks the original signatures; arm64 Macs won't run unsigned code.
    for dest in copied.values():
        run("codesign", "--force", "--sign", "-", dest)
    print(f"  {len(copied) - len(TOOLS)} libraries")


def _model(dest: Path) -> None:
    from bs_roformer import ensure_model_assets

    from playalong.separate import MODEL

    checkpoint, config = ensure_model_assets(MODEL, download_missing=False)
    folder = dest / checkpoint.parent.name  # the model's slug, where bs_roformer looks for it
    folder.mkdir(parents=True)
    print(f"Model {checkpoint.name}")
    for f in (checkpoint, config):
        shutil.copy2(f, folder / f.name)


def _version() -> dict:
    commit = run("git", "rev-parse", "--short", "HEAD", cwd=ROOT).strip()
    dirty = bool(run("git", "status", "--porcelain", "--untracked-files=no", cwd=ROOT).strip())
    today = datetime.date.today()
    return {"version": f"{today:%Y.%m.%d}", "series": SERIES, "commit": commit + ("-dirty" if dirty else ""),
            "python": platform.python_version(), "arch": platform.machine(), "built": today.isoformat()}


def _check(out: Path) -> None:
    """Run the copy with Homebrew and the project venv out of reach."""
    env = {"PATH": "/usr/bin:/bin", "HOME": os.environ["HOME"]}
    print("Checking")
    print("  " + run(out / "bin" / "playalong", "--help", env=env).splitlines()[0])
    probe = "import torch, pedalboard, yt_dlp, bs_roformer, soundfile; print(torch.__version__, torch.backends.mps.is_available())"
    print("  torch", run(out / "python" / "bin" / "python3", "-I", "-c", probe, env=env).strip())
    for tool in TOOLS:
        print("  " + run(out / "bin" / tool, "--version" if tool == "deno" else "-version", env=env).splitlines()[0])
    for f in [*(out / "bin").iterdir(), *(out / "lib").iterdir()]:
        if f.name != "playalong" and "/opt/homebrew" in run("otool", "-L", f):
            raise SystemExit(f"{f} still loads from /opt/homebrew")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "dist", help="where the runtime folder goes")
    args = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("builds on Apple Silicon Macs only")

    out = args.out / NAME
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    _python(out / "python")
    _tools(out / "bin", out / "lib")
    _model(out / "models")
    launcher = out / "bin" / "playalong"
    launcher.write_text(LAUNCHER)
    launcher.chmod(0o755)
    info = _version()
    (out / "runtime.json").write_text(json.dumps(info, indent=2) + "\n")
    _check(out)
    size = run("du", "-sh", out).split()[0]
    print(f"\n{out}  ({size}, version {info['version']}, {info['commit']})")


if __name__ == "__main__":
    main()
