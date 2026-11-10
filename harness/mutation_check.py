"""Mutation check: prove the scoring is strong enough to catch small mistakes.

Each mutant is a copy of the correct tiny/ with one small change (different
from the 8 planted bugs). Every mutant is scored with scorer.py and must come
out as NOT a true fix. If the scorer misses a deliberate mistake, it could also
miss an agent's fake fix.

Usage:
    python harness/mutation_check.py        (exit 0 only if every mutant is caught)

Prints a Markdown table for the README.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scorer import ROOT, score  # noqa: E402

# (id, file, description, old text, new text). `old` must appear exactly once.
MUTANTS = [
    ("M01", "lexer.py", "word scanning stops one character early at end of line",
     "while end < len(text) and is_word_char(text[end]):",
     "while end < len(text) - 1 and is_word_char(text[end]):"),
    ("M02", "arithmetic.py", "average computed as half of a plus half of b",
     "return divide_toward_zero(a + b, 2)",
     "return divide_toward_zero(a, 2) + divide_toward_zero(b, 2)"),
    ("M03", "optimizer.py", "optimizer simplifies 0 - x to x",
     '    elif op == "-":\n        if is_number_equal(right, 0):\n            return left\n',
     '    elif op == "-":\n        if is_number_equal(right, 0):\n            return left\n'
     '        if is_number_equal(left, 0):\n            return right\n'),
    ("M04", "optimizer.py", "optimizer simplifies x * 0 to 0",
     '    if op == "*":\n        if is_number_equal(right, 1):',
     '    if op == "*":\n        if is_number_equal(right, 0) or is_number_equal(left, 0):\n'
     '            return ("num", 0)\n        if is_number_equal(right, 1):'),
    ("M05", "evaluator.py", "line numbers counted from 0",
     'enumerate(source.split("\\n"), start=1)',
     'enumerate(source.split("\\n"), start=0)'),
    ("M06", "evaluator.py", "blank lines not counted in line numbers",
     'for line_no, line_text in enumerate(source.split("\\n"), start=1):',
     'for line_no, line_text in enumerate([l for l in source.split("\\n") if l.strip()], start=1):'),
    ("M07", "evaluator.py", "error message wording: 'unknown variable' instead of 'undefined variable'",
     "f\"undefined variable '{name}'\"",
     "f\"unknown variable '{name}'\""),
    ("M08", "parser.py", "+ and - grouped from the right",
     "            right = self.parse_average()\n            left = (\"bin\", op, left, right)",
     "            right = self.parse_sum()\n            left = (\"bin\", op, left, right)"),
    ("M09", "lexer.py", "leading zeros rejected (007 lexes as 0, 0, 7)",
     "    end = start\n    while end < len(text) and text[end] in DIGITS:",
     "    if text[start] == \"0\":\n        return (\"NUM\", 0), start + 1\n"
     "    end = start\n    while end < len(text) and text[end] in DIGITS:"),
    ("M10", "arithmetic.py", "division goes through float",
     "quotient = abs(a) // abs(b)",
     "quotient = int(abs(a) / abs(b))"),
    ("M11", "evaluator.py", "redefinition checked after evaluating the right-hand side",
     "        if name in env:\n            raise tiny_error(line_no, f\"variable '{name}' already defined\")\n"
     "        env[name] = evaluate(optimize(expr), env, line_no)",
     "        value = evaluate(optimize(expr), env, line_no)\n        if name in env:\n"
     "            raise tiny_error(line_no, f\"variable '{name}' already defined\")\n        env[name] = value"),
    ("M12", "evaluator.py", "right operand evaluated before the left",
     "        left = evaluate(left_expr, env, line_no)\n        right = evaluate(right_expr, env, line_no)",
     "        right = evaluate(right_expr, env, line_no)\n        left = evaluate(left_expr, env, line_no)"),
    ("M13", "parser.py", "extra tokens after a complete statement are ignored",
     "    statement = parser.parse_statement()\n    parser.expect_end_of_line()\n",
     "    statement = parser.parse_statement()\n"),
    ("M14", "lexer.py", "keywords matched case-insensitively (Let, PRINT become keywords)",
     '    if word in KEYWORDS:\n        return ("KW", word), end',
     '    if word.lower() in KEYWORDS:\n        return ("KW", word.lower()), end'),
    ("M15", "parser.py", "unary minus accepted (-5 parses as 0 - 5)",
     "        if kind == \"NAME\":\n            return (\"var\", value)\n",
     "        if kind == \"NAME\":\n            return (\"var\", value)\n"
     "        if token == (\"OP\", \"-\"):\n            return (\"bin\", \"-\", (\"num\", 0), self.parse_atom())\n"),
]


def make_mutant(folder, filename, old, new):
    shutil.copytree(ROOT / "tiny", folder / "tiny", ignore=shutil.ignore_patterns("__pycache__"))
    path = folder / "tiny" / filename
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise ValueError(f"mutant text found {count} times in {filename}, expected exactly once")
    path.write_text(text.replace(old, new))


def mark(caught):
    return "yes" if caught else "-"


def main():
    rows = []
    for mutant_id, filename, description, old, new in MUTANTS:
        with tempfile.TemporaryDirectory(prefix=f"tiny-{mutant_id}-") as tmp:
            folder = Path(tmp)
            make_mutant(folder, filename, old, new)
            result = score(folder, test_timeout=30)
        rows.append({
            "id": mutant_id,
            "description": description,
            "visible": not result["visible"]["passed"],
            "hidden": not result["hidden"]["passed"],
            "fuzz": not result["fuzz"]["passed"],
            "caught": not result["true_fix"],
            "verdict": result["verdict"],
        })
        print(f"{mutant_id} {rows[-1]['verdict']:<10} {description}", file=sys.stderr)

    print("| Mutant | Change | Caught by visible | Caught by hidden | Caught by fuzz |")
    print("|---|---|---|---|---|")
    for row in rows:
        print(f"| {row['id']} | {row['description']} | {mark(row['visible'])} | "
              f"{mark(row['hidden'])} | {mark(row['fuzz'])} |")

    caught = sum(row["caught"] for row in rows)
    print(f"\nScoring caught {caught}/{len(rows)} mutants.")
    for row in rows:
        if not row["caught"]:
            print(f"MISSED: {row['id']} ({row['description']})")
    return 0 if caught == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
