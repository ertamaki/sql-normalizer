"""Handler 3: Normalize GROUP_CONCAT ... SEPARATOR.

Rewrites:
    GROUP_CONCAT(... SEPARATOR '...')
To:
    GROUP_CONCAT(...)

Strips the SEPARATOR clause while preserving DISTINCT, ORDER BY, and nested functions.
"""

import re

from ..utils import find_matching_paren


def normalize_group_concat(sql: str) -> str:
    """Remove SEPARATOR clauses from all GROUP_CONCAT calls."""
    result = []
    upper = sql.upper()
    i = 0
    length = len(sql)

    while i < length:
        # Find next GROUP_CONCAT
        match_pos = upper.find("GROUP_CONCAT", i)
        if match_pos == -1:
            result.append(sql[i:])
            break

        # Check not inside a string
        if _is_inside_string(sql, match_pos):
            result.append(sql[i:match_pos + 12])
            i = match_pos + 12
            continue

        # Find the opening paren
        after_kw = sql[match_pos + 12:].lstrip()
        paren_offset = match_pos + 12 + (len(sql[match_pos + 12:]) - len(after_kw))

        if paren_offset >= length or sql[paren_offset] != "(":
            result.append(sql[i:match_pos + 12])
            i = match_pos + 12
            continue

        # Find matching closing paren
        try:
            close_paren = find_matching_paren(sql, paren_offset)
        except ValueError:
            result.append(sql[i:match_pos + 12])
            i = match_pos + 12
            continue

        # Extract the content inside parens
        inner = sql[paren_offset + 1:close_paren]

        # Remove SEPARATOR clause from inner content
        cleaned_inner = _remove_separator(inner)

        # Rebuild
        result.append(sql[i:paren_offset + 1])
        result.append(cleaned_inner)
        result.append(")")
        i = close_paren + 1

    return "".join(result)


def _remove_separator(inner: str) -> str:
    """Remove SEPARATOR '...' from the end of a GROUP_CONCAT body.

    The SEPARATOR keyword is always the last clause before the closing paren,
    after any ORDER BY clause.
    """
    # Scan backwards-ish: find SEPARATOR keyword at depth 0
    upper = inner.upper()
    i = 0
    length = len(inner)
    last_separator_pos = -1

    while i < length:
        ch = inner[i]

        if ch == "'":
            # Skip string
            i += 1
            while i < length:
                if inner[i] == "'":
                    if i + 1 < length and inner[i + 1] == "'":
                        i += 2
                    else:
                        break
                else:
                    i += 1
            i += 1
            continue

        if ch == '"':
            i += 1
            while i < length and inner[i] != '"':
                i += 1
            i += 1
            continue

        if ch == "(":
            # Skip nested parens
            depth = 1
            i += 1
            while i < length and depth > 0:
                if inner[i] == "(":
                    depth += 1
                elif inner[i] == ")":
                    depth -= 1
                elif inner[i] == "'":
                    i += 1
                    while i < length:
                        if inner[i] == "'":
                            if i + 1 < length and inner[i + 1] == "'":
                                i += 2
                            else:
                                break
                        else:
                            i += 1
                elif inner[i] == '"':
                    i += 1
                    while i < length and inner[i] != '"':
                        i += 1
                i += 1
            continue

        # Check for SEPARATOR keyword at depth 0
        if upper[i:i + 9] == "SEPARATOR" and (i == 0 or not upper[i - 1].isalnum()):
            # Check it's followed by whitespace (not part of a longer word)
            after = i + 9
            if after >= length or not upper[after].isalnum():
                last_separator_pos = i

        i += 1

    if last_separator_pos == -1:
        return inner

    # Remove from SEPARATOR to end, preserving trailing whitespace pattern
    before = inner[:last_separator_pos].rstrip()
    return before


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
