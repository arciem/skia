# Pinned custom CanvasKit build

This candidate branch merges the recovered custom workflow tip `a16179cc946b488a4afa5009d4b6483c92db852f` with the official CanvasKit 0.42.0 tag at `e2def78fa232884d4aedcf3ad92d4a0dd673b898`. Both histories remain ancestors. The source module's unchanged 0.41.1 label is not the release identity: the official tag matches the published 0.42.0 package's gitHead. This is an isolated port, not a claim that a consumer has adopted it.

The custom surface retains `familyName`, `getParagraphInfo` and `EnhancedGlyphRun` with text direction. Shaped runs preserve the custom null `typeface` contract instead of creating caller-owned Typeface handles. The recording canvas has stack ownership, and zero-run indexing is guarded. The moved UTF header follows this release. Immutable Path and mutable PathBuilder are the upstream model; no legacy mutable-Path facade is provided.

## Build

Use Python 3.8 or later, Git, Bash and Make on a supported desktop build host. The setup command synchronizes the exact `DEPS` references, installs this release's Emscripten 4.0.7 in this checkout and activates its SDK-local configuration. It does not install global software or change shell profiles. Existing SDK downloads can be reused, but dependencies must be at their clean pinned revisions. Annotated tag references are compared with their peeled commits.

Choose a new output path outside the source checkout, with an existing parent. The workflow refuses existing output, unexpected source changes and an incorrect SDK. It uses the original dependency synchronization and release Make target. The release build needs no npm dependency install; npm dependencies in this module are for its JavaScript test infrastructure. This deliberately corrects the old `npm install ci` command rather than perpetuating it.

```sh
python3 tools/build-custom-canvaskit.py setup --output ../custom-canvaskit-output
```

After setup, use the same SDK and dependency checkout for an incremental release. Choose another fresh output directory to preserve previous artifacts.

```sh
python3 tools/build-custom-canvaskit.py build --output ../custom-canvaskit-next
```

The upstream Make/compile targets manage their own ignored `build` and `out` products, including rebuilding static archives. The workflow never cleans a caller's output directory or writes into another application. `--source` can point to another checkout of the same merged history. The diff from the release is limited to the two custom paragraph source/type files and the explicit build/test/documentation/packaging files in the script's allowlist; both source parents must be ancestors of HEAD. A pending uncommitted merge does not satisfy that final workflow guard.

The output contains `canvaskit.js`, `canvaskit.wasm`, the tracked `index.d.ts`, and `BUILD.json` with source, dependency, toolchain and member identities. Caller `BUILD_DIR`, `EMCC_*` and `EM_*` settings are refused before synchronization or building. Other caller build flags are not inherited: only ordinary host path/locale/home settings and SDK-provided variables reach Make. The record separates the workflow Python from the actual Python, Make, GN, Ninja and SDK Node executables/versions used by the build environment. Archive metadata and a consuming package's ESM wrapper are separate concerns; this command does not publish a package or choose a consumer's module format.

## Checks

Run the fast path/source/version refusal tests:

```sh
python3 tools/test_build_custom_canvaskit.py
```

A real setup/build and byte comparison are required to establish source-to-binary reproducibility on a host; these fast tests alone do not prove it. Record the actual compiler and dependency state rather than inferring provenance from a version label. Keep any earlier output and report meaningful differences before adopting a rebuilt engine.

On an ARM macOS host, this SDK's x86_64 native Closure compiler may fail with an executable-architecture error; Emscripten then reports its Java compiler fallback. Preserve the complete diagnostic and actual Java version rather than calling that build warning-free. No emulator installation or system configuration is needed for the fallback.

## Explicit packaging

With Node and an existing npm executable, `tools/package-custom-canvaskit.mjs` takes a build directory, the exact custom declaration file, a fresh external output directory and the absolute selected npm executable. It emits separately checksummed raw and ESM packages as `canvaskit` version 2.0.0, preserving JS/WASM/type bodies. The major identity reflects the immutable-Path API break; the upstream release remains separately identified as 0.42.0. The ESM wrapper and declaration entry adaptation are tested, not assumed from the previous SDK. Packaging does not install dependencies or publish anything. Run `tools/test_package_custom_canvaskit.mjs` through the selected npm's `exec -- node --test` command. Actual Node and browser loading against the rebuilt WASM remain separate qualification checks.
