"""Tests for shared utility functions."""

from exasol_sql_normalizer.utils import (
    _cap_table_ref,
    extract_quoted_string,
    extract_tables_from_statement,
    is_inside_string,
    skip_quoted_string,
    skip_whitespace,
)


class TestExtractQuotedString:
    def test_simple_string(self):
        end, content = extract_quoted_string("'hello world'", 0)
        assert end == 13
        assert content == "hello world"

    def test_escaped_quotes(self):
        end, content = extract_quoted_string("'it''s a test'", 0)
        assert content == "it's a test"

    def test_empty_string(self):
        end, content = extract_quoted_string("''", 0)
        assert end == 2
        assert content == ""

    def test_not_at_quote(self):
        end, content = extract_quoted_string("hello", 0)
        assert end == 0
        assert content == ""

    def test_with_offset(self):
        end, content = extract_quoted_string("SELECT 'abc'", 7)
        assert content == "abc"

    def test_multiline_content(self):
        sql = "'\nSELECT a\nFROM t\n'"
        end, content = extract_quoted_string(sql, 0)
        assert "SELECT a" in content
        assert "FROM t" in content


class TestSkipQuotedString:
    def test_skips_past_closing_quote(self):
        assert skip_quoted_string("'hello' rest", 0) == 7

    def test_handles_escaped_quotes(self):
        assert skip_quoted_string("'it''s'", 0) == 7


class TestSkipWhitespace:
    def test_skips_spaces(self):
        assert skip_whitespace("   hello", 0) == 3

    def test_skips_tabs_newlines(self):
        assert skip_whitespace("\t\n\r hello", 0) == 4

    def test_no_whitespace(self):
        assert skip_whitespace("hello", 0) == 0


class TestIsInsideString:
    def test_outside_string(self):
        assert is_inside_string("SELECT 'a' FROM t", 15) is False

    def test_inside_string(self):
        assert is_inside_string("SELECT 'hello' FROM t", 9) is True

    def test_after_escaped_quote(self):
        assert is_inside_string("'it''s here'", 7) is True


class TestCapTableRef:
    def test_one_part_unchanged(self):
        assert _cap_table_ref("orders") == "orders"

    def test_two_parts_unchanged(self):
        assert _cap_table_ref("dbo.orders") == "dbo.orders"

    def test_three_parts_capped(self):
        assert _cap_table_ref("some_db.dbo.orders") == "dbo.orders"

    def test_four_parts_capped(self):
        assert _cap_table_ref("srv.db.dbo.tbl") == "dbo.tbl"

    def test_bracket_quoted_three_parts(self):
        result = _cap_table_ref("[some_db].[dbo].[orders]")
        assert result == "dbo.orders"

    def test_bracket_quoted_with_spaces(self):
        result = _cap_table_ref("[My DB].[dbo].[Order Details]")
        assert result == "dbo.[Order Details]"

    def test_two_part_bracket_unchanged(self):
        assert _cap_table_ref("[dbo].[orders]") == "[dbo].[orders]"


class TestExtractTablesFromStatement:
    def test_simple_from(self):
        tables = extract_tables_from_statement("SELECT a, b FROM remote_table")
        assert tables == ["remote_table"]

    def test_schema_qualified(self):
        tables = extract_tables_from_statement("SELECT a FROM dbo.orders")
        assert tables == ["dbo.orders"]

    def test_three_part_capped(self):
        tables = extract_tables_from_statement("SELECT a FROM some_db.dbo.orders")
        assert tables == ["dbo.orders"]

    def test_bracket_quoted(self):
        tables = extract_tables_from_statement("SELECT a FROM [dbo].[orders]")
        assert tables == ["[dbo].[orders]"]

    def test_bracket_three_part_capped(self):
        tables = extract_tables_from_statement(
            "SELECT a FROM [some_db].[dbo].[orders]"
        )
        assert tables == ["dbo.orders"]

    def test_join(self):
        tables = extract_tables_from_statement(
            "SELECT a FROM t1 INNER JOIN t2 ON t1.id = t2.id"
        )
        assert "t1" in tables
        assert "t2" in tables

    def test_left_outer_join(self):
        tables = extract_tables_from_statement(
            "SELECT a FROM t1 LEFT OUTER JOIN t2 ON t1.id = t2.id"
        )
        assert "t1" in tables
        assert "t2" in tables

    def test_multiple_joins(self):
        tables = extract_tables_from_statement(
            "SELECT a FROM t1 JOIN t2 ON 1=1 LEFT JOIN t3 ON 1=1"
        )
        assert len(tables) == 3

    def test_comma_separated(self):
        tables = extract_tables_from_statement(
            "SELECT a FROM t1, t2 WHERE t1.id = t2.id"
        )
        assert "t1" in tables
        assert "t2" in tables

    def test_no_from_returns_empty(self):
        tables = extract_tables_from_statement("SELECT 1")
        assert tables == []

    def test_empty_string_returns_empty(self):
        tables = extract_tables_from_statement("")
        assert tables == []

    def test_subquery_from_not_matched(self):
        """FROM followed by ( should not capture the paren as a table."""
        tables = extract_tables_from_statement(
            "SELECT a FROM (SELECT b FROM inner_t) sub"
        )
        # inner_t is extracted (a real dependency), but no '(' is captured
        assert "inner_t" in tables
        assert all("(" not in t for t in tables)

    def test_escaped_quotes_in_raw_input(self):
        """Input comes directly from the STATEMENT string (still escaped)."""
        tables = extract_tables_from_statement(
            "SELECT a FROM t WHERE name LIKE ''test%''"
        )
        assert tables == ["t"]

    def test_deduplicates(self):
        tables = extract_tables_from_statement(
            "SELECT a FROM t1 JOIN t1 ON 1=1"
        )
        assert tables == ["t1"]

    def test_with_alias(self):
        """Alias after table name should not be captured as a table."""
        tables = extract_tables_from_statement(
            "SELECT a FROM dbo.orders AS o"
        )
        assert tables == ["dbo.orders"]

    def test_union_extracts_both(self):
        tables = extract_tables_from_statement(
            "SELECT a FROM t1 UNION ALL SELECT b FROM t2"
        )
        assert "t1" in tables
        assert "t2" in tables
