"""Earned color: syntax highlighting for completed lines.

Pygments tokenizes the whole target file once (so multi-line constructs
highlight correctly) and the result is split into per-line prompt_toolkit
fragments. Only ANSI palette colors are used, so the user's terminal theme
still decides what the colors look like (DESIGN.md: typethru has no theme).
"""

from __future__ import annotations

from pygments.lexers import get_lexer_for_filename
from pygments.token import Token
from pygments.util import ClassNotFound

# Most-specific first; token types walk up to their parent until a match.
_STYLE_MAP = [
    (Token.Comment, "fg:ansibrightblack italic"),
    (Token.Literal.String, "fg:ansigreen"),
    (Token.Literal.Number, "fg:ansimagenta"),
    (Token.Operator.Word, "fg:ansiblue bold"),
    (Token.Keyword, "fg:ansiblue bold"),
    (Token.Name.Function, "fg:ansicyan"),
    (Token.Name.Class, "fg:ansicyan bold"),
    (Token.Name.Decorator, "fg:ansicyan"),
    (Token.Name.Builtin, "fg:ansicyan"),
    (Token.Name.Tag, "fg:ansiblue"),
    (Token.Name.Attribute, "fg:ansicyan"),
    (Token.Generic.Heading, "bold"),
]


def _style_for(token) -> str:
    while token is not None:
        for match, style in _STYLE_MAP:
            if token is match:
                return style
        token = token.parent
    return ""


def highlight_file(path: str, text: str) -> list[list[tuple[str, str]]] | None:
    """Per-line style fragments for the whole file, or None when no lexer
    matches the filename."""
    try:
        lexer = get_lexer_for_filename(path, text)
    except ClassNotFound:
        return None
    lines: list[list[tuple[str, str]]] = [[]]
    for token, value in lexer.get_tokens(text):
        style = _style_for(token)
        parts = value.split("\n")
        for i, part in enumerate(parts):
            if i > 0:
                lines.append([])
            if part:
                lines[-1].append((style, part))
    return lines


def line_fragments(
    per_line: list[list[tuple[str, str]]] | None, lineno: int, expected_text: str
) -> list[tuple[str, str]] | None:
    """Fragments for 1-based `lineno`, or None when unavailable or when the
    tokenized text doesn't reproduce the line exactly (defensive: a lexer
    must never change what's on screen)."""
    if per_line is None or not 1 <= lineno <= len(per_line):
        return None
    frags = per_line[lineno - 1]
    if "".join(text for _, text in frags) != expected_text:
        return None
    return frags
