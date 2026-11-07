import hashlib
import importlib.util
import json
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_package():
    spec = importlib.util.spec_from_file_location("runtime_package", ROOT / "runtime" / "package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_runtime(root: Path) -> Path:
    rt = root / "Playalong Runtime"
    (rt / "bin").mkdir(parents=True)
    (rt / "bin" / "playalong").write_text("#!/bin/sh\n")
    (rt / "models" / "sw").mkdir(parents=True)
    (rt / "models" / "sw" / "w.ckpt").write_bytes(b"weights" * 100)
    (rt / "downloader").mkdir()
    (rt / "pycache").mkdir()
    (rt / "pycache" / "x.pyc").write_bytes(b"")
    (rt / "runtime.json").write_text(json.dumps(
        {"version": "2026.11.07", "series": 1, "commit": "abc1234", "python": "3.12.14", "arch": "arm64"}))
    return rt


def members(archive: Path) -> list[str]:
    raw = subprocess.run(["zstd", "-dc", str(archive)], capture_output=True, check=True).stdout
    tar = archive.with_suffix("")
    tar.write_bytes(raw)
    with tarfile.open(tar) as t:
        return t.getnames()


def test_manifest_names_both_archives_with_checksums(tmp_path, monkeypatch):
    package = load_package()
    monkeypatch.setattr(package, "RUNTIME", fake_runtime(tmp_path))
    monkeypatch.setattr(package, "OUT", tmp_path / "release")
    manifest = package.build()

    runtime, model = manifest["runtime"], manifest["model"]
    assert runtime["url"] == ("https://github.com/spilikin/playalong/releases/download/runtime-2026.11.07/"
                              "playalong-runtime-2026.11.07-arm64.tar.zst")
    assert runtime["series"] == 1 and runtime["tag"] == "runtime-2026.11.07"
    assert model["tag"] == "model-sw" and model["name"] == "sw"
    for entry in (runtime, model):
        path = tmp_path / "release" / entry["file"]
        assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert entry["size"] == path.stat().st_size
    names = members(tmp_path / "release" / runtime["file"])
    assert "bin/playalong" in names and not any(n.startswith(("models", "downloader", "pycache")) for n in names)
    assert members(tmp_path / "release" / model["file"]) == ["models", "models/sw", "models/sw/w.ckpt"]
    assert json.loads((tmp_path / "release" / "manifest.json").read_text()) == manifest

    first = model["sha256"]
    assert package.build()["model"]["sha256"] == first  # the same files pack the same way
