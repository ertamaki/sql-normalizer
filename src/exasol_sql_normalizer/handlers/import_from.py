"""Handler 2: Normalize IMPORT FROM statements (without column definitions).

Rewrites:
    IMPORT FROM JDBC AT connection STATEMENT '...'
To:
    SELECT * FROM __JDBC_IMPORT__connection.schema.table
    (or FROM __JDBC_IMPORT__connection as fallback when no tables are found)
"""

import re

from ..utils import (
    extract_quoted_string,
    extract_tables_from_statement,
    is_inside_string,
    skip_quoted_string,
    skip_whitespace,
)


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
        if is_inside_string(sql, match_pos):
            result.append(sql[i:match_pos + 6])
            i = match_pos + 6
            continue

        # Check "FROM JDBC AT" follows "IMPORT" (not "INTO")
        cursor = match_pos + 6
        cursor = skip_whitespace(sql, cursor)

        match = re.match(
            # also capture /*...*/ block comments
            r'FROM\s+JDBC\s+AT\s+(/\*[^*]*\*+(?:[^/*][^*]*\*+)*/|\S+)',
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
        cursor = skip_whitespace(sql, cursor)

        # Optional: STATEMENT '...' — extract content for table references
        stmt_tables: list[str] = []
        if upper[cursor:cursor + 9] == "STATEMENT":
            cursor += 9
            cursor = skip_whitespace(sql, cursor)
            if cursor < length and sql[cursor] == "'":
                cursor, stmt_content = extract_quoted_string(sql, cursor)
                stmt_tables = extract_tables_from_statement(stmt_content)
            else:
                cursor = skip_quoted_string(sql, cursor)

        if stmt_tables:
            table_refs = ", ".join(
                f"__JDBC_IMPORT__{connection_name}.{t}" for t in stmt_tables
            )
        else:
            table_refs = f"__JDBC_IMPORT__{connection_name}"
        result.append(f"SELECT * FROM {table_refs}")
        i = cursor

    return "".join(result)
