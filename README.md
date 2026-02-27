# exasol-sql-normalizer

A lightweight SQL translator that rewrites Exasol-specific syntax into standard SQL that tools like [sqlglot](https://github.com/tobymao/sqlglot) can parse.

## Why This Exists

Exasol's SQL dialect includes several constructs that no major SQL parser (sqlglot, sqlparse, etc.) handles correctly:

- **`IMPORT INTO / IMPORT FROM`** — proprietary remote data import via JDBC connections
- **`GROUP_CONCAT ... SEPARATOR`** — aggregate with MySQL-style separator clause
- **`CONVERT(TYPE CHARSET, expr)`** — cast with charset specifier, reverse argument order
- **`REGEXP_LIKE` as infix operator** — `column REGEXP_LIKE('pattern')` instead of function-call syntax

We [reported one of these issues](https://github.com/tobymao/sqlglot/issues/7156) to sqlglot. The response was that Exasol support is low priority for the core team. Rather than wait for upstream support, this normalizer rewrites Exasol SQL into equivalent standard SQL before it hits the parser.

This is **not** a comprehensive Exasol-to-ANSI translator — it targets the specific constructs that cause real parse failures. It may have bugs or miss edge cases, but it's a practical starting point. I hope to keep it maintained until I have time to write a proper Exasol dialect PR for sqlglot.

The normalizer is a **pure function**: SQL string in, SQL string out. No dependencies beyond Python's standard library. No side effects. Each construct has an isolated handler with its own tests.

## Installation

```bash
pip install git+https://github.com/ertamaki/sql-normalizer.git
```

For development:

```bash
git clone https://github.com/ertamaki/sql-normalizer.git
cd sql-normalizer
pip install -e ".[dev]"
```

## Usage

```python
from exasol_sql_normalizer import normalize

raw_sql = """
CREATE OR REPLACE TABLE DW_TEMP.MY_TABLE AS
WITH data AS (
    SELECT col1, col2
    FROM (
        IMPORT INTO (col1 VARCHAR(50), col2 DECIMAL(10,0))
        FROM JDBC AT MY_CONNECTION
        STATEMENT 'SELECT a, b FROM remote_db.dbo.my_table'
    )
)
SELECT
    convert(VARCHAR(10000) UTF8, group_concat(DISTINCT col1 ORDER BY col1 SEPARATOR '|')) AS combined,
    col2
FROM data
WHERE col2 REGEXP_LIKE('[0-9]+')
GROUP BY col2
"""

normalized = normalize(raw_sql)
print(normalized)
```

Output:

```sql
CREATE OR REPLACE TABLE DW_TEMP.MY_TABLE AS
WITH data AS (
    SELECT col1, col2
    FROM (
        SELECT col1, col2 FROM __JDBC_IMPORT__MY_CONNECTION
    )
)
SELECT
    CAST(group_concat(DISTINCT col1 ORDER BY col1) AS VARCHAR(10000)) AS combined,
    col2
FROM data
WHERE REGEXP_LIKE(col2, '[0-9]+')
GROUP BY col2
```

The normalized SQL is standard enough for sqlglot (or any other parser) to handle:

```python
import sqlglot
ast = sqlglot.parse_one(normalized, dialect="tsql")  # works
```

## What It Handles

### 1. `IMPORT INTO` — Remote JDBC Import with Column Definitions

Exasol can import data from remote databases inline within a query:

```sql
SELECT * FROM (
    IMPORT INTO (
        order_id VARCHAR(50),
        amount DECIMAL(10,2),
        created_at TIMESTAMP
    )
    FROM JDBC AT CON_PRODUCTION
    STATEMENT 'SELECT order_id, amount, created_at FROM orders'
)
```

**Normalized to:**

```sql
SELECT * FROM (
    SELECT order_id, amount, created_at FROM __JDBC_IMPORT__CON_PRODUCTION
)
```

The column names are extracted from the type declaration block. The remote SQL statement is dropped (it runs on a different database and may use a completely different dialect). The connection name is preserved as a synthetic table name (`__JDBC_IMPORT__<connection>`) so downstream tools can track data lineage back to the remote source.

**Column name handling:**
- Quoted names: `"RowID" DECIMAL(10,0)` → `RowID`
- Charset specifiers in types are ignored: `VARCHAR(50) UTF8` — only the column name is extracted
- Column type definitions are discarded (only names matter for the SELECT)

### 2. `IMPORT FROM` — Remote JDBC Import without Column Definitions

Similar to `IMPORT INTO`, but without an explicit column declaration:

```sql
SELECT * FROM (
    IMPORT FROM JDBC AT CON_ANALYTICS
    STATEMENT 'SELECT name, revenue FROM summary'
)
```

**Normalized to:**

```sql
SELECT * FROM (
    SELECT * FROM __JDBC_IMPORT__CON_ANALYTICS
)
```

Since there are no column definitions, the replacement uses `SELECT *`.

### 3. `GROUP_CONCAT ... SEPARATOR`

Exasol's `GROUP_CONCAT` supports a `SEPARATOR` clause (MySQL-style syntax):

```sql
GROUP_CONCAT(DISTINCT trim(name) ORDER BY name SEPARATOR '|')
```

**Normalized to:**

```sql
GROUP_CONCAT(DISTINCT trim(name) ORDER BY name)
```

The `SEPARATOR '...'` clause is stripped. The rest of the function call (DISTINCT, ORDER BY, nested functions) is preserved intact. This is a lossy transformation — the separator value is lost — but it preserves the structural information that matters for SQL analysis (which columns are aggregated, what ordering is used).

**Handles:**
- Multiple `GROUP_CONCAT` calls in one query
- Nested function calls inside (e.g., `trim(replace(col, '|', ','))`)
- Various separator values: `','`, `'|'`, `'; '`
- Both `DISTINCT` and non-`DISTINCT` variants
- `ORDER BY` clauses before the `SEPARATOR`

### 4. `CONVERT(TYPE CHARSET, expr)` — Exasol's CONVERT/CAST

Exasol's `CONVERT` is functionally equivalent to `CAST`, but with:
- Reverse argument order: type first, expression second
- Optional charset specifier on the type: `VARCHAR(n) UTF8`

```sql
CONVERT(VARCHAR(10000) UTF8, group_concat(col))
```

**Normalized to:**

```sql
CAST(group_concat(col) AS VARCHAR(10000))
```

**Handles:**
- Charset specifiers: `UTF8`, `ASCII` (stripped)
- Nested expressions as the second argument
- Types with precision: `VARCHAR(10000)`, `DECIMAL(10,2)`
- Multiple `CONVERT` calls in one query

**Note on execution order:** This handler runs *after* the GROUP_CONCAT handler, so by the time CONVERT is processed, any inner `GROUP_CONCAT SEPARATOR` has already been normalized.

### 5. `REGEXP_LIKE` Infix Operator

Exasol allows `REGEXP_LIKE` as an infix operator (like `LIKE`):

```sql
WHERE column REGEXP_LIKE('[0-9]+')
```

**Normalized to:**

```sql
WHERE REGEXP_LIKE(column, '[0-9]+')
```

This rewrites the infix form into standard function-call syntax that parsers expect.

**Handles:**
- Qualified column names: `t.column REGEXP_LIKE('pattern')`
- Patterns with special regex characters

## Handler Execution Order

The handlers run in a fixed order:

```
1. IMPORT INTO      (most impactful, self-contained)
2. IMPORT FROM      (same family as #1)
3. GROUP_CONCAT     (must run before CONVERT — CONVERT often wraps GROUP_CONCAT)
4. CONVERT          (depends on GROUP_CONCAT being normalized first)
5. REGEXP_LIKE      (independent, lowest frequency)
```

The only ordering dependency is **3 before 4**: `CONVERT(VARCHAR(10000) UTF8, GROUP_CONCAT(... SEPARATOR '|'))` must have the inner GROUP_CONCAT normalized before CONVERT rewrites the outer call.

## What It Does NOT Handle

This normalizer targets the specific constructs that cause parse failures in real-world Exasol ETL scripts. It is not a complete Exasol-to-ANSI translator. Known limitations:

- **`IMPORT` outside subqueries** — the normalizer expects `IMPORT` to appear as a derived table (`FROM (IMPORT ...)`). Top-level `IMPORT` statements are not rewritten.
- **Exasol UDFs / scripting** — Lua, Python, R, and Java UDFs embedded in SQL are not handled. Strip these with a preprocessor before normalizing.
- **`MERGE` with Exasol extensions** — Exasol's MERGE syntax has minor deviations from the standard that this normalizer does not address.
- **`CONNECT BY`** — Exasol's hierarchical query syntax is not rewritten.
- **Remote STATEMENT content** — the SQL inside `STATEMENT '...'` (which runs on a remote database) is discarded, not translated. It may be T-SQL, PL/SQL, or any other dialect.

## Testing

```bash
pytest tests/ -v
```

Tests are organized per handler:
- **Unit tests** — isolated SQL snippets with a single construct
- **Passthrough tests** — SQL without Exasol constructs passes through unchanged
- **Composition tests** — multiple constructs in one query (e.g., CONVERT wrapping GROUP_CONCAT inside an IMPORT INTO CTE)
- **Round-trip tests** — `normalize()` output parses successfully with `sqlglot.parse_one(..., dialect="tsql")`

## Background & Motivation

This normalizer was born out of a practical need: parsing Exasol SQL with [sqlglot](https://github.com/tobymao/sqlglot). sqlglot is an excellent SQL parser, but it has no first-class Exasol dialect support. Using `dialect="tsql"` as a workaround gets you most of the way — but a handful of Exasol-specific constructs cause hard parse failures.

We [reported the issue](https://github.com/tobymao/sqlglot/issues/7156) to sqlglot. The maintainers flagged it as low priority and suggested a community PR. Writing a proper sqlglot dialect requires deep knowledge of their internals and could take a while to get merged, so in the meantime this normalizer serves as a lightweight preprocessing step.

It's nowhere near all-encompassing and may not handle every edge case, but it solves the specific constructs that cause the most breakage. The goal is to keep it maintained and eventually contribute a proper Exasol dialect upstream.

## License

MIT

## Contributing

Issues and PRs welcome. If you encounter an Exasol SQL construct that breaks your parser, open an issue with the SQL snippet and expected normalization.
