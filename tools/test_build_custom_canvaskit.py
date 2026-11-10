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
        with patch.object(workflow, "read_command", side_effect=["", "src/changed.cpp", ""]):
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


if __name__ == "__main__":
    unittest.main()
