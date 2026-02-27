"""Handler 5: Normalize REGEXP_LIKE infix operator to function-call syntax.

Rewrites:
    column REGEXP_LIKE('pattern')
To:
    REGEXP_LIKE(column, 'pattern')
"""

import re

# SQL keywords that can appear before REGEXP_LIKE but are NOT column expressions
_SQL_KEYWORDS = {
    "WHERE", "AND", "OR", "ON", "WHEN", "THEN", "ELSE", "CASE", "NOT",
    "SELECT", "FROM", "SET", "VALUES", "HAVING", "IF", "ELSEIF",
}


def normalize_regexp_like(sql: str) -> str:
    """Rewrite infix REGEXP_LIKE to function-call syntax."""
    # Use regex to find: <identifier> <whitespace> REGEXP_LIKE <whitespace>? ( ... )
    # The identifier is a column name or qualified name (t.col)
    #
    # Strategy: find each REGEXP_LIKE, look back for a column expression.
    # If the preceding word is a SQL keyword (WHERE, AND, etc.), it's function-call syntax.

    result = []
    upper = sql.upper()
    i = 0
    length = len(sql)

    while i < length:
        match_pos = upper.find("REGEXP_LIKE", i)
        if match_pos == -1:
            result.append(sql[i:])
            break

        # Check not inside a string
        if _is_inside_string(sql, match_pos):
            result.append(sql[i:match_pos + 11])
            i = match_pos + 11
            continue

        # Look backwards to extract the preceding token
        before = sql[i:match_pos]
        before_stripped = before.rstrip()

        # Extract the last word/identifier from before
        col_expr = _extract_trailing_identifier(before_stripped)

        if not col_expr or col_expr.upper() in _SQL_KEYWORDS:
            # No column expr or it's a SQL keyword — this is already function syntax
            result.append(sql[i:match_pos + 11])
            i = match_pos + 11
            continue

        # Find the opening paren after REGEXP_LIKE
        cursor = match_pos + 11
        while cursor < length and sql[cursor] in (" ", "\t", "\n", "\r"):
            cursor += 1

        if cursor >= length or sql[cursor] != "(":
            result.append(sql[i:match_pos + 11])
            i = match_pos + 11
            continue

        # Find matching closing paren
        close_paren = _find_matching_paren(sql, cursor)
        if close_paren == -1:
            result.append(sql[i:match_pos + 11])
            i = match_pos + 11
            continue

        args = sql[cursor + 1:close_paren]

        # Build: prefix (without col_expr) + REGEXP_LIKE(col_expr, args)
        prefix = before_stripped[:len(before_stripped) - len(col_expr)]
        result.append(prefix)
        result.append(f"REGEXP_LIKE({col_expr}, {args})")
        i = close_paren + 1

    return "".join(result)


def _extract_trailing_identifier(s: str) -> str:
    """Extract the last identifier (column name or qualified name) from a string.

    Returns empty string if the string doesn't end with an identifier.
    Handles: col, t.col, schema.t.col, "QuotedCol", t."QuotedCol"
    """
    if not s:
        return ""

    i = len(s) - 1

    # Handle quoted identifier
    if s[i] == '"':
        j = i - 1
        while j >= 0 and s[j] != '"':
            j -= 1
        if j < 0:
            return ""
        start = j
        # Check for qualifier: t."col"
        if start > 0 and s[start - 1] == ".":
            k = start - 2
            while k >= 0 and (s[k].isalnum() or s[k] in ("_", ".")):
                k -= 1
            return s[k + 1:]
        return s[start:]

    # Unquoted: walk back through alnum, underscore, dot
    if not (s[i].isalnum() or s[i] == "_"):
        return ""

    while i >= 0 and (s[i].isalnum() or s[i] in ("_", ".")):
        i -= 1

    return s[i + 1:]


def _find_matching_paren(sql: str, open_pos: int) -> int:
    """Find matching closing paren."""
    depth = 1
    i = open_pos + 1
    length = len(sql)

    while i < length:
        ch = sql[i]
        if ch == "'":
            i += 1
            while i < length:
                if sql[i] == "'":
                    if i + 1 < length and sql[i + 1] == "'":
                        i += 2
                    else:
                        break
                else:
                    i += 1
        elif ch == '"':
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

    return -1


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
