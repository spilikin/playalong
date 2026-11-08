import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_build():
    spec = importlib.util.spec_from_file_location("runtime_build", ROOT / "runtime" / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def launch(tmp_path: Path, **env: str) -> dict:
    """Run the launcher of a fake runtime whose playalong only reports where things go."""
    rt = tmp_path / "Playalong Runtime"
    (rt / "bin").mkdir(parents=True)
    (rt / "python" / "bin").mkdir(parents=True)
    (rt / "python" / "bin" / "python3").symlink_to(sys.executable)
    launcher = rt / "bin" / "playalong"
    launcher.write_text(load_build().LAUNCHER)
    launcher.chmod(0o755)
    code = tmp_path / "code" / "playalong"
    code.mkdir(parents=True)
    (code / "__init__.py").write_text(
        "import os, sys\n"
        "def main():\n"
        "    print(sys.pycache_prefix)\n"
        "    print(os.environ['DENO_DIR'])\n"
        "    print(os.environ['PLAYALONG_CACHE'])\n")
    home = tmp_path / "home"
    home.mkdir()
    out = subprocess.run([str(launcher)], capture_output=True, text=True, check=True,
                         env={"PATH": "/usr/bin:/bin", "HOME": str(home), "PLAYALONG_CODE": str(code.parent), **env})
    prefix, deno, cache = out.stdout.split("\n")[:3]
    return {"prefix": prefix, "deno": deno, "cache": cache, "rt": rt, "code": code}


def test_caches_go_to_the_users_caches_folder_not_the_runtime_or_the_app(tmp_path):
    got = launch(tmp_path)
    cache = tmp_path / "home" / "Library" / "Caches" / "dev.playalong"
    assert (got["prefix"], got["deno"], got["cache"]) == (str(cache / "pycache"), str(cache / "deno"), str(cache))
    assert not list(got["rt"].rglob("*.pyc")) and not list(got["code"].rglob("*.pyc"))


def test_the_app_can_name_its_own_cache_folder(tmp_path):
    mine = tmp_path / "elsewhere"
    assert launch(tmp_path, PLAYALONG_CACHE=str(mine))["prefix"] == str(mine / "pycache")


def test_a_second_runtime_on_one_day_gets_its_own_version():
    build = load_build()
    assert build._version()["version"].count(".") == 2
    assert build._version("2026.11.08.2")["version"] == "2026.11.08.2"
