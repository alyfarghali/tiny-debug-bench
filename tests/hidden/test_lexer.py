"""Hidden tests: the lexer, directly and through run()."""

import pytest

from tiny import TinyError, run
from tiny.lexer import lex


# ---- direct lex() tests ----------------------------------------------------

def test_lex_let_statement():
    assert lex("let x = 007", 1) == [
        ("KW", "let"),
        ("NAME", "x"),
        ("OP", "="),
        ("NUM", 7),
    ]


def test_lex_both_keywords():
    assert lex("let print", 1) == [("KW", "let"), ("KW", "print")]


def test_lex_every_operator():
    assert lex("+-*/~()=", 1) == [("OP", c) for c in "+-*/~()="]


def test_lex_needs_no_whitespace_between_tokens():
    assert lex("print(a+b)", 1) == [
        ("KW", "print"),
        ("OP", "("),
        ("NAME", "a"),
        ("OP", "+"),
        ("NAME", "b"),
        ("OP", ")"),
    ]


def test_lex_whitespace_only_line_is_empty():
    assert lex("   \t  ", 1) == []


def test_lex_tabs_and_carriage_return_are_whitespace():
    assert lex("\tprint\t1\r", 1) == [("KW", "print"), ("NUM", 1)]


def test_lex_leading_zeros():
    assert lex("000 0010", 1) == [("NUM", 0), ("NUM", 10)]


def test_lex_huge_number_is_exact():
    digits = "123456789" * 10
    assert lex(digits, 1) == [("NUM", int(digits))]


def test_lex_number_then_name_uses_maximal_munch():
    assert lex("12abc", 1) == [("NUM", 12), ("NAME", "abc")]


@pytest.mark.parametrize(
    "word",
    ["letter", "printer", "let_", "print2", "_let", "Let", "PRINT", "lets", "_", "a1_b2"],
)
def test_lex_non_keywords_are_names(word):
    assert lex(word, 1) == [("NAME", word)]


@pytest.mark.parametrize(
    "line, symbol",
    [
        ("print 1 $ 2", "$"),
        ("print 1.5", "."),
        ("print 5 % 2", "%"),
        ("let é = 1", "é"),
        ("print 1 # comment", "#"),
        ("print 2 ^ 3", "^"),
        ("print [1]", "["),
        ("print 'a'", "'"),
        ("print 1, 2", ","),
        ("print ²", "²"),
    ],
)
def test_lex_unknown_symbol(line, symbol):
    with pytest.raises(TinyError) as info:
        lex(line, 4)
    assert str(info.value) == f"Line 4: unknown symbol '{symbol}'"


# ---- lexer behavior through run() ------------------------------------------

@pytest.mark.parametrize(
    "source, expected",
    [
        ("print 007", [7]),
        ("print 000", [0]),
        ("print 010 + 01", [11]),  # decimal, not octal
        ("let x=5\nprint x", [5]),
        ("print 1+2*3", [7]),
        ("print(4)", [4]),
        ("\tprint\t9", [9]),
    ],
)
def test_lexing_through_run(source, expected):
    assert run(source) == expected


def test_keyword_prefixed_names_through_run():
    source = (
        "let letter = 1\n"
        "let printer = 2\n"
        "let let_ = 3\n"
        "let print1 = 4\n"
        "print letter + printer + let_ + print1"
    )
    assert run(source) == [10]


def test_names_are_case_sensitive():
    assert run("let a = 1\nlet A = 2\nprint a\nprint A") == [1, 2]


def test_capitalized_keyword_is_a_name():
    assert run("let Let = 5\nlet Print = 6\nprint Let * Print") == [30]
