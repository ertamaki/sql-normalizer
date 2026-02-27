"""Tests for Handler 4: CONVERT with charset normalization."""

from exasol_sql_normalizer.handlers.convert import normalize_convert_charset


class TestConvertBasic:
    def test_simple_convert_utf8(self):
        sql = "SELECT CONVERT(VARCHAR(100) UTF8, some_column) FROM t"
        result = normalize_convert_charset(sql)
        assert "CAST(some_column AS VARCHAR(100))" in result
        assert "CONVERT" not in result
        assert "UTF8" not in result

    def test_convert_with_precision(self):
        sql = "SELECT CONVERT(VARCHAR(10000) UTF8, col1) FROM t"
        result = normalize_convert_charset(sql)
        assert "CAST(col1 AS VARCHAR(10000))" in result

    def test_convert_ascii(self):
        sql = "SELECT CONVERT(VARCHAR(100) ASCII, col1) FROM t"
        result = normalize_convert_charset(sql)
        assert "CAST(col1 AS VARCHAR(100))" in result

    def test_convert_with_nested_expr(self):
        sql = "SELECT CONVERT(VARCHAR(10000) UTF8, group_concat(DISTINCT col1 ORDER BY col1)) FROM t"
        result = normalize_convert_charset(sql)
        assert "CAST(group_concat(DISTINCT col1 ORDER BY col1) AS VARCHAR(10000))" in result

    def test_convert_decimal_type(self):
        sql = "SELECT CONVERT(DECIMAL(10,2) UTF8, col1) FROM t"
        result = normalize_convert_charset(sql)
        assert "CAST(col1 AS DECIMAL(10,2))" in result


class TestConvertEdgeCases:
    def test_tsql_convert_without_charset_unchanged(self):
        """T-SQL CONVERT without charset should NOT be rewritten."""
        sql = "SELECT CONVERT(VARCHAR(100), some_column) FROM t"
        result = normalize_convert_charset(sql)
        assert result == sql

    def test_multiple_converts(self):
        sql = (
            "SELECT\n"
            "    CONVERT(VARCHAR(100) UTF8, col1) AS a,\n"
            "    CONVERT(VARCHAR(200) UTF8, col2) AS b\n"
            "FROM t"
        )
        result = normalize_convert_charset(sql)
        assert "CAST(col1 AS VARCHAR(100))" in result
        assert "CAST(col2 AS VARCHAR(200))" in result
        assert "CONVERT" not in result

    def test_convert_keyword_in_string_not_matched(self):
        sql = "SELECT 'CONVERT(VARCHAR(100) UTF8, x)' AS label FROM t"
        result = normalize_convert_charset(sql)
        assert result == sql

    def test_convert_as_part_of_identifier_not_matched(self):
        sql = "SELECT MY_CONVERT(a, b) FROM t"
        result = normalize_convert_charset(sql)
        assert result == sql

    def test_lowercase_convert(self):
        sql = "SELECT convert(VARCHAR(10000) UTF8, col1) FROM t"
        result = normalize_convert_charset(sql)
        assert "CAST(col1 AS VARCHAR(10000))" in result


class TestConvertPassthrough:
    def test_standard_sql_unchanged(self):
        sql = "SELECT a, b FROM t WHERE x > 1"
        assert normalize_convert_charset(sql) == sql

    def test_empty_string(self):
        assert normalize_convert_charset("") == ""
