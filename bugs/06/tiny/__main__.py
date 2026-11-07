import sys

from . import TinyError, run


def main(argv):
    if len(argv) != 2:
        print("usage: python -m tiny PROGRAM.tiny", file=sys.stderr)
        return 2

    path = argv[1]
    try:
        with open(path, encoding="utf-8") as file:
            source = file.read()
    except OSError as error:
        print(f"cannot read {path}: {error.strerror}", file=sys.stderr)
        return 1

    try:
        outputs = run(source)
    except TinyError as error:
        print(error, file=sys.stderr)
        return 1

    if hasattr(sys, "set_int_max_str_digits"):
        sys.set_int_max_str_digits(0)
    for value in outputs:
        print(value)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
