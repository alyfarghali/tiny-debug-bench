"""Visible tests: lexer basics."""

from tiny import run
from tiny.lexer import lex


def test_lex_let_statement():
    assert lex("let x = 007", 1) == [
        ("KW", "let"),
        ("NAME", "x"),
        ("OP", "="),
        ("NUM", 7),
    ]


def test_leading_zeros():
    assert run("print 007") == [7]


def test_keyword_prefixed_names_are_normal_names():
    assert run("let letter = 3\nlet printer = 4\nprint letter + printer") == [7]
