"""Check that the Gemini API key works and show which models it can use.

Usage:
    export GEMINI_API_KEY="your-key"
    python check_setup.py                  # list models, then ping the default
    GEMINI_MODEL=<model-id> python check_setup.py   # ping a specific model
"""

import os
import sys

from google import genai

DEFAULT_MODEL = "gemini-3.6-flash"  # free tier; verified working 2026-11-07


def main() -> int:
    if not os.environ.get("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set. Get a free key at https://aistudio.google.com/apikey")
        return 1

    client = genai.Client()  # reads GEMINI_API_KEY from the environment

    print("Models available to this key that support generateContent:")
    for m in client.models.list():
        if "generateContent" in (m.supported_actions or []):
            print(f"  {m.name.removeprefix('models/')}")

    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    print(f"\nPinging {model} ...")
    try:
        resp = client.models.generate_content(model=model, contents="Reply with the single word: ok")
    except Exception as e:  # surface quota / model-name errors plainly
        print(f"Request failed: {e}")
        return 1
    print(f"Response: {resp.text.strip()!r}")
    print("Setup OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
