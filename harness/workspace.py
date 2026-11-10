"""Build the agent's working folder for one run.

The folder is a fresh temp directory OUTSIDE the repo, so the agent can never
reach git history, the answer key, or the correct code, even by accident.

It contains only:
    tiny/            the bug's copy of the code (what the agent fixes)
    tests/visible/   the tests the agent may run
    SPEC.md          only if setup["spec"] is on

It never contains: tests/hidden, bugs.json, the correct tiny/, verify_bugs.py,
the harness, or .git.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NO_CACHE = shutil.ignore_patterns("__pycache__", "*.pyc")


def make_workdir(bug_id, setup):
    bug_tiny = ROOT / "bugs" / bug_id / "tiny"
    if not bug_tiny.is_dir():
        raise ValueError(f"unknown bug id {bug_id!r}")

    workdir = Path(tempfile.mkdtemp(prefix=f"tiny-bug{bug_id}-")).resolve()
    if workdir.is_relative_to(ROOT.resolve()):
        shutil.rmtree(workdir)
        raise RuntimeError(f"temp folder {workdir} is inside the repo; set TMPDIR elsewhere")

    shutil.copytree(bug_tiny, workdir / "tiny", ignore=NO_CACHE)
    shutil.copytree(ROOT / "tests" / "visible", workdir / "tests" / "visible", ignore=NO_CACHE)
    if setup.get("spec", False):
        shutil.copy(ROOT / "SPEC.md", workdir / "SPEC.md")
    return workdir
