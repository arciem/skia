#!/usr/bin/env python3
"""Fast refusal tests; the documented real setup/build remains a separate qualification."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("custom_build", Path(__file__).with_name("build-custom-canvaskit.py"))
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


class BuildGuards(unittest.TestCase):
    def test_existing_output_is_untouched_before_commands(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            source.mkdir()
            output = root / "previous"
            output.mkdir()
            (output / "keep").write_text("original")
            with patch.object(workflow.subprocess, "check_output") as command:
                with self.assertRaisesRegex(ValueError, "fresh path"):
                    workflow.build("setup", source, output)
                command.assert_not_called()
            self.assertEqual((output / "keep").read_text(), "original")
            dangling = root / "dangling"
            dangling.symlink_to(root / "absent")
            with self.assertRaisesRegex(ValueError, "symbolic links"):
                workflow.validate_paths(source, dangling)
            self.assertFalse((root / "absent").exists())

    def test_output_inside_source_or_symlinked_inside_refuses(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source"
            source.mkdir()
            alias = root / "alias"
            alias.symlink_to(source, target_is_directory=True)
            for output in [source / "new", alias / "new"]:
                with self.assertRaisesRegex(ValueError, "outside"):
                    workflow.validate_paths(source, output)
                self.assertFalse(output.exists())

    def test_source_changes_refuse_before_build(self):
        with patch.object(workflow, "read_command", side_effect=["", "", "src/changed.cpp", ""]):
            with self.assertRaisesRegex(ValueError, "pinned baseline"):
                workflow.validate_source(Path("."))

    def test_wrong_sdk_refuses(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)
            script = source / "third_party/externals/emsdk/emsdk_env.sh"
            script.parent.mkdir(parents=True)
            script.write_text("")
            compiler = script.parent / "upstream/emscripten/emcc"
            compiler.parent.mkdir(parents=True)
            compiler.write_text("#!/bin/sh\nprintf 'emcc version 3.1.45\\n'\n")
            compiler.chmod(0o755)
            with self.assertRaisesRegex(ValueError, "Wrong Emscripten"):
                workflow.sdk_environment(source)

    def test_annotated_dependency_pin_uses_peeled_commit(self):
        helper = {"parse_file_to_dict": lambda _: {"deps": {"dep": "https://example.invalid/source@tag-object"}}}
        with patch.object(workflow.runpy, "run_path", return_value=helper), patch.object(workflow, "read_command", side_effect=["commit", "commit", "", str(Path("dep").resolve())]) as command:
            result = workflow.dependencies(Path("."))
            self.assertEqual(result[0]["revision"], "tag-object")
            self.assertEqual(command.call_args_list[0].args[0][-1], "tag-object^{commit}")

    def test_dependency_revision_dirty_status_and_checkout_custody(self):
        helper = {"parse_file_to_dict": lambda _: {"deps": {"dep": "https://example.invalid/source@pin"}}}
        cases = [
            (["expected", "different", ""], "clean DEPS revision"),
            (["expected", "expected", " M tracked.cpp"], "clean DEPS revision"),
            (["expected", "expected", "", str(Path(".").resolve())], "custody"),
        ]
        for replies, message in cases:
            with self.subTest(message=message, replies=replies):
                with patch.object(workflow.runpy, "run_path", return_value=helper), patch.object(workflow, "read_command", side_effect=replies):
                    with self.assertRaisesRegex(ValueError, message):
                        workflow.dependencies(Path("."))

    def test_nonancestor_source_refuses(self):
        error = workflow.subprocess.CalledProcessError(1, ["git", "merge-base"])
        with patch.object(workflow, "read_command", side_effect=error) as command:
            with self.assertRaises(workflow.subprocess.CalledProcessError):
                workflow.validate_source(Path("."))
            self.assertEqual(command.call_args.args[0][:3], ["git", "merge-base", "--is-ancestor"])

    def test_untracked_engine_change_refuses(self):
        with patch.object(workflow, "read_command", side_effect=["", "", "", "src/untracked.cpp"]):
            with self.assertRaisesRegex(ValueError, "pinned baseline"):
                workflow.validate_source(Path("."))

    def test_workflow_only_source_changes_are_admitted(self):
        with patch.object(workflow, "read_command", side_effect=["", "", "tools/build-custom-canvaskit.py", "", ""]):
            workflow.validate_source(Path("."))

    def test_uncommitted_allowlisted_source_refuses(self):
        for dirty in [" M modules/canvaskit/paragraph_bindings.cpp", "M  modules/canvaskit/npm_build/types/index.d.ts", "?? tools/package-custom-canvaskit.mjs"]:
            with self.subTest(dirty=dirty), patch.object(workflow, "read_command", side_effect=["", "", "", "", dirty]) as command:
                with self.assertRaisesRegex(ValueError, "checkout must be clean"):
                    workflow.validate_source(Path("."))
                self.assertEqual(command.call_args.args[0], ["git", "status", "--porcelain"])

    def test_absent_sdk_refuses(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "SDK is absent"):
                workflow.sdk_environment(Path(folder))

    def test_caller_output_and_compiler_overrides_refuse_before_commands(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)
            sentinel = source / "keep.a"
            sentinel.write_text("original")
            for key in ["BUILD_DIR", "EMCC_CFLAGS", "EM_CONFIG", "EM_CACHE"]:
                with self.subTest(key=key), patch.dict(workflow.os.environ, {key: folder}), patch.object(workflow.subprocess, "check_output") as command:
                    with self.assertRaisesRegex(ValueError, "caller build environment"):
                        workflow.build("setup", source, source.parent / (source.name + "-output"))
                    command.assert_not_called()
                    self.assertEqual(sentinel.read_text(), "original")

    def test_unselected_caller_build_flags_are_not_inherited(self):
        with patch.dict(workflow.os.environ, {"CFLAGS": "unexpected", "MAKEFLAGS": "unexpected"}):
            env = workflow.base_environment()
            self.assertNotIn("CFLAGS", env)
            self.assertNotIn("MAKEFLAGS", env)

    def test_postbuild_source_change_prevents_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)
            output = source.parent / (source.name + "-output")
            with patch.object(workflow, "validate_source", side_effect=[None, ValueError("pinned baseline moved")]), patch.object(workflow, "dependencies", return_value=[]), patch.object(workflow, "sdk_environment", return_value=({}, "version")), patch.object(workflow.subprocess, "run") as command:
                with self.assertRaisesRegex(ValueError, "pinned baseline moved"):
                    workflow.build("build", source, output)
                command.assert_called_once()
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
