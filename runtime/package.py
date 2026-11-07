"""Pack `dist/Playalong Runtime/` for download, and publish it on GitHub Releases.

    uv run python runtime/package.py            # archives and manifest in dist/release/
    uv run python runtime/package.py --publish  # and upload them (needs gh, signed in)

Two archives, so an update doesn't fetch the model again:
- `playalong-runtime-<version>-arm64.tar.zst`: Python, packages and tools, in release `runtime-<version>`;
- `playalong-model-<slug>.tar.zst`: the separation model, in release `model-<slug>`, uploaded once.

`manifest.json` names both with their URLs, sizes and sha256. It lives in release `updates`,
replaced on each publish, so the app always finds the newest runtime at one URL.
"""

import argparse
import hashlib
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "spilikin/playalong"
RUNTIME = ROOT / "dist" / "Playalong Runtime"
OUT = ROOT / "dist" / "release"
UPDATES = "updates"  # rolling release with what the app polls
MANIFEST = "manifest.json"
MANIFEST_FORMAT = "playalong-runtime-manifest"
# Left out of the runtime archive: the model has its own, downloader/ is a local update, and pycache/
# holds bytecode the runtime writes for itself.
SEPARATE = ("models", "downloader", "pycache")


def url(tag: str, name: str) -> str:
    return f"https://github.com/{REPO}/releases/download/{tag}/{name}"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _tree_size(root: Path) -> int:
    return sum(p.lstat().st_size for p in root.rglob("*") if not p.is_dir())


def pack(source: Path, members: list[Path], dest: Path) -> None:
    """tar | zstd -19: about a sixth of the size for the runtime, half for the model."""
    print(f"Packing {dest.name}")
    with subprocess.Popen(["zstd", "-q", "-19", "-T0", "-f", "-o", str(dest)], stdin=subprocess.PIPE) as z:
        with tarfile.open(fileobj=z.stdin, mode="w|", format=tarfile.PAX_FORMAT) as tar:
            for m in members:
                tar.add(m, arcname=m.relative_to(source).as_posix())
        z.stdin.close()
    if z.returncode:
        raise SystemExit(f"zstd failed for {dest.name}")


def entry(release: str, path: Path, unpacked: int, **extra) -> dict:
    return {**extra, "file": path.name, "url": url(release, path.name), "size": path.stat().st_size,
            "sha256": sha256(path), "unpacked_size": unpacked}


def build() -> dict:
    if not (RUNTIME / "runtime.json").exists():
        raise SystemExit(f"No runtime in {RUNTIME}; run runtime/build.py first")
    info = json.loads((RUNTIME / "runtime.json").read_text())
    if info["commit"].endswith("-dirty"):
        raise SystemExit("The runtime was built from uncommitted changes; commit and build again")
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.iterdir():
        old.unlink()

    version = info["version"]
    runtime_tag = f"runtime-{version}"
    runtime_file = OUT / f"playalong-runtime-{version}-{info['arch']}.tar.zst"
    members = [p for p in sorted(RUNTIME.iterdir()) if p.name not in SEPARATE]
    pack(RUNTIME, members, runtime_file)

    (model_dir,) = (RUNTIME / "models").iterdir()
    slug = model_dir.name
    model_tag = f"model-{slug}"
    model_file = OUT / f"playalong-model-{slug}.tar.zst"
    pack(RUNTIME, [RUNTIME / "models"], model_file)

    unpacked = sum(_tree_size(m) if m.is_dir() else m.lstat().st_size for m in members)
    manifest = {
        "format": MANIFEST_FORMAT,
        "version": 1,
        "runtime": entry(runtime_tag, runtime_file, unpacked, version=version, series=info.get("series", 1), commit=info["commit"],
                         python=info["python"], arch=info["arch"], tag=runtime_tag),
        "model": entry(model_tag, model_file, _tree_size(model_dir), name=slug, tag=model_tag),
    }
    (OUT / MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n")
    for f in sorted(OUT.iterdir()):
        print(f"  {f.name}  {f.stat().st_size / 1e6:.0f} MB")
    return manifest


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args, "--repo", REPO], text=True, capture_output=True, check=check)


def _assets(tag: str) -> dict[str, str] | None:
    """Asset name -> sha256 digest of a release, or None if there is no such release."""
    found = gh("release", "view", tag, "--json", "assets", check=False)
    if found.returncode:
        return None
    return {a["name"]: (a.get("digest") or "").removeprefix("sha256:") for a in json.loads(found.stdout)["assets"]}


def publish(manifest: dict) -> None:
    runtime, model = manifest["runtime"], manifest["model"]
    if _assets(runtime["tag"]) is not None:
        raise SystemExit(f"Release {runtime['tag']} exists already; a runtime version is published once")
    # Tags go on the commit the runtime was built from, which has to be on GitHub.
    commit = subprocess.run(["git", "rev-parse", runtime["commit"]], cwd=ROOT, text=True, capture_output=True,
                            check=True).stdout.strip()
    pushed = subprocess.run(["git", "branch", "-r", "--contains", commit], cwd=ROOT, text=True, capture_output=True)
    if not pushed.stdout.strip():
        raise SystemExit(f"Commit {runtime['commit']} isn't pushed; push it first")

    assets = _assets(model["tag"])
    if assets is None:
        gh("release", "create", model["tag"], str(OUT / model["file"]), "--latest=false", "--target", commit,
           "--title", f"Model {model['name']}",
           "--notes", "The separation model for the Playalong runtime; the app downloads it once.")
    elif model["file"] not in assets:
        gh("release", "upload", model["tag"], str(OUT / model["file"]))
    elif assets[model["file"]] and assets[model["file"]] != model["sha256"]:
        # tar and zstd pack the same files the same way, so a different digest means a different model.
        raise SystemExit(f"{model['file']} in release {model['tag']} differs from this build's; "
                         "a changed model needs a new name")

    gh("release", "create", runtime["tag"], str(OUT / runtime["file"]), "--latest=false", "--target", commit,
       "--title", f"Runtime {runtime['version']}",
       "--notes", f"Playalong runtime {runtime['version']} (commit {runtime['commit']}, Python {runtime['python']}, "
                  f"Apple Silicon). The app downloads and updates it; see the README's Portable runtime section.")
    if _assets(UPDATES) is None:
        gh("release", "create", UPDATES, str(OUT / MANIFEST), "--latest=false", "--target", commit,
           "--title", "Updates", "--notes", "What the app checks for updates: manifest.json (runtime) and latest.json (app).")
    else:
        gh("release", "upload", UPDATES, str(OUT / MANIFEST), "--clobber")
    print(f"Published runtime {runtime['version']}; manifest at {url(UPDATES, MANIFEST)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--publish", action="store_true", help="upload to GitHub Releases (needs gh, signed in)")
    args = parser.parse_args()
    manifest = build()
    if args.publish:
        publish(manifest)


if __name__ == "__main__":
    main()
