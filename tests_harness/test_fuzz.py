"""Acceptance tests for harness/fuzz.py (separate from Tiny's own tests).

Run with:  pytest tests_harness
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from harness.fuzz import (
    FEATURES,
    FuzzerError,
    fuzz_compare,
    generate_programs,
    render_program,
)

ROOT = Path(__file__).resolve().parents[1]
BUG_IDS = sorted(path.name for path in (ROOT / "bugs").iterdir() if path.is_dir())
FUZZ_CLI = ROOT / "harness" / "fuzz.py"


def make_fake_implementation(folder, run_body):
    """A minimal tiny/ package whose run() executes `run_body`."""
    package = folder / "tiny"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "class TinyError(Exception):\n"
        "    pass\n\n"
        "def run(source):\n"
        f"    {run_body}\n"
    )
    return folder


def copy_correct_tiny(folder):
    shutil.copytree(ROOT / "tiny", folder / "tiny")
    return folder


# 1. Determinism --------------------------------------------------------------

def test_same_seed_gives_same_programs():
    first = [render_program(p) for p in generate_programs(500, seed=0)]
    second = [render_program(p) for p in generate_programs(500, seed=0)]
    assert first == second


def test_different_seed_gives_different_programs():
    assert [render_program(p) for p in generate_programs(50, seed=0)] != [
        render_program(p) for p in generate_programs(50, seed=1)
    ]


# 2. Correct vs. correct --------------------------------------------------------

def test_correct_vs_correct_has_no_mismatches():
    result = fuzz_compare(ROOT, ROOT)
    assert result.passed
    assert result.n_mismatches == 0
    assert result.mismatches == []
    assert result.counts["reference"] == result.counts["candidate"]


# 3. Detects every bug ----------------------------------------------------------

@pytest.mark.parametrize("bug_id", BUG_IDS)
def test_detects_every_bug(bug_id):
    result = fuzz_compare(ROOT, ROOT / "bugs" / bug_id, shrink=False)
    assert not result.passed
    assert result.n_mismatches > 0


def test_bug_05_is_caught_many_times():
    # The hand-written tests catch ~ grouping the wrong way only a few times;
    # the fuzzer should catch it far more often.
    result = fuzz_compare(ROOT, ROOT / "bugs" / "05", shrink=False)
    assert result.n_mismatches >= 50


# 4. Reference crash guard -------------------------------------------------------

def test_crashing_reference_raises(tmp_path):
    fake = make_fake_implementation(tmp_path / "fake", 'raise RuntimeError("boom")')
    with pytest.raises(FuzzerError, match="reference crash"):
        fuzz_compare(fake, ROOT, n=20)


# 5. Coverage -----------------------------------------------------------------

def test_coverage_has_no_gaps():
    result = fuzz_compare(ROOT, ROOT, n=2000)
    gaps = [feature for feature in FEATURES if result.coverage[feature] == 0]
    assert gaps == []


# 6. Isolation ----------------------------------------------------------------

def test_isolation_finds_difference_between_two_copies(tmp_path):
    same = copy_correct_tiny(tmp_path / "same")
    changed = copy_correct_tiny(tmp_path / "changed")
    arithmetic = changed / "tiny" / "arithmetic.py"
    text = arithmetic.read_text()
    assert text.count("return left + right") == 1
    arithmetic.write_text(text.replace("return left + right", "return left + right + 1"))

    assert fuzz_compare(ROOT, same, n=300).passed
    assert not fuzz_compare(same, changed, n=300, shrink=False).passed


def test_runner_imports_tiny_from_the_given_folder_only(tmp_path):
    # A folder with no tiny/ must not silently fall back to the repo's tiny.
    with pytest.raises(FuzzerError, match="does not contain a tiny/ package"):
        fuzz_compare(ROOT, tmp_path, n=10)


# Extra behavior ----------------------------------------------------------------

def test_hanging_candidate_is_marked_timeout(tmp_path):
    hang = make_fake_implementation(tmp_path / "hang", "while True: pass")
    result = fuzz_compare(ROOT, hang, n=6, batch_timeout=30, program_timeout=1)
    candidate = result.counts["candidate"]
    assert candidate["timeout"] == 3  # MAX_TIMEOUTS, then the rest are skipped
    assert candidate["skipped"] == 3
    assert not result.passed


def test_hang_in_some_programs_only(tmp_path):
    # Hangs only on the rare programs containing "$"; everything else runs.
    partial = make_fake_implementation(
        tmp_path / "partial",
        'import time\n    if "$" in source:\n        time.sleep(100)\n    return []',
    )
    result = fuzz_compare(ROOT, partial, n=300, program_timeout=0.5)
    assert result.counts["candidate"]["timeout"] >= 1
    assert result.counts["candidate"]["ok"] > 0


def test_candidate_with_syntax_error_counts_as_crash(tmp_path):
    broken = copy_correct_tiny(tmp_path / "broken")
    (broken / "tiny" / "parser.py").write_text("def broken(:\n")
    result = fuzz_compare(ROOT, broken, n=50, shrink=False)
    assert result.counts["candidate"]["crash"] == 50


def test_candidate_printing_does_not_break_results(tmp_path):
    noisy = copy_correct_tiny(tmp_path / "noisy")
    evaluator = noisy / "tiny" / "evaluator.py"
    text = evaluator.read_text()
    assert text.count("    env = {}\n") == 1
    evaluator.write_text(text.replace("    env = {}\n", "    print('debug!')\n    env = {}\n", 1))
    assert fuzz_compare(ROOT, noisy, n=200).passed


def test_shrinking_gives_a_short_program():
    result = fuzz_compare(ROOT, ROOT / "bugs" / "02", n=500)
    shrunk = result.mismatches[0]
    assert "original" in shrunk
    assert len(shrunk["program"].splitlines()) <= 2


def test_cli_exit_codes():
    same = subprocess.run([sys.executable, str(FUZZ_CLI), str(ROOT), str(ROOT), "--n", "200"],
                          capture_output=True, text=True)
    assert same.returncode == 0, same.stderr
    assert "PASS" in same.stdout

    different = subprocess.run([sys.executable, str(FUZZ_CLI), str(ROOT), str(ROOT / "bugs" / "05"),
                                "--n", "500"], capture_output=True, text=True)
    assert different.returncode == 1, different.stderr
    assert "Mismatch 1" in different.stdout
