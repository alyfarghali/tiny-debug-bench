"""Hidden tests: every error message, line numbers, error order, and the CLI."""

import subprocess
import sys
from pathlib import Path

import pytest

from tiny import TinyError, run

REPO_ROOT = Path(__file__).resolve().parents[2]


def assert_error(source, message):
    with pytest.raises(TinyError) as info:
        run(source)
    assert str(info.value) == message


@pytest.mark.parametrize(
    "source, message",
    [
        # unknown symbol
        ("print 1 $ 2", "Line 1: unknown symbol '$'"),
        ("print 1.5", "Line 1: unknown symbol '.'"),
        # unexpected token
        ("print 1 2", "Line 1: unexpected token '2'"),
        ("print 1 )", "Line 1: unexpected token ')'"),
        ("print * 2", "Line 1: unexpected token '*'"),
        ("print let", "Line 1: unexpected token 'let'"),
        ("print print", "Line 1: unexpected token 'print'"),
        ("let x = 1 = 2", "Line 1: unexpected token '='"),
        ("let x == 1", "Line 1: unexpected token '='"),
        ("print 1 + + 2", "Line 1: unexpected token '+'"),
        ("print ()", "Line 1: unexpected token ')'"),
        ("print -5", "Line 1: unexpected token '-'"),  # no unary minus
        ("print 2 * -3", "Line 1: unexpected token '-'"),
        ("let x = 5 print x", "Line 1: unexpected token 'print'"),
        ("print 1 (2)", "Line 1: unexpected token '('"),
        ("print 12abc", "Line 1: unexpected token 'abc'"),
        # unexpected end of line
        ("print", "Line 1: unexpected end of line"),
        ("print 1 +", "Line 1: unexpected end of line"),
        ("print 2 ~", "Line 1: unexpected end of line"),
        ("let x =", "Line 1: unexpected end of line"),
        ("print (", "Line 1: unexpected end of line"),
        ("print (1 +", "Line 1: unexpected end of line"),
        # expected ')'
        ("print (1 + 2", "Line 1: expected ')'"),
        ("print (1 2)", "Line 1: expected ')'"),
        ("print ((1)", "Line 1: expected ')'"),
        ("print (1 + 2 = 3", "Line 1: expected ')'"),
        # expected 'let' or 'print'
        ("x = 5", "Line 1: expected 'let' or 'print'"),
        ("5", "Line 1: expected 'let' or 'print'"),
        ("Print 1", "Line 1: expected 'let' or 'print'"),
        ("= 1", "Line 1: expected 'let' or 'print'"),
        ("(print 1)", "Line 1: expected 'let' or 'print'"),
        ("printx 1", "Line 1: expected 'let' or 'print'"),
        ("letx = 1", "Line 1: expected 'let' or 'print'"),
        ("+ 1", "Line 1: expected 'let' or 'print'"),
        # expected variable name after 'let'
        ("let", "Line 1: expected variable name after 'let'"),
        ("let 5 = 1", "Line 1: expected variable name after 'let'"),
        ("let print = 1", "Line 1: expected variable name after 'let'"),
        ("let let = 1", "Line 1: expected variable name after 'let'"),
        ("let = 1", "Line 1: expected variable name after 'let'"),
        ("let (x) = 1", "Line 1: expected variable name after 'let'"),
        # expected '=' after variable name
        ("let x", "Line 1: expected '=' after variable name"),
        ("let x 5", "Line 1: expected '=' after variable name"),
        ("let x + 1", "Line 1: expected '=' after variable name"),
        # undefined variable
        ("print y", "Line 1: undefined variable 'y'"),
        ("let x = x + 1", "Line 1: undefined variable 'x'"),
        ("print 1 + z", "Line 1: undefined variable 'z'"),
        ("let a = 1\nprint A", "Line 2: undefined variable 'A'"),
        # already defined (checked BEFORE the right-hand side)
        ("let x = 1\nlet x = 2", "Line 2: variable 'x' already defined"),
        ("let x = 1\nlet x = y", "Line 2: variable 'x' already defined"),
        ("let x = 1\nlet x = 1 / 0", "Line 2: variable 'x' already defined"),
        ("let x = 1\nlet x = x", "Line 2: variable 'x' already defined"),
        # division by zero
        ("print 1 / 0", "Line 1: division by zero"),
        ("print 0 / 0", "Line 1: division by zero"),
        ("print 5 / (3 - 3)", "Line 1: division by zero"),
        ("let z = 0\nprint 1 / z", "Line 2: division by zero"),
        ("print 1 / ((0 - 1) ~ 0)", "Line 1: division by zero"),  # -1 ~ 0 is 0
        ("let a = 0 - 1\nprint 1 / (a ~ 0)", "Line 2: division by zero"),
    ],
)
def test_error_message(source, message):
    assert_error(source, message)


# ---- line numbers count blank lines ----------------------------------------

@pytest.mark.parametrize(
    "source, message",
    [
        ("\n\nprint y", "Line 3: undefined variable 'y'"),
        ("print 1\n\n   \n\tprint 1 / 0", "Line 4: division by zero"),
        ("\n \n\t\nlet 5 = 1", "Line 4: expected variable name after 'let'"),
        ("print 1\nprint 2\nprint $", "Line 3: unknown symbol '$'"),
        ("\r\nprint (1", "Line 2: expected ')'"),
        ("let a = 1\n\nlet b = 2\n\n\nlet a = 3", "Line 6: variable 'a' already defined"),
    ],
)
def test_error_line_numbers(source, message):
    assert_error(source, message)


# ---- which error wins --------------------------------------------------------

def test_no_partial_output_on_error():
    assert_error("print 1\nprint 1 / 0\nprint 2", "Line 2: division by zero")


def test_earlier_runtime_error_beats_later_syntax_error():
    assert_error("print 1\nprint 1 / 0\nprint $", "Line 2: division by zero")


def test_first_line_error_stops_execution():
    assert_error("print $\nprint y", "Line 1: unknown symbol '$'")


@pytest.mark.parametrize(
    "source, message",
    [
        ("print y / 0", "Line 1: undefined variable 'y'"),
        ("print (1 / 0) + y", "Line 1: division by zero"),
        ("print y + z", "Line 1: undefined variable 'y'"),
        ("print 1 / 0 ~ y", "Line 1: division by zero"),
    ],
)
def test_left_operand_error_reported_first(source, message):
    assert_error(source, message)


# ---- command line ------------------------------------------------------------

def run_cli(tmp_path, source):
    program = tmp_path / "program.tiny"
    program.write_text(source, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "tiny", str(program)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_cli_prints_each_output_on_its_own_line(tmp_path):
    result = run_cli(tmp_path, "print 1\nlet x = 0 - 7\nprint x / 2")
    assert result.returncode == 0
    assert result.stdout == "1\n-3\n"


def test_cli_reports_error_and_exits_1(tmp_path):
    result = run_cli(tmp_path, "print 1\n\nprint y")
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "Line 3: undefined variable 'y'"
