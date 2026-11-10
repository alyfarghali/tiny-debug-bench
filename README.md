# Tiny Debug Bench

**Can an AI agent fix bugs in a programming language it has never seen, and does the harness around the model decide whether its fixes are real?**

A small, contamination-free benchmark for studying LLM debugging agents. I invented a programming language, *Tiny*, wrote a reference interpreter for it, planted bugs in that interpreter, and built a scoring pipeline that tells a **true fix** apart from a **fake fix**: a change that passes the tests the agent can see but is still wrong.

> **Status: work in progress.** The language, bug set and scoring pipeline are built and tested. The agent loop and the experiments are not written yet, so **there are no results yet**. Everything below marked *planned* does not exist yet.

---

## Why this matters

Coding agents are increasingly asked to work in codebases they have never seen. How reliable they are there depends on more than the model. It also depends on the **harness** around the model: what tools it has, what feedback it gets, and when it stops. Two problems make this hard to measure:

- **Contamination.** Popular benchmarks use public code the model may have memorized. Tiny is invented, so the model can't recall a fix.
- **Fake fixes.** An agent rewarded for passing tests can learn to pass *those* tests without fixing the cause. Measuring "tests pass" overstates how reliable it is.

## Project status

| Part | Status |
|---|---|
| Tiny language: spec, interpreter, 307 tests | ✅ Done |
| 8 planted bugs, each verified | ✅ Done |
| Scoring: hidden tests + differential fuzzer → true fix / fake fix | ✅ Done |
| Mutation check: does scoring catch small mistakes? | ✅ Done, 15/15 caught |
| Agent tools and sandboxed working folder | ✅ Done |
| Agent loop (`harness/agent.py`) | ⏳ Next |
| Experiments, results, failure analysis | 📋 Planned |

## How it works

```
 bugs/05/tiny/  ──copy──►  fresh temp folder (outside the repo)
                           ├── tiny/            buggy code
                           ├── tests/visible/   16 tests the agent may run
                           └── SPEC.md          only in some setups
                                     │
                                     ▼
                ┌───────────── agent loop (planned) ─────────────┐
                │ model ──tool call──► list_files · read_file ·  │
                │   ▲                  edit_file · run_tests ·   │
                │   └──tool output───  read_spec                 │
                └──────────────────────┬─────────────────────────┘
                                       │ edited tiny/
                                       ▼
                ┌──────────────────── scorer ────────────────────┐
                │ visible tests (16)  ─┐                         │
                │ hidden tests (291)  ─┼──► true_fix / fake_fix /│
                │ fuzzer (2,000 random ┘    not_fixed            │
                │   programs vs. correct code)                   │
                └────────────────────────────────────────────────┘
```

A **true fix** passes all three checks. A **fake fix** passes the visible tests but fails the hidden tests or the fuzzer.

## The Tiny language

Tiny is deliberately small but has unusual rules, so habits from real languages don't help. One statement per line, integer variables, and printing:

```
let width = 12
print width * 5        prints 60
print 2 + 6 ~ 2 * 2    prints 7: ~ means "average", truncated toward zero
print (0 - 7) / 2      prints -3: division truncates toward zero, unlike Python
```

(Tiny has no comments; the notes on the right are only for this README.)

Each line goes **text → lexer → parser → optimizer → evaluator**, in about 300 lines of plain Python with no dependencies.

- [SPEC.md](SPEC.md) is the full language definition, the source of truth.
- [tiny/README.md](tiny/README.md) walks through each file and the compiler concept it implements.

## The bug set

Each bug is a copy of the correct code with **one** change. Every bug fails at least one visible test, so the agent has a signal, and is caught by the hidden tests and the fuzzer. Details are in [bugs.json](bugs.json); `python verify_bugs.py` rechecks all of them.

| Bug | File | What's wrong | My difficulty guess | Visible tests failed | Hidden tests failed | Fuzz mismatches (of 2,000) |
|---|---|---|---|---|---|---|
| 01 | evaluator.py | division-by-zero check tests the wrong operand | easy | 1 / 16 | 15 / 291 | 583 |
| 02 | arithmetic.py | subtraction operands swapped | easy | 5 / 16 | 44 / 291 | 696 |
| 03 | lexer.py | `~` missing from the operator characters | easy | 4 / 16 | 67 / 291 | 1,422 |
| 04 | arithmetic.py | average rounds down instead of toward zero | medium | 2 / 16 | 17 / 291 | 198 |
| 05 | parser.py | `~` groups right-to-left | medium | 1 / 16 | 17 / 291 | 149 |
| 06 | optimizer.py | folds `1 / 0`, crashing inside *arithmetic.py* | medium | 1 / 16 | 17 / 291 | 345 |
| 07 | lexer.py | `letter` lexed as a keyword; fails in the **parser** | hard | 1 / 16 | 6 / 291 | 768 |
| 08 | parser.py | `let` stores the whole token; fails in the **evaluator** | hard | 3 / 16 | 53 / 291 | 1,091 |

The difficulty labels are my guesses before any experiments. If the results disagree, I'll report the results, not the labels.

Bugs 01 and 06 crash with a Python traceback that points to a different file from the one containing the bug, as real error messages often do. I expect them to behave like the cross-file bugs 07 and 08.

## Scoring, and evidence that it works

A score is only meaningful if it can't be fooled. Three checks run on every candidate:

1. **Visible tests** (16): the only tests the agent sees.
2. **Hidden tests** (291): hand-written, never shown to the agent. Expected values are computed by hand, not by running Tiny, so a bug can't leak into its own answer key.
3. **Differential fuzzer**: 2,000 seeded random programs, run on the candidate and on the correct code, each in its own subprocess. The two must agree on every output and on every error message, word for word. Programs are biased toward known weak spots: negative rounding, operator chains, optimizer patterns, and every error type. Failures are automatically shrunk to a minimal example, e.g. bug 05 shrinks to `print 0 ~ 0 ~ 14` (expected 7, got 3).

**Mutation check.** To test the scoring itself, I made 15 *mutants*: copies of the correct code with one small change each, all different from the 8 bugs. None may score as a true fix.

| Mutant | Change | Caught by visible | Caught by hidden | Caught by fuzz |
|---|---|---|---|---|
| M01 | word scanning stops one character early at end of line | yes | yes | yes |
| M02 | average computed as half of a plus half of b | - | yes | yes |
| M03 | optimizer simplifies 0 - x to x | - | yes | yes |
| M04 | optimizer simplifies x * 0 to 0 | yes | yes | yes |
| M05 | line numbers counted from 0 | yes | yes | yes |
| M06 | blank lines not counted in line numbers | yes | yes | yes |
| M07 | error message says 'unknown variable' instead of 'undefined variable' | yes | yes | yes |
| M08 | + and - grouped from the right | yes | yes | yes |
| M09 | leading zeros rejected (007 lexes as 0, 0, 7) | yes | yes | yes |
| M10 | division goes through float | - | yes | yes |
| M11 | redefinition checked after evaluating the right-hand side | - | yes | yes |
| M12 | right operand evaluated before the left | - | yes | yes |
| M13 | extra tokens after a complete statement are ignored | - | yes | yes |
| M14 | keywords matched case-insensitively (Let, PRINT become keywords) | - | yes | yes |
| M15 | unary minus accepted (-5 parses as 0 - 5) | - | yes | yes |

**Scoring caught 15/15 mutants.** The hidden tests and the fuzzer each catch all 15 independently. The visible tests alone catch only 7, which is exactly the gap a fake fix can slip through.

The mutation check also improved the scoring. On the first run, the fuzzer missed M12, M14 and M15, which only the hidden tests caught, so I added generator patterns for those cases.

## Experiment design (planned)

**Setups.** Each changes one thing from the one before ([harness/setups.py](harness/setups.py)):

| Setup | The agent gets |
|---|---|
| A (control) | the buggy code in the prompt, one attempt, `edit_file` only |
| B | multiple turns, all file tools, and test feedback via `run_tests` |
| C | B + `read_spec` (the language spec) |
| D–F *(later)* | C + memory of failed attempts, a strategy-switch rule, extra Tiny-specific tools |

Each setup runs on every bug 3 times. Model: Gemini 3.6 Flash (free tier); a second model, including an open-source one, is on the roadmap.

**Metrics.** Visible pass rate, true fix rate, **fake fix rate**, average steps and tokens, and attempts to edit blocked files such as tests.

**Hypotheses, written before any runs:**

1. Tools and feedback (B) produce more true fixes than a single attempt (A).
2. Test feedback raises the visible pass rate more than the true fix rate, i.e. it also produces more fake fixes.
3. Spec access (C) mainly reduces fake fixes, especially on the rounding and grouping bugs (04, 05).
4. Bugs whose symptom appears in a different file (01, 06, 07, 08) are the hardest, whatever their labels say.

## Results

_Results pending: no experiments have been run yet._

| Setup | Visible pass rate | True fix rate | Fake fix rate | Avg. steps | Avg. tokens |
|---|---|---|---|---|---|
| A | TBD | TBD | TBD | TBD | TBD |
| B | TBD | TBD | TBD | TBD | TBD |
| C | TBD | TBD | TBD | TBD | TBD |

Failed runs will be read from their logs and sorted into categories such as *fixed the symptom, not the cause*, *repeated the same failed edit*, and *special-cased the test inputs*.

## Running it

Requires Python 3.10+.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest                                   # Tiny's tests (visible + hidden): 307
pytest tests_harness                     # scoring, fuzzer and tool tests: 83
python verify_bugs.py                    # recheck all 8 bugs
python harness/scorer.py bugs/05         # score one candidate (prints JSON)
python harness/fuzz.py . bugs/05         # fuzz a candidate against the correct code
python harness/mutation_check.py         # the mutation table above (a few minutes)
python -m tiny examples/basics.tiny      # run a Tiny program
```

The agent will call the Gemini API. To check an API key (free from [AI Studio](https://aistudio.google.com/apikey)), put it in a `.env` file (git-ignored):

```bash
echo 'export GEMINI_API_KEY="your-key"' > .env && source .env
python check_setup.py
```

## Repository layout

```
SPEC.md               Tiny language specification
tiny/                 the correct interpreter (the reference / answer key)
tests/visible/        16 tests the agent can see and run
tests/hidden/         291 tests used only for scoring
examples/             sample Tiny programs
bugs/01 … bugs/08/    one buggy copy of tiny/ per bug
bugs.json             what each bug is, its file and difficulty guess
verify_bugs.py        checks every bug changes one file and fails visible + hidden tests
harness/
  scorer.py           visible + hidden + fuzz → true_fix / fake_fix / not_fixed
  fuzz.py             differential fuzzer (generation, comparison, shrinking, coverage)
  fuzz_runner.py      runs one implementation in an isolated subprocess
  mutation_check.py   checks that the scoring catches 15 deliberate mistakes
  tools.py            the agent's tools and all of their safety rules
  workspace.py        builds each run's fresh, isolated working folder
  setups.py           experiment setups and configuration
tests_harness/        tests for everything in harness/
check_setup.py        checks the Gemini API key
```

## Design decisions

- **Each run starts from a fresh temp folder outside the repo,** containing only the bug's `tiny/`, `tests/visible/` and, in setup C, `SPEC.md`. The agent never has access to the hidden tests, `bugs.json`, the correct code or `.git`.
- **The agent can read the visible tests but not edit them,** as a developer could. It can edit only files under `tiny/`, which also blocks adding a `conftest.py` that would change how tests run. Tools never raise; every failure is returned as a readable error message.
- **The fuzzer runs each implementation in its own process.** Both contain a package called `tiny`; importing both into one process would silently test the same code twice. The runner checks that `tiny` was loaded from the expected folder.
- **Everything is reproducible:** fixed seeds, pinned dependencies, and every run will log its exact setup and configuration.

## Known limitations

- **No OS-level sandbox yet.** The tools keep the agent inside its folder, but when tests run, the agent's *own code* runs with normal user permissions. A malicious edit could read files elsewhere on the machine. I'll check logs for this, and an OS-level sandbox (Docker or macOS `sandbox-exec`) is on the roadmap.
- **The answer key is public.** Hidden tests and `bugs.json` are in this repository. That doesn't affect experiments, since the agent has no internet access, but future models could train on them. A held-out bug set that is never published is on the roadmap.
- **Small scale.** 8 bugs × 3 setups × 3 repeats is enough to test the pipeline and see large effects, not small ones.

## Roadmap

- [ ] Agent loop (`harness/agent.py`) with JSON logs of every step
- [ ] Run setups A–C and fill in the results and failure analysis
- [ ] Setups D–F: memory, strategy switching, Tiny-specific tools
- [ ] Second model, including an open-source one
- [ ] Held-out bug set, never published
- [ ] OS-level sandbox for test runs
- [ ] Trace viewer for agent logs
