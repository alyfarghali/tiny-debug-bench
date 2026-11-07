"""Visible tests: Tiny's arithmetic and variables."""

from tiny import run


def test_division_truncates_toward_zero():
    assert run("print 7 / 2\nprint (0 - 7) / 2") == [3, -3]


def test_average_truncates_toward_zero():
    assert run("print 6 ~ 4\nprint (0 - 5) ~ 2") == [5, -1]


def test_variables_through_evaluator():
    assert run("let a = 0 - 7\nlet b = 2\nprint a / b\nprint a ~ b") == [-3, -2]
