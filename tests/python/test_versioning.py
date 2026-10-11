"""Release version inheritance, drift detection and safe version updates."""

import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    sys.version_info < (3, 11), reason="release tooling uses Python 3.11+"
)


@pytest.fixture
def version_checkout(tmp_path):
    for name in (
        "Cargo.toml",
        "Cargo.lock",
        "uv.lock",
        "pyproject.toml",
        "crates/ezjww-core/Cargo.toml",
        "crates/ezjww-wasm/Cargo.toml",
        "packages/ezjww/package.json",
        "scripts/check-release.py",
    ):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return tmp_path


@pytest.mark.parametrize(
    "name,old,new,message",
    [
        (
            "crates/ezjww-core/Cargo.toml",
            "version.workspace = true",
            'version = "0.0.0"',
            "inherit",
        ),
        ("pyproject.toml", 'dynamic = ["version"]', 'version = "0.0.0"', "inherited"),
        ("Cargo.lock", 'name = "ezjww-core"', 'name = "missing-core"', "missing"),
        ("uv.lock", 'name = "ezjww"', 'name = "ezjww"\nversion = "0.0.0"', "dynamic"),
        (
            "packages/ezjww/package.json",
            '"version": "',
            '"version": "9',
            "versions differ",
        ),
        (
            "Cargo.lock",
            'name = "ezjww-core"\nversion = "',
            'name = "ezjww-core"\nversion = "9',
            "versions differ",
        ),
    ],
)
def test_version_gate_rejects_drift(version_checkout, name, old, new, message):
    check = runpy.run_path(str(ROOT / "scripts/check-release.py"))["check_versions"]
    check(root=version_checkout)
    path = version_checkout / name
    source = path.read_text(encoding="utf-8")
    assert old in source
    path.write_text(source.replace(old, new), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        check(root=version_checkout)


@pytest.mark.parametrize("version", ["v1.2.3", "1.2", "01.2.3", "1.2.3rc1", "1.2.3\n"])
def test_bump_rejects_invalid_versions_without_writes(tmp_path, version):
    bump = runpy.run_path(str(ROOT / "scripts/bump-version.py"))["bump_version"]
    with pytest.raises(ValueError, match="final version"):
        bump(version, root=tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("failed_tool", ["cargo", "uv"])
def test_bump_restores_preexisting_edits_on_failure(
    version_checkout, monkeypatch, failed_tool
):
    script = runpy.run_path(str(ROOT / "scripts/bump-version.py"))
    cargo = version_checkout / "Cargo.toml"
    cargo.write_text(
        cargo.read_text(encoding="utf-8") + "\n# Keep my edits.\n", encoding="utf-8"
    )
    originals = {
        name: (version_checkout / name).read_bytes() for name in script["FILES"]
    }

    def fail(command, **kwargs):
        # Resolvers may have written a partial lockfile before failing.
        (version_checkout / "Cargo.lock").write_bytes(b"partial cargo lock")
        if command[0] == failed_tool:
            (version_checkout / "uv.lock").write_bytes(b"partial uv lock")
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        script["bump_version"]("9.8.7", root=version_checkout)
    assert {
        name: (version_checkout / name).read_bytes() for name in originals
    } == originals


@pytest.mark.skipif(
    not shutil.which("cargo") or not shutil.which("uv"),
    reason="version bump integration requires cargo and uv",
)
def test_bump_updates_versions_without_changing_dependency_pins(version_checkout):
    import json
    import tomllib

    # cargo metadata requires targets to exist but does not compile their contents.
    for directory in ("src", "crates/ezjww-core/src", "crates/ezjww-wasm/src"):
        target = version_checkout / directory
        target.mkdir(parents=True)
        (target / "lib.rs").write_text("", encoding="utf-8")
    script = runpy.run_path(str(ROOT / "scripts/bump-version.py"))
    originals = {
        name: (version_checkout / name).read_bytes() for name in script["FILES"]
    }
    before = tomllib.loads(originals["Cargo.lock"].decode("utf-8"))
    script["bump_version"]("9.8.7", root=version_checkout, offline=True)
    lock = tomllib.loads((version_checkout / "Cargo.lock").read_text(encoding="utf-8"))
    local = {"ezjww", "ezjww-core", "ezjww-wasm"}
    assert {p["version"] for p in lock["package"] if p["name"] in local} == {"9.8.7"}
    assert [p for p in lock["package"] if p["name"] not in local] == [
        p for p in before["package"] if p["name"] not in local
    ]
    assert (
        tomllib.loads((version_checkout / "uv.lock").read_text(encoding="utf-8"))[
            "package"
        ]
        == tomllib.loads(originals["uv.lock"].decode("utf-8"))["package"]
    )
    package = version_checkout / "packages/ezjww/package.json"
    assert json.loads(package.read_text(encoding="utf-8"))["version"] == "9.8.7"
    cargo = tomllib.loads((version_checkout / "Cargo.toml").read_text(encoding="utf-8"))
    assert cargo["workspace"]["package"]["version"] == "9.8.7"
    old_version = next(p["version"] for p in before["package"] if p["name"] == "ezjww")
    script["bump_version"](old_version, root=version_checkout, offline=True)
    for name, original in originals.items():
        parse = json.loads if name.endswith(".json") else tomllib.loads
        assert parse((version_checkout / name).read_text(encoding="utf-8")) == parse(
            original.decode("utf-8")
        )
