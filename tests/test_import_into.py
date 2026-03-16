"""Tests for Handler 1: IMPORT INTO normalization."""

from exasol_sql_normalizer.handlers.import_into import normalize_import_into


class TestImportIntoBasic:
    def test_simple_import_into(self):
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT INTO (col1 INT, col2 VARCHAR(50))\n"
            "    FROM JDBC AT MY_CONNECTION\n"
            "    STATEMENT 'SELECT a, b FROM remote_table'\n"
            ")"
        )
        result = normalize_import_into(sql)
        assert "SELECT col1, col2 FROM __JDBC_IMPORT__MY_CONNECTION.remote_table" in result
        assert "IMPORT INTO" not in result
        assert "STATEMENT" not in result

    def test_schema_qualified_table(self):
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT INTO (col1 INT, col2 VARCHAR(50))\n"
            "    FROM JDBC AT MY_CONNECTION\n"
            "    STATEMENT 'SELECT a, b FROM dbo.my_table'\n"
            ")"
        )
        result = normalize_import_into(sql)
        assert "SELECT col1, col2 FROM __JDBC_IMPORT__MY_CONNECTION.dbo.my_table" in result

    def test_three_part_ref_capped_to_two(self):
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT INTO (col1 INT)\n"
            "    FROM JDBC AT CONN1\n"
            "    STATEMENT 'SELECT a FROM some_db.dbo.orders'\n"
            ")"
        )
        result = normalize_import_into(sql)
        # 3-part ref capped to schema.table; db name dropped
        assert "__JDBC_IMPORT__CONN1.dbo.orders" in result

    def test_multiline_column_defs(self):
        sql = (
            "SELECT * FROM (\n"
            "IMPORT INTO\n"
            "(\n"
            "row_id INT\n"
            ", user_permissions NVARCHAR(1000)\n"
            ")\n"
            "FROM JDBC AT CON_PRODUCTION\n"
            "STATEMENT\n"
            "'\n"
            "SELECT t.\"RowID\", convert(varchar(1000), t.\"Permissions\",1) as Permissions\n"
            "FROM dbo.users t\n"
            "'\n"
            ")"
        )
        result = normalize_import_into(sql)
        assert "SELECT row_id, user_permissions FROM __JDBC_IMPORT__CON_PRODUCTION.dbo.users" in result
        assert "IMPORT INTO" not in result

    def test_quoted_column_names(self):
        sql = (
            'SELECT * FROM (\n'
            '    IMPORT INTO ("RowID" DECIMAL(10,0), order_id VARCHAR(50) UTF8)\n'
            '    FROM JDBC AT CON_GATEWAY\n'
            "    STATEMENT 'SELECT a, b FROM remote'\n"
            ')'
        )
        result = normalize_import_into(sql)
        assert "SELECT RowID, order_id FROM __JDBC_IMPORT__CON_GATEWAY.remote" in result

    def test_charset_in_column_type(self):
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT INTO (name VARCHAR(50) UTF8, id INT)\n"
            "    FROM JDBC AT CONN1\n"
            "    STATEMENT 'SELECT name, id FROM t'\n"
            ")"
        )
        result = normalize_import_into(sql)
        assert "SELECT name, id FROM __JDBC_IMPORT__CONN1.t" in result


class TestImportIntoMultiTable:
    def test_join_in_statement(self):
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT INTO (a INT, b INT)\n"
            "    FROM JDBC AT CONN1\n"
            "    STATEMENT 'SELECT a, b FROM dbo.orders INNER JOIN dbo.items ON orders.id = items.order_id'\n"
            ")"
        )
        result = normalize_import_into(sql)
        assert "__JDBC_IMPORT__CONN1.dbo.orders" in result
        assert "__JDBC_IMPORT__CONN1.dbo.items" in result

    def test_left_join_in_statement(self):
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT INTO (a INT)\n"
            "    FROM JDBC AT CONN1\n"
            "    STATEMENT 'SELECT a FROM t1 LEFT OUTER JOIN t2 ON t1.id = t2.id'\n"
            ")"
        )
        result = normalize_import_into(sql)
        assert "__JDBC_IMPORT__CONN1.t1" in result
        assert "__JDBC_IMPORT__CONN1.t2" in result

    def test_comma_separated_from(self):
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT INTO (a INT)\n"
            "    FROM JDBC AT CONN1\n"
            "    STATEMENT 'SELECT a FROM t1, t2 WHERE t1.id = t2.id'\n"
            ")"
        )
        result = normalize_import_into(sql)
        assert "__JDBC_IMPORT__CONN1.t1" in result
        assert "__JDBC_IMPORT__CONN1.t2" in result


class TestImportIntoEdgeCases:
    def test_statement_with_escaped_quotes(self):
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT INTO (col1 INT)\n"
            "    FROM JDBC AT CONN1\n"
            "    STATEMENT 'SELECT col1 FROM t WHERE name LIKE ''test%'''\n"
            ")"
        )
        result = normalize_import_into(sql)
        assert "__JDBC_IMPORT__CONN1.t" in result
        assert "STATEMENT" not in result

    def test_multiple_imports(self):
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT INTO (a INT) FROM JDBC AT CONN1 STATEMENT 'SELECT 1 FROM t1'\n"
            ") t1\n"
            "JOIN (\n"
            "    IMPORT INTO (b INT) FROM JDBC AT CONN2 STATEMENT 'SELECT 2 FROM t2'\n"
            ") t2 ON t1.a = t2.b"
        )
        result = normalize_import_into(sql)
        assert "__JDBC_IMPORT__CONN1.t1" in result
        assert "__JDBC_IMPORT__CONN2.t2" in result
        assert "IMPORT INTO" not in result

    def test_import_keyword_in_string_literal_not_matched(self):
        sql = "SELECT 'IMPORT INTO something' AS label FROM t"
        result = normalize_import_into(sql)
        assert result == sql

    def test_no_statement_clause_fallback(self):
        """When STATEMENT is absent, fall back to connection-only phantom table."""
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT INTO (col1 INT)\n"
            "    FROM JDBC AT CONN1\n"
            ")"
        )
        result = normalize_import_into(sql)
        assert "SELECT col1 FROM __JDBC_IMPORT__CONN1" in result

    def test_statement_with_no_from_fallback(self):
        """STATEMENT with no FROM clause falls back to connection-only."""
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT INTO (col1 INT)\n"
            "    FROM JDBC AT CONN1\n"
            "    STATEMENT 'SELECT 1'\n"
            ")"
        )
        result = normalize_import_into(sql)
        assert "SELECT col1 FROM __JDBC_IMPORT__CONN1" in result

    def test_bracket_quoted_table_refs(self):
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT INTO (a INT)\n"
            "    FROM JDBC AT CONN1\n"
            "    STATEMENT 'SELECT a FROM [dbo].[orders]'\n"
            ")"
        )
        result = normalize_import_into(sql)
        assert "__JDBC_IMPORT__CONN1.[dbo].[orders]" in result


class TestImportIntoPassthrough:
    def test_standard_sql_unchanged(self):
        sql = "SELECT a, b FROM my_table WHERE x > 1"
        assert normalize_import_into(sql) == sql

    def test_empty_string(self):
        assert normalize_import_into("") == ""

    def test_select_with_subquery(self):
        sql = "SELECT * FROM (SELECT a FROM t) sub"
        assert normalize_import_into(sql) == sql
