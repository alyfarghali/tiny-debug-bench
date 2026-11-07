"""Check that every bug in bugs.json is a valid planted bug.

For each bug, this checks that:
  1. bugs/<id>/tiny/ differs from the correct tiny/ in exactly the file
     listed in bugs.json,
  2. at least one visible test fails, and
  3. at least one hidden test fails.

Each bug is tested in a fresh temporary copy, so nothing here touches the
real tiny/ package.

Usage:
    python verify_bugs.py
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEST_TIMEOUT_SECONDS = 60


def changed_files(bug_package):
    """Names of .py files that differ between tiny/ and the bug's copy."""
    correct = {p.name: p.read_text() for p in (ROOT / "tiny").glob("*.py")}
    buggy = {p.name: p.read_text() for p in bug_package.glob("*.py")}
    names = sorted(set(correct) | set(buggy))
    return [name for name in names if correct.get(name) != buggy.get(name)]


def run_suite(package, suite):
    """Run one test suite against `package` and return (passed, failed)."""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        shutil.copytree(package, workspace / "tiny")
        shutil.copytree(ROOT / "tests", workspace / "tests")
        shutil.copy(ROOT / "pytest.ini", workspace / "pytest.ini")
        result = subprocess.run(
            [sys.executable, "-m", "pytest", f"tests/{suite}", "-q", "-p", "no:cacheprovider"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT_SECONDS,
        )
    summary = result.stdout.strip().splitlines()[-1]
    passed = re.search(r"(\d+) passed", summary)
    failed = re.search(r"(\d+) failed", summary)
    return (int(passed.group(1)) if passed else 0, int(failed.group(1)) if failed else 0)


def main():
    bugs = json.loads((ROOT / "bugs.json").read_text())
    all_ok = True

    _, base_visible_failed = run_suite(ROOT / "tiny", "visible")
    _, base_hidden_failed = run_suite(ROOT / "tiny", "hidden")
    baseline_ok = base_visible_failed == 0 and base_hidden_failed == 0
    print(f"Correct code: visible failed={base_visible_failed}, hidden failed={base_hidden_failed}  "
          f"{'OK' if baseline_ok else 'PROBLEM'}\n")
    all_ok &= baseline_ok

    print(f"{'bug':<4} {'difficulty':<10} {'file':<20} {'visible fail':>12} {'hidden fail':>12}  result")
    for bug in bugs:
        package = ROOT / "bugs" / bug["id"] / "tiny"
        problems = []

        changed = changed_files(package)
        expected = [Path(bug["file"]).name]
        if changed != expected:
            problems.append(f"changed files {changed}, expected {expected}")

        visible_passed, visible_failed = run_suite(package, "visible")
        hidden_passed, hidden_failed = run_suite(package, "hidden")
        if visible_failed == 0:
            problems.append("no visible test fails")
        if hidden_failed == 0:
            problems.append("no hidden test fails")

        visible = f"{visible_failed}/{visible_passed + visible_failed}"
        hidden = f"{hidden_failed}/{hidden_passed + hidden_failed}"
        result = "OK" if not problems else "PROBLEM: " + "; ".join(problems)
        print(f"{bug['id']:<4} {bug['difficulty']:<10} {bug['file']:<20} {visible:>12} {hidden:>12}  {result}")
        all_ok &= not problems

    print("\nAll bugs verified." if all_ok else "\nSome bugs failed verification.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
