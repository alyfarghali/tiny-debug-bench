"""Visible tests: precedence, associativity, and tree shape."""

from tiny import run
from tiny.lexer import lex
from tiny.parser import parse_line


def test_multiplication_before_addition():
    assert run("print 2 + 3 * 4") == [14]


def test_average_sits_between_sum_and_product():
    assert run("print 2 + 6 ~ 2 * 2") == [7]


def test_subtraction_is_left_associative():
    assert run("print 10 - 3 - 2") == [5]


def test_average_is_left_associative():
    assert run("print 8 ~ 4 ~ 0") == [3]


def test_parse_line_builds_tree():
    assert parse_line(lex("print 1 + 2 * 3", 1), 1) == (
        "print",
        ("bin", "+", ("num", 1), ("bin", "*", ("num", 2), ("num", 3))),
    )
