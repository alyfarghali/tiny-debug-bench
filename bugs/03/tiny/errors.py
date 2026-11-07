class TinyError(Exception):
    pass


def tiny_error(line_no, message):
    return TinyError(f"Line {line_no}: {message}")
