# Pinned custom CanvasKit build

This branch preserves the custom paragraph bindings and declarations on Skia revision `32abed4e3e666dd354e39a6504a654ccb956e46e`. The custom surface includes `familyName`, `getParagraphInfo` and `EnhancedGlyphRun` with text direction. The engine source is unchanged by the workflow recovery.

## Build

Use Python 3.8 or later, Git, Bash and Make on a supported desktop build host. The setup command synchronizes the exact `DEPS` references, installs Emscripten 3.1.44 in this checkout and activates its SDK-local configuration. It does not install global software or change shell profiles. Existing SDK downloads can be reused, but dependencies must be at their clean pinned revisions. Annotated tag references are compared with their peeled commits.

Choose a new output path outside the source checkout, with an existing parent. The workflow refuses existing output, unexpected source changes and an incorrect SDK. It uses the original dependency synchronization and release Make target. The release build needs no npm dependency install; npm dependencies in this module are for its JavaScript test infrastructure. This deliberately corrects the old `npm install ci` command rather than perpetuating it.

```sh
python3 tools/build-custom-canvaskit.py setup --output ../custom-canvaskit-output
```

After setup, use the same SDK and dependency checkout for an incremental release. Choose another fresh output directory to preserve previous artifacts.

```sh
python3 tools/build-custom-canvaskit.py build --output ../custom-canvaskit-next
```

The upstream Make/compile targets manage their own ignored `build` and `out` products, including rebuilding static archives. The workflow never cleans a caller's output directory or writes into another application. `--source` can point to an independent checkout of the same baseline; only the three workflow files may differ from it.

The output contains `canvaskit.js`, `canvaskit.wasm`, the tracked `index.d.ts`, and `BUILD.json` with source, dependency, toolchain and member identities. Caller `BUILD_DIR`, `EMCC_*` and `EM_*` settings are refused before synchronization or building. Other caller build flags are not inherited: only ordinary host path/locale/home settings and SDK-provided variables reach Make. The record separates the workflow Python from the actual Python, Make, GN, Ninja and SDK Node executables/versions used by the build environment. Archive metadata and a consuming package's ESM wrapper are separate concerns; this command does not publish a package or choose a consumer's module format.

## Checks

Run the fast path/source/version refusal tests:

```sh
python3 tools/test_build_custom_canvaskit.py
```

A real setup/build and byte comparison are required to establish source-to-binary reproducibility on a host; these fast tests alone do not prove it. Record the actual compiler and dependency state rather than inferring provenance from a version label. Keep any earlier output and report meaningful differences before adopting a rebuilt engine.
