"""SQL 控制台的语句护栏。

目标：避免控制台被当成"随手执行 DDL/DML"的入口（DDL 请走存储过程版本下发）。
- 始终禁止多语句（分号）
- 默认只读：仅允许 SELECT / WITH / EXPLAIN / SHOW / VALUES / TABLE
- 需要写操作时开启 BM_SQL_CONSOLE_WRITE=1，此时允许 INSERT/UPDATE/DELETE
- DROP / ALTER / TRUNCATE / CREATE / GRANT / REVOKE / COPY 任何模式都拒绝
"""
import re

READONLY_HEAD = ("select", "with", "explain", "show", "values", "table", "describe")
DML_KEYWORDS = ("insert", "update", "delete")
ALWAYS_BLOCKED = (
    "drop", "alter", "truncate", "create", "grant", "revoke", "copy",
    "comment", "set ", "begin", "commit", "rollback", "pg_sleep", "dblink",
)
_COMMENT_RE = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.S)
_WORD_RE = re.compile(r"[a-z_][a-z0-9_]*")


def strip_comments(sql):
    return _COMMENT_RE.sub(" ", sql or "")


def check_sql(sql, allow_write=False):
    """返回 (ok, reason)。"""
    text = strip_comments(sql).strip().rstrip(";").strip()
    if not text:
        return False, "SQL 为空"
    if ";" in text:
        return False, "控制台禁止一次执行多条语句"
    lowered = text.lower()
    for word in _WORD_RE.findall(lowered):
        if word in ALWAYS_BLOCKED:
            return False, f"控制台禁止执行 {word.upper()} 语句（DDL 请通过存储过程下发）"
    head = lowered.split()[0] if lowered.split() else ""
    if head in DML_KEYWORDS and not allow_write:
        return False, f"控制台当前为只读模式，禁止 {head.upper()}（设置 BM_SQL_CONSOLE_WRITE=1 可放开）"
    if head not in READONLY_HEAD and head not in DML_KEYWORDS:
        return False, f"不支持的语句类型：{head.upper()}"
    return True, ""
