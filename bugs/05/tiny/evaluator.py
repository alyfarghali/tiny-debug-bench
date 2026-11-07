from .arithmetic import apply_operator
from .errors import tiny_error
from .lexer import lex
from .optimizer import optimize
from .parser import parse_line


def evaluate(expr, env, line_no):
    kind = expr[0]

    if kind == "num":
        return expr[1]

    if kind == "var":
        name = expr[1]
        if name not in env:
            raise tiny_error(line_no, f"undefined variable '{name}'")
        return env[name]

    if kind == "bin":
        _, op, left_expr, right_expr = expr
        left = evaluate(left_expr, env, line_no)
        right = evaluate(right_expr, env, line_no)
        if op == "/" and right == 0:
            raise tiny_error(line_no, "division by zero")
        return apply_operator(op, left, right)

    raise ValueError(f"unknown expression kind {kind!r}")


def run(source):
    env = {}
    outputs = []
    for line_no, line_text in enumerate(source.split("\n"), start=1):
        if line_text.strip() == "":
            continue
        tokens = lex(line_text, line_no)
        statement = parse_line(tokens, line_no)
        execute(statement, env, outputs, line_no)
    return outputs


def execute(statement, env, outputs, line_no):
    if statement[0] == "let":
        _, name, expr = statement
        if name in env:
            raise tiny_error(line_no, f"variable '{name}' already defined")
        env[name] = evaluate(optimize(expr), env, line_no)
    else:
        _, expr = statement
        outputs.append(evaluate(optimize(expr), env, line_no))
