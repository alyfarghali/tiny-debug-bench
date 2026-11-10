"""The agent's tools: the only way it can see or change anything.

All safety rules live in Tools.call():
  * Paths must resolve to a location inside the workdir (no ../, no absolute
    paths elsewhere, no symlinks pointing out).
  * Only files under tiny/ can be edited. That covers "test files can't be
    edited" and "no new files outside tiny/", and also stops edits to SPEC.md
    or new config files (like conftest.py) that could change how tests run.
  * Tools the setup doesn't allow are refused, even if the model invents a call.
  * Nothing ever raises: every failure comes back as an "Error: ..." string the
    agent can read and learn from.

Tool availability:
  list_files, read_file   multi_turn
  edit_file               always
  run_tests               feedback
  read_spec               spec

read_file may read tests/visible/: real developers read tests, and that shows
the agent what is expected. The tests still can't be edited.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

TOOL_SCHEMAS = {
    "list_files": {
        "name": "list_files",
        "description": "List every file in the project, one path per line.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "read_file": {
        "name": "read_file",
        "description": "Read a file. Each line is prefixed with its line number, like '12: code'.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Path relative to the project root, e.g. tiny/parser.py"}},
            "required": ["path"],
        },
    },
    "edit_file": {
        "name": "edit_file",
        "description": "Replace the ENTIRE contents of a file under tiny/ with new_content. "
                       "Write the whole file, not just the changed lines. Test files cannot be edited.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the project root, e.g. tiny/parser.py"},
                "new_content": {"type": "string", "description": "The complete new file contents"},
            },
            "required": ["path", "new_content"],
        },
    },
    "run_tests": {
        "name": "run_tests",
        "description": "Run the visible test suite (tests/visible). The first line is a summary like "
                       "'RESULT: 3 failed, 13 passed'; failure details follow.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "read_spec": {
        "name": "read_spec",
        "description": "Read SPEC.md, the specification of the Tiny language.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

# Which setup key must be on for each tool. None means always available.
TOOL_REQUIRES = {
    "list_files": "multi_turn",
    "read_file": "multi_turn",
    "edit_file": None,
    "run_tests": "feedback",
    "read_spec": "spec",
}

EDITABLE_ROOT = "tiny"


class ToolError(Exception):
    """Raised inside a tool; turned into an 'Error: ...' string by call()."""


class Tools:
    def __init__(self, workdir, setup, config):
        self.workdir = Path(workdir).resolve()
        self.setup = setup
        self.config = config
        self.max_chars = config["tool_output_max_chars"]
        self.test_timeout = config["test_timeout_s"]
        self.stats = {"calls": {}, "errors": {}, "blocked_edits": 0}

    # ---- what the model sees -------------------------------------------------

    def allowed(self, name):
        required = TOOL_REQUIRES.get(name)
        return name in TOOL_REQUIRES and (required is None or self.setup.get(required, False))

    def schemas(self):
        return [TOOL_SCHEMAS[name] for name in TOOL_SCHEMAS if self.allowed(name)]

    # ---- dispatch: every safety rule runs through here -------------------------

    def call(self, name, args):
        """Run a tool by name. Always returns a string; never raises."""
        name = str(name)
        self.stats["calls"][name] = self.stats["calls"].get(name, 0) + 1
        try:
            result = self.dispatch(name, args)
        except ToolError as error:
            result = f"Error: {error}"
        except Exception as error:  # noqa: BLE001 - a harness bug must still never crash the run
            result = f"Error: internal error in {name}: {type(error).__name__}: {error}"
        if result.startswith("Error:"):
            self.stats["errors"][name] = self.stats["errors"].get(name, 0) + 1
        return result

    def dispatch(self, name, args):
        if name not in TOOL_SCHEMAS:
            raise ToolError(f"unknown tool '{name}'")
        if not self.allowed(name):
            raise ToolError(f"tool '{name}' is not available in this setup")
        args = self.check_args(name, args)
        return getattr(self, f"tool_{name}")(**args)

    def check_args(self, name, args):
        if args is None:
            args = {}
        if not isinstance(args, dict):
            raise ToolError(f"arguments for '{name}' must be an object, got {type(args).__name__}")
        schema = TOOL_SCHEMAS[name]["parameters"]
        for key in args:
            if key not in schema["properties"]:
                raise ToolError(f"unexpected argument '{key}' for '{name}'")
        for key in schema["required"]:
            if key not in args:
                raise ToolError(f"missing required argument '{key}' for '{name}'")
            if not isinstance(args[key], str):
                raise ToolError(f"argument '{key}' for '{name}' must be a string")
        return args

    # ---- paths -------------------------------------------------------------------

    def resolve(self, path):
        """Turn a user path into an absolute path that is inside the workdir."""
        if not path.strip():
            raise ToolError("path is empty")
        if "\x00" in path:
            raise ToolError("path contains a null byte")
        full = (self.workdir / path).resolve()  # follows .. and symlinks
        if not full.is_relative_to(self.workdir):
            raise ToolError(f"path '{path}' is outside the project folder")
        return full

    def relative(self, full):
        return full.relative_to(self.workdir).as_posix()

    # ---- the tools ---------------------------------------------------------------

    def tool_list_files(self):
        files = []
        for path in self.workdir.rglob("*"):
            rel = path.relative_to(self.workdir)
            if any(part.startswith(".") or part == "__pycache__" for part in rel.parts):
                continue
            if path.is_file():
                files.append(rel.as_posix())
        return "\n".join(sorted(files)) or "(no files)"

    def tool_read_file(self, path):
        full = self.resolve(path)
        if not full.is_file():
            raise ToolError(f"no such file '{path}'")
        try:
            text = full.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ToolError(f"'{path}' is not a text file")
        numbered = "\n".join(f"{n}: {line}" for n, line in enumerate(text.split("\n"), start=1))
        return self.trim_start(numbered)

    def tool_edit_file(self, path, new_content):
        try:
            full = self.resolve(path)
        except ToolError:
            self.stats["blocked_edits"] += 1
            raise
        rel = self.relative(full)
        if rel.split("/")[0] != EDITABLE_ROOT or rel == EDITABLE_ROOT:
            self.stats["blocked_edits"] += 1
            if rel.startswith("tests/") or rel == "tests":
                raise ToolError(f"'{rel}' is a test file; test files cannot be edited")
            raise ToolError(f"'{rel}' cannot be edited; only files under {EDITABLE_ROOT}/ can be changed")
        if full.is_dir():
            raise ToolError(f"'{rel}' is a folder, not a file")
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(new_content, encoding="utf-8")
        return f"Wrote {rel} ({len(new_content.splitlines())} lines)."

    def tool_run_tests(self):
        remove_pycache(self.workdir)
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/visible", "-q", "--tb=short", "-p", "no:cacheprovider"],
                cwd=self.workdir,
                capture_output=True,
                text=True,
                timeout=self.test_timeout,
                env=clean_env(),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return f"Error: tests timed out after {self.test_timeout:g}s (possible infinite loop)"
        output = (completed.stdout + completed.stderr).strip()
        return f"{result_line(output, completed.returncode)}\n{self.trim_end(output)}"

    def tool_read_spec(self):
        spec = self.workdir / "SPEC.md"
        if not spec.is_file():
            raise ToolError("SPEC.md is not available")
        return self.trim_start(spec.read_text(encoding="utf-8"))

    # ---- output trimming ----------------------------------------------------------

    def trim_start(self, text):
        """For files: keep the beginning."""
        if len(text) <= self.max_chars:
            return text
        return text[:self.max_chars] + "\n...(truncated)"

    def trim_end(self, text):
        """For test output: keep the end, where pytest's summary is."""
        if len(text) <= self.max_chars:
            return text
        return "(truncated)...\n" + text[-self.max_chars:]


def result_line(output, returncode):
    """A first line the harness can parse, e.g. 'RESULT: 3 failed, 13 passed'."""
    counts = {"failed": 0, "passed": 0, "errors": 0}
    lines = output.splitlines()
    summary = lines[-1] if lines else ""
    for number, word in re.findall(r"(\d+) (passed|failed|errors?)", summary):
        counts["errors" if word.startswith("error") else word] = int(number)
    if not any(counts.values()):
        return f"RESULT: no tests ran (exit code {returncode})"
    text = f"RESULT: {counts['failed']} failed, {counts['passed']} passed"
    if counts["errors"]:
        text += f", {counts['errors']} errors"
    return text


def remove_pycache(folder):
    """Stale compiled files must never be used after an edit."""
    for cache in folder.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)


def clean_env():
    """The test run must import the workdir's tiny/, nothing else."""
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env
