"""Shared utilities for SQL string scanning."""

import re


# ---------------------------------------------------------------------------
# Table-reference extraction from STATEMENT strings
# ---------------------------------------------------------------------------

# A single T-SQL identifier segment: [bracketed] or bare
_IDENT_SEG = r'(?:\[[^\]]+\]|[A-Za-z_#@][A-Za-z0-9_#@$]*)'

# A dotted table reference (1-4 parts): schema.table, [db].[schema].[table], etc.
_TABLE_REF = _IDENT_SEG + r'(?:\.' + _IDENT_SEG + r')*'

# Keywords that precede a table reference
_JOIN_KW = r'(?:INNER|LEFT|RIGHT|CROSS|FULL)(?:\s+OUTER)?\s+JOIN'
_TABLE_KW = r'(?:FROM|JOIN|' + _JOIN_KW + r')'

_STMT_TABLE_PATTERN = re.compile(
    _TABLE_KW + r'\s+(' + _TABLE_REF + r')',
    re.IGNORECASE,
)

_COMMA_TABLE_PATTERN = re.compile(
    r'\s*,\s*(' + _TABLE_REF + r')',
    re.IGNORECASE,
)

# For splitting a dotted ref into segments (bracket-aware)
_SEG_PATTERN = re.compile(r'\[([^\]]+)\]|([A-Za-z_#@][A-Za-z0-9_#@$]*)')

_BARE_IDENT = re.compile(r'^[A-Za-z_#@][A-Za-z0-9_#@$]*$')


def _quote_if_needed(ident: str) -> str:
    """Wrap in [brackets] if the identifier needs quoting."""
    if _BARE_IDENT.match(ident):
        return ident
    return f'[{ident}]'


def _split_ref(ref: str) -> list[str]:
    """Split a dotted table ref into unquoted segment names."""
    return [m.group(1) or m.group(2) for m in _SEG_PATTERN.finditer(ref)]


def _cap_table_ref(ref: str, max_parts: int = 2) -> str:
    """Cap a table reference to at most *max_parts* rightmost segments.

    If already at or below *max_parts*, the original string is returned
    unchanged.  Otherwise the reference is split, the last *max_parts*
    segments are kept, and segments that require quoting are wrapped in
    brackets.
    """
    parts = _split_ref(ref)
    if len(parts) <= max_parts:
        return ref
    capped = parts[-max_parts:]
    return '.'.join(_quote_if_needed(p) for p in capped)


def extract_tables_from_statement(raw_stmt: str) -> list[str]:
    """Extract table references from a remote SQL STATEMENT string.

    Returns a deduplicated list of table references (capped to schema.table)
    found after FROM / JOIN keywords.  Returns an empty list when no tables
    are found, signalling that the caller should use the fallback output.
    """
    # Unescape Exasol '' -> '
    stmt_sql = raw_stmt.replace("''", "'")

    # Neutralise string literals so FROM/JOIN inside strings are invisible
    stmt_clean = re.sub(r"'[^']*(?:''[^']*)*'", "''", stmt_sql)

    seen: set[str] = set()
    tables: list[str] = []

    for m in _STMT_TABLE_PATTERN.finditer(stmt_clean):
        capped = _cap_table_ref(m.group(1))
        key = capped.upper()
        if key not in seen:
            seen.add(key)
            tables.append(capped)

        # Forward-scan for comma-separated tables (FROM t1, t2)
        pos = m.end()
        while True:
            cm = _COMMA_TABLE_PATTERN.match(stmt_clean, pos)
            if not cm:
                break
            capped = _cap_table_ref(cm.group(1))
            key = capped.upper()
            if key not in seen:
                seen.add(key)
                tables.append(capped)
            pos = cm.end()

    return tables


# ---------------------------------------------------------------------------
# Quoted-string helpers
# ---------------------------------------------------------------------------

def extract_quoted_string(sql: str, pos: int) -> tuple[int, str]:
    """Extract content of a single-quoted string starting at *pos*.

    Returns ``(end_pos, content)`` where *end_pos* is the index after the
    closing quote and *content* is the unescaped string body (``''`` → ``'``).
    """
    if pos >= len(sql) or sql[pos] != "'":
        return pos, ""

    i = pos + 1
    chars: list[str] = []
    while i < len(sql):
        if sql[i] == "'":
            if i + 1 < len(sql) and sql[i + 1] == "'":
                chars.append("'")
                i += 2
            else:
                return i + 1, "".join(chars)
        else:
            chars.append(sql[i])
            i += 1

    return len(sql), "".join(chars)


def skip_quoted_string(sql: str, pos: int) -> int:
    """Skip past a single-quoted string starting at *pos*.

    Returns the position after the closing quote.
    """
    end, _ = extract_quoted_string(sql, pos)
    return end


def skip_whitespace(sql: str, pos: int) -> int:
    """Advance past whitespace characters."""
    while pos < len(sql) and sql[pos] in (" ", "\t", "\n", "\r"):
        pos += 1
    return pos


def is_inside_string(sql: str, pos: int) -> bool:
    """Check if position *pos* is inside a single-quoted string."""
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


# ---------------------------------------------------------------------------
# Parenthesis matching
# ---------------------------------------------------------------------------

def find_matching_paren(sql: str, open_pos: int) -> int:
    """Find the position of the closing parenthesis matching the one at open_pos.

    Tracks:
    - Nested parentheses depth
    - Single-quoted strings (including '' escape)
    - Double-quoted identifiers

    Args:
        sql: The SQL string.
        open_pos: Index of the opening '(' character.

    Returns:
        Index of the matching ')' character.

    Raises:
        ValueError: If no matching closing paren is found.
    """
    if sql[open_pos] != "(":
        raise ValueError(f"Character at position {open_pos} is {sql[open_pos]!r}, not '('")

    depth = 1
    i = open_pos + 1
    length = len(sql)

    while i < length:
        ch = sql[i]

        if ch == "'":
            # Skip single-quoted string (handles '' escape)
            i += 1
            while i < length:
                if sql[i] == "'":
                    if i + 1 < length and sql[i + 1] == "'":
                        i += 2  # escaped quote
                    else:
                        break  # end of string
                else:
                    i += 1
        elif ch == '"':
            # Skip double-quoted identifier
            i += 1
            while i < length and sql[i] != '"':
                i += 1
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i

        i += 1

    raise ValueError(f"No matching closing paren for '(' at position {open_pos}")
