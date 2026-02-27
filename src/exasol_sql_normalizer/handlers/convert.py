"""Handler 4: Normalize Exasol's CONVERT(TYPE CHARSET, expr) to CAST(expr AS TYPE).

Only rewrites CONVERT calls that have a charset specifier (UTF8, ASCII),
which distinguishes Exasol's form from T-SQL's CONVERT(type, expr [, style]).

Rewrites:
    CONVERT(VARCHAR(10000) UTF8, expr)
To:
    CAST(expr AS VARCHAR(10000))
"""

import re

from ..utils import find_matching_paren

# Charset keywords that identify Exasol's CONVERT form
_CHARSETS = {"UTF8", "ASCII"}


def normalize_convert_charset(sql: str) -> str:
    """Rewrite Exasol CONVERT(type charset, expr) as CAST(expr AS type)."""
    result = []
    upper = sql.upper()
    i = 0
    length = len(sql)

    while i < length:
        match_pos = upper.find("CONVERT", i)
        if match_pos == -1:
            result.append(sql[i:])
            break

        # Make sure it's not part of a longer identifier
        if match_pos > 0 and (upper[match_pos - 1].isalnum() or upper[match_pos - 1] == "_"):
            result.append(sql[i:match_pos + 7])
            i = match_pos + 7
            continue
        after_end = match_pos + 7
        if after_end < length and (upper[after_end].isalnum() or upper[after_end] == "_"):
            result.append(sql[i:match_pos + 7])
            i = match_pos + 7
            continue

        # Check not inside a string
        if _is_inside_string(sql, match_pos):
            result.append(sql[i:match_pos + 7])
            i = match_pos + 7
            continue

        # Find opening paren
        after_kw = sql[match_pos + 7:].lstrip()
        paren_offset = match_pos + 7 + (len(sql[match_pos + 7:]) - len(after_kw))

        if paren_offset >= length or sql[paren_offset] != "(":
            result.append(sql[i:match_pos + 7])
            i = match_pos + 7
            continue

        # Find matching closing paren
        try:
            close_paren = find_matching_paren(sql, paren_offset)
        except ValueError:
            result.append(sql[i:match_pos + 7])
            i = match_pos + 7
            continue

        inner = sql[paren_offset + 1:close_paren]

        # Try to parse as Exasol CONVERT: type [charset], expr
        parsed = _parse_exasol_convert(inner)
        if parsed is None:
            # Not an Exasol CONVERT (no charset) — leave as-is
            result.append(sql[i:close_paren + 1])
            i = close_paren + 1
            continue

        type_str, expr = parsed
        result.append(sql[i:match_pos])
        result.append(f"CAST({expr} AS {type_str})")
        i = close_paren + 1

    return "".join(result)


def _parse_exasol_convert(inner: str) -> tuple[str, str] | None:
    """Parse the inner content of CONVERT(...) to extract type and expression.

    Returns (type_str, expression) if this is an Exasol CONVERT with charset,
    or None if it's not.
    """
    # The first argument is a type like "VARCHAR(10000) UTF8"
    # We need to find the comma that separates type from expression,
    # but the type itself may contain parens (e.g., VARCHAR(10000), DECIMAL(10,2))

    i = 0
    inner_stripped = inner.lstrip()
    i = len(inner) - len(inner_stripped)
    length = len(inner)

    # Parse the type: identifier followed by optional (precision) followed by optional charset
    # First, get the type name
    type_start = i
    while i < length and (inner[i].isalnum() or inner[i] == "_"):
        i += 1

    type_name = inner[type_start:i]
    if not type_name:
        return None

    # Optional precision in parens: (10000) or (10,2)
    type_with_precision = type_name
    rest = inner[i:].lstrip()
    i = len(inner) - len(rest)

    if i < length and inner[i] == "(":
        # Find matching close paren for precision
        depth = 1
        j = i + 1
        while j < length and depth > 0:
            if inner[j] == "(":
                depth += 1
            elif inner[j] == ")":
                depth -= 1
            j += 1
        type_with_precision = inner[type_start:j].strip()
        # Reconstruct properly: type_name + paren content
        type_with_precision = type_name + inner[i:j]
        i = j

    # Check for charset keyword
    rest = inner[i:].lstrip()
    i = len(inner) - len(rest)

    charset_start = i
    while i < length and (inner[i].isalnum() or inner[i] == "_"):
        i += 1

    potential_charset = inner[charset_start:i].upper()

    if potential_charset not in _CHARSETS:
        # No charset — not an Exasol CONVERT
        return None

    # Now expect a comma separating type from expression
    rest = inner[i:].lstrip()
    i = len(inner) - len(rest)

    if i >= length or inner[i] != ",":
        return None

    # Everything after the comma is the expression
    expr = inner[i + 1:].strip()
    if not expr:
        return None

    return (type_with_precision, expr)


def _is_inside_string(sql: str, pos: int) -> bool:
    """Check if position pos is inside a single-quoted string."""
    in_string = False
    i = 0
    while i < pos:
        if sql[i] == "'":
            if in_string:
                if i + 1 < len(sql) and sql[i + 1] == "'":
                    i += 2
                    continue
                in_string = False
            else:
                in_string = True
        i += 1
    return in_string
