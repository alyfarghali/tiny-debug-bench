"""Acceptance tests for harness/tools.py and harness/workspace.py.

Run with:  pytest tests_harness
"""

import os
import shutil
from pathlib import Path

import pytest

from harness.setups import CONFIG, SETUPS
from harness.tools import Tools
from harness.workspace import make_workdir

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def workdirs():
    """Make workdirs and always clean them up afterwards."""
    made = []

    def make(bug_id="02", setup_name="C"):
        workdir = make_workdir(bug_id, SETUPS[setup_name])
        made.append(workdir)
        return workdir

    yield make
    for workdir in made:
        shutil.rmtree(workdir, ignore_errors=True)


def tools_for(workdir, setup_name="C", **config_overrides):
    return Tools(workdir, SETUPS[setup_name], {**CONFIG, **config_overrides})


# 1. Paths stay inside the workdir ------------------------------------------------

@pytest.mark.parametrize("path", [
    "../SPEC.md",
    "/etc/passwd",
    "tiny/../../SPEC.md",
    "~/.ssh/id_rsa",
    "..",
    str(ROOT / "bugs.json"),
    str(ROOT / "tests" / "hidden" / "test_errors.py"),
])
def test_read_file_outside_workdir_is_refused(workdirs, path):
    tools = tools_for(workdirs())
    result = tools.call("read_file", {"path": path})
    assert result.startswith("Error:")
    assert "root:" not in result and "def " not in result


def test_symlink_pointing_outside_is_refused(workdirs):
    workdir = workdirs()
    (workdir / "tiny" / "escape").symlink_to(ROOT / "bugs.json")
    tools = tools_for(workdir)
    assert "outside the project folder" in tools.call("read_file", {"path": "tiny/escape"})
    assert tools.call("edit_file", {"path": "tiny/escape", "new_content": "x"}).startswith("Error:")
    assert (ROOT / "bugs.json").read_text().startswith("[")


# 2. Test files can't be edited --------------------------------------------------

@pytest.mark.parametrize("path", [
    "tests/visible/test_x.py",
    "tests/visible/test_lexer.py",
    "tiny/../tests/visible/test_lexer.py",
    "tests/conftest.py",
])
def test_editing_tests_is_refused(workdirs, path):
    workdir = workdirs()
    before = {p: p.read_text() for p in (workdir / "tests").rglob("*.py")}
    tools = tools_for(workdir)
    result = tools.call("edit_file", {"path": path, "new_content": "def test_ok(): pass\n"})
    assert result.startswith("Error:") and "test file" in result
    after = {p: p.read_text() for p in (workdir / "tests").rglob("*.py")}
    assert after == before
    assert tools.stats["blocked_edits"] == 1


@pytest.mark.parametrize("path", ["conftest.py", "SPEC.md", "pytest.ini", "tiny", "evil/x.py"])
def test_editing_outside_tiny_is_refused(workdirs, path):
    workdir = workdirs()
    tools = tools_for(workdir)
    assert tools.call("edit_file", {"path": path, "new_content": "x"}).startswith("Error:")
    assert not (workdir / "conftest.py").exists()
    assert not (workdir / "pytest.ini").exists()
    assert (workdir / "SPEC.md").read_text() == (ROOT / "SPEC.md").read_text()


def test_new_file_inside_tiny_is_allowed(workdirs):
    workdir = workdirs()
    result = tools_for(workdir).call("edit_file", {"path": "tiny/helpers.py", "new_content": "X = 1\n"})
    assert result.startswith("Wrote")
    assert (workdir / "tiny" / "helpers.py").read_text() == "X = 1\n"


# 3. Setup controls which tools exist ---------------------------------------------

def test_setup_b_has_no_spec(workdirs):
    workdir = workdirs(setup_name="B")
    assert not (workdir / "SPEC.md").exists()
    result = tools_for(workdir, "B").call("read_spec", {})
    assert result.startswith("Error:") and "not available in this setup" in result


def test_setup_a_refuses_tools_it_does_not_have(workdirs):
    tools = tools_for(workdirs(setup_name="A"), "A")
    for name, args in [("read_file", {"path": "tiny/lexer.py"}), ("list_files", {}),
                       ("run_tests", {}), ("read_spec", {})]:
        assert "not available in this setup" in tools.call(name, args)


def test_schemas_per_setup():
    def names(setup_name):
        return {schema["name"] for schema in Tools("/tmp", SETUPS[setup_name], CONFIG).schemas()}

    assert names("A") == {"edit_file"}
    assert names("B") == {"list_files", "read_file", "edit_file", "run_tests"}
    assert names("C") == {"list_files", "read_file", "edit_file", "run_tests", "read_spec"}


def test_missing_setup_keys_mean_off():
    tools = Tools("/tmp", {"multi_turn": True}, CONFIG)  # no "feedback" or "spec" keys
    assert {s["name"] for s in tools.schemas()} == {"list_files", "read_file", "edit_file"}


# 4. run_tests --------------------------------------------------------------------

def test_run_tests_before_and_after_fix(workdirs):
    workdir = workdirs("02")
    tools = tools_for(workdir)
    before = tools.call("run_tests", {})
    assert before.startswith("RESULT: 5 failed, 11 passed")

    correct = (ROOT / "tiny" / "arithmetic.py").read_text()
    assert tools.call("edit_file", {"path": "tiny/arithmetic.py", "new_content": correct}).startswith("Wrote")
    after = tools.call("run_tests", {})
    assert after.startswith("RESULT: 0 failed, 16 passed")


def test_run_tests_uses_the_workdir_code_not_the_repo(workdirs):
    # PYTHONPATH pointing at the repo must not leak the correct code in.
    os.environ["PYTHONPATH"] = str(ROOT)
    try:
        result = tools_for(workdirs("02")).call("run_tests", {})
    finally:
        del os.environ["PYTHONPATH"]
    assert result.startswith("RESULT: 5 failed")


def test_infinite_loop_times_out(workdirs):
    workdir = workdirs()
    (workdir / "tests" / "visible" / "test_loop.py").write_text("def test_loop():\n    while True:\n        pass\n")
    result = tools_for(workdir, test_timeout_s=2).call("run_tests", {})
    assert result == "Error: tests timed out after 2s (possible infinite loop)"


def test_broken_code_reports_errors_not_crash(workdirs):
    workdir = workdirs()
    tools = tools_for(workdir)
    tools.call("edit_file", {"path": "tiny/parser.py", "new_content": "def broken(:\n"})
    result = tools.call("run_tests", {})
    assert result.startswith("RESULT:")
    assert "SyntaxError" in result


def test_test_output_keeps_the_end(workdirs):
    tools = tools_for(workdirs("03"), tool_output_max_chars=200)
    result = tools.call("run_tests", {})
    first_line, rest = result.split("\n", 1)
    assert first_line.startswith("RESULT: 4 failed")
    assert rest.startswith("(truncated)...")
    assert "failed" in rest[-200:]


# 5. Bad calls become error strings ---------------------------------------------------

@pytest.mark.parametrize("name, args", [
    ("nonexistent", {}),
    ("read_file", {}),
    ("read_file", None),
    ("read_file", "tiny/lexer.py"),
    ("read_file", {"path": 5}),
    ("read_file", {"path": ""}),
    ("read_file", {"path": "tiny/\x00lexer.py"}),
    ("read_file", {"path": "tiny/missing.py"}),
    ("read_file", {"path": "tiny"}),
    ("read_file", {"path": "tiny/lexer.py", "extra": 1}),
    ("edit_file", {"path": "tiny/lexer.py"}),
    ("edit_file", {"path": "tiny/lexer.py", "new_content": None}),
    (None, {}),
])
def test_bad_calls_return_error_strings(workdirs, name, args):
    result = tools_for(workdirs()).call(name, args)
    assert isinstance(result, str) and result.startswith("Error:")


def test_unknown_tool_message():
    assert Tools("/tmp", SETUPS["C"], CONFIG).call("nonexistent", {}) == "Error: unknown tool 'nonexistent'"


# 6. Reading -----------------------------------------------------------------------

def test_read_file_has_line_numbers(workdirs):
    result = tools_for(workdirs()).call("read_file", {"path": "tiny/errors.py"})
    assert result.splitlines()[0] == "1: class TinyError(Exception):"


def test_read_file_can_read_visible_tests(workdirs):
    result = tools_for(workdirs()).call("read_file", {"path": "tests/visible/test_lexer.py"})
    assert "def test_leading_zeros" in result


def test_read_file_truncates_long_files(workdirs):
    result = tools_for(workdirs(), tool_output_max_chars=100).call("read_file", {"path": "tiny/parser.py"})
    assert result.endswith("...(truncated)")
    assert len(result) <= 100 + len("\n...(truncated)")


def test_list_files_hides_cache_and_hidden_files(workdirs):
    workdir = workdirs()
    (workdir / "tiny" / "__pycache__").mkdir()
    (workdir / "tiny" / "__pycache__" / "x.pyc").write_bytes(b"")
    (workdir / ".hidden").write_text("secret")
    listing = tools_for(workdir).call("list_files", {}).splitlines()
    assert listing == sorted(listing)
    assert "tiny/lexer.py" in listing and "tests/visible/test_lexer.py" in listing and "SPEC.md" in listing
    assert not any("__pycache__" in line or ".hidden" in line for line in listing)


def test_read_spec_in_setup_c(workdirs):
    result = tools_for(workdirs(setup_name="C")).call("read_spec", {})
    assert result.startswith("# The Tiny Language Specification")


# 7. Stats --------------------------------------------------------------------------

def test_stats_count_calls_errors_and_blocked_edits(workdirs):
    tools = tools_for(workdirs())
    tools.call("read_file", {"path": "tiny/lexer.py"})
    tools.call("read_file", {"path": "../x"})
    for _ in range(4):
        tools.call("edit_file", {"path": "tests/visible/test_lexer.py", "new_content": ""})
    assert tools.stats["calls"] == {"read_file": 2, "edit_file": 4}
    assert tools.stats["errors"] == {"read_file": 1, "edit_file": 4}
    assert tools.stats["blocked_edits"] == 4


# 8. make_workdir ----------------------------------------------------------------------

def test_workdir_contains_only_what_the_agent_may_see(workdirs):
    workdir = workdirs("05", "C")
    files = {p.relative_to(workdir).as_posix() for p in workdir.rglob("*") if p.is_file()}
    assert not workdir.is_relative_to(ROOT)
    assert not (workdir / ".git").exists()
    assert not (workdir / "tests" / "hidden").exists()
    assert not any(name in files for name in ["bugs.json", "verify_bugs.py", "pytest.ini"])
    assert not any(f.startswith(("harness/", "bugs/", "examples/")) for f in files)
    assert files == (
        {f"tiny/{p.name}" for p in (ROOT / "bugs" / "05" / "tiny").glob("*.py")}
        | {f"tests/visible/{p.name}" for p in (ROOT / "tests" / "visible").glob("*.py")}
        | {"SPEC.md"}
    )
    # It's the bug's code, not the correct code.
    assert (workdir / "tiny" / "parser.py").read_text() == (ROOT / "bugs" / "05" / "tiny" / "parser.py").read_text()
    assert (workdir / "tiny" / "parser.py").read_text() != (ROOT / "tiny" / "parser.py").read_text()


def test_each_workdir_is_fresh(workdirs):
    first = workdirs("02")
    (first / "tiny" / "arithmetic.py").write_text("changed")
    second = workdirs("02")
    assert first != second
    assert (second / "tiny" / "arithmetic.py").read_text() != "changed"


def test_unknown_bug_id():
    with pytest.raises(ValueError):
        make_workdir("99", SETUPS["A"])
