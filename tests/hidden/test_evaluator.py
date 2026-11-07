"""Hidden tests: Tiny's arithmetic semantics, variables, and program output.

Arithmetic cases run twice: once with constants (folded by the optimizer) and
once through variables (computed by the evaluator), so both paths are checked.
"""

import pytest

from tiny import run


def literal(n):
    """Write an int as Tiny source. Tiny has no unary minus, so -7 is (0 - 7)."""
    return str(n) if n >= 0 else f"(0 - {-n})"


DIVISION_CASES = [
    (7, 2, 3),
    (-7, 2, -3),
    (7, -2, -3),
    (-7, -2, 3),
    (6, 3, 2),
    (-6, 3, -2),
    (0, 5, 0),
    (0, -4, 0),
    (1, 3, 0),
    (-1, 3, 0),
    (-9, 4, -2),
    (9, 9, 1),
]

AVERAGE_CASES = [
    (6, 4, 5),
    (5, 2, 3),
    (-5, 2, -1),
    (2, -5, -1),
    (-5, -2, -3),
    (0, 0, 0),
    (1, 0, 0),
    (-1, 0, 0),
    (7, 7, 7),
    (-3, -3, -3),
    (1, 2, 1),
    (-1, -2, -1),
]


@pytest.mark.parametrize("a, b, expected", DIVISION_CASES)
def test_division_constants(a, b, expected):
    assert run(f"print {literal(a)} / {literal(b)}") == [expected]


@pytest.mark.parametrize("a, b, expected", DIVISION_CASES)
def test_division_variables(a, b, expected):
    source = f"let a = {literal(a)}\nlet b = {literal(b)}\nprint a / b"
    assert run(source) == [expected]


@pytest.mark.parametrize("a, b, expected", AVERAGE_CASES)
def test_average_constants(a, b, expected):
    assert run(f"print {literal(a)} ~ {literal(b)}") == [expected]


@pytest.mark.parametrize("a, b, expected", AVERAGE_CASES)
def test_average_variables(a, b, expected):
    source = f"let a = {literal(a)}\nlet b = {literal(b)}\nprint a ~ b"
    assert run(source) == [expected]


def test_average_with_zero_is_not_an_error():
    assert run("print 1 ~ 0") == [0]


# ---- huge integers: results must be exact ----------------------------------

A = 123456789012345678901234567890
B = 987654321098765432109876543210


@pytest.mark.parametrize(
    "source, expected",
    [
        (f"print {A} * {B}", A * B),
        (f"let a = {A}\nlet b = {B}\nprint a * b - a", A * B - A),
        ("print 1000000000000000000000000000000 / 3", 333333333333333333333333333333),
        ("print (0 - 1000000000000000000000000000001) / 2", -500000000000000000000000000000),
        ("print 99999999999999999999 ~ 99999999999999999998", 99999999999999999998),
        ("print (0 - 99999999999999999999) ~ 0", -49999999999999999999),
        # 2**53 + 1: the smallest integer a float can't represent.
        ("print 9007199254740993 + 0", 9007199254740993),
        ("let n = 9007199254740993\nprint n / 1", 9007199254740993),
        ("let n = 9007199254740993\nprint n ~ n", 9007199254740993),
        ("let n = 9007199254740993\nprint (0 - n) / 1", -9007199254740993),
    ],
)
def test_huge_integers(source, expected):
    assert run(source) == [expected]


def test_powers_of_two_stay_exact():
    source = (
        "let a = 2 * 2\n"
        "let b = a * a\n"
        "let c = b * b\n"
        "let d = c * c\n"
        "let e = d * d\n"
        "let f = e * e\n"
        "print f\n"
        "print f * f / 3"
    )
    assert run(source) == [2**64, 2**128 // 3]


# ---- variables ---------------------------------------------------------------

def test_variables_build_on_each_other():
    assert run("let x = 5\nlet y = x * x\nprint y - x") == [20]


def test_underscore_name():
    assert run("let _ = 4\nprint _ * _") == [16]


def test_variable_used_many_times():
    assert run("let x = 3\nprint x + x * x - x / x") == [11]


# ---- program structure and output --------------------------------------------

@pytest.mark.parametrize(
    "source, expected",
    [
        ("", []),
        ("\n\n  \n\t\n", []),
        ("let x = 1", []),
        ("print 1\nprint 2\nprint 3", [1, 2, 3]),
        ("print 5\n", [5]),
        ("print 1\r\nprint 2\r\n", [1, 2]),
        ("\n\nprint 1\n\n\nprint 2\n\n", [1, 2]),
        ("let x = 2\nprint x\nlet y = x * 10\nprint y", [2, 20]),
    ],
)
def test_program_output(source, expected):
    assert run(source) == expected
