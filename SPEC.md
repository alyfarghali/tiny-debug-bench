# The Tiny Language Specification

Tiny is a small, made-up language with integer variables and printing. Some of its rules are deliberately unusual, such as the `~` operator and division that truncates toward zero, so a reader can't rely on habits from other languages.

This document is the source of truth. If the implementation and this spec disagree, the implementation is wrong.

## 1. Programs and lines

- A program is text with **one statement per line**. Lines are separated by `\n`. A `\r` before the `\n` counts as whitespace.
- Lines are numbered starting at **1**, and **every** line is counted, blank ones included.
- Blank or whitespace-only lines are skipped.
- Execution goes top to bottom. Each line is lexed, parsed, optimized and executed before the next line is read, so the **first error in reading order** is the one reported.
- `run(source)` returns the list of printed values in order. If any error occurs, it raises `TinyError` and returns nothing: **no partial output**.

## 2. Statements

| Form | Meaning |
|---|---|
| `let NAME = EXPR` | Define a new variable `NAME` with the value of `EXPR`. |
| `print EXPR` | Output the value of `EXPR`. |

Anything else is an error. A complete statement followed by extra tokens is also an error.

## 3. Tokens

| Token | Rule | Examples |
|---|---|---|
| Number | One or more ASCII digits `0`–`9`. Non-negative. Leading zeros are allowed and ignored. | `0`, `42`, `007` (= 7) |
| Name | An ASCII letter or `_`, then any number of ASCII letters, digits or `_`. Case-sensitive. | `x`, `_tmp`, `Total2`, `letter` |
| Keyword | `let` and `print`. Reserved: they cannot be variable names. | `let`, `print` |
| Operator / symbol | `+` `-` `*` `/` `~` `(` `)` `=` | |

- **Maximal munch:** a word is read in full before checking whether it is a keyword. So `letter`, `printer`, `let_` and `print1` are ordinary names. Keywords are case-sensitive, so `Let` and `PRINT` are names too.
- A digit run ends where the digits end: `12abc` lexes as the number `12` followed by the name `abc`. That makes a parse error, not a lex error.
- Whitespace (any character for which Python's `str.isspace()` is true) separates tokens and is otherwise ignored. No whitespace is needed between tokens: `print(1+2)` is valid.
- **Any other character is an error**, including `.`, `%`, `#`, `,`, and non-ASCII letters and digits such as `é` or `²`.
- **There is no unary minus.** Write `0 - 5` for negative five.

## 4. Expressions

### Grammar

```
statement := "let" NAME "=" sum
           | "print" sum
sum       := average { ("+" | "-") average }
average   := product { "~" product }
product   := atom { ("*" | "/") atom }
atom      := NUMBER | NAME | "(" sum ")"
```

### Precedence (lowest to highest)

| Level | Operators | Associativity |
|---|---|---|
| 1 (lowest) | `+` `-` | left |
| 2 | `~` | left |
| 3 | `*` `/` | left |
| 4 (highest) | numbers, names, `( … )` | — |

All binary operators are **left-associative**, including `~`:

- `10 - 3 - 2` = `(10 - 3) - 2` = **5**
- `8 ~ 4 ~ 0` = `(8 ~ 4) ~ 0` = `6 ~ 0` = **3**
- `2 + 6 ~ 2 * 2` = `2 + (6 ~ (2 * 2))` = `2 + 5` = **7**

## 5. Semantics

All values are integers of unlimited size. All arithmetic is exact; floating point is never used.

| Operation | Rule | Examples |
|---|---|---|
| `a + b`, `a - b`, `a * b` | Ordinary integer arithmetic | `2 * 3` = 6 |
| `a / b` | Integer division, **truncated toward zero** (not Python's floor). `b = 0` is an error. | `7 / 2` = 3, `(0 - 7) / 2` = −3, `7 / (0 - 2)` = −3 |
| `a ~ b` | Average of `a` and `b`, **truncated toward zero**, i.e. `(a + b) / 2` by the rule above. Never an error. | `6 ~ 4` = 5, `5 ~ 2` = 3, `(0 - 5) ~ 2` = −1 |

**Evaluation order.** In `a OP b`, `a` is evaluated completely before `b`. If both sides would cause errors, the left side's error is reported.

**Variables.**

- Variables are **immutable**. A `let` for a name that already exists is an error. This check happens **before** the right-hand side is evaluated, so `let x = 1/0` on an existing `x` reports `already defined`.
- Using an undefined variable is an error. This includes using a variable inside its own definition: `let x = x + 1` fails when `x` doesn't already exist.

## 6. Errors

Every error is a `TinyError` whose message is exactly `Line N: <message>`, where `N` is the line being processed.

| Message | When |
|---|---|
| `Line N: unknown symbol 'X'` | The lexer finds a character `X` that can't start any token. |
| `Line N: unexpected token 'X'` | A token appears where it isn't allowed: where an operand was expected, or after a complete statement. |
| `Line N: unexpected end of line` | The line ends where an operand was expected. |
| `Line N: expected ')'` | A `(` expression is complete but the next token is not `)` (or there is none). |
| `Line N: expected 'let' or 'print'` | The line doesn't start with a keyword. |
| `Line N: expected variable name after 'let'` | `let` is not followed by a name (including a keyword, or nothing). |
| `Line N: expected '=' after variable name` | `let NAME` is not followed by `=`. |
| `Line N: undefined variable 'X'` | `X` is used but not defined. |
| `Line N: variable 'X' already defined` | `let X = …` when `X` already exists. |
| `Line N: division by zero` | The right side of `/` evaluates to 0. |

In `unexpected token 'X'`, `X` is the token's text. For a number token this is its decimal value without leading zeros, so `print 1 007` reports `'7'`.

## 7. Optimizer

Before each expression is evaluated, the optimizer simplifies its tree. **The optimizer must never change a program's output or its errors.**

The tree is rewritten **bottom-up**: children first, then the parent. So `x * (2 - 1)` → `x * 1` → `x`.

| Rule | Result |
|---|---|
| Constant folding: both sides of an operator are numbers | One number, computed with Tiny's rules for `/` and `~` |
| `x * 1`, `1 * x` | `x` |
| `x + 0`, `0 + x` | `x` |
| `x - 0` | `x` |

Things the optimizer must **not** do:

- Fold a division by zero (`5 / 0` stays as it is, so the evaluator reports the error).
- Simplify `0 - x` (it means −x, not x).
- Simplify `x * 0` or `0 * x` to `0` (that would hide an `undefined variable` error).
- Apply any rule not listed above (for example, `x / 1` is left alone).

## 8. Data formats

These are the Python values passed between pipeline stages.

**Tokens** (from `lex(line_text, line_no)`):

| Tuple | Example |
|---|---|
| `("NUM", int)` | `("NUM", 7)` |
| `("NAME", str)` | `("NAME", "letter")` |
| `("KW", str)` | `("KW", "let")` |
| `("OP", str)` | `("OP", "~")` |

**Expression trees** (from the parser, input and output of `optimize(expr)`):

| Tuple | Meaning |
|---|---|
| `("num", int)` | integer constant (the optimizer may produce negative ones) |
| `("var", name)` | variable reference |
| `("bin", op, left, right)` | binary operator; `op` is one of `+ - * / ~` |

Parentheses have no node of their own; they only affect the tree's shape. Example: `2 + 6 ~ 2 * 2` parses to

```python
("bin", "+", ("num", 2),
             ("bin", "~", ("num", 6),
                          ("bin", "*", ("num", 2), ("num", 2))))
```

**Statements** (from `parse_line(tokens, line_no)`): `("let", name, expr)` and `("print", expr)`. Called directly with an empty token list, `parse_line` raises `expected 'let' or 'print'`. `run()` never does this, because it skips blank lines.

## 9. Command line

```
python -m tiny program.tiny
```

- On success, prints each output value on its own line to stdout and exits with code 0.
- On a Tiny error, prints the error message to stderr and exits with code 1. Nothing is printed to stdout.
- Wrong arguments: prints usage to stderr and exits with code 2.
