def divide_toward_zero(a, b):
    quotient = abs(a) // abs(b)
    result_is_negative = (a < 0) != (b < 0)
    if result_is_negative:
        return -quotient
    return quotient


def average_toward_zero(a, b):
    return (a + b) // 2


def apply_operator(op, left, right):
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    if op == "/":
        return divide_toward_zero(left, right)
    if op == "~":
        return average_toward_zero(left, right)
    raise ValueError(f"unknown operator {op!r}")
