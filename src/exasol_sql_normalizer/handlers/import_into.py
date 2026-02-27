"""Handler 1: Normalize IMPORT INTO statements.

Rewrites:
    IMPORT INTO (col1 TYPE, col2 TYPE, ...) FROM JDBC AT connection STATEMENT '...'
To:
    SELECT col1, col2, ... FROM __JDBC_IMPORT__connection
"""

import re


def normalize_import_into(sql: str) -> str:
    """Replace all IMPORT INTO blocks with equivalent SELECT statements."""
    result = []
    upper = sql.upper()
    i = 0
    length = len(sql)

    while i < length:
        match_pos = upper.find("IMPORT", i)
        if match_pos == -1:
            result.append(sql[i:])
            break

        # Check not inside a string
        if _is_inside_string(sql, match_pos):
            result.append(sql[i:match_pos + 6])
            i = match_pos + 6
            continue

        # Check "INTO" follows "IMPORT" with whitespace
        cursor = match_pos + 6
        cursor = _skip_whitespace(sql, cursor)
        if not upper[cursor:cursor + 4] == "INTO":
            result.append(sql[i:match_pos + 6])
            i = match_pos + 6
            continue

        cursor += 4  # past "INTO"
        cursor = _skip_whitespace(sql, cursor)

        # Expect opening paren
        if cursor >= length or sql[cursor] != "(":
            result.append(sql[i:match_pos + 6])
            i = match_pos + 6
            continue

        # Append everything before IMPORT
        result.append(sql[i:match_pos])

        # Find matching closing paren for column definitions
        close_paren = _find_matching_paren(sql, cursor)
        if close_paren == -1:
            result.append(sql[match_pos:match_pos + 6])
            i = match_pos + 6
            continue

        # Extract column names
        col_defs_str = sql[cursor + 1:close_paren]
        columns = _extract_column_names(col_defs_str)

        cursor = close_paren + 1
        cursor = _skip_whitespace(sql, cursor)

        # Expect: FROM JDBC AT <connection>
        from_match = re.match(
            # Also capture /*...*/ block comments:
            r'FROM\s+JDBC\s+AT\s+(/\*[^*]*\*+(?:[^/*][^*]*\*+)*/|\S+)',
            sql[cursor:],
            re.IGNORECASE,
        )
        if not from_match:
            result.append(sql[match_pos:close_paren + 1])
            i = close_paren + 1
            continue

        connection_name = from_match.group(1)
        cursor += from_match.end()
        cursor = _skip_whitespace(sql, cursor)

        # Optional: STATEMENT '...'
        if upper[cursor:cursor + 9] == "STATEMENT":
            cursor += 9
            cursor = _skip_whitespace(sql, cursor)
            cursor = _skip_quoted_string(sql, cursor)

        # Build replacement
        col_list = ", ".join(columns) if columns else "*"
        result.append(f"SELECT {col_list} FROM __JDBC_IMPORT__{connection_name}")
        i = cursor

    return "".join(result)


def _extract_column_names(col_defs: str) -> list[str]:
    """Extract column names from a column definition block."""
    columns = []
    for part in _split_column_defs(col_defs):
        part = part.strip()
        if not part:
            continue
        name = _extract_single_column_name(part)
        if name:
            columns.append(name)
    return columns


def _split_column_defs(col_defs: str) -> list[str]:
    """Split column definitions by commas, respecting parentheses in type defs."""
    parts = []
    depth = 0
    current = []

    for ch in col_defs:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)

    if current:
        parts.append("".join(current))
    return parts


def _extract_single_column_name(col_def: str) -> str:
    """Extract the column name from a single column definition."""
    col_def = col_def.strip()
    if not col_def:
        return ""

    if col_def.startswith('"'):
        end_quote = col_def.find('"', 1)
        if end_quote != -1:
            return col_def[1:end_quote]
        return col_def[1:]

    match = re.match(r'(\w+)', col_def)
    return match.group(1) if match else ""


def _skip_whitespace(sql: str, pos: int) -> int:
    """Advance past whitespace characters."""
    while pos < len(sql) and sql[pos] in (" ", "\t", "\n", "\r"):
        pos += 1
    return pos


def _find_matching_paren(sql: str, open_pos: int) -> int:
    """Find matching closing paren, aware of strings and nested parens."""
    depth = 1
    i = open_pos + 1
    length = len(sql)

    while i < length:
        ch = sql[i]
        if ch == "'":
            i = _end_of_quoted_string(sql, i)
        elif ch == '"':
            i += 1
            while i < length and sql[i] != '"':
                i += 1
            i += 1
        elif ch == "(":
            depth += 1
            i += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
            i += 1
        else:
            i += 1

    return -1


def _skip_quoted_string(sql: str, pos: int) -> int:
    """Skip past a single-quoted string starting at pos. Returns position after closing quote."""
    if pos >= len(sql) or sql[pos] != "'":
        return pos

    i = pos + 1
    while i < len(sql):
        if sql[i] == "'":
            if i + 1 < len(sql) and sql[i + 1] == "'":
                i += 2  # escaped quote
            else:
                return i + 1  # past closing quote
        else:
            i += 1

    return len(sql)


def _end_of_quoted_string(sql: str, pos: int) -> int:
    """Return position after the closing quote of a single-quoted string at pos."""
    i = pos + 1
    while i < len(sql):
        if sql[i] == "'":
            if i + 1 < len(sql) and sql[i + 1] == "'":
                i += 2
            else:
                return i + 1
        else:
            i += 1
    return len(sql)


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
