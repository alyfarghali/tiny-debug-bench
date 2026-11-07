"""Visible tests: the optimizer."""

import pytest

from tiny import TinyError, run
from tiny.optimizer import optimize


def test_optimize_bottom_up():
    expr = ("bin", "*", ("var", "x"), ("bin", "-", ("num", 2), ("num", 1)))
    assert optimize(expr) == ("var", "x")


def test_times_zero_keeps_undefined_variable_error():
    with pytest.raises(TinyError) as info:
        run("print x * 0")
    assert str(info.value) == "Line 1: undefined variable 'x'"
