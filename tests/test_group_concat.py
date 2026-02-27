"""Tests for Handler 3: GROUP_CONCAT SEPARATOR normalization."""

from exasol_sql_normalizer.handlers.group_concat import normalize_group_concat


class TestGroupConcatBasic:
    def test_simple_separator(self):
        sql = "SELECT GROUP_CONCAT(col SEPARATOR ',') FROM t"
        result = normalize_group_concat(sql)
        assert "SEPARATOR" not in result
        assert "GROUP_CONCAT(col)" in result

    def test_separator_with_pipe(self):
        sql = "SELECT GROUP_CONCAT(col SEPARATOR '|') FROM t"
        result = normalize_group_concat(sql)
        assert "SEPARATOR" not in result
        assert "GROUP_CONCAT(col)" in result

    def test_distinct_and_order_by(self):
        sql = "SELECT GROUP_CONCAT(DISTINCT col ORDER BY col SEPARATOR '|') FROM t"
        result = normalize_group_concat(sql)
        assert "SEPARATOR" not in result
        assert "DISTINCT col ORDER BY col" in result

    def test_separator_semicolon_space(self):
        sql = "SELECT group_concat(f.item_name order by f.item_id separator '; ') as item_name FROM t"
        result = normalize_group_concat(sql)
        assert "separator" not in result.lower()
        assert "f.item_name order by f.item_id" in result


class TestGroupConcatNested:
    def test_nested_functions(self):
        sql = (
            "SELECT group_concat(\n"
            "    DISTINCT trim(replace(t.name, '|', ','))\n"
            "    ORDER BY trim(t.name)\n"
            "    SEPARATOR '|') as names FROM t"
        )
        result = normalize_group_concat(sql)
        assert "SEPARATOR" not in result
        assert "trim(replace(t.name, '|', ','))" in result
        assert "ORDER BY trim(t.name)" in result

    def test_multiple_group_concats(self):
        sql = (
            "SELECT\n"
            "    group_concat(DISTINCT col1 SEPARATOR '|') as A,\n"
            "    group_concat(DISTINCT col2 ORDER BY col2 SEPARATOR ',') as B\n"
            "FROM t"
        )
        result = normalize_group_concat(sql)
        assert result.lower().count("separator") == 0
        assert "col1" in result
        assert "col2" in result


class TestGroupConcatEdgeCases:
    def test_separator_keyword_in_string_not_stripped(self):
        """SEPARATOR inside a string literal should not be affected."""
        sql = "SELECT 'GROUP_CONCAT SEPARATOR' AS label FROM t"
        result = normalize_group_concat(sql)
        assert result == sql

    def test_no_separator_unchanged(self):
        sql = "SELECT GROUP_CONCAT(col) FROM t"
        result = normalize_group_concat(sql)
        assert result == sql


class TestGroupConcatPassthrough:
    def test_standard_sql_unchanged(self):
        sql = "SELECT a, b FROM t WHERE x > 1"
        assert normalize_group_concat(sql) == sql

    def test_empty_string(self):
        assert normalize_group_concat("") == ""
