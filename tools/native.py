#!/usr/bin/env python3
"""Build this native mod into Horizon, package it, and prove it in a running game.

    python3 tools/native.py check            # apply on the pinned Horizon, cargo check the game
    python3 tools/native.py build            # ... and build it (fast profile); prints the binary
    python3 tools/native.py package          # target/<id>-<version>.hnmod for the registry
    python3 tools/native.py proof --resources PATH   # build, then drive the game with horizon-ctl
    --horizon REV   build on another Horizon commit (`latest` = the newest Nightly) instead of
                    compatibility.json's: the mod uses only the native hook points, so it builds
                    on any Horizon whose NATIVE_HOOKS_API is the one it names, as the launcher does.

Horizon's source comes from GitHub's archive of the commit, never a local checkout; horizon-mixins is
built once at the pinned commit. Everything goes under target/.
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "target"
COMPAT = json.loads((ROOT / "compatibility.json").read_text())
MIXINS = ROOT / "mixins"
BUNDLE = next(p for p in MIXINS.iterdir() if (p / "horizon-mixin.toml").is_file())
MANIFEST = tomllib.loads((BUNDLE / "horizon-mixin.toml").read_text())
MOD_ID = MANIFEST["mod"]["id"]
VERSION = MANIFEST["mod"]["version"]
REPO = "horizon-rust/horizon"
HOOKS_FILE = "crates/horizon-client/src/game/native_hooks.rs"
HOOKS_LINE = re.compile(r"^pub\(crate\) const NATIVE_HOOKS_API: u32 = (\d+);$", re.M)


def log(*args):
    print(*args, file=sys.stderr, flush=True)


def get(url):
    request = urllib.request.Request(url, headers={"User-Agent": "horizon-native-mod"})
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def latest_nightly():
    """The commit of the newest Nightly: its permanent nightly-source/<date>-<short> tag."""
    refs = json.loads(get(f"https://api.github.com/repos/{REPO}/git/matching-refs/tags/nightly-source/"))
    newest = max(refs, key=lambda r: r["ref"])
    return get_commit(newest["ref"].removeprefix("refs/tags/"))


def get_commit(ref):
    return json.loads(get(f"https://api.github.com/repos/{REPO}/commits/{ref}"))["sha"]


def source(revision):
    """Horizon's source at `revision`, unpacked once into target/horizon/<revision>/."""
    out = TARGET / "horizon" / revision
    if (out / ".horizon-revision").is_file():
        return out
    log(f"Downloading Horizon {revision[:7]}")
    data = get(f"https://codeload.github.com/{REPO}/tar.gz/{revision}")
    partial = TARGET / "horizon" / f".{revision}.partial"
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        archive.extractall(partial, filter="data")
    top = next(partial.iterdir())
    # horizon-mixins refuses links; the source has a few (docs), none needed to build.
    for path in top.rglob("*"):
        if path.is_symlink():
            path.unlink()
    (top / ".horizon-revision").write_text(revision)
    shutil.rmtree(out, ignore_errors=True)
    top.rename(out)
    shutil.rmtree(partial)
    return out


def hooks_api(tree):
    found = HOOKS_LINE.search((tree / HOOKS_FILE).read_text()) if (tree / HOOKS_FILE).is_file() else None
    return int(found.group(1)) if found else None


def tool():
    """horizon-mixins at the pinned commit, built once."""
    rev = COMPAT["horizon_mixins_revision"]
    root = TARGET / "horizon-mixins" / rev
    binary = root / "bin" / "horizon-mixins"
    if not binary.is_file():
        log(f"Building horizon-mixins {rev[:7]}")
        subprocess.run(["cargo", "install", "--locked", "--quiet", "--git", COMPAT["horizon_mixins_repository"],
                        "--rev", rev, "--root", str(root), "horizon-mixins-cli"], check=True)
    return binary


def stage(revision):
    """The mod applied on Horizon `revision`: target/stage/ (cargo's incremental state survives)."""
    tree = source(revision)
    api = hooks_api(tree)
    if api != COMPAT["hooks"]:
        sys.exit(f"Horizon {revision[:7]} has native hook points v{api}, this mod needs v{COMPAT['hooks']}.")
    # As the launcher does for a mod on the hook points: pin the copy to the commit it builds on.
    mods = TARGET / "mods"
    shutil.rmtree(mods, ignore_errors=True)
    shutil.copytree(BUNDLE, mods / MOD_ID)
    toml = mods / MOD_ID / "horizon-mixin.toml"
    toml.write_text(re.sub(r'horizon_revision = "[0-9a-f]{40}"', f'horizon_revision = "{revision}"', toml.read_text()))
    fresh = (TARGET / "stage.new").resolve()
    shutil.rmtree(fresh, ignore_errors=True)
    subprocess.run([str(tool()), "apply", "--workspace", str(tree), "--mods", str(mods), "--out", str(fresh)],
                   check=True, stdout=subprocess.DEVNULL)
    out = TARGET / "stage"
    out.mkdir(exist_ok=True)
    # Only changed files are replaced, so cargo rebuilds only what changed.
    subprocess.run(["rsync", "-a", "--checksum", "--delete", f"{fresh}/", f"{out}/"], check=True)
    shutil.rmtree(fresh)
    return out


def cargo(stage_dir, action):
    jobs = os.environ.get("FLEET_LOAD_JOBS") or os.environ.get("CARGO_BUILD_JOBS")
    command = ["cargo", action, "--locked", "-p", "horizon-client", "--bin", "horizon-client"]
    if action == "build":
        command += ["--bin", "horizon-ctl", "--profile", "fast"]
    if os.environ.get("NATIVE_NO_DEFAULT_FEATURES"):
        command.append("--no-default-features")
    if jobs:
        command += ["-j", jobs]
    env = dict(os.environ, CARGO_TARGET_DIR=str(TARGET / "cargo"), RUSTFLAGS="-D warnings")
    subprocess.run(command, cwd=stage_dir, env=env, check=True)
    return TARGET / "cargo" / "fast"


def package():
    """A deterministic .hnmod: horizon-native.json and the bundle's .rs and .toml files."""
    manifest = {"schema": 1, "id": MOD_ID, "version": VERSION, "game": COMPAT["game"],
                "horizon": COMPAT["horizon_revision"], "mixins": COMPAT["horizon_mixins_revision"],
                "hooks": COMPAT["hooks"]}
    pinned = MANIFEST.get("compatibility", {}).get("horizon_revision")
    if pinned != COMPAT["horizon_revision"]:
        sys.exit(f"horizon-mixin.toml pins {pinned}, compatibility.json {COMPAT['horizon_revision']}")
    files = {"horizon-native.json": (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()}
    for path in sorted(BUNDLE.iterdir()):
        if path.suffix in (".rs", ".toml"):
            files[f"mixins/{MOD_ID}/{path.name}"] = path.read_bytes()
    out = TARGET / f"{MOD_ID}-{VERSION}.hnmod"
    TARGET.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    print(json.dumps({"file": str(out), "size": out.stat().st_size,
                      "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["check", "build", "package", "proof"])
    parser.add_argument("--horizon", default=COMPAT["horizon_revision"],
                        help="a Horizon commit, `latest` (newest Nightly) or a tag")
    parser.add_argument("--resources", help="prepared resources (proof): .local/horizon-client/26.3")
    args = parser.parse_args()
    if args.action == "package":
        return package()
    revision = latest_nightly() if args.horizon == "latest" else args.horizon
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        revision = get_commit(revision)
    log(f"{MOD_ID} {VERSION} on Horizon {revision[:7]}")
    out = stage(revision)
    if args.action == "check":
        cargo(out, "check")
        print(json.dumps({"mod": MOD_ID, "horizon": revision, "check": "ok"}))
        return
    binaries = cargo(out, "build")
    if args.action == "build":
        print(json.dumps({"mod": MOD_ID, "horizon": revision, "game": str(binaries / "horizon-client")}))
        return
    if not args.resources:
        sys.exit("proof needs --resources (prepared resources for Minecraft 26.3)")
    sys.path.insert(0, str(ROOT / "tools"))
    import proof
    proof.run(binaries / "horizon-ctl", Path(args.resources).resolve(), TARGET / "proof")


if __name__ == "__main__":
    main()
