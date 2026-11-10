"""Experiment configuration. Plain data, no logic.

Each setup turns harness features on or off. Later setups (D, E, F) add keys
such as "memory", "switch" and "tiny_tools". Code must read every key with
setup.get(key, False), so a missing key means "off" and older setups keep
working unchanged.

Every run saves a copy of its setup and CONFIG into its log, so results always
record exactly what was used.
"""

SETUPS = {
    "A": {"multi_turn": False, "feedback": False, "spec": False},
    "B": {"multi_turn": True, "feedback": True, "spec": False},
    "C": {"multi_turn": True, "feedback": True, "spec": True},
}

CONFIG = {
    "model": "gemini-3.6-flash",
    "max_steps": 15,
    "test_timeout_s": 30,
    "tool_output_max_chars": 3000,
    "repeats": 3,
    "fuzz_seed": 0,
}
