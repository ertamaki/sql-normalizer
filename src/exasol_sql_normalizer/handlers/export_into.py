"""Handler: Normalize EXPORT ... INTO SCRIPT statements.

Rewrites:
    EXPORT(
      <inner_query>
    )
    INTO SCRIPT <schema.name>
    WITH
      KEY1 = 'value1'
      KEY2 = 'value2'
      ...
    ;
To:
    CREATE TABLE <schema.name> AS
    <inner_query>
"""

import re

from .import_into import _is_inside_string, _skip_whitespace, _find_matching_paren


def normalize_export_into(sql: str) -> str:
    """Replace all EXPORT(...) INTO SCRIPT blocks with CREATE TABLE AS statements."""
    result = []
    upper = sql.upper()
    i = 0
    length = len(sql)

    while i < length:
        match_pos = upper.find("EXPORT", i)
        if match_pos == -1:
            result.append(sql[i:])
            break

        if _is_inside_string(sql, match_pos):
            result.append(sql[i:match_pos + 6])
            i = match_pos + 6
            continue

        cursor = match_pos + 6
        cursor = _skip_whitespace(sql, cursor)

        # Expect opening paren immediately after EXPORT
        if cursor >= length or sql[cursor] != "(":
            result.append(sql[i:match_pos + 6])
            i = match_pos + 6
            continue

        # Append everything before EXPORT
        result.append(sql[i:match_pos])

        # Find matching closing paren
        close_paren = _find_matching_paren(sql, cursor)
        if close_paren == -1:
            result.append(sql[match_pos:match_pos + 6])
            i = match_pos + 6
            continue

        inner_query = sql[cursor + 1:close_paren].strip()

        cursor = close_paren + 1
        cursor = _skip_whitespace(sql, cursor)

        # Expect: INTO SCRIPT <target>
        into_match = re.match(
            r'INTO\s+SCRIPT\s+(\S+)',
            sql[cursor:],
            re.IGNORECASE,
        )
        if not into_match:
            result.append(sql[match_pos:close_paren + 1])
            i = close_paren + 1
            continue

        target_name = into_match.group(1)
        cursor += into_match.end()
        cursor = _skip_whitespace(sql, cursor)

        # Strip optional WITH ... ; tail
        if upper[cursor:cursor + 4] == "WITH":
            cursor = _skip_with_clause(sql, cursor)

        result.append(f"CREATE TABLE {target_name} AS\n{inner_query}")
        i = cursor

    return "".join(result)


def _skip_with_clause(sql: str, pos: int) -> int:
    """Skip past WITH key=value pairs until ; or end of string."""
    length = len(sql)
    i = pos + 4  # past "WITH"

    while i < length:
        ch = sql[i]
        if ch == ";":
            return i + 1  # past the semicolon
        elif ch == "'":
            i = _skip_single_quoted(sql, i)
        else:
            i += 1

    return length


def _skip_single_quoted(sql: str, pos: int) -> int:
    """Skip past a single-quoted string starting at pos."""
    i = pos + 1
    length = len(sql)
    while i < length:
        if sql[i] == "'":
            if i + 1 < length and sql[i + 1] == "'":
                i += 2
            else:
                return i + 1
        else:
            i += 1
    return length
