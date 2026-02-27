"""Handler 2: Normalize IMPORT FROM statements (without column definitions).

Rewrites:
    IMPORT FROM JDBC AT connection STATEMENT '...'
To:
    SELECT * FROM __JDBC_IMPORT__connection
"""

import re


def normalize_import_from(sql: str) -> str:
    """Replace all IMPORT FROM JDBC blocks with SELECT * statements.

    This handles IMPORT FROM (without INTO), which has no column definitions.
    IMPORT INTO is handled separately and runs first, so by the time this handler
    runs, only bare IMPORT FROM blocks remain.
    """
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

        # Check "FROM JDBC AT" follows "IMPORT" (not "INTO")
        cursor = match_pos + 6
        cursor = _skip_whitespace(sql, cursor)

        match = re.match(
            r'FROM\s+JDBC\s+AT\s+(\S+)',
            sql[cursor:],
            re.IGNORECASE,
        )
        if not match:
            result.append(sql[i:match_pos + 6])
            i = match_pos + 6
            continue

        connection_name = match.group(1)

        # Append everything before IMPORT
        result.append(sql[i:match_pos])

        cursor += match.end()
        cursor = _skip_whitespace(sql, cursor)

        # Optional: STATEMENT '...'
        if upper[cursor:cursor + 9] == "STATEMENT":
            cursor += 9
            cursor = _skip_whitespace(sql, cursor)
            cursor = _skip_quoted_string(sql, cursor)

        result.append(f"SELECT * FROM __JDBC_IMPORT__{connection_name}")
        i = cursor

    return "".join(result)


def _skip_whitespace(sql: str, pos: int) -> int:
    """Advance past whitespace characters."""
    while pos < len(sql) and sql[pos] in (" ", "\t", "\n", "\r"):
        pos += 1
    return pos


def _skip_quoted_string(sql: str, pos: int) -> int:
    """Skip past a single-quoted string starting at pos."""
    if pos >= len(sql) or sql[pos] != "'":
        return pos

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
