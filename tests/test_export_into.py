"""Tests for EXPORT ... INTO SCRIPT normalization."""

from exasol_sql_normalizer.handlers.export_into import normalize_export_into


class TestExportIntoBasic:
    def test_export_with_ctes(self):
        sql = (
            "EXPORT(\n"
            "WITH params AS (SELECT 1 AS x)\n"
            "SELECT * FROM params\n"
            ")\n"
            "INTO SCRIPT DW_CLOUD_STORAGE_EXTENSION.EXPORT_PATH\n"
            "WITH\n"
            "BUCKET_PATH = 'gs://my-bucket/path/'\n"
            "DATA_FORMAT = 'PARQUET'\n"
            ";"
        )
        result = normalize_export_into(sql)
        assert "CREATE TABLE DW_CLOUD_STORAGE_EXTENSION.EXPORT_PATH AS" in result
        assert "WITH params AS (SELECT 1 AS x)" in result
        assert "SELECT * FROM params" in result
        assert "EXPORT(" not in result
        assert "INTO SCRIPT" not in result
        assert "BUCKET_PATH" not in result
        assert "PARQUET" not in result

    def test_export_simple_select(self):
        sql = (
            "EXPORT(\n"
            "SELECT a, b FROM my_table WHERE x > 1\n"
            ")\n"
            "INTO SCRIPT SCHEMA1.EXPORT_FUNC\n"
            "WITH\n"
            "KEY1 = 'val1'\n"
            ";"
        )
        result = normalize_export_into(sql)
        assert "CREATE TABLE SCHEMA1.EXPORT_FUNC AS" in result
        assert "SELECT a, b FROM my_table WHERE x > 1" in result
        assert "INTO SCRIPT" not in result
        assert "KEY1" not in result


class TestExportIntoEdgeCases:
    def test_export_keyword_in_string_literal(self):
        sql = "SELECT 'EXPORT(something)' AS label FROM t"
        result = normalize_export_into(sql)
        assert result == sql

    def test_no_export_passthrough(self):
        sql = "SELECT a, b FROM my_table WHERE x > 1"
        result = normalize_export_into(sql)
        assert result == sql

    def test_empty_string(self):
        assert normalize_export_into("") == ""

    def test_nested_parens_in_export_body(self):
        sql = (
            "EXPORT(\n"
            "SELECT CAST(a AS VARCHAR(100)), (SELECT MAX(b) FROM t2) AS mx\n"
            "FROM t1\n"
            "WHERE c IN (1, 2, 3)\n"
            ")\n"
            "INTO SCRIPT MY_SCHEMA.MY_EXPORT\n"
            "WITH\n"
            "PATH = '/data/out'\n"
            ";"
        )
        result = normalize_export_into(sql)
        assert "CREATE TABLE MY_SCHEMA.MY_EXPORT AS" in result
        assert "CAST(a AS VARCHAR(100))" in result
        assert "(SELECT MAX(b) FROM t2)" in result
        assert "WHERE c IN (1, 2, 3)" in result
        assert "INTO SCRIPT" not in result

    def test_multiple_with_pairs_stripped(self):
        sql = (
            "EXPORT(\n"
            "SELECT 1\n"
            ")\n"
            "INTO SCRIPT S.E\n"
            "WITH\n"
            "A = '1'\n"
            "B = '2'\n"
            "C = '3'\n"
            "D = '4'\n"
            ";"
        )
        result = normalize_export_into(sql)
        assert "CREATE TABLE S.E AS" in result
        assert "SELECT 1" in result
        assert "A = " not in result
        assert "B = " not in result
        assert "C = " not in result
        assert "D = " not in result

    def test_with_values_containing_special_chars(self):
        sql = (
            "EXPORT(\n"
            "SELECT 1\n"
            ")\n"
            "INTO SCRIPT S.E\n"
            "WITH\n"
            "BUCKET_PATH = 'gs://my-bucket/path/to/data/'\n"
            "CONNECTION = 'user=admin;pass=s3cr3t!@#'\n"
            ";"
        )
        result = normalize_export_into(sql)
        assert "CREATE TABLE S.E AS" in result
        assert "gs://my-bucket" not in result
        assert "s3cr3t" not in result

    def test_no_semicolon_at_end(self):
        sql = (
            "EXPORT(\n"
            "SELECT 1\n"
            ")\n"
            "INTO SCRIPT S.E\n"
            "WITH\n"
            "KEY = 'val'"
        )
        result = normalize_export_into(sql)
        assert "CREATE TABLE S.E AS" in result
        assert "SELECT 1" in result
        assert "KEY = " not in result

    def test_export_without_into_script_not_matched(self):
        sql = "EXPORT(SELECT 1) INTO TABLE foo"
        result = normalize_export_into(sql)
        assert result == sql
