"""Tests for Handler 5: REGEXP_LIKE infix normalization."""

from exasol_sql_normalizer.handlers.regexp_like import normalize_regexp_like


class TestRegexpLikeBasic:
    def test_simple_infix(self):
        sql = "SELECT * FROM t WHERE col REGEXP_LIKE('[0-9]+')"
        result = normalize_regexp_like(sql)
        assert "REGEXP_LIKE(col, '[0-9]+')" in result

    def test_qualified_column(self):
        sql = "SELECT * FROM t WHERE t.col REGEXP_LIKE('[0-9]+')"
        result = normalize_regexp_like(sql)
        assert "REGEXP_LIKE(t.col, '[0-9]+')" in result

    def test_with_and_clause(self):
        sql = "WHERE x = 1 AND l.OBJECT_ID REGEXP_LIKE('[0-9]+')"
        result = normalize_regexp_like(sql)
        assert "REGEXP_LIKE(l.OBJECT_ID, '[0-9]+')" in result
        assert "x = 1 AND" in result


class TestRegexpLikeEdgeCases:
    def test_already_function_syntax_unchanged(self):
        """REGEXP_LIKE already in function form should not be modified."""
        sql = "SELECT * FROM t WHERE REGEXP_LIKE(col, '[0-9]+')"
        result = normalize_regexp_like(sql)
        assert result == sql

    def test_regexp_like_in_string_not_matched(self):
        sql = "SELECT 'col REGEXP_LIKE pattern' AS label FROM t"
        result = normalize_regexp_like(sql)
        assert result == sql

    def test_with_comment_after(self):
        sql = "WHERE col REGEXP_LIKE('[0-9]+') --exclude edge cases"
        result = normalize_regexp_like(sql)
        assert "REGEXP_LIKE(col, '[0-9]+')" in result
        assert "--exclude edge cases" in result


class TestRegexpLikePassthrough:
    def test_standard_sql_unchanged(self):
        sql = "SELECT a, b FROM t WHERE x LIKE '%pattern%'"
        assert normalize_regexp_like(sql) == sql

    def test_empty_string(self):
        assert normalize_regexp_like("") == ""
