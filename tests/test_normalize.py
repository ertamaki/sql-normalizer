"""Integration tests for the full normalize() pipeline."""

from exasol_sql_normalizer import normalize


class TestNormalizeChain:
    def test_convert_wrapping_group_concat(self):
        """CONVERT wrapping GROUP_CONCAT — tests ordering dependency (handler 3 before 4)."""
        sql = "SELECT convert(VARCHAR(10000) UTF8, group_concat(DISTINCT col1 ORDER BY col1 SEPARATOR '|')) AS combined FROM t"
        result = normalize(sql)
        assert "SEPARATOR" not in result
        assert "CONVERT" not in result.upper()
        assert "UTF8" not in result
        assert "CAST(" in result
        assert "group_concat(DISTINCT col1 ORDER BY col1)" in result

    def test_full_real_world_query(self):
        """Full pattern: IMPORT INTO + CONVERT + GROUP_CONCAT + REGEXP_LIKE."""
        sql = (
            "CREATE OR REPLACE TABLE staging.my_table AS\n"
            "WITH data AS (\n"
            "    SELECT col1, col2\n"
            "    FROM (\n"
            "        IMPORT INTO (col1 VARCHAR(50), col2 DECIMAL(10,0))\n"
            "        FROM JDBC AT MY_CONNECTION\n"
            "        STATEMENT 'SELECT a, b FROM remote_db.dbo.my_table'\n"
            "    )\n"
            ")\n"
            "SELECT\n"
            "    convert(VARCHAR(10000) UTF8, group_concat(DISTINCT col1 ORDER BY col1 SEPARATOR '|')) AS combined,\n"
            "    col2\n"
            "FROM data\n"
            "WHERE col2 REGEXP_LIKE('[0-9]+')\n"
            "GROUP BY col2"
        )
        result = normalize(sql)

        # IMPORT INTO replaced
        assert "IMPORT INTO" not in result
        assert "SELECT col1, col2 FROM __JDBC_IMPORT__MY_CONNECTION" in result

        # GROUP_CONCAT SEPARATOR stripped
        assert "SEPARATOR" not in result

        # CONVERT rewritten to CAST
        assert "CAST(" in result
        assert "UTF8" not in result

        # REGEXP_LIKE rewritten to function syntax
        assert "REGEXP_LIKE(col2, '[0-9]+')" in result

        # Structure preserved
        assert "CREATE OR REPLACE TABLE staging.my_table AS" in result
        assert "WITH data AS" in result
        assert "GROUP BY col2" in result

    def test_import_from_in_pipeline(self):
        sql = (
            "SELECT * FROM (\n"
            "    IMPORT FROM JDBC AT CON_ANALYTICS\n"
            "    STATEMENT 'SELECT 1'\n"
            ")"
        )
        result = normalize(sql)
        assert "SELECT * FROM __JDBC_IMPORT__CON_ANALYTICS" in result

    def test_standard_sql_passthrough(self):
        sql = "SELECT a, b, SUM(c) FROM my_table WHERE x > 1 GROUP BY a, b"
        assert normalize(sql) == sql

    def test_empty_string(self):
        assert normalize("") == ""

    def test_only_group_concat_no_separator(self):
        sql = "SELECT GROUP_CONCAT(col) FROM t"
        assert normalize(sql) == sql


class TestSqlglotRoundTrip:
    """Verify that normalized SQL can be parsed by sqlglot.

    These tests require sqlglot to be installed (dev dependency).
    """

    def test_full_query_parses(self):
        try:
            import sqlglot
        except ImportError:
            import pytest
            pytest.skip("sqlglot not installed")

        sql = (
            "CREATE OR REPLACE TABLE staging.my_table AS\n"
            "WITH data AS (\n"
            "    SELECT col1, col2\n"
            "    FROM (\n"
            "        IMPORT INTO (col1 VARCHAR(50), col2 DECIMAL(10,0))\n"
            "        FROM JDBC AT MY_CONNECTION\n"
            "        STATEMENT 'SELECT a, b FROM remote_db.dbo.my_table'\n"
            "    )\n"
            ")\n"
            "SELECT\n"
            "    convert(VARCHAR(10000) UTF8, group_concat(DISTINCT col1 ORDER BY col1 SEPARATOR '|')) AS combined,\n"
            "    col2\n"
            "FROM data\n"
            "WHERE col2 REGEXP_LIKE('[0-9]+')\n"
            "GROUP BY col2"
        )
        result = normalize(sql)
        # Should not raise
        ast = sqlglot.parse_one(result, dialect="tsql")
        assert ast is not None

    def test_import_from_parses(self):
        try:
            import sqlglot
        except ImportError:
            import pytest
            pytest.skip("sqlglot not installed")

        sql = (
            "SELECT col1 FROM (\n"
            "    IMPORT FROM JDBC AT CON_ANALYTICS\n"
            "    STATEMENT 'SELECT 1'\n"
            ")"
        )
        result = normalize(sql)
        ast = sqlglot.parse_one(result, dialect="tsql")
        assert ast is not None

    def test_group_concat_parses(self):
        try:
            import sqlglot
        except ImportError:
            import pytest
            pytest.skip("sqlglot not installed")

        sql = "SELECT GROUP_CONCAT(DISTINCT col ORDER BY col SEPARATOR '|') FROM t"
        result = normalize(sql)
        ast = sqlglot.parse_one(result, dialect="tsql")
        assert ast is not None
