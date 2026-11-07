# SkyLink Bench: Can an AI agent debug a system it has never seen?

A small benchmark and a hand-written agent harness for testing whether an LLM agent can find and fix planted bugs in an invented protocol it could not have memorized.

> **Status: design stage.** This README describes the planned system and experiment. None of the components below have been implemented yet. Items move out of "planned" only when the code is in the repo.

---

## Why this matters

AI agents are increasingly asked to work in codebases they have never seen. How reliable they are there depends a lot on the harness around the model: its tools, feedback, memory and stopping rules, not only on which model is used. SkyLink Bench tests harness design directly, on code that cannot be in the training data.

## How it works (planned)

1. I invented a protocol called **SkyLink** for a fictional drone swarm and wrote a spec for it.
2. I write a Python implementation of the spec, with tests.
3. For each trial, **one bug** is planted in a fresh copy of the implementation.
4. An agent tries to fix the bug using only the code, the visible tests and (in some setups) the spec.
5. The result is scored against a **hidden test suite** the agent never sees.

The protocol is invented, so the model cannot recall a known fix. This avoids benchmark contamination.

```
            +-------------------------------------------+
            |  fresh copy of buggy SkyLink code         |
            +---------------------+---------------------+
                                  |
                                  v
   +-----------+   tool call   +--------------------------------+
   |   Model   | ------------> | Tools: read_file, read_spec,   |
   | (Gemini   |               |        edit_file, run_tests    |
   |  3.6      | <------------ +--------------------------------+
   |  Flash)   |  tool result /                 |
   +-----------+  test output                   v
         ^                      +--------------------------------+
         |                      | Controller: step limit,        |
         +-- memory notes ----- | timeout, protected test files, |
             (failed fixes)     | strategy switch, stop on pass  |
                                +---------------+----------------+
                                                |
                                                v
                          hidden test suite + JSON log of the run
```

## The SkyLink protocol (planned)

The full specification will live in [`SPEC.md`](SPEC.md). The implementation is split into modules, and each one is a place where bugs can be planted:

| Module | Responsibility |
|---|---|
| `packet.py` | Binary header with a custom bit layout: version, priority, urgent flag, drone ID |
| `checksum.py` | Custom checksum: byte sum, rotate, XOR with drone ID |
| `fragment.py` | Message fragmentation and reassembly with custom duplicate and gap rules |
| `link.py` | Radio link selection from signal strength (dBm), noise and battery |
| `retry.py` | Retry backoff policy |
| `parser.py` | Parser for a small drone command language, e.g. `GOTO 12.5,40.1 ALT 30` |

## Harness design (planned)

The harness is written in plain Python with Google's `google-genai` SDK, without LangChain or any other agent framework. The model is **Gemini 3.6 Flash** (`gemini-3.6-flash`) on the free tier of the Gemini API. The model ID is set with the `GEMINI_MODEL` environment variable, so every result can be tied to the exact model used.

| Part | Design |
|---|---|
| **Tools** (`tools.py`) | `read_file`, `run_tests`, `edit_file`, `read_spec` |
| **Feedback** | Test output is returned to the model after each run |
| **Memory** | Notes on fixes already tried and why they failed |
| **Control logic** (`agent.py`) | Step limit; test timeout; stop when tests pass; test files cannot be edited; switch strategy after repeated failures |
| **Isolation** | Every run starts from a fresh copy of the buggy code |
| **Logging** | Full logs of each run saved as JSON |

## Experiment design (planned)

### Ablation

Each setup changes one thing from the one before it:

| Setup | Configuration |
|---|---|
| **A** (control) | Code only, one attempt, no tools |
| **B** | Tools + test feedback |
| **C** | B + `read_spec` tool |
| **D** | C + memory |
| **E** (full harness) | D + strategy-switch rule |

Each setup runs on every bug at least 3 times.

### Metrics

| Metric | Definition |
|---|---|
| Visible pass rate | Share of runs that pass the tests the agent can see |
| True fix rate | Share of runs that pass the hidden test suite |
| Damage rate | Share of runs that pass the visible tests but fail the hidden ones (fake fixes) |
| Avg. steps | Mean agent steps per run |
| Avg. tokens | Mean tokens per run |

### Hypotheses (written before running)

1. The full harness (E) beats the control (A) on true fix rate.
2. Test feedback raises visible pass rate but also raises fake fixes.
3. Spec access mainly reduces fake fixes, especially on bit-layout and unit bugs.
4. Memory and strategy switching help mostly on cross-file bugs.

### Contamination check

Before the experiments, the model gets only each function's name and docstring and writes the function from scratch. If that version passes the tests, the bug is too standard to be a fair test and gets replaced.

## Results

_Results pending: no experiments have been run yet._

| Setup | Visible pass rate | True fix rate | Damage rate | Avg. steps | Avg. tokens |
|---|---|---|---|---|---|
| A (control) | TBD | TBD | TBD | TBD | TBD |
| B (+ tools, feedback) | TBD | TBD | TBD | TBD | TBD |
| C (+ spec) | TBD | TBD | TBD | TBD | TBD |
| D (+ memory) | TBD | TBD | TBD | TBD | TBD |
| E (full harness) | TBD | TBD | TBD | TBD | TBD |

_Chart pending: true fix rate vs. damage rate by setup (to be generated by `make_chart.py`)._

## Findings and failure analysis

_Findings pending._

Failed runs will be read from the JSON logs and sorted into categories such as:

- **Fixed symptom, not cause**: the visible tests pass, but the underlying spec violation remains
- **Repeated same fix**: the agent retries an edit that already failed
- **Fake fix**: the agent special-cases test inputs instead of fixing the logic

Each hypothesis will be marked supported, not supported or inconclusive, with the evidence for each.

## How to run it

These setup steps work now:

```bash
# Create an environment and install dependencies (pytest, google-genai)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Free API key from https://aistudio.google.com/apikey, kept in .env (gitignored, never commit it)
cat > .env <<'EOF'
export GEMINI_API_KEY="your-key-here"
export GEMINI_MODEL="gemini-3.6-flash"
EOF
source .env

# Confirm the key works and list available models
python check_setup.py
```

_Planned: these commands won't work until the code exists._

```bash
# Run all setups on all bugs (planned)
python run_experiments.py

# Generate the results chart (planned)
python make_chart.py
```

## Repo structure

Current contents:

```
harness/
├── README.md
├── requirements.txt      # google-genai, pytest (pinned)
├── check_setup.py        # verifies API key, lists usable models
└── .gitignore
```

Planned layout:

```
harness/
├── README.md
├── SPEC.md               # SkyLink protocol specification
├── skylink/              # reference implementation
│   ├── packet.py
│   ├── checksum.py
│   ├── fragment.py
│   ├── link.py
│   ├── retry.py
│   └── parser.py
├── tests/                # visible tests (agent can run)
├── hidden_tests/         # hidden tests (agent never sees)
├── bugs/                 # planted-bug definitions
├── tools.py              # agent tools
├── agent.py              # agent loop and control logic
├── run_experiments.py    # runs setups A–E
├── make_chart.py         # results chart
└── logs/                 # JSON run logs
```

## Roadmap

**Core (planned, needed for the first results):**

- [ ] `SPEC.md` and the six SkyLink modules
- [ ] Visible and hidden test suites
- [ ] Bug set and contamination check
- [ ] Harness: `tools.py`, `agent.py`
- [ ] `run_experiments.py` and `make_chart.py`
- [ ] Results table, chart and failure analysis

**Extensions (planned, after the core):**

- [ ] Compare a second model, including an open-source model
- [ ] Held-out bug set that is not used while developing the harness
- [ ] TypeScript trace viewer for the JSON run logs
- [ ] C-language version of the bugs
