"""Hidden tests: parse trees, precedence, associativity, and parentheses."""

import pytest

from tiny import TinyError, run
from tiny.lexer import lex
from tiny.parser import parse_line


def num(n):
    return ("num", n)


def var(name):
    return ("var", name)


def bin_(op, left, right):
    return ("bin", op, left, right)


def parse(text, line_no=1):
    return parse_line(lex(text, line_no), line_no)


# ---- direct parse_line() tests ---------------------------------------------

def test_parse_print_precedence_tree():
    assert parse("print 1 + 2 * 3") == (
        "print",
        bin_("+", num(1), bin_("*", num(2), num(3))),
    )


def test_parse_let():
    assert parse("let x = y") == ("let", "x", var("y"))


def test_parse_subtraction_left_associative_tree():
    assert parse("print 10 - 3 - 2") == (
        "print",
        bin_("-", bin_("-", num(10), num(3)), num(2)),
    )


def test_parse_average_left_associative_tree():
    assert parse("print 8 ~ 4 ~ 0") == (
        "print",
        bin_("~", bin_("~", num(8), num(4)), num(0)),
    )


def test_parse_division_left_associative_tree():
    assert parse("print a / b * c") == (
        "print",
        bin_("*", bin_("/", var("a"), var("b")), var("c")),
    )


def test_parse_spec_example_tree():
    assert parse("print 2 + 6 ~ 2 * 2") == (
        "print",
        bin_("+", num(2), bin_("~", num(6), bin_("*", num(2), num(2)))),
    )


def test_parse_parentheses_change_tree_shape():
    assert parse("print (1 + 2) * 3") == (
        "print",
        bin_("*", bin_("+", num(1), num(2)), num(3)),
    )


def test_parse_redundant_parentheses_leave_no_node():
    assert parse("print ((x))") == ("print", var("x"))


def test_parser_does_not_optimize():
    assert parse("print 1 + 2") == ("print", bin_("+", num(1), num(2)))


def test_parse_error_uses_given_line_number():
    with pytest.raises(TinyError) as info:
        parse("print", 7)
    assert str(info.value) == "Line 7: unexpected end of line"


def test_parse_empty_token_list():
    with pytest.raises(TinyError) as info:
        parse_line([], 3)
    assert str(info.value) == "Line 3: expected 'let' or 'print'"


# ---- precedence: every pair of precedence levels ---------------------------
# Each case is chosen so that the wrong grouping gives a different answer.

@pytest.mark.parametrize(
    "expr, expected",
    [
        # + - versus * /
        ("2 + 3 * 4", 14),
        ("2 * 3 + 4", 10),
        ("10 - 6 / 2", 7),
        ("10 / 2 - 3", 2),
        # + - versus ~
        ("1 + 9 ~ 3", 7),
        ("9 ~ 3 + 1", 7),
        ("20 - 4 ~ 2", 17),
        ("10 ~ 4 - 3", 4),
        # ~ versus * /
        ("2 ~ 4 * 3", 7),
        ("4 * 3 ~ 2", 7),
        ("12 / 2 ~ 4", 5),
        ("8 ~ 12 / 4", 5),
        # all three levels
        ("2 + 6 ~ 2 * 2", 7),
        ("1 + 2 * 3 ~ 4 - 5", 1),
    ],
)
def test_precedence(expr, expected):
    assert run(f"print {expr}") == [expected]


# ---- associativity: operators on the same level -----------------------------

@pytest.mark.parametrize(
    "expr, expected",
    [
        ("10 - 3 - 2", 5),
        ("10 - 3 + 2", 9),
        ("20 - 5 + 3 - 2", 16),
        ("100 / 10 / 5", 2),
        ("100 / 10 * 5", 50),
        ("3 * 9 / 2", 13),
        ("8 ~ 4 ~ 0", 3),
        ("0 ~ 4 ~ 8", 5),
    ],
)
def test_left_associativity(expr, expected):
    assert run(f"print {expr}") == [expected]


def test_precedence_with_variables_reaches_evaluator():
    source = "let a = 2\nlet b = 6\nprint a + b ~ a * a\nprint b - a - a"
    assert run(source) == [7, 2]


# ---- parentheses ------------------------------------------------------------

@pytest.mark.parametrize(
    "expr, expected",
    [
        ("(2 + 3) * 4", 20),
        ("2 * (3 + 4)", 14),
        ("(1 + 9) ~ 3", 6),
        ("10 - (3 - 2)", 9),
        ("8 ~ (4 ~ 0)", 5),
        ("100 / (10 / 5)", 50),
        ("((((7))))", 7),
        ("((1 + 2) * (3 + 4)) / (2 ~ 4)", 7),
        ("100 / (10 / (5 / 2))", 20),
    ],
)
def test_parentheses(expr, expected):
    assert run(f"print {expr}") == [expected]


def test_deeply_nested_parentheses():
    depth = 50
    assert run("print " + "(" * depth + "1" + ")" * depth) == [1]


# ---- how ~ groups: chains and mixes with other operators --------------------
# Every case is chosen so that right-to-left grouping gives a different answer.

@pytest.mark.parametrize(
    "expr, expected",
    [
        ("0 ~ 0 ~ 8", 4),
        ("16 ~ 0 ~ 0 ~ 0", 2),
        ("1 ~ 3 ~ 5 ~ 7", 5),
        ("(0 - 8) ~ 4 ~ 0", -1),
        ("(0 - 9) ~ 0 ~ 0", -2),
        ("12 ~ 4 ~ 2 * 2", 6),
        ("2 * 6 ~ 4 ~ 0", 4),
        ("8 ~ 2 * 2 ~ 0", 3),
        ("20 / 2 ~ 6 ~ 0", 4),
        ("1 + 8 ~ 4 ~ 0", 4),
        ("8 ~ 4 ~ 0 + 1", 4),
    ],
)
def test_average_chain_groups_left(expr, expected):
    assert run(f"print {expr}") == [expected]


def test_average_chain_groups_left_through_variables():
    source = "let a = 8\nlet b = 4\nlet c = 0\nprint a ~ b ~ c"
    assert run(source) == [3]


def test_parse_average_chain_tree():
    assert parse("print a ~ b ~ c ~ d") == (
        "print",
        bin_("~", bin_("~", bin_("~", var("a"), var("b")), var("c")), var("d")),
    )


def test_parse_average_chain_with_product_tree():
    assert parse("print a ~ b ~ c * d") == (
        "print",
        bin_("~", bin_("~", var("a"), var("b")), bin_("*", var("c"), var("d"))),
    )
