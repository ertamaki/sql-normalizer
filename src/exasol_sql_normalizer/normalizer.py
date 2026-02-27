from .handlers import (
    normalize_import_into,
    normalize_import_from,
    normalize_group_concat,
    normalize_convert_charset,
    normalize_regexp_like,
)


def normalize(sql: str) -> str:
    """Rewrite Exasol-specific SQL into standard SQL.

    Handler execution order matters: GROUP_CONCAT must run before CONVERT
    because CONVERT often wraps GROUP_CONCAT expressions.
    """
    sql = normalize_import_into(sql)
    sql = normalize_import_from(sql)
    sql = normalize_group_concat(sql)
    sql = normalize_convert_charset(sql)
    sql = normalize_regexp_like(sql)
    return sql
