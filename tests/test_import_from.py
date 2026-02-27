"""Tests for Handler 2: IMPORT FROM normalization."""

from exasol_sql_normalizer.handlers.import_from import normalize_import_from


class TestImportFromBasic:
    def test_simple_import_from(self):
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT FROM JDBC AT CON_ANALYTICS\n"
            "    STATEMENT 'SELECT a, b FROM remote_table'\n"
            ")"
        )
        result = normalize_import_from(sql)
        assert "SELECT * FROM __JDBC_IMPORT__CON_ANALYTICS" in result
        assert "IMPORT FROM JDBC" not in result
        assert "STATEMENT" not in result

    def test_multiline_statement(self):
        sql = (
            "SELECT col1, col2 FROM (\n"
            "    IMPORT FROM JDBC AT CON_ANALYTICS\n"
            "    STATEMENT '\n"
            "        SELECT\n"
            "            q1.promoter_name AS [promoter_name]\n"
            "        FROM [replica_db].[dbo].[orders] AS TDL_T\n"
            "    '\n"
            ")"
        )
        result = normalize_import_from(sql)
        assert "SELECT * FROM __JDBC_IMPORT__CON_ANALYTICS" in result
        assert "IMPORT FROM JDBC" not in result

    def test_preserves_surrounding_sql(self):
        sql = (
            "SELECT\n"
            "    promoter_name AS promoter_name\n"
            "FROM\n"
            "(\n"
            "    IMPORT FROM JDBC AT CON_ANALYTICS\n"
            "    STATEMENT 'SELECT 1'\n"
            ")\n"
            "WHERE x = 1"
        )
        result = normalize_import_from(sql)
        assert "promoter_name AS promoter_name" in result
        assert "WHERE x = 1" in result
        assert "SELECT * FROM __JDBC_IMPORT__CON_ANALYTICS" in result


class TestImportFromEdgeCases:
    def test_import_keyword_in_string_not_matched(self):
        sql = "SELECT 'IMPORT FROM something' AS label FROM t"
        result = normalize_import_from(sql)
        assert result == sql

    def test_statement_with_escaped_quotes(self):
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT FROM JDBC AT CONN1\n"
            "    STATEMENT 'SELECT ''hello'' FROM t'\n"
            ")"
        )
        result = normalize_import_from(sql)
        assert "SELECT * FROM __JDBC_IMPORT__CONN1" in result
        assert "STATEMENT" not in result


class TestImportFromPassthrough:
    def test_standard_sql_unchanged(self):
        sql = "SELECT a, b FROM my_table WHERE x > 1"
        assert normalize_import_from(sql) == sql

    def test_empty_string(self):
        assert normalize_import_from("") == ""

    def test_import_into_not_matched(self):
        """IMPORT INTO should NOT be handled by this handler."""
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT INTO (col1 INT)\n"
            "    FROM JDBC AT CONN1\n"
            "    STATEMENT 'SELECT 1'\n"
            ")"
        )
        # This handler only matches IMPORT FROM (not IMPORT INTO)
        result = normalize_import_from(sql)
        assert "IMPORT INTO" in result
