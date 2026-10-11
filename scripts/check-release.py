#!/usr/bin/env python3
"""Check release versions and the hashes of the exact qualified artifacts.

Release tooling requires Python 3.11+ (the package itself supports Python 3.9+).
"""

import argparse
import hashlib
import json
import re
import tomllib
from collections import Counter
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parents[1]


def check_versions(root=ROOT, tag=None):
    def toml(path):
        return tomllib.loads((root / path).read_text(encoding="utf-8"))

    project = toml("pyproject.toml")["project"]
    version = toml("Cargo.toml")["workspace"]["package"]["version"]
    if "version" in project or "version" not in project.get("dynamic", []):
        raise ValueError("Python version must be inherited from Cargo.toml")
    versions = {"Cargo.toml:workspace.package": version}
    for path in (
        "Cargo.toml",
        "crates/ezjww-core/Cargo.toml",
        "crates/ezjww-wasm/Cargo.toml",
    ):
        if toml(path)["package"]["version"] != {"workspace": True}:
            raise ValueError(f"{path} must inherit the workspace version")
    versions["package.json"] = json.loads(
        (root / "packages/ezjww/package.json").read_text()
    )["version"]
    for lock in ("Cargo.lock", "uv.lock"):
        expected = (
            {"ezjww", "ezjww-core", "ezjww-wasm"} if lock == "Cargo.lock" else {"ezjww"}
        )
        found = []
        for package in toml(lock)["package"]:
            if package["name"] in expected:
                found.append(package["name"])
                if lock == "uv.lock":
                    # uv omits the version of an editable project whose version
                    # is dynamic; the built wheel is checked independently.
                    if "version" in package or package.get("source") != {
                        "editable": "."
                    }:
                        raise ValueError(
                            "uv.lock must use the dynamic editable version"
                        )
                else:
                    versions[lock + ":" + package["name"]] = package["version"]
        if Counter(found) != Counter(expected):
            raise ValueError(f"missing or duplicate workspace packages in {lock}")
    if set(versions.values()) != {version} or not re.fullmatch(
        r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version
    ):
        raise ValueError(
            "release versions differ or are not final versions: " + repr(versions)
        )
    if tag and tag != "v" + version:
        raise ValueError(f"tag {tag!r} does not match v{version}")
    if project["requires-python"] != ">=3.9":
        raise ValueError("update the distribution checks when changing Python support")
    return version


def verify_artifacts(directory, version):
    paths = {
        p.name: p
        for p in directory.iterdir()
        if p.is_file() and p.name.endswith((".whl", ".tar.gz", ".tgz"))
    }
    kinds = Counter(
        "wheel" if n.endswith(".whl") else "sdist" if n.endswith(".tar.gz") else "npm"
        for n in paths
    )
    if kinds != {"wheel": 4, "sdist": 1, "npm": 1}:
        raise ValueError("expected four platform wheels, one sdist and one npm archive")
    verified = set()
    for report_path in directory.glob("*-verification.json"):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        key = "archive" if "archive" in report else "wheel"
        # Reports made by Windows use backslashes; accept that basename on Linux.
        name = PureWindowsPath(report[key]).name
        if name not in paths or name in verified or report["version"] != version:
            raise ValueError(
                "invalid or duplicate qualification report: " + report_path.name
            )
        if (
            hashlib.sha256(paths[name].read_bytes()).hexdigest()
            != report[key + "_sha256"]
        ):
            raise ValueError("qualified artifact changed: " + name)
        verified.add(name)
    if verified != set(paths):
        raise ValueError("missing artifact qualification report")
    return sorted(verified)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag")
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    version = check_versions(tag=args.tag)
    if args.artifacts:
        print(
            "Verified artifacts: "
            + ", ".join(verify_artifacts(args.artifacts, version))
        )
    print("Release metadata verified: " + version)


if __name__ == "__main__":
    main()
