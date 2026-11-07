from .arithmetic import apply_operator


def optimize(expr):
    if expr[0] != "bin":
        return expr

    _, op, left, right = expr
    left = optimize(left)
    right = optimize(right)

    if is_number(left) and is_number(right):
        return ("num", apply_operator(op, left[1], right[1]))

    return simplify_identity(op, left, right)


def simplify_identity(op, left, right):
    if op == "*":
        if is_number_equal(right, 1):
            return left
        if is_number_equal(left, 1):
            return right
    elif op == "+":
        if is_number_equal(right, 0):
            return left
        if is_number_equal(left, 0):
            return right
    elif op == "-":
        if is_number_equal(right, 0):
            return left
    return ("bin", op, left, right)


def is_number(expr):
    return expr[0] == "num"


def is_number_equal(expr, value):
    return is_number(expr) and expr[1] == value


def is_division_by_zero(op, right):
    return op == "/" and is_number_equal(right, 0)
