"""Visible tests: error messages and line numbers."""

import pytest

from tiny import TinyError, run


def assert_error(source, message):
    with pytest.raises(TinyError) as info:
        run(source)
    assert str(info.value) == message


def test_unknown_symbol():
    assert_error("print 1 $ 2", "Line 1: unknown symbol '$'")


def test_variable_already_defined():
    assert_error("let x = 1\nlet x = 2", "Line 2: variable 'x' already defined")


def test_division_by_zero_line_counts_blank_lines():
    assert_error("print 1\n\n   \nprint 1 / 0", "Line 4: division by zero")
