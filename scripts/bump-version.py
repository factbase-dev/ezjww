#!/usr/bin/env python3
"""Set the workspace version and synchronize npm and lockfiles (Python 3.11+).

Usage: python scripts/bump-version.py 0.6.2
Requires cargo and uv. Pass --offline to use only cached dependencies.
Does not commit, tag, or publish anything.
"""

import argparse
import json
import re
import runpy
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("Cargo.toml", "packages/ezjww/package.json", "Cargo.lock", "uv.lock")
FINAL_VERSION = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"


def bump_version(version, root=ROOT, offline=False):
    if not re.fullmatch(FINAL_VERSION, version):
        raise ValueError("expected a final version such as 0.6.2 (without a v prefix)")

    originals = {name: (root / name).read_bytes() for name in FILES}
    cargo, count = re.subn(
        r"(?m)(^\[workspace\.package\][^\S\n]*\n(?:(?!\[)[^\n]*\n)*?"
        r'version\s*=\s*)"[^"]+"',
        lambda match: match[1] + json.dumps(version),
        originals["Cargo.toml"].decode("utf-8"),
    )
    if count != 1:
        raise ValueError("expected one version in Cargo.toml [workspace.package]")
    package = json.loads(originals["packages/ezjww/package.json"])
    package["version"] = version
    flags = ["--offline"] if offline else []
    try:
        (root / "Cargo.toml").write_bytes(cargo.encode("utf-8"))
        (root / "packages/ezjww/package.json").write_bytes(
            (json.dumps(package, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        )
        # Resolve against existing locks without --upgrade, retaining dependency
        # pins. Cargo updates all workspace packages; uv records a dynamic version.
        subprocess.run(
            ["cargo", "metadata", "--format-version", "1", *flags],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(["uv", "lock", *flags], cwd=root, check=True)
        check = runpy.run_path(str(root / "scripts/check-release.py"))["check_versions"]
        check(root=root, tag="v" + version)
    except (Exception, KeyboardInterrupt):
        for name, content in originals.items():
            (root / name).write_bytes(content)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="final version, e.g. 0.6.2")
    parser.add_argument(
        "--offline", action="store_true", help="use cached dependencies only"
    )
    args = parser.parse_args()
    try:
        bump_version(args.version, offline=args.offline)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Version update failed: {error}\n")
    print(f"Version synchronized: {args.version}. Review the diff before committing.")


if __name__ == "__main__":
    main()
