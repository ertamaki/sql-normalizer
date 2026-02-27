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
        assert "SELECT col1, col2 FROM __JDBC_IMPORT__MY_CONNECTION" in result
        assert "IMPORT INTO" not in result
        assert "STATEMENT" not in result

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
        assert "SELECT row_id, user_permissions FROM __JDBC_IMPORT__CON_PRODUCTION" in result
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
        assert "SELECT RowID, order_id FROM __JDBC_IMPORT__CON_GATEWAY" in result

    def test_charset_in_column_type(self):
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT INTO (name VARCHAR(50) UTF8, id INT)\n"
            "    FROM JDBC AT CONN1\n"
            "    STATEMENT 'SELECT name, id FROM t'\n"
            ")"
        )
        result = normalize_import_into(sql)
        assert "SELECT name, id FROM __JDBC_IMPORT__CONN1" in result


class TestImportIntoEdgeCases:
    def test_statement_with_escaped_quotes(self):
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT INTO (col1 INT)\n"
            "    FROM JDBC AT CONN1\n"
            "    STATEMENT 'SELECT ''hello'' FROM t'\n"
            ")"
        )
        result = normalize_import_into(sql)
        assert "SELECT col1 FROM __JDBC_IMPORT__CONN1" in result
        assert "STATEMENT" not in result

    def test_multiple_imports(self):
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT INTO (a INT) FROM JDBC AT CONN1 STATEMENT 'SELECT 1'\n"
            ") t1\n"
            "JOIN (\n"
            "    IMPORT INTO (b INT) FROM JDBC AT CONN2 STATEMENT 'SELECT 2'\n"
            ") t2 ON t1.a = t2.b"
        )
        result = normalize_import_into(sql)
        assert "SELECT a FROM __JDBC_IMPORT__CONN1" in result
        assert "SELECT b FROM __JDBC_IMPORT__CONN2" in result
        assert "IMPORT INTO" not in result

    def test_import_keyword_in_string_literal_not_matched(self):
        sql = "SELECT 'IMPORT INTO something' AS label FROM t"
        result = normalize_import_into(sql)
        assert result == sql


class TestImportIntoPassthrough:
    def test_standard_sql_unchanged(self):
        sql = "SELECT a, b FROM my_table WHERE x > 1"
        assert normalize_import_into(sql) == sql

    def test_empty_string(self):
        assert normalize_import_into("") == ""

    def test_select_with_subquery(self):
        sql = "SELECT * FROM (SELECT a FROM t) sub"
        assert normalize_import_into(sql) == sql
