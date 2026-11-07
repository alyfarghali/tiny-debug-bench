# Tiny

Tiny is a small, made-up programming language written in plain Python with no dependencies. It's the codebase for a research project: bugs will be planted in it to test whether an AI agent can fix code it has never seen. Because the language is invented, the model can't have memorized it.

The full language definition is in [SPEC.md](SPEC.md).

```
let width = 12
let area = width * 5
print area            # prints 60
print 2 + 6 ~ 2 * 2   # prints 7  (~ is "average", truncated toward zero)
print (0 - 7) / 2     # prints -3 (division truncates toward zero)
```

(The `#` notes are only for this README. Tiny has no comments.)

## How it works

Each line of a program goes through four stages:

```
text ─► lexer ─► parser ─► optimizer ─► evaluator ─► output
        tokens   tree      simpler tree  integer
```

| File | Role |
|---|---|
| `tiny/lexer.py` | Splits a line into tokens |
| `tiny/parser.py` | Builds an expression tree (recursive descent) |
| `tiny/optimizer.py` | Folds constants and removes `* 1`, `+ 0`, `- 0` |
| `tiny/evaluator.py` | Computes values; `run()` drives the whole pipeline |
| `tiny/arithmetic.py` | Tiny's `/` and `~` rules, shared by optimizer and evaluator |
| `tiny/errors.py` | `TinyError` and the `Line N: ...` message format |

The source files have no comments. A walkthrough of each file and the compiler concept it implements is in [tiny/README.md](tiny/README.md).

## Running a program

Requires Python 3.10+.

```bash
python -m tiny examples/basics.tiny
```

From Python:

```python
from tiny import run, TinyError
run("let x = 5\nprint x * 2")   # [10]
```

## Running the tests

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest tests/visible    # ~15 basic tests
pytest tests/hidden     # thorough suite: every rule and edge case
pytest                  # both
```

The visible tests are the ones an agent will be allowed to see and run. The hidden tests are used to score whether a fix is actually correct.

## Other files

- `examples/`: three sample programs (`basics`, `rounding`, `big_numbers`)
- `check_setup.py`: checks the Gemini API key used by the (not yet built) agent
