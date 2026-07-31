from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable


CELL_RE = re.compile(r"^(\$?[A-Z]{1,3}\$?\d+)$")
REF_RE = re.compile(r"(?<![A-Z0-9_])(?P<col>\$?[A-Z]{1,3})(?P<row>\$?\d+)")


def col_number(col: str) -> int:
    value = 0
    for char in col.replace("$", ""):
        value = value * 26 + ord(char) - 64
    return value


def col_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def normalize_ref(ref: str) -> str:
    return ref.replace("$", "").upper()


def translate_formula(formula: str, source: str, target: str) -> str:
    """Translate a shared formula while respecting absolute A1 references."""
    sm = re.fullmatch(r"([A-Z]+)(\d+)", source.upper())
    tm = re.fullmatch(r"([A-Z]+)(\d+)", target.upper())
    if not sm or not tm:
        return formula
    col_delta = col_number(tm.group(1)) - col_number(sm.group(1))
    row_delta = int(tm.group(2)) - int(sm.group(2))

    def repl(match: re.Match[str]) -> str:
        raw_col, raw_row = match.group("col"), match.group("row")
        fixed_col, fixed_row = raw_col.startswith("$"), raw_row.startswith("$")
        new_col = col_number(raw_col) if fixed_col else col_number(raw_col) + col_delta
        new_row = int(raw_row.replace("$", "")) if fixed_row else int(raw_row) + row_delta
        col = ("$" if fixed_col else "") + col_name(new_col)
        row = ("$" if fixed_row else "") + str(new_row)
        return col + row

    return REF_RE.sub(repl, formula)


def numeric(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class RangeValue:
    cells: list[str]
    values: list[Any]


TOKEN_RE = re.compile(
    r'\s*(?:(?P<number>\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)|'
    r'(?P<string>"(?:[^"]|"")*")|'
    r'(?P<cell>\$?[A-Z]{1,3}\$?\d+)|'
    r'(?P<ident>[A-Z_][A-Z0-9_.]*)|'
    r'(?P<op><>|<=|>=|[+\-*/^%=<>,:()]))',
    re.IGNORECASE,
)


class FormulaError(RuntimeError):
    pass


class FormulaParser:
    def __init__(self, formula: str, get_cell: Callable[[str], Any], get_range: Callable[[str, str], RangeValue]):
        self.get_cell = get_cell
        self.get_range = get_range
        self.tokens = self._tokenize(formula.lstrip("="))
        self.position = 0

    @staticmethod
    def _tokenize(text: str) -> list[tuple[str, str]]:
        tokens: list[tuple[str, str]] = []
        pos = 0
        while pos < len(text):
            match = TOKEN_RE.match(text, pos)
            if not match:
                raise FormulaError(f"Unsupported formula fragment: {text[pos:pos+30]!r}")
            kind = match.lastgroup or ""
            tokens.append((kind, match.group(kind)))
            pos = match.end()
        return tokens

    def peek(self, value: str | None = None) -> bool:
        if self.position >= len(self.tokens):
            return False
        return value is None or self.tokens[self.position][1].upper() == value.upper()

    def take(self, value: str | None = None) -> tuple[str, str]:
        if self.position >= len(self.tokens):
            raise FormulaError("Unexpected end of formula")
        token = self.tokens[self.position]
        if value is not None and token[1].upper() != value.upper():
            raise FormulaError(f"Expected {value!r}, got {token[1]!r}")
        self.position += 1
        return token

    def parse(self) -> Any:
        value = self.comparison()
        if self.position != len(self.tokens):
            raise FormulaError(f"Unexpected token {self.tokens[self.position]}")
        return value

    def comparison(self) -> Any:
        left = self.additive()
        if self.peek() and self.tokens[self.position][1] in ("=", "<>", "<", ">", "<=", ">="):
            op = self.take()[1]
            right = self.additive()
            if op == "=": return left == right
            if op == "<>": return left != right
            if op == "<": return left < right
            if op == ">": return left > right
            if op == "<=": return left <= right
            return left >= right
        return left

    def additive(self) -> Any:
        value = self.multiplicative()
        while self.peek() and self.tokens[self.position][1] in ("+", "-"):
            op = self.take()[1]
            rhs = self.multiplicative()
            value = numeric(value) + numeric(rhs) if op == "+" else numeric(value) - numeric(rhs)
        return value

    def multiplicative(self) -> Any:
        value = self.power()
        while self.peek() and self.tokens[self.position][1] in ("*", "/"):
            op = self.take()[1]
            rhs = self.power()
            if op == "*":
                value = numeric(value) * numeric(rhs)
            else:
                denominator = numeric(rhs)
                if denominator == 0:
                    raise ZeroDivisionError
                value = numeric(value) / denominator
        return value

    def power(self) -> Any:
        value = self.unary()
        while self.peek("^"):
            self.take("^")
            value = numeric(value) ** numeric(self.unary())
        return value

    def unary(self) -> Any:
        if self.peek("+"):
            self.take("+")
            return numeric(self.unary())
        if self.peek("-"):
            self.take("-")
            return -numeric(self.unary())
        value = self.primary()
        if self.peek("%"):
            self.take("%")
            value = numeric(value) / 100.0
        return value

    def primary(self) -> Any:
        kind, raw = self.take()
        if kind == "number":
            return float(raw)
        if kind == "string":
            return raw[1:-1].replace('""', '"')
        if raw == "(":
            value = self.comparison()
            self.take(")")
            return value
        if kind == "cell":
            start = normalize_ref(raw)
            if self.peek(":"):
                self.take(":")
                _, end = self.take()
                return self.get_range(start, normalize_ref(end))
            return self.get_cell(start)
        if kind == "ident" and self.peek("("):
            return self.function(raw.upper())
        if kind == "ident":
            if raw.upper() == "TRUE": return True
            if raw.upper() == "FALSE": return False
        raise FormulaError(f"Unexpected token {(kind, raw)}")

    def function(self, name: str) -> Any:
        self.take("(")
        args: list[Any] = []
        if not self.peek(")"):
            while True:
                try:
                    args.append(self.comparison())
                except (FormulaError, ZeroDivisionError) as exc:
                    args.append(exc)
                if not self.peek(","):
                    break
                self.take(",")
        self.take(")")
        if name == "SUM":
            values: list[float] = []
            for arg in args:
                if isinstance(arg, RangeValue): values.extend(numeric(v) for v in arg.values)
                elif not isinstance(arg, Exception): values.append(numeric(arg))
            return sum(values)
        if name == "IF":
            if len(args) != 3: raise FormulaError("IF expects 3 arguments")
            return args[1] if bool(args[0]) else args[2]
        if name == "IFERROR":
            if len(args) != 2: raise FormulaError("IFERROR expects 2 arguments")
            return args[1] if isinstance(args[0], Exception) else args[0]
        if name == "SUMIFS":
            if len(args) != 3 or not isinstance(args[0], RangeValue) or not isinstance(args[1], RangeValue):
                raise FormulaError("Only one-condition SUMIFS is supported")
            criterion = args[2]
            return sum(numeric(value) for value, test in zip(args[0].values, args[1].values) if test == criterion)
        raise FormulaError(f"Unsupported Excel function: {name}")


def evaluate(formula: str, get_cell: Callable[[str], Any], get_range: Callable[[str, str], RangeValue]) -> Any:
    value = FormulaParser(formula, get_cell, get_range).parse()
    if isinstance(value, Exception):
        raise value
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise FormulaError("Non-finite result")
    return value
