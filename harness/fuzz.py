"""Differential fuzzer for Tiny.

Generates random Tiny programs, runs them through a reference implementation
and a candidate implementation, and reports every program where the two
disagree. scorer.py uses this as an independent check alongside the hidden
tests (which this file never uses).

Each implementation runs in its own subprocess (fuzz_runner.py). Both contain
a package named `tiny`, and importing both into one process would silently
test the same code twice.

Python API:
    fuzz_compare(reference_dir, candidate_dir, n=2000, seed=0) -> FuzzResult

Command line:
    python harness/fuzz.py <reference_dir> <candidate_dir> [--n 2000] [--seed 0]

A "dir" is any folder that contains a tiny/ package.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path

RUNNER = Path(__file__).resolve().parent / "fuzz_runner.py"

# Running
BATCH_SIZE = 500
BATCH_TIMEOUT_SECONDS = 60
PROGRAM_TIMEOUT_SECONDS = 5
MAX_REPORTED_MISMATCHES = 10
MAX_SHRUNK_MISMATCHES = 3
MAX_SHRINK_STEPS = 50
MAX_TIMEOUTS = 3  # per run_programs call; after this many, the rest are skipped
SKIPPED = {"kind": "skipped", "value": None}
HANG_KINDS = ("timeout", "skipped")

# Generation
MAX_DEPTH = 4
MAX_STATEMENTS = 6
ERROR_PROGRAM_RATE = 0.25
BLANK_LINE_RATE = 0.10
FORCED_PATTERN_RATE = 0.30
PAREN_RATE = 0.20
HUGE = 10**15

# Tricky names: start with a keyword, or are a keyword in another case.
NAME_POOL = ["x", "y", "z", "a1", "_t", "letter", "printer", "lets", "Let", "PRINT"]
TRICKY_NAMES = {"letter", "printer", "lets", "Let", "PRINT"}
OPERATORS = ["+", "-", "*", "/", "~"]
PRECEDENCE = {"+": 1, "-": 1, "~": 2, "*": 3, "/": 3}
OPTIMIZER_PATTERNS = ["x * 1", "1 * x", "x + 0", "0 + x", "x - 0", "0 - x", "x * 0"]
UNKNOWN_SYMBOLS = ["$", "@", "%", "#", "&", "^", ".", ","]
SOUP_TOKENS = [
    "let", "print", "x", "y", "letter", "0", "1", "7", "007",
    "+", "-", "*", "/", "~", "(", ")", "=",
]
ERROR_KINDS = [
    "undefined", "undefined in own let", "redefine", "divide by literal zero",
    "divide by runtime zero", "unknown symbol", "missing paren", "missing equals",
    "let without name", "extra tokens", "trailing operator", "not a statement",
    "keyword as name", "token soup", "two errors", "unary minus",
]

# The 10 Tiny error messages (after the "Line N: " prefix).
ERROR_TYPES = {
    "unknown symbol": r"unknown symbol '.+'",
    "unexpected token": r"unexpected token '.+'",
    "unexpected end of line": r"unexpected end of line",
    "expected ')'": r"expected '\)'",
    "expected 'let' or 'print'": r"expected 'let' or 'print'",
    "expected variable name": r"expected variable name after 'let'",
    "expected '='": r"expected '=' after variable name",
    "undefined variable": r"undefined variable '.+'",
    "already defined": r"variable '.+' already defined",
    "division by zero": r"division by zero",
}

FEATURES = (
    [f"op {op}" for op in OPERATORS]
    + [f"pair {parent} > {child}" for parent in OPERATORS for child in OPERATORS]
    + ["negative in /", "negative in ~"]
    + [f"optimizer {pattern}" for pattern in OPTIMIZER_PATTERNS]
    + [f"error {name}" for name in ERROR_TYPES]
    + ["huge number", "leading zeros", "blank lines", "tricky names"]
)


class FuzzerError(Exception):
    """A problem with the fuzzer or the reference, not with the candidate."""


@dataclass
class FuzzResult:
    passed: bool
    n_programs: int
    n_mismatches: int
    mismatches: list  # up to 10 of {"program", "expected", "got"} (+ "original" if shrunk)
    counts: dict  # {"reference": {kind: n}, "candidate": {kind: n}}
    coverage: dict  # {feature: number of programs containing it}


# ---------------------------------------------------------------------------
# Program representation
#
# The generator builds its own small trees and renders them to text. Rendering
# adds parentheses wherever precedence or left-associativity requires them, so
# the correct parser reads back exactly the tree that was generated.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Num:
    value: int
    text: str  # usually str(value); "007" for leading zeros
    paren: bool = False


@dataclass(frozen=True)
class Var:
    name: str
    paren: bool = False


@dataclass(frozen=True)
class Bin:
    op: str
    left: object
    right: object
    paren: bool = False


@dataclass(frozen=True)
class Stmt:
    kind: str  # "let", "print", "raw" (error line, fixed text) or "blank"
    name: str | None = None
    expr: object = None
    text: str = ""


def num(value):
    return Num(value, str(value))


def negative(n):
    """Tiny has no unary minus, so -n is written (0 - n)."""
    return Bin("-", num(0), num(n), paren=True)


def is_negative_literal(node):
    return (
        isinstance(node, Bin) and node.op == "-" and node.paren
        and is_num(node.left, 0) and isinstance(node.right, Num)
    )


def is_num(node, value):
    return isinstance(node, Num) and node.value == value


def render(node, parent_prec=0, side="left"):
    if isinstance(node, Num):
        text = node.text
    elif isinstance(node, Var):
        text = node.name
    else:
        prec = PRECEDENCE[node.op]
        text = f"{render(node.left, prec, 'left')} {node.op} {render(node.right, prec, 'right')}"
        # Lower precedence needs parens; so does an equal-precedence RIGHT
        # child, because every Tiny operator is left-associative.
        if prec < parent_prec or (side == "right" and prec == parent_prec):
            return f"({text})"
    return f"({text})" if node.paren else text


def render_statement(stmt):
    if stmt.kind == "let":
        return f"let {stmt.name} = {render(stmt.expr)}"
    if stmt.kind == "print":
        return f"print {render(stmt.expr)}"
    return stmt.text


def render_program(program):
    return "\n".join(render_statement(stmt) for stmt in program)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def generate_programs(n, seed):
    """The same (n, seed) always gives the same list of programs."""
    generator = ProgramGenerator(random.Random(seed))
    return [generator.program() for _ in range(n)]


class ProgramGenerator:
    """All randomness comes from the one `rng` passed in, never the global random."""

    def __init__(self, rng):
        self.rng = rng

    def coin(self, probability):
        return self.rng.random() < probability

    # ---- programs ----------------------------------------------------------

    def program(self):
        statements, defined_before = self.base_statements()
        if self.coin(ERROR_PROGRAM_RATE):
            statements = self.with_error(statements, defined_before)
        if self.coin(BLANK_LINE_RATE):
            statements = self.with_blank_lines(statements)
        return statements

    def base_statements(self):
        """Mostly lets, always ending with a print. Also returns, for each
        position, which names are defined before it."""
        count = self.rng.randint(1, MAX_STATEMENTS)
        statements, defined, defined_before = [], [], []
        for i in range(count):
            defined_before.append(list(defined))
            unused = [name for name in NAME_POOL if name not in defined]
            is_last = i == count - 1
            if not is_last and unused and self.coin(0.75):
                name = self.rng.choice(unused)
                statements.append(Stmt("let", name=name, expr=self.expression(defined)))
                defined.append(name)
            else:
                statements.append(Stmt("print", expr=self.expression(defined)))
        defined_before.append(list(defined))
        return statements, defined_before

    def with_error(self, statements, defined_before):
        """Insert an error at a random line, not always line 1."""
        position = self.rng.randint(0, len(statements))
        error = self.error_statements(defined_before[position])
        return statements[:position] + error + statements[position:]

    def with_blank_lines(self, statements):
        statements = list(statements)
        for _ in range(self.rng.randint(1, 2)):
            position = self.rng.randint(0, len(statements))
            statements.insert(position, Stmt("blank", text=self.rng.choice(["", "   ", "\t"])))
        return statements

    # ---- expressions -------------------------------------------------------

    def expression(self, defined):
        if self.coin(FORCED_PATTERN_RATE):
            return self.forced_pattern(defined)
        return self.random_expr(defined, MAX_DEPTH)

    def random_expr(self, defined, depth):
        if depth == 0 or self.coin(0.3):
            return self.leaf(defined)
        op = self.rng.choice(OPERATORS)
        left = self.random_expr(defined, depth - 1)
        if op == "/":
            right = self.divisor(defined, depth - 1)
        else:
            right = self.random_expr(defined, depth - 1)
        return Bin(op, left, right, paren=self.coin(PAREN_RATE))

    def divisor(self, defined, depth):
        """Usually a nonzero number. Random divisors are 0 so often that most
        programs would stop at 'division by zero' and test nothing else.
        Division by zero is still tested on purpose by forced patterns and
        error programs."""
        if self.coin(0.2):
            return self.random_expr(defined, depth)
        value = self.rng.choice([self.rng.randint(1, 20), self.rng.randint(1, 20), self.rng.randint(HUGE, 10**30 - 1)])
        node = negative(value) if self.coin(0.3) else num(value)
        return replace(node, paren=True) if self.coin(PAREN_RATE) else node

    def leaf(self, defined):
        if defined and self.coin(0.35):
            node = Var(self.rng.choice(defined))
        else:
            node = self.number()
        return replace(node, paren=True) if self.coin(PAREN_RATE) else node

    def number(self):
        roll = self.rng.random()
        if roll < 0.25:
            return negative(self.positive_value())
        if roll < 0.35:
            value = self.rng.randint(0, 20)
            return Num(value, "0" * self.rng.randint(1, 2) + str(value))
        return num(self.positive_value())

    def positive_value(self):
        roll = self.rng.random()
        if roll < 0.4:
            return self.rng.choice([0, 1, 2])  # optimizer rules, division by zero
        if roll < 0.9:
            return self.rng.randint(0, 20)
        return self.rng.randint(HUGE, 10**30 - 1)

    def small(self, defined):
        return self.random_expr(defined, 1)

    def forced_pattern(self, defined):
        """Shapes that target known weak spots."""
        kind = self.rng.choice(["chain", "chain", "mixed", "optimizer", "optimizer", "divide by zero"])

        if kind == "chain":  # associativity: a ~ b ~ c, a - b - c, a / b / c
            op = self.rng.choice(["~", "~", "-", "/", "+", "*"])
            node = self.small(defined)
            for _ in range(self.rng.randint(2, 3)):
                node = Bin(op, node, self.small(defined))
            return node

        if kind == "mixed":  # precedence: a + b ~ c * d  or  a * b ~ c + d
            a, b, c, d = (self.small(defined) for _ in range(4))
            sum_op = self.rng.choice(["+", "-"])
            product_op = self.rng.choice(["*", "/"])
            if self.coin(0.5):
                return Bin(sum_op, a, Bin("~", b, Bin(product_op, c, d)))
            return Bin(sum_op, Bin("~", Bin(product_op, a, b), c), d)

        if kind == "optimizer":
            pattern = self.rng.choice(OPTIMIZER_PATTERNS)
            return optimizer_shape(pattern, self.random_expr(defined, 2))

        k = self.rng.randint(0, 9)  # division by 0 or by an expression equal to 0
        denominator = self.rng.choice([num(0), Bin("-", num(k), num(k))])
        return Bin("/", self.small(defined), denominator)

    # ---- error programs ----------------------------------------------------

    def error_statements(self, defined):
        kind = self.rng.choice(ERROR_KINDS)
        unused = [name for name in NAME_POOL if name not in defined] or ["q"]
        fresh = self.rng.choice(unused)
        expr = self.random_expr(defined, 2)
        text = render(expr)

        if kind == "redefine" and not defined:
            kind = "undefined"

        if kind == "undefined":
            use = self.rng.choice([
                Var(fresh),
                Bin(self.rng.choice(OPERATORS), expr, Var(fresh)),
                Bin("*", Var(fresh), num(0)),  # the optimizer must not hide this
            ])
            return [Stmt("print", expr=use)]
        if kind == "undefined in own let":
            return [Stmt("let", name=fresh, expr=Bin(self.rng.choice(OPERATORS), Var(fresh), expr))]
        if kind == "redefine":
            name = self.rng.choice(defined)
            rhs = self.rng.choice([expr, Bin("/", expr, num(0)), Var(fresh)])  # checked before the rhs
            return [Stmt("let", name=name, expr=rhs)]
        if kind == "divide by literal zero":
            return [Stmt("print", expr=Bin("/", expr, num(0)))]
        if kind == "divide by runtime zero":
            k = self.rng.randint(0, 9)
            return [
                Stmt("let", name=fresh, expr=Bin("-", num(k), num(k))),
                Stmt("print", expr=Bin("/", expr, Var(fresh))),
            ]
        if kind == "unknown symbol":
            line = f"print {text}"
            cut = self.rng.randint(0, len(line))
            return [raw(line[:cut] + self.rng.choice(UNKNOWN_SYMBOLS) + line[cut:])]
        if kind == "missing paren":
            return [raw(f"print ({text}")]
        if kind == "missing equals":
            return [raw(f"let {fresh} {text}")]
        if kind == "let without name":
            return [raw(f"let = {text}")]
        if kind == "extra tokens":
            return [raw(f"print {text} {self.rng.choice(['5', ')', '(', 'x', '=', 'print'])}")]
        if kind == "trailing operator":
            return [raw(f"print {text} {self.rng.choice(OPERATORS)}")]
        if kind == "not a statement":
            return [raw(self.rng.choice([text, f"{fresh} = {text}"]))]
        if kind == "keyword as name":
            return [raw(f"let {self.rng.choice(['let', 'print'])} = {text}")]
        if kind == "two errors":  # which side is evaluated first decides the error
            failures = [Var(fresh), Bin("/", self.small(defined), num(0))]
            self.rng.shuffle(failures)
            return [Stmt("print", expr=Bin(self.rng.choice(OPERATORS), failures[0], failures[1]))]
        if kind == "unary minus":  # Tiny has none: "-5" must be an error
            value = self.rng.randint(0, 20)
            return [raw(self.rng.choice([f"print -{value}", f"print {text} * -{value}",
                                         f"let {fresh} = -{value}"]))]
        # token soup: random valid tokens, to find parser crashes
        count = self.rng.randint(1, 8)
        return [raw(" ".join(self.rng.choice(SOUP_TOKENS) for _ in range(count)))]


def raw(text):
    return Stmt("raw", text=text)


def optimizer_shape(pattern, x):
    shapes = {
        "x * 1": Bin("*", x, num(1)),
        "1 * x": Bin("*", num(1), x),
        "x + 0": Bin("+", x, num(0)),
        "0 + x": Bin("+", num(0), x),
        "x - 0": Bin("-", x, num(0)),
        "0 - x": Bin("-", num(0), x),
        "x * 0": Bin("*", x, num(0)),
    }
    return shapes[pattern]


# ---------------------------------------------------------------------------
# Running implementations
# ---------------------------------------------------------------------------

def run_programs(impl_dir, texts, batch_timeout=BATCH_TIMEOUT_SECONDS,
                 program_timeout=PROGRAM_TIMEOUT_SECONDS):
    """Run every program against one implementation, in batches of subprocesses.

    The runner times each program itself. After MAX_TIMEOUTS timeouts in this
    call, the implementation clearly hangs, so the remaining programs are
    marked "skipped" instead of each waiting out its own timeout.
    """
    results = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        budget = MAX_TIMEOUTS - sum(r["kind"] == "timeout" for r in results)
        if budget <= 0:
            results.extend(SKIPPED for _ in batch)
            continue
        try:
            results.extend(run_batch(impl_dir, batch, batch_timeout, program_timeout, budget))
        except subprocess.TimeoutExpired:
            # Backstop for hangs the runner's own timer can't interrupt.
            results.extend(run_one_at_a_time(impl_dir, batch, program_timeout, budget))
    return results


def run_one_at_a_time(impl_dir, texts, timeout, budget):
    results = []
    for text in texts:
        if sum(r["kind"] == "timeout" for r in results) >= budget:
            results.append(SKIPPED)
            continue
        try:
            results.extend(run_batch(impl_dir, [text], timeout + 5, timeout, 1))
        except subprocess.TimeoutExpired:
            results.append({"kind": "timeout", "value": None})
    return results


def run_batch(impl_dir, texts, timeout, program_timeout, max_timeouts):
    completed = subprocess.run(
        [sys.executable, "-I", str(RUNNER), str(Path(impl_dir).resolve()),
         str(program_timeout), str(max_timeouts)],
        input=json.dumps(texts),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        raise FuzzerError(f"runner failed for {impl_dir}:\n{completed.stderr[-2000:]}")
    results = json.loads(completed.stdout)
    if len(results) != len(texts):
        raise FuzzerError(f"runner returned {len(results)} results for {len(texts)} programs")
    return results


def check_reference(results, texts):
    for result, text in zip(results, texts):
        if result["kind"] in ("crash",) + HANG_KINDS:
            raise FuzzerError(
                f"reference {result['kind']} ({result['value']}) on program:\n{text}\n"
                "This is a fuzzer or reference bug, not a candidate bug."
            )


def check_implementation_dir(path):
    if not (Path(path) / "tiny" / "__init__.py").is_file():
        raise FuzzerError(f"{path} does not contain a tiny/ package")


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def fuzz_compare(reference_dir, candidate_dir, n=2000, seed=0, shrink=True,
                 batch_timeout=BATCH_TIMEOUT_SECONDS, program_timeout=PROGRAM_TIMEOUT_SECONDS):
    """Run n random programs on both implementations and report differences.

    Two results match only if both kind and value are identical.
    Raises FuzzerError if the reference itself crashes or times out.
    """
    check_implementation_dir(reference_dir)
    check_implementation_dir(candidate_dir)
    timeouts = {"batch_timeout": batch_timeout, "program_timeout": program_timeout}

    programs = generate_programs(n, seed)
    texts = [render_program(program) for program in programs]  # same list for both sides

    reference = run_programs(reference_dir, texts, **timeouts)
    check_reference(reference, texts)
    candidate = run_programs(candidate_dir, texts, **timeouts)

    mismatch_indexes = [i for i in range(n) if reference[i] != candidate[i]]
    mismatches = []
    for rank, i in enumerate(mismatch_indexes[:MAX_REPORTED_MISMATCHES]):
        report = {"program": texts[i], "expected": reference[i], "got": candidate[i]}
        # Hangs aren't shrunk: every shrinking step would wait out a timeout.
        if shrink and rank < MAX_SHRUNK_MISMATCHES and candidate[i]["kind"] not in HANG_KINDS:
            small, expected, got = shrink_program(programs[i], reference_dir, candidate_dir, timeouts)
            if render_program(small) != texts[i]:
                report = {"program": render_program(small), "expected": expected,
                          "got": got, "original": texts[i]}
        mismatches.append(report)

    return FuzzResult(
        passed=not mismatch_indexes,
        n_programs=n,
        n_mismatches=len(mismatch_indexes),
        mismatches=mismatches,
        counts={"reference": count_kinds(reference), "candidate": count_kinds(candidate)},
        coverage=compute_coverage(programs, reference),
    )


def count_kinds(results):
    counts = {"ok": 0, "error": 0, "crash": 0, "timeout": 0, "skipped": 0}
    for result in results:
        counts[result["kind"]] += 1
    return counts


# ---------------------------------------------------------------------------
# Shrinking: make a mismatching program smaller while it still mismatches.
# ---------------------------------------------------------------------------

def shrink_program(program, reference_dir, candidate_dir, timeouts):
    """Greedy shrinking. Each step tries every one-step-smaller version in a
    single batch and keeps the first that still mismatches."""
    current = program
    current_text = render_program(current)
    expected = got = None
    for _ in range(MAX_SHRINK_STEPS):
        candidates = [c for c in shrink_candidates(current) if len(render_program(c)) < len(current_text)]
        if not candidates:
            break
        texts = [render_program(c) for c in candidates]
        reference = run_programs(reference_dir, texts, **timeouts)
        check_reference(reference, texts)
        candidate = run_programs(candidate_dir, texts, **timeouts)
        for smaller, text, ref, cand in zip(candidates, texts, reference, candidate):
            if ref != cand and cand["kind"] not in HANG_KINDS:
                current, current_text, expected, got = smaller, text, ref, cand
                break
        else:
            break

    if expected is None:  # nothing shrank; report the original's results
        [expected] = run_programs(reference_dir, [current_text], **timeouts)
        [got] = run_programs(candidate_dir, [current_text], **timeouts)
    return current, expected, got


def shrink_candidates(program):
    # 1. Delete one statement.
    if len(program) > 1:
        for i in range(len(program)):
            yield program[:i] + program[i + 1:]
    # 2. Simplify one subexpression.
    for i, stmt in enumerate(program):
        if stmt.expr is not None:
            for smaller in expr_reductions(stmt.expr):
                yield program[:i] + [replace(stmt, expr=smaller)] + program[i + 1:]


def expr_reductions(node):
    """Every expression one step simpler than `node`."""
    if isinstance(node, Bin):
        yield node.left
        yield node.right
        yield num(0)
        yield num(1)
        if node.paren:
            yield replace(node, paren=False)
        for left in expr_reductions(node.left):
            yield replace(node, left=left)
        for right in expr_reductions(node.right):
            yield replace(node, right=right)
    elif node.paren:
        yield replace(node, paren=False)
    elif isinstance(node, Num) and node.text not in ("0", "1"):
        yield num(0)
        yield num(1)


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------

def compute_coverage(programs, reference_results):
    """How many programs contain each feature. A zero means a generator gap."""
    coverage = {feature: 0 for feature in FEATURES}
    for program, result in zip(programs, reference_results):
        for feature in program_features(program, result):
            coverage[feature] += 1
    return coverage


def program_features(program, reference_result):
    found = set()
    for stmt in program:
        if stmt.kind == "blank":
            found.add("blank lines")
        if stmt.kind == "let" and stmt.name in TRICKY_NAMES:
            found.add("tricky names")
        if stmt.expr is not None:
            add_expr_features(stmt.expr, found)
    if reference_result["kind"] == "error":
        error_type = classify_error(reference_result["value"])
        if error_type:
            found.add(f"error {error_type}")
    return found


def add_expr_features(node, found):
    if isinstance(node, Num):
        if node.value >= HUGE:
            found.add("huge number")
        if len(node.text) > 1 and node.text.startswith("0"):
            found.add("leading zeros")
        return
    if isinstance(node, Var):
        if node.name in TRICKY_NAMES:
            found.add("tricky names")
        return

    found.add(f"op {node.op}")
    for child in (node.left, node.right):
        if isinstance(child, Bin):
            found.add(f"pair {node.op} > {child.op}")
    if node.op in ("/", "~") and (is_negative_literal(node.left) or is_negative_literal(node.right)):
        found.add(f"negative in {node.op}")
    pattern = optimizer_pattern(node)
    if pattern:
        found.add(f"optimizer {pattern}")
    add_expr_features(node.left, found)
    add_expr_features(node.right, found)


def optimizer_pattern(node):
    op, left, right = node.op, node.left, node.right
    if op == "*" and (is_num(left, 0) or is_num(right, 0)):
        return "x * 0"
    if op == "*" and is_num(right, 1):
        return "x * 1"
    if op == "*" and is_num(left, 1):
        return "1 * x"
    if op == "+" and is_num(right, 0):
        return "x + 0"
    if op == "+" and is_num(left, 0):
        return "0 + x"
    if op == "-" and is_num(right, 0):
        return "x - 0"
    if op == "-" and is_num(left, 0) and not is_negative_literal(node):
        return "0 - x"
    return None


def classify_error(message):
    match = re.fullmatch(r"Line \d+: (.*)", message, re.DOTALL)
    if not match:
        return None
    for name, pattern in ERROR_TYPES.items():
        if re.fullmatch(pattern, match.group(1), re.DOTALL):
            return name
    return None


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def describe(result):
    if result["kind"] in HANG_KINDS:
        return result["kind"]
    return f"{result['kind']}: {result['value']}"


def print_report(result, reference_dir, candidate_dir):
    print(f"Reference: {reference_dir}")
    print(f"Candidate: {candidate_dir}")
    print(f"Programs:  {result.n_programs}")
    print(f"Mismatches: {result.n_mismatches}\n")

    print(f"{'outcome':<10}{'reference':>11}{'candidate':>11}")
    for kind in ("ok", "error", "crash", "timeout", "skipped"):
        print(f"{kind:<10}{result.counts['reference'][kind]:>11}{result.counts['candidate'][kind]:>11}")

    gaps = [feature for feature, count in result.coverage.items() if count == 0]
    print(f"\nCoverage ({len(FEATURES) - len(gaps)}/{len(FEATURES)} features seen):")
    for feature, count in result.coverage.items():
        print(f"  {feature:<34}{count:>6}{'   <-- GAP' if count == 0 else ''}")

    for number, mismatch in enumerate(result.mismatches[:3], start=1):
        print(f"\n--- Mismatch {number}{' (shrunk)' if 'original' in mismatch else ''}")
        print(mismatch["program"])
        print(f"expected  {describe(mismatch['expected'])}")
        print(f"got       {describe(mismatch['got'])}")

    print("\nPASS: no differences found." if result.passed else "\nFAIL: implementations differ.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Differential fuzzer for Tiny.")
    parser.add_argument("reference_dir")
    parser.add_argument("candidate_dir")
    parser.add_argument("--n", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    result = fuzz_compare(args.reference_dir, args.candidate_dir, n=args.n, seed=args.seed)
    print_report(result, args.reference_dir, args.candidate_dir)
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
