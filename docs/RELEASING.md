# Preparing and publishing a release

Creating or merging a release preparation PR does not publish packages.
The [changelog](../CHANGELOG.md) and
[extension guide](WRITER_EXTENSIONS.md) describe the writer additions. The
[0.4 migration guide](MIGRATING_0_4.md) still applies when upgrading from 0.3.x.

## Local qualification

Use Rust, uv, Python 3.11+ with `maturin`/`pip`, Node.js 22.12+ and pnpm 9.15.1.
The distributed Python package continues to support Python 3.9+; only the release
tooling requires `tomllib` from Python 3.11+.

Set the next version with one command (replace `0.6.2` with the intended version):

```sh
python scripts/bump-version.py 0.6.2
```

The source of truth is `[workspace.package].version` in the root `Cargo.toml`.
All Rust packages [inherit it](https://doc.rust-lang.org/cargo/reference/workspaces.html#the-package-table)
with `version.workspace = true`; Maturin reads it for Python through
[`dynamic = ["version"]`](https://www.maturin.rs/metadata.html#dynamic-metadata).
The command updates the workspace
version and npm metadata, regenerates Cargo/uv locks without requesting dependency
upgrades, and checks consistency. uv records the editable package with a dynamic
version, so `uv.lock` no longer duplicates the release number. Use `--offline`
when dependencies are already cached. If a step fails, the command restores the
four files it can modify, including any edits present before it ran. It does not
commit, create tags or publish packages.

Review the resulting diff, update the changelog, then qualify the release:

```sh
python scripts/check-release.py
cargo test --workspace --locked
cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
cargo fmt --all --check
python scripts/jwc/check_corpus.py
python scripts/jww/check_fixtures.py
maturin build --release --locked --out dist
python scripts/check-wheel.py --wheel-dir dist --report wheel-verification.json
maturin sdist --out sdist
python scripts/check-sdist.py --archive sdist/*.tar.gz --report sdist-verification.json
```

Run package tests/typechecks, browser build, web-WASM and cross-language checks
as in [CI](../.github/workflows/ci.yml). From `packages/ezjww`, pack the npm archive
with `pnpm pack --pack-destination ../../dist`; from the repository root verify it:

```sh
node scripts/check-npm-package.mjs --archive dist/ezjww-*.tgz --report npm-verification.json
```

Use fresh output directories so a previous artifact cannot be selected. The
wheel/npm probes install offline into new temporary directories and exercise
JWW creation/readback, exact mixed-drawing bytes, existing JWW/JWC reading and DXF
conversion. The sdist check validates its payload and embedded template, extracts
outside the checkout, builds with the archived lockfile and runs the archived
wheel probe in another clean environment. Rust/build tools and their dependency
caches are still required; this is not a claim of a fully offline source build.

The sdist uses Maturin's [Git generator](https://www.maturin.rs/config.html), so
create it from a Git checkout with the intended files tracked. This preserves
both Cargo workspace members and the shared lockfile. The default Cargo generator
omitted the WASM member but retained its lock entries in this project, causing
`--locked` builds from the archive to fail. The sdist gate checks the complete
workspace and builds without rewriting the lockfile.

## Release workflow

The [release workflow](../.github/workflows/release.yml) has two modes:

- **Run workflow / `workflow_dispatch`:** build and qualify all artifacts, upload
  them and their JSON reports, and skip both publish jobs. Use this on the
  preparation branch to inspect Linux x86_64/aarch64, Windows and macOS wheels,
  sdist and npm output.
- **Push `vX.Y.Z`:** require the tag to match Python, all Cargo packages, npm and
  Cargo lockfile versions; build and qualify every distribution; then publish
  the exact archives from that run. Both registries wait for all build jobs to pass.

The publish jobs verify every archive's SHA-256 against its qualification report.
npm publishes the tested `.tgz` with lifecycle scripts disabled, so `prepack`
cannot create a different WASM binary during publication. Python publishes the
tested four platform wheels (Linux x86_64 and aarch64, Windows, macOS) and sdist.
OIDC permission is limited to the two publish jobs. The existing PyPI token
configuration and npm Trusted Publisher
account configuration must be available when publishing; branch verification
does not validate registry credentials. Registry uploads are separate operations,
so failure at one registry does not roll back the other.

Before a release tag, finalize the changelog date, run `scripts/bump-version.py`
for the intended version, and pass the branch workflow. The final tag push is the
publishing action. Afterward, check both registries and installed-package behavior separately;
successful builds or a merged PR alone do not establish publication.

CI's Windows reader/package checks do not run Jw_cad. Retain the Wine/Windows
distinction and known native limitations in [the compatibility report](JWW_COMPATIBILITY.md).
