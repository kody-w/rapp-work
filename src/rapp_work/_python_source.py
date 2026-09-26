"""Bounded pre-parse measure of untrusted Python source (``rapp-work-sdk/1`` §11.2).

Discovery parses a discovered file with the interpreter's own parser, which has
no bound that holds on every supported Python: on 3.10 a long left-recursive
chain such as ``1+1+1...`` overflows the C stack while the syntax tree is
converted to Python objects, and some shapes take quadratic time. This module
reads only tokens, never evaluates anything, and says whether a source stays
within fixed nesting, cost, integer-literal, and replacement-field bounds.

Every supported interpreter sees the same measure: Python 3.12 and later
tokenize f-string replacement fields natively, and on 3.10 and 3.11, whose
tokenizer returns an f-string as one string token, the fields are found by a
port of CPython's own f-string scanner (``Parser/string_parser.c``).
"""

from __future__ import annotations

import bisect
import io
import tokenize
from collections.abc import Generator, Iterator
from typing import NamedTuple

MAX_SOURCE_NESTING = 256
MAX_SOURCE_COST = 131_072
MAX_DECIMAL_DIGITS = 640
MAX_FORMAT_FIELDS = 1_024
LINE_COST_WIDTH = 4_096

WITHIN = "within"
OVER_COST = "over-cost"
OVER_LIMIT = "over-limit"
INVALID = "invalid"

_OPEN, _CLOSE, _COMMA, _SEMI, _OP, _NAME, _NUMBER, _STRING = range(8)
_FSTART, _FEND, _NEWLINE, _INDENT, _DEDENT, _OTHER = range(8, 14)
# kind, text, physical row, inside a formatted string literal
Token = tuple[int, str, int, bool]

_COUNTED_KEYWORDS = frozenset(
    {"and", "async", "await", "else", "for", "from", "if", "in", "is", "not", "or", "yield"}
)
_BRACKET_PAIRS = {"(": ")", "[": "]", "{": "}"}
_FORMAT_START = frozenset(
    getattr(tokenize, name)
    for name in ("FSTRING_START", "TSTRING_START")
    if hasattr(tokenize, name)
)
_FORMAT_MIDDLE = frozenset(
    getattr(tokenize, name)
    for name in ("FSTRING_MIDDLE", "TSTRING_MIDDLE")
    if hasattr(tokenize, name)
)
_FORMAT_END = frozenset(
    getattr(tokenize, name)
    for name in ("FSTRING_END", "TSTRING_END")
    if hasattr(tokenize, name)
)
_NATIVE_FORMAT_TOKENS = bool(_FORMAT_START)
_SKIPPED = frozenset({tokenize.ENCODING, tokenize.ENDMARKER}) | _FORMAT_MIDDLE
_CPYTHON_MAXLEVEL = 200
# CPython's tokenizer refuses the 100th indentation level on every supported version.
_CPYTHON_MAXINDENT = 100
_PY_ISSPACE = frozenset(" \t\n\r\x0b\x0c")


class SourceMeasure(NamedTuple):
    verdict: str
    cost: int
    nesting: int


class _Stop(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _classify(kind: int, text: str) -> int:
    if kind == tokenize.OP:
        if text in _BRACKET_PAIRS:
            return _OPEN
        if text in {")", "]", "}"}:
            return _CLOSE
        if text == ",":
            return _COMMA
        if text == ";":
            return _SEMI
        return _OP
    if kind == tokenize.NAME:
        return _NAME
    if kind == tokenize.NUMBER:
        return _NUMBER
    if kind == tokenize.STRING:
        return _STRING
    if kind == tokenize.NEWLINE:
        return _NEWLINE
    if kind == tokenize.INDENT:
        return _INDENT
    if kind == tokenize.DEDENT:
        return _DEDENT
    return _OTHER


def _native_tokens(text: str) -> Iterator[Token]:
    formats = 0
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        kind = token.type
        if kind in _FORMAT_START:
            formats += 1
            yield _FSTART, "", token.start[0], True
        elif kind in _FORMAT_END:
            formats -= 1
            yield _FEND, "", token.start[0], True
        elif kind not in _SKIPPED:
            yield _classify(kind, token.string), token.string, token.start[0], formats > 0


def _legacy_tokens(text: str, row_base: int, in_format: bool) -> Iterator[Token]:
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        kind = token.type
        if kind in _SKIPPED:
            continue
        row = row_base + token.start[0] - 1
        if kind == tokenize.STRING and "f" in _prefix(token.string).lower():
            yield from _LegacyFormat(token.string, row).tokens()
        else:
            yield _classify(kind, token.string), token.string, row, in_format


def _prefix(literal: str) -> str:
    end = 0
    while end < len(literal) and literal[end].isalpha():
        end += 1
    return literal[:end]


class _LegacyFormat:
    """CPython 3.10/3.11 f-string field scanner, ported for measurement only.

    It mirrors ``fstring_find_literal`` and ``fstring_find_expr``: the fields it
    finds are exactly the ones the interpreter parses. Where CPython raises a
    SyntaxError, the source is invalid and no tree will be built.
    """

    def __init__(self, literal: str, row: int) -> None:
        prefix = _prefix(literal)
        self.raw = "r" in prefix.lower()
        quoted = literal[len(prefix) :]
        quote = quoted[0]
        triple = len(quoted) >= 6 and quoted[1] == quote and quoted[2] == quote
        width = 3 if triple else 1
        self.body = quoted[width:-width]
        self.offset = len(prefix) + width
        self.row = row
        self.newlines = [index for index, character in enumerate(literal) if character == "\n"]
        self.end_row = row + len(self.newlines)

    def _row(self, position: int) -> int:
        return self.row + bisect.bisect_right(self.newlines, self.offset + position - 1)

    def tokens(self) -> Iterator[Token]:
        yield _FSTART, "", self.row, True
        position = yield from self._concat(0, 0)
        if position < len(self.body) - 1:
            raise _Stop(INVALID)
        yield _FEND, "", self.end_row, True

    def _concat(self, position: int, level: int) -> Generator[Token, None, int]:
        body = self.body
        end = len(body)
        while True:
            position, doubled = self._find_literal(position, level)
            if doubled:
                continue
            if position >= end or body[position] == "}":
                break
            position = yield from self._find_expr(position, level)
        if level and (position >= end or body[position] != "}"):
            raise _Stop(INVALID)
        return position

    def _find_literal(self, position: int, level: int) -> tuple[int, bool]:
        body = self.body
        end = len(body)
        while position < end:
            character = body[position]
            position += 1
            if not self.raw and character == "\\" and position < end:
                character = body[position]
                position += 1
                if character == "N":
                    if position < end:
                        position += 1
                        if body[position - 1] == "{":
                            while position < end:
                                position += 1
                                if body[position - 1] == "}":
                                    break
                    continue
            if character in "{}":
                if level == 0:
                    if position < end and body[position] == character:
                        return position + 1, True
                    if character == "}":
                        raise _Stop(INVALID)
                return position - 1, False
        return position, False

    def _find_expr(self, position: int, level: int) -> Generator[Token, None, int]:
        if level >= 2:
            raise _Stop(INVALID)
        body = self.body
        end = len(body)
        field_row = self._row(position)
        position += 1
        start = position
        quote = ""
        triple = False
        nested: list[str] = []
        while position < end:
            character = body[position]
            if character == "\\":
                raise _Stop(INVALID)
            if quote:
                if character == quote:
                    if not triple:
                        quote = ""
                    elif position + 2 < end and body[position + 1] == body[position + 2] == quote:
                        quote = ""
                        position += 2
            elif character in "'\"":
                triple = (
                    position + 2 < end and body[position + 1] == body[position + 2] == character
                )
                if triple:
                    position += 2
                quote = character
            elif character in _BRACKET_PAIRS:
                if len(nested) >= _CPYTHON_MAXLEVEL:
                    raise _Stop(INVALID)
                nested.append(character)
            elif character == "#":
                raise _Stop(INVALID)
            elif not nested and character in "!:}=<>":
                if (
                    position + 1 < end
                    and body[position + 1] == "="
                    and character in "!=<>"
                ):
                    position += 2
                    continue
                if character not in "<>":
                    break
            elif character in ")]}":
                if not nested or _BRACKET_PAIRS[nested.pop()] != character:
                    raise _Stop(INVALID)
            position += 1
        if quote or nested or position >= end:
            raise _Stop(INVALID)
        expression = body[start:position]
        if not expression.strip(" \t\n\f"):
            raise _Stop(INVALID)
        yield _OPEN, "{", field_row, True
        yield from self._expression_tokens(expression, self._row(start))
        if body[position] == "=":
            yield _OP, "=", self._row(position), True
            position += 1
            while position < end and body[position] in _PY_ISSPACE:
                position += 1
            if position >= end:
                raise _Stop(INVALID)
        if body[position] == "!":
            yield _OP, "!", self._row(position), True
            position += 1
            if position >= end or body[position] not in "sra":
                raise _Stop(INVALID)
            yield _NAME, body[position], self._row(position), True
            position += 1
        if position >= end:
            raise _Stop(INVALID)
        if body[position] == ":":
            yield _OP, ":", self._row(position), True
            position += 1
            if position >= end:
                raise _Stop(INVALID)
            position = yield from self._concat(position, level + 1)
        if position >= end or body[position] != "}":
            raise _Stop(INVALID)
        yield _CLOSE, "}", self._row(position), True
        return position + 1

    @staticmethod
    def _expression_tokens(expression: str, row: int) -> Iterator[Token]:
        # CPython parses the field as "(" + expression + ")"; the added pair is not counted.
        inner = _legacy_tokens("(" + expression + ")", row, True)
        next(inner, None)
        held: Token | None = None
        for token in inner:
            if token[0] == _NEWLINE:
                break
            if held is not None:
                yield held
            held = token


class _Group:
    __slots__ = ("base", "count", "fields", "format", "peak", "pending", "run", "running")

    def __init__(self, base: int, count: int, format_: bool) -> None:
        self.base = base
        self.count = count
        self.format = format_
        self.pending = 0
        self.run = 0
        self.running = False
        self.fields = 0
        self.peak = base + count


def _tokens(text: str) -> Iterator[Token]:
    if _NATIVE_FORMAT_TOKENS:
        return _native_tokens(text)
    return _legacy_tokens(text, 1, False)


def measure_source(text: str, limit: int) -> SourceMeasure:
    """Measure ``text`` against the fixed bounds and a cost ``limit``.

    ``over-cost`` means the measure stopped at the first unit beyond ``limit``;
    ``over-limit`` means another fixed bound was exceeded first. ``cost`` is the
    number of cost units read, and ``nesting`` the largest estimate reached.
    """

    if "\x00" in text:
        return SourceMeasure(INVALID, 0, 0)
    source = text.replace("\r\n", "\n").replace("\r", "\n")
    line_lengths = [len(line) for line in source.split("\n")]
    last_row = len(line_lengths)
    groups = [_Group(0, 0, False)]
    formats: list[_Group] = []
    owner = groups[0]
    indent = [0]
    statement = 3
    total = 0
    cost = 0
    deepest = 0
    line_start = True
    try:
        for kind, value, row, in_format in _tokens(source):
            if in_format:
                cost += 1 + line_lengths[min(row, last_row) - 1] // LINE_COST_WIDTH
            else:
                cost += 1
            if cost > limit:
                raise _Stop(OVER_COST)
            if kind == _NEWLINE or kind == _SEMI:
                groups = [_Group(0, 0, False)]
                formats = []
                owner = groups[0]
                total = 0
                if kind == _NEWLINE:
                    line_start = True
                continue
            if kind == _INDENT:
                if len(indent) >= _CPYTHON_MAXINDENT:
                    raise _Stop(INVALID)
                indent.append(0)
                continue
            if kind == _DEDENT:
                if len(indent) > 1:
                    indent.pop()
                continue
            if kind == _OTHER:
                continue
            if line_start:
                line_start = False
                if kind == _NAME and value == "elif":
                    indent[-1] += 1
                elif not (kind == _NAME and value == "else"):
                    indent[-1] = 0
                statement = 1 + sum(2 + run for run in indent)
            top = groups[-1]
            if kind == _STRING or kind == _FSTART:
                if not top.running:
                    top.running = True
                    top.run = 0
                    top.fields = 0
                if kind == _FSTART:
                    if not formats:
                        owner = top
                    group = _Group(statement + total, 1, True)
                    groups.append(group)
                    formats.append(group)
                    total += 1
            elif kind == _FEND:
                if not top.format:
                    raise _Stop(INVALID)
                groups.pop()
                formats.pop()
                total -= top.count
                if formats:
                    formats[-1].peak = max(formats[-1].peak, top.peak)
                enclosing = groups[-1]
                enclosing.run = max(enclosing.run, top.peak - top.base)
            elif kind == _CLOSE:
                if len(groups) > 1 and not top.format:
                    groups.pop()
                    total -= top.count
            elif kind == _COMMA:
                top.running = False
                if not top.pending:
                    total -= top.count
                    top.count = 0
            else:
                if top.running:
                    top.running = False
                    top.count += top.run
                    total += top.run
                if kind == _OPEN:
                    if top.format:
                        # Replacement fields of one literal are siblings, as elements after a comma.
                        total -= top.count - 1
                        top.count = 1
                    top.count += 2
                    total += 2
                    if formats and value == "{":
                        owner.fields += 1
                        if owner.fields > MAX_FORMAT_FIELDS:
                            raise _Stop(OVER_LIMIT)
                    groups.append(_Group(0, 0, False))
                elif kind == _OP:
                    if value == ":" and top.pending:
                        top.pending -= 1
                    top.count += 1
                    total += 1
                elif kind == _NAME:
                    if value == "lambda":
                        top.pending += 1
                        top.count += 2
                        total += 2
                    elif value in _COUNTED_KEYWORDS:
                        top.count += 1
                        total += 1
                elif kind == _NUMBER:
                    digits = value.replace("_", "")
                    if digits.isascii() and digits.isdigit() and len(digits) > MAX_DECIMAL_DIGITS:
                        raise _Stop(OVER_LIMIT)
            depth = statement + total
            deepest = max(deepest, depth)
            if depth > MAX_SOURCE_NESTING:
                raise _Stop(OVER_LIMIT)
            if formats and depth > formats[-1].peak:
                formats[-1].peak = depth
    except _Stop as stop:
        return SourceMeasure(stop.reason, cost, deepest)
    except (tokenize.TokenError, SyntaxError):
        return SourceMeasure(INVALID, cost, deepest)
    return SourceMeasure(WITHIN, cost, deepest)
