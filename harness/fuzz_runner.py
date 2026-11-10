"""Run Tiny programs against ONE implementation, in its own process.

fuzz.py launches this script once per implementation and batch:

    python -I fuzz_runner.py <implementation_dir> <program_timeout_s> <max_timeouts>
        < programs.json  > results.json

stdin:  a JSON list of program source strings
stdout: a JSON list of results, one per program, in the same order:
    {"kind": "ok",    "value": [outputs]}       run() returned normally
    {"kind": "error", "value": "<message>"}     run() raised the implementation's TinyError
    {"kind": "crash", "value": "<ExceptionType>"} anything else (incl. RecursionError)
    {"kind": "timeout", "value": None}          ran longer than program_timeout_s
    {"kind": "skipped", "value": None}          not run: max_timeouts already reached

Each program gets its own time limit (a SIGALRM timer), so one infinite loop
costs only program_timeout_s instead of the whole batch. Once max_timeouts
programs have timed out, the candidate clearly hangs, so the rest are skipped.

Isolation: `-I` keeps the current directory, PYTHONPATH and user site-packages
off sys.path, and this script then puts <implementation_dir> first. After
importing, it checks that `tiny` really came from that folder and exits with
code 2 if not, so two implementations can never be confused.
"""

import json
import signal
import sys
import tempfile
from pathlib import Path

WRONG_PACKAGE_EXIT_CODE = 2


class ProgramTimeout(BaseException):
    """BaseException, so a candidate's `except Exception` can't swallow it."""


def on_alarm(signum, frame):
    raise ProgramTimeout()


def main():
    impl_dir = Path(sys.argv[1]).resolve()
    program_timeout = float(sys.argv[2])
    max_timeouts = int(sys.argv[3])
    programs = json.loads(sys.stdin.read())

    # Anything the implementation prints must not corrupt our JSON output.
    real_stdout = sys.stdout
    sys.stdout = sys.stderr

    # Tiny integers have no size limit; let json and str() handle any of them.
    if hasattr(sys, "set_int_max_str_digits"):
        sys.set_int_max_str_digits(0)

    # Compiled bytecode goes to a throwaway folder: never written into the
    # implementation's folder, and never a stale cache read back from it.
    sys.pycache_prefix = tempfile.mkdtemp(prefix="tiny-pycache-")
    sys.path.insert(0, str(impl_dir))
    try:
        import tiny
    except BaseException as error:  # e.g. a SyntaxError in an agent's edit
        results = [crash(error) for _ in programs]
    else:
        check_isolation(tiny, impl_dir)
        error_class = getattr(tiny, "TinyError", None)
        results = run_all(tiny, error_class, programs, program_timeout, max_timeouts)

    real_stdout.write(json.dumps(results))


def check_isolation(tiny, impl_dir):
    expected = impl_dir / "tiny"
    actual = Path(tiny.__file__).resolve().parent if getattr(tiny, "__file__", None) else None
    if actual != expected:
        print(f"isolation failure: imported tiny from {actual}, expected {expected}", file=sys.stderr)
        sys.exit(WRONG_PACKAGE_EXIT_CODE)


def run_all(tiny, error_class, programs, program_timeout, max_timeouts):
    can_time_out = hasattr(signal, "setitimer")  # not on Windows; fuzz.py's batch timeout still applies
    if can_time_out:
        signal.signal(signal.SIGALRM, on_alarm)
    results = []
    timeouts = 0
    for program in programs:
        if timeouts >= max_timeouts:
            results.append({"kind": "skipped", "value": None})
            continue
        result = run_one(tiny, error_class, program, program_timeout if can_time_out else 0)
        timeouts += result["kind"] == "timeout"
        results.append(result)
    return results


def run_one(tiny, error_class, program, timeout):
    try:
        if timeout:
            signal.setitimer(signal.ITIMER_REAL, timeout)
        try:
            outputs = tiny.run(program)
            return {"kind": "ok", "value": [normalize(value) for value in outputs]}
        finally:
            if timeout:
                signal.setitimer(signal.ITIMER_REAL, 0)
    except ProgramTimeout:
        return {"kind": "timeout", "value": None}
    except BaseException as error:
        if isinstance(error_class, type) and isinstance(error, error_class):
            return {"kind": "error", "value": str(error)}
        return crash(error)


def normalize(value):
    """Keep ints as ints. Anything else (a bug returning strings, say) becomes a
    tagged string, so it is JSON-safe and can never equal a real int."""
    if type(value) is int:
        return value
    return f"<{type(value).__name__}> {value!r}"


def crash(error):
    return {"kind": "crash", "value": type(error).__name__}


if __name__ == "__main__":
    main()
