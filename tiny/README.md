# Inside the `tiny` package

This file holds all the explanations for the code in `tiny/`. The source files themselves have no comments or docstrings.

Every line of a Tiny program goes through the same pipeline:

```
text ─► lexer ─► parser ─► optimizer ─► evaluator ─► output
        tokens   tree      simpler tree  integer
```

The language rules are defined in [../SPEC.md](../SPEC.md).

---

## `__init__.py`

The package entry point. It exports the public API, `run` and `TinyError`.

## `errors.py`

Every stage of the pipeline (lexer, parser, evaluator) reports problems the same way: by raising a `TinyError` whose message is exactly what the user should see, in the form `Line N: <message>`.

- **`TinyError`**: any error in a Tiny program, such as an unknown symbol, bad syntax, or a runtime problem like dividing by zero. `str(error)` is the full user-facing message, e.g. `Line 3: undefined variable 'x'`.
- **`tiny_error(line_no, message)`**: builds a `TinyError` with the standard `Line N: ` prefix. Callers write `raise tiny_error(line_no, "...")`, so the message format lives in exactly one place.

## `lexer.py`: one line of text → list of tokens

**Compiler concept: lexical analysis** (also called scanning or tokenizing). The lexer reads raw characters and groups them into meaningful units called tokens, like the number 42 or the name `total`. Later stages never look at characters again; they only see tokens. This keeps the parser simple: it doesn't need to know that `"007"` and `"7"` are the same number, or that spaces don't matter.

Token formats (tuples):

| Token | Meaning |
|---|---|
| `("NUM", int)` | non-negative integer literal; `"007"` becomes `("NUM", 7)` |
| `("NAME", str)` | variable name, e.g. `("NAME", "letter")` |
| `("KW", str)` | reserved keyword: `("KW", "let")` or `("KW", "print")` |
| `("OP", str)` | operator or symbol, one of `+ - * / ~ ( ) =` |

- **`DIGITS` and `LETTERS`** are ASCII only, on purpose. Python's `str.isdigit()` and `str.isalpha()` also accept characters like `²` and `é`, which are not part of Tiny.
- **`lex(line_text, line_no)`** scans left to right. At each position, the current character decides what kind of token starts there, and a helper reads the rest of that token. Whitespace only separates tokens; it is never a token itself. Any character that can't start a token raises `unknown symbol`.
- **`read_number(text, start)`** reads a run of digits and returns `(token, position just after the number)`. Python's `int()` is exact for any length of digit string, and `"007"` becomes 7.
- **`read_word(text, start)`** reads a name or keyword using **maximal munch**: it reads the longest possible word first, and only then checks whether the whole word is a keyword. That's why `letter` is a name and not the keyword `let` followed by `ter`.
- **`is_word_char(char)`**: true for characters allowed after the first character of a name (letters, digits, `_`).

## `parser.py`: tokens → statement tree

**Compiler concept: recursive-descent parsing.** The grammar has one function per precedence level. A lower-precedence function calls the next-higher one to read its operands, so higher-precedence operators get grouped first, deeper in the tree:

```
statement := "let" NAME "=" sum  |  "print" sum
sum       := average { ("+" | "-") average }     lowest precedence
average   := product { "~" product }
product   := atom { ("*" | "/") atom }
atom      := NUM | NAME | "(" sum ")"            highest precedence
```

Each `{ ... }` repetition is a `while` loop that folds the result into the LEFT operand (`left = ("bin", op, left, right)`), which makes every binary operator **left-associative**: `10 - 3 - 2` becomes `(10 - 3) - 2`.

Output formats (tuples):

- expressions: `("num", int)`, `("var", name)`, `("bin", op, left, right)`
- statements: `("let", name, expr)`, `("print", expr)`

Parentheses don't get a node of their own. They only change the shape of the tree, which is all they need to do.

- **`parse_line(tokens, line_no)`** parses one line's tokens into a statement tree. The whole line must be exactly one statement; leftover tokens are an error.
- **`token_text(token)`** gives a token's text for error messages, e.g. `("OP", "+")` → `"+"`. A NUM token holds an int, so its text is the number's decimal form without leading zeros (`"007"` shows as `"7"`).
- **`Parser`** walks through a list of tokens with a cursor (`pos`).
  - *Cursor helpers:* `peek()` looks at the current token without consuming it. `advance()` consumes it and moves on. Both return `None` once the cursor is past the last token. `at_operator(symbols)` is true if the current token is an OP whose symbol is in `symbols`. `error(message)` builds a `TinyError` for this line.
  - *Statements:* `parse_statement()` dispatches on the first keyword. `parse_let_rest()` parses the part of `let NAME = EXPR` after the `let` keyword. `expect_end_of_line()` raises `unexpected token` if anything is left over.
  - *Expressions, lowest precedence first:* `parse_sum()`, `parse_average()`, `parse_product()`, `parse_atom()`, each implementing the grammar rule above.
  - In `parse_atom()`, the parenthesized case calls back up to `parse_sum`, the LOWEST level. That recursion is what lets parentheses override precedence.

## `arithmetic.py`: Tiny's arithmetic rules

**Compiler concept: one source of truth for semantics.** The optimizer computes some results ahead of time (constant folding), and the evaluator computes the rest at run time. If the two disagreed about what `7 / 2` means, optimizing a program would change its output. Keeping the rules in one module means they can't drift apart.

All arithmetic is exact integer arithmetic. No floats are used anywhere, so results stay correct for numbers of any size.

- **`divide_toward_zero(a, b)`**: integer division that truncates toward zero. `b` must not be 0. Python's `//` rounds toward NEGATIVE INFINITY (`-7 // 2 == -4`), but Tiny rounds toward zero (`-7 / 2 == -3`). So it divides the magnitudes, which gives the right digits, and then puts the sign back.
- **`average_toward_zero(a, b)`**: the average of `a` and `b`, truncated toward zero: `5 ~ 2 == 3`, `-5 ~ 2 == -1`.
- **`apply_operator(op, left, right)`**: applies one Tiny binary operator to two integers. The caller must check for division by zero first, because only the caller knows the line number for the error message. The final `ValueError` can't happen for trees the parser builds, since it only ever produces the five operators.

## `optimizer.py`: expression tree → simpler expression tree

**Compiler concept: semantics-preserving tree rewriting.** An optimizer may change HOW a result is computed, but never WHAT the program does: not its output, and not its errors. Every rule here must hold for all possible variable values, including variables that are undefined.

Rules:

- **Constant folding:** an operator whose two sides are both numbers is replaced by its result, using Tiny's own `/` and `~` rules. A division by zero is never folded; it stays in the tree so the evaluator reports the error.
- **Identities:** `x * 1`, `1 * x`, `x + 0`, `0 + x` and `x - 0` all become `x`.
- **Deliberately NOT simplified:**
  - `0 - x` (it is −x, not x)
  - `x * 0` (becoming 0 would hide an `undefined variable` error for `x`)

The rewrite is **bottom-up**: children are optimized before their parent, so `x * (2 - 1)` first becomes `x * 1`, and then `x`.

- **`optimize(expr)`** returns a simplified tree that behaves exactly like `expr`. Numbers and variables are already as simple as they get, so only `bin` nodes are rewritten.
- **`simplify_identity(op, left, right)`** removes an operand that has no effect (multiply by 1, add or subtract 0). It returns the operator node unchanged if no identity rule applies.
- **`is_number`, `is_number_equal`, `is_division_by_zero`**: small predicates on tree nodes.

## `evaluator.py`: tree → integer, and the program driver

**Compiler concept: tree-walking interpretation with an environment.** `evaluate()` walks an expression tree recursively: a number is itself, a variable is looked up in the environment (a dict of name → value), and an operator node evaluates its left child, then its right child, then combines them. `run()` is the driver for the whole pipeline:

```
source text -> (per line) lex -> parse_line -> optimize -> evaluate
```

Each line goes through every stage before the next line is read, so errors are reported in the order a reader would hit them, top to bottom.

- **`evaluate(expr, env, line_no)`** computes the integer value of an expression tree. The left operand is evaluated fully before the right one, so when both sides contain errors, the left one is reported.
- **`run(source)`** runs a Tiny program and returns the printed values, in order. It raises `TinyError` at the first error, and when that happens nothing is returned, not even values printed before the error. It splits on `"\n"` only, because `str.splitlines()` would also split on characters like form feed, which would throw off the line numbers. Blank lines are skipped but still counted.
- **`execute(statement, env, outputs, line_no)`** carries out one statement, updating `env` (let) or `outputs` (print). Variables are immutable, and the "already defined" check must come BEFORE evaluating the right-hand side, so `let x = 1/0` on an existing `x` reports `already defined`, not `division by zero`.

## `__main__.py`: command line

`python -m tiny program.tiny` prints each output value on its own line. On a Tiny error, it prints the error message to stderr and exits with code 1. Wrong arguments print a usage line and exit with code 2.

Python 3.11+ refuses to print ints with more than 4300 digits by default. Tiny integers have no size limit, so `main` lifts that cap with `sys.set_int_max_str_digits(0)` before printing.
