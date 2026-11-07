from .errors import tiny_error


def parse_line(tokens, line_no):
    parser = Parser(tokens, line_no)
    statement = parser.parse_statement()
    parser.expect_end_of_line()
    return statement


def token_text(token):
    return str(token[1])


class Parser:
    def __init__(self, tokens, line_no):
        self.tokens = tokens
        self.pos = 0
        self.line_no = line_no

    def peek(self):
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def advance(self):
        token = self.peek()
        self.pos += 1
        return token

    def at_operator(self, symbols):
        token = self.peek()
        return token is not None and token[0] == "OP" and token[1] in symbols

    def error(self, message):
        return tiny_error(self.line_no, message)

    def parse_statement(self):
        token = self.peek()
        if token == ("KW", "let"):
            self.advance()
            return self.parse_let_rest()
        if token == ("KW", "print"):
            self.advance()
            return ("print", self.parse_sum())
        raise self.error("expected 'let' or 'print'")

    def parse_let_rest(self):
        name_token = self.peek()
        if name_token is None or name_token[0] != "NAME":
            raise self.error("expected variable name after 'let'")
        self.advance()

        if not self.at_operator(("=",)):
            raise self.error("expected '=' after variable name")
        self.advance()

        return ("let", name_token[1], self.parse_sum())

    def expect_end_of_line(self):
        token = self.peek()
        if token is not None:
            raise self.error(f"unexpected token '{token_text(token)}'")

    def parse_sum(self):
        left = self.parse_average()
        while self.at_operator(("+", "-")):
            op = self.advance()[1]
            right = self.parse_average()
            left = ("bin", op, left, right)
        return left

    def parse_average(self):
        left = self.parse_product()
        while self.at_operator(("~",)):
            op = self.advance()[1]
            right = self.parse_product()
            left = ("bin", op, left, right)
        return left

    def parse_product(self):
        left = self.parse_atom()
        while self.at_operator(("*", "/")):
            op = self.advance()[1]
            right = self.parse_atom()
            left = ("bin", op, left, right)
        return left

    def parse_atom(self):
        token = self.advance()
        if token is None:
            raise self.error("unexpected end of line")

        kind, value = token
        if kind == "NUM":
            return ("num", value)
        if kind == "NAME":
            return ("var", value)
        if token == ("OP", "("):
            inner = self.parse_sum()
            if not self.at_operator((")",)):
                raise self.error("expected ')'")
            self.advance()
            return inner
        raise self.error(f"unexpected token '{token_text(token)}'")
