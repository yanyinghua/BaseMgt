"""主数据物理表 DDL 生成与差异同步。

原则：**只增不改不删**。已有列的类型不会被改写，删除/停用字段也不会自动 DROP COLUMN，
避免误伤生产数据；确需变更请手工确认后执行 preview 给出的建议 SQL。
"""
from apps.catalog import services

SYSTEM_TIMESTAMP_FIELDS = ["created_at", "updated_at"]


def sql_type(field):
    kind = field.data_type
    if kind == "char":
        return f"varchar({field.length or 64})"
    if kind == "text":
        return "text"
    if kind == "int":
        return "integer"
    if kind == "bigint":
        return "bigint"
    if kind == "decimal":
        return f"numeric({field.precision or 18},{field.scale or 2})"
    if kind == "date":
        return "date"
    if kind == "datetime":
        return "timestamp"
    if kind == "bool":
        return "boolean"
    if kind == "json":
        return "jsonb"
    if kind == "enum":
        return f"varchar({field.length or 32})"
    if kind == "ref":
        return "integer"
    raise ValueError(f"不支持的字段类型: {kind}")


def _column_ddl(field):
    parts = [f'"{field.name}"', sql_type(field)]
    if field.name == "id":
        return '"id" serial PRIMARY KEY'
    if not field.nullable:
        parts.append("NOT NULL")
    if field.default_value:
        parts.append(f"DEFAULT {field.default_value}")
    elif field.name in SYSTEM_TIMESTAMP_FIELDS:
        parts.append("DEFAULT now()")
    return " ".join(parts)


def active_fields(entity):
    return entity.fields.filter(status="active").order_by("sort_order", "id")


def create_table_sql(entity):
    """生成建表语句及注释。"""
    lines = [f'CREATE TABLE IF NOT EXISTS "{entity.schema}"."{entity.table_name}" (']
    columns = []
    uniques = []
    for field in active_fields(entity):
        columns.append("    " + _column_ddl(field))
        if field.unique and field.name != "id":
            uniques.append(field)
    lines.append(",\n".join(columns))
    lines.append(");")
    stmts = ["\n".join(lines)]

    stmts.append(
        f'COMMENT ON TABLE "{entity.schema}"."{entity.table_name}" IS '
        f"'{_escape(entity.name)}';"
    )
    for field in active_fields(entity):
        if field.label:
            stmts.append(
                f'COMMENT ON COLUMN "{entity.schema}"."{entity.table_name}"."{field.name}" '
                f"IS '{_escape(field.label)}';"
            )
    stmts += index_sql(entity, include_all=True)
    return stmts


def index_sql(entity, include_all=False):
    stmts = []
    for field in active_fields(entity):
        if field.name == "id":
            continue
        if include_all and field.unique:
            stmts.append(
                f'CREATE UNIQUE INDEX IF NOT EXISTS uq_{entity.table_name}_{field.name} '
                f'ON "{entity.schema}"."{entity.table_name}" ("{field.name}");'
            )
        elif include_all and field.indexed:
            stmts.append(
                f'CREATE INDEX IF NOT EXISTS idx_{entity.table_name}_{field.name} '
                f'ON "{entity.schema}"."{entity.table_name}" ("{field.name}");'
            )
    return stmts


def existing_columns(entity):
    return columns_of(entity.data_source, entity.schema, entity.table_name)


def columns_of(data_source, schema, table):
    try:
        rows = services.list_columns(data_source, schema, table)
    except Exception:  # noqa: BLE001  表不存在
        return None
    return {r["column_name"]: r for r in rows} if rows else None


def table_exists(entity):
    return existing_columns(entity) is not None


# ---------- 变更审计表 ----------

AUDIT_TABLE = "mdm_data_change_log"


def audit_table_sql(entity):
    """主数据字段级变更日志表（所有主数据共用一张，落在同一个库里）。"""
    table = f'"{entity.schema}"."{AUDIT_TABLE}"'
    return f"""
CREATE TABLE IF NOT EXISTS {table} (
    id          bigserial PRIMARY KEY,
    entity_key  varchar(64)  NOT NULL,
    record_id   integer,
    action      varchar(20)  NOT NULL,
    field_name  varchar(100) NOT NULL,
    old_value   text,
    new_value   text,
    operator    varchar(64),
    changed_at  timestamp DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mdm_log_entity ON {table} (entity_key, record_id);
CREATE INDEX IF NOT EXISTS idx_mdm_log_time ON {table} (changed_at DESC);
"""


def audit_table_exists(entity):
    return columns_of(entity.data_source, entity.schema, AUDIT_TABLE) is not None


def diff_sql(entity):
    """计算结构差异：返回 (是否需建表, sql列表, 提示列表)。"""
    cols = existing_columns(entity)
    if cols is None:
        return True, create_table_sql(entity), ["表不存在，将新建"]

    missing = [f for f in active_fields(entity) if f.name not in cols]
    stmts, notes = [], []
    for field in missing:
        stmts.append(
            f'ALTER TABLE "{entity.schema}"."{entity.table_name}" '
            f'ADD COLUMN "{field.name}" {sql_type(field)};'
        )
        if field.label:
            stmts.append(
                f'COMMENT ON COLUMN "{entity.schema}"."{entity.table_name}"."{field.name}" '
                f"IS '{_escape(field.label)}';"
            )
        if field.unique:
            stmts.append(
                f'CREATE UNIQUE INDEX IF NOT EXISTS uq_{entity.table_name}_{field.name} '
                f'ON "{entity.schema}"."{entity.table_name}" ("{field.name}");'
            )
        elif field.indexed:
            stmts.append(
                f'CREATE INDEX IF NOT EXISTS idx_{entity.table_name}_{field.name} '
                f'ON "{entity.schema}"."{entity.table_name}" ("{field.name}");'
            )
        notes.append(f"新增列 {field.name} ({field.label})")

    # 已停用/删除的字段不自动删除列，只提示
    active_names = {f.name for f in active_fields(entity)}
    for name in cols:
        if name in SYSTEM_TIMESTAMP_FIELDS or name == "id":
            continue
        if name not in active_names:
            notes.append(f"库中列 {name} 已无对应字段定义，未自动删除（手工确认后再 DROP）")
    return False, stmts, notes


def _escape(text):
    return (text or "").replace("'", "''")
