from .errors import tiny_error

KEYWORDS = {"let", "print"}
OPERATORS = set("+-*/~()=")

DIGITS = set("0123456789")
LETTERS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")


def lex(line_text, line_no):
    tokens = []
    pos = 0
    while pos < len(line_text):
        char = line_text[pos]
        if char.isspace():
            pos += 1
        elif char in DIGITS:
            token, pos = read_number(line_text, pos)
            tokens.append(token)
        elif char in LETTERS or char == "_":
            token, pos = read_word(line_text, pos)
            tokens.append(token)
        elif char in OPERATORS:
            tokens.append(("OP", char))
            pos += 1
        else:
            raise tiny_error(line_no, f"unknown symbol '{char}'")
    return tokens


def read_number(text, start):
    end = start
    while end < len(text) and text[end] in DIGITS:
        end += 1
    return ("NUM", int(text[start:end])), end


def read_word(text, start):
    end = start
    while end < len(text) and is_word_char(text[end]):
        end += 1
    word = text[start:end]
    if word.startswith(tuple(KEYWORDS)):
        return ("KW", word), end
    return ("NAME", word), end


def is_word_char(char):
    return char in LETTERS or char in DIGITS or char == "_"
