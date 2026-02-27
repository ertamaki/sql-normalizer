"""Shared utilities for SQL string scanning."""


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
