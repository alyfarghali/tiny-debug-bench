"""Hidden tests: optimize() directly, and proof through run() that the
optimizer never changes a program's output or its errors."""

import pytest

from tiny import TinyError, run
from tiny.optimizer import optimize


def num(n):
    return ("num", n)


def var(name):
    return ("var", name)


def bin_(op, left, right):
    return ("bin", op, left, right)


X = var("x")


# ---- constant folding ------------------------------------------------------

@pytest.mark.parametrize(
    "expr, expected",
    [
        (bin_("+", num(2), num(3)), num(5)),
        (bin_("-", num(2), num(5)), num(-3)),
        (bin_("*", num(4), num(5)), num(20)),
        (bin_("/", num(-7), num(2)), num(-3)),
        (bin_("/", num(7), num(-2)), num(-3)),
        (bin_("~", num(5), num(2)), num(3)),
        (bin_("~", num(-5), num(2)), num(-1)),
        (bin_("-", num(0), num(0)), num(0)),
        (bin_("+", bin_("+", num(1), num(2)), bin_("+", num(3), num(4))), num(10)),
    ],
)
def test_constant_folding(expr, expected):
    assert optimize(expr) == expected


@pytest.mark.parametrize(
    "expr, expected",
    [
        (bin_("/", num(1), num(0)), bin_("/", num(1), num(0))),
        (bin_("/", num(0), num(0)), bin_("/", num(0), num(0))),
        # The right side folds to 0, but the division itself must not fold.
        (bin_("/", num(1), bin_("-", num(2), num(2))), bin_("/", num(1), num(0))),
        # x * 1 removal can expose a division by zero, which stays unfolded.
        (bin_("*", num(1), bin_("/", num(1), num(0))), bin_("/", num(1), num(0))),
    ],
)
def test_division_by_zero_is_never_folded(expr, expected):
    assert optimize(expr) == expected


# ---- identity rules --------------------------------------------------------

@pytest.mark.parametrize(
    "expr",
    [
        bin_("*", X, num(1)),
        bin_("*", num(1), X),
        bin_("+", X, num(0)),
        bin_("+", num(0), X),
        bin_("-", X, num(0)),
    ],
)
def test_identity_rules_simplify_to_x(expr):
    assert optimize(expr) == X


@pytest.mark.parametrize(
    "expr",
    [
        bin_("-", num(0), X),  # 0 - x is -x, not x
        bin_("*", X, num(0)),  # would hide an undefined-variable error
        bin_("*", num(0), X),
        bin_("/", X, num(1)),  # not one of Tiny's rules
        bin_("~", X, num(0)),
        bin_("/", num(1), X),
        bin_("+", X, num(1)),
        bin_("*", X, num(2)),
    ],
)
def test_non_rules_leave_tree_unchanged(expr):
    assert optimize(expr) == expr


def test_leaves_are_unchanged():
    assert optimize(num(7)) == num(7)
    assert optimize(var("y")) == var("y")


# ---- bottom-up ---------------------------------------------------------------

def test_bottom_up_spec_example():
    assert optimize(bin_("*", X, bin_("-", num(2), num(1)))) == X


def test_bottom_up_nested():
    expr = bin_(
        "*",
        bin_("+", X, bin_("-", num(3), num(3))),
        bin_("/", num(4), num(4)),
    )
    assert optimize(expr) == X


def test_bottom_up_chain_of_ones():
    assert optimize(bin_("*", bin_("*", X, num(1)), num(1))) == X


def test_partial_folding_keeps_variable():
    expr = bin_("+", X, bin_("*", num(2), num(3)))
    assert optimize(expr) == bin_("+", X, num(6))


# ---- through run(): output and errors never change --------------------------

@pytest.mark.parametrize(
    "source, expected",
    [
        ("let x = 4\nprint 0 - x", [-4]),
        ("let x = 9\nprint x * (2 - 1) + (3 - 3)", [9]),
        ("print (0 - 7) / 2", [-3]),
        ("print (0 - 5) ~ 2", [-1]),
        ("print (0 - 1) ~ 0", [0]),
        ("let x = 6\nprint x * 0", [0]),
        ("let x = 7\nprint x / 1", [7]),
        ("let x = 3\nprint 0 - x - 0", [-3]),
    ],
)
def test_optimizer_preserves_output(source, expected):
    assert run(source) == expected


@pytest.mark.parametrize(
    "source, message",
    [
        ("print x * 0", "Line 1: undefined variable 'x'"),
        ("print 0 * x", "Line 1: undefined variable 'x'"),
        ("print (3 - 3) * x", "Line 1: undefined variable 'x'"),
        ("print x * 1", "Line 1: undefined variable 'x'"),
        ("print 1 * x", "Line 1: undefined variable 'x'"),
        ("print x + 0", "Line 1: undefined variable 'x'"),
        ("print 0 + x", "Line 1: undefined variable 'x'"),
        ("print x - 0", "Line 1: undefined variable 'x'"),
        ("print 5 / 0", "Line 1: division by zero"),
        ("print (2 - 2) / (1 - 1)", "Line 1: division by zero"),
        ("print 1 * (5 / 0)", "Line 1: division by zero"),
        ("print (5 / 0) + 0", "Line 1: division by zero"),
    ],
)
def test_optimizer_preserves_errors(source, message):
    with pytest.raises(TinyError) as info:
        run(source)
    assert str(info.value) == message
