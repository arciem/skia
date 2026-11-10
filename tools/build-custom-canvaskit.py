#!/usr/bin/env python3
"""Build the pinned custom CanvasKit without changing a caller's environment or outputs."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

BASELINE = "e2def78fa232884d4aedcf3ad92d4a0dd673b898"
CUSTOM_BASELINE = "a16179cc946b488a4afa5009d4b6483c92db852f"
SDK_VERSION = "4.0.7"
WORKFLOW_FILES = {
    "tools/build-custom-canvaskit.py",
    "tools/test_build_custom_canvaskit.py",
    "modules/canvaskit/CUSTOM_BUILD.md",
    "modules/canvaskit/paragraph_bindings.cpp",
    "modules/canvaskit/npm_build/types/index.d.ts",
    "tools/package-custom-canvaskit.mjs",
    "tools/test_package_custom_canvaskit.mjs",
}


def base_environment():
    # Build settings must not inherit caller compiler flags, output roots or caches.
    forbidden = [key for key in os.environ if key == "BUILD_DIR" or key.startswith(("EMCC_", "EM_"))]
    if forbidden:
        raise ValueError("Unexpected caller build environment: " + ", ".join(sorted(forbidden)))
    return {key: os.environ[key] for key in ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE") if key in os.environ}


def read_command(argv, cwd, env=None):
    return subprocess.check_output(argv, cwd=cwd, env=env, text=True).strip()


def validate_paths(source, output):
    if output.is_symlink():
        raise ValueError("Output must be a fresh path; symbolic links are not output destinations")
    source, output = source.resolve(), output.resolve()
    if not source.is_dir() or not output.parent.is_dir():
        raise ValueError("Source and output parent must already exist")
    if output.exists() or output.is_symlink():
        raise ValueError("Output must be a fresh path; existing artifacts are never replaced")
    if source == output or source in output.parents:
        raise ValueError("Output must be outside the source checkout")
    return source, output


def validate_source(source):
    read_command(["git", "merge-base", "--is-ancestor", BASELINE, "HEAD"], source)
    read_command(["git", "merge-base", "--is-ancestor", CUSTOM_BASELINE, "HEAD"], source)
    changed = set(read_command(["git", "diff", "--name-only", BASELINE, "--"], source).splitlines())
    untracked = set(read_command(["git", "ls-files", "--others", "--exclude-standard"], source).splitlines())
    if (changed | untracked) - WORKFLOW_FILES:
        raise ValueError("Source differs from the pinned baseline outside the custom source/build allowlist")
    if read_command(["git", "status", "--porcelain"], source):
        raise ValueError("Source checkout must be clean; commit tracked and untracked changes before building")


def dependencies(source):
    helper = runpy.run_path(str(source / "tools/git-sync-deps"))
    values = helper["parse_file_to_dict"](str(source / "DEPS"))["deps"]
    result = []
    for name, value in sorted(values.items()):
        if not isinstance(value, str):
            continue
        checkout = source / name
        pin = value.rsplit("@", 1)[1]
        expected = read_command(["git", "rev-parse", pin + "^{commit}"], checkout)
        actual = read_command(["git", "rev-parse", "HEAD"], checkout)
        if expected != actual or read_command(["git", "status", "--porcelain", "--untracked-files=no"], checkout):
            raise ValueError("Dependency is not at its clean DEPS revision: " + name)
        if Path(read_command(["git", "rev-parse", "--show-toplevel"], checkout)).resolve() != checkout.resolve():
            raise ValueError("Dependency Git custody resolves outside its checkout: " + name)
        result.append({"path": name, "revision": pin, "commit": actual})
    return result


def sdk_environment(source):
    script = source / "third_party/externals/emsdk/emsdk_env.sh"
    if not script.is_file():
        raise ValueError("SDK is absent; run setup first")
    raw = subprocess.check_output(
        ["/bin/bash", "-c", 'set -e; source "$1" >/dev/null 2>&1; env -0', "sdk-env", str(script)],
        cwd=source, env=base_environment(),
    )
    # Only SDK settings are collected; never persist or print the inherited environment.
    allowed = {"PATH", "EMSDK", "EM_CONFIG", "EMSDK_NODE", "EMSDK_PYTHON", "EMSDK_PY"}
    env = base_environment()
    for entry in raw.split(b"\0"):
        if b"=" in entry:
            key, value = entry.split(b"=", 1)
            if key.decode() in allowed:
                env[key.decode()] = value.decode()
    emcc = source / "third_party/externals/emsdk/upstream/emscripten/emcc"
    version = read_command([str(emcc), "--version"], source, env)
    if not version.splitlines()[0].split().count(SDK_VERSION):
        raise ValueError("Wrong Emscripten version; expected " + SDK_VERSION)
    return env, version


def build(mode, source, output):
    source, output = validate_paths(source, output)
    clean_environment = base_environment()
    validate_source(source)
    if mode == "setup":
        env = dict(clean_environment, GIT_SYNC_DEPS_SKIP_EMSDK="1")
        subprocess.run([sys.executable, str(source / "tools/git-sync-deps")], cwd=source, env=env, check=True)
        sdk = source / "third_party/externals/emsdk/emsdk.py"
        # SDK-local configuration only: no --permanent, --system, profile edits or global installs.
        for operation in ["install", "activate"]:
            subprocess.run([sys.executable, str(sdk), operation, SDK_VERSION], cwd=source, env=clean_environment, check=True)
    inventory = dependencies(source)
    env, compiler = sdk_environment(source)
    subprocess.run(["make", "release"], cwd=source / "modules/canvaskit", env=env, check=True)
    validate_source(source)
    tools = {}
    for name, command, flag in [
        ("python3", shutil.which("python3", path=env["PATH"]), "--version"),
        ("make", shutil.which("make", path=env["PATH"]), "--version"),
        ("gn", str(source / "bin/gn"), "--version"),
        ("ninja", str(source / "third_party/ninja/ninja"), "--version"),
        ("sdk_node", env.get("EMSDK_NODE"), "--version"),
    ]:
        if not command:
            raise ValueError("Build tool is absent: " + name)
        tools[name] = {"executable": command, "version": read_command([command, flag], source, env).splitlines()[0]}
    paths = {
        "canvaskit.js": source / "modules/canvaskit/build/canvaskit.js",
        "canvaskit.wasm": source / "modules/canvaskit/build/canvaskit.wasm",
        "index.d.ts": source / "modules/canvaskit/npm_build/types/index.d.ts",
    }
    bodies = {name: path.read_bytes() for name, path in paths.items()}
    output.mkdir(exist_ok=False)
    for name, body in bodies.items():
        (output / name).write_bytes(body)
    manifest = {
        "source": read_command(["git", "rev-parse", "HEAD"], source),
        "baseline": BASELINE,
        "workflow_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "mode": mode,
        "workflow_python": sys.version.split()[0],
        "build_tools": tools,
        "environment": "Caller BUILD_DIR/EMCC_*/EM_* refused; only HOME/PATH/TMPDIR/LANG/LC_ALL/LC_CTYPE and SDK-provided settings reach the build.",
        "emscripten": compiler,
        "target": "make release (default WebGL build)",
        "dependencies": inventory,
        "files": {name: {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()} for name, body in bodies.items()},
    }
    (output / "BUILD.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("CUSTOM CANVASKIT BUILD PASS", output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["setup", "build"])
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        build(args.mode, args.source, args.output)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, "CUSTOM CANVASKIT BUILD ERROR: " + str(error) + "\n")


if __name__ == "__main__":
    main()
