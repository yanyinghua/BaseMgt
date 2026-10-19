"""数据源访问层：连接、查询、存储过程调用与目录同步。

只实现 PostgreSQL（psycopg2）；MySQL 需安装 pymysql 后按同样接口扩展。
"""
import hashlib
import time
from contextlib import contextmanager

from django.conf import settings
from django.utils import timezone

from .models import StoredProcedure, StoredProcedureVersion

# 简单连接缓存：{data_source_id: (conn, expire_ts)}
_CONN_CACHE = {}


def _cache_key(ds):
    return f"{ds.id}:{ds.engine}:{ds.host}:{ds.port}:{ds.database}:{ds.username}"


def _make_conn(ds):
    if ds.engine == "postgres":
        import psycopg2
        import psycopg2.extras

        kwargs = dict(
            host=ds.host,
            port=ds.port,
            dbname=ds.database,
            user=ds.username,
            password=ds.get_password(),
        )
        kwargs.update(ds.options or {})
        timeout = int(getattr(settings, "BM_SQL_TIMEOUT_MS", 0) or 0)
        if timeout > 0:
            kwargs.setdefault("options", f"-c statement_timeout={timeout}")
        conn = psycopg2.connect(**kwargs)
        conn.autocommit = False
        return conn
    if ds.engine == "mysql":
        import pymysql  # noqa: F401  需额外安装

        return pymysql.connect(
            host=ds.host,
            port=ds.port,
            database=ds.database,
            user=ds.username,
            password=ds.get_password(),
            **(ds.options or {}),
        )
    raise ValueError(f"暂不支持的数据源类型: {ds.engine}")


@contextmanager
def connection(ds, reuse=True):
    """获取一个连接；默认复用缓存连接，出错时自动重连一次。"""
    ttl = getattr(settings, "BM_CONN_TTL", 300)
    key = _cache_key(ds)
    conn = None
    if reuse and ttl > 0:
        cached = _CONN_CACHE.get(key)
        if cached and cached[1] > time.time():
            conn = cached[0]
    if conn is None:
        conn = _make_conn(ds)
        if ttl > 0:
            _CONN_CACHE[key] = (conn, time.time() + ttl)
    try:
        yield conn
    except Exception:
        # 连接可能已失效，丢弃缓存后让异常继续向上抛
        try:
            conn.close()
        except Exception:
            pass
        _CONN_CACHE.pop(key, None)
        raise


def reset_conn_cache(ds_id=None):
    if ds_id is None:
        for key, (conn, _) in list(_CONN_CACHE.items()):
            try:
                conn.close()
            except Exception:
                pass
        _CONN_CACHE.clear()
        return
    for key in [k for k in _CONN_CACHE if k.startswith(f"{ds_id}:")]:
        conn, _ = _CONN_CACHE.pop(key)
        try:
            conn.close()
        except Exception:
            pass


def get_default_data_source():
    from .models import DataSource

    ds = DataSource.objects.filter(is_default=True, status="active").first()
    if ds is None:
        ds = DataSource.objects.filter(status="active").first()
    if ds is None:
        raise ValueError("尚未配置任何可用数据源")
    return ds


def get_data_source(key=None):
    from .models import DataSource

    if key:
        return DataSource.objects.get(key=key, status="active")
    return get_default_data_source()


def _rows_to_dicts(cursor):
    if not cursor.description:
        return []
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def query(ds, sql, params=None, fetch="all", commit=True):
    """执行 SQL。

    fetch: none(不取结果) / one / all / scalar / column
    """
    with connection(ds) as conn:
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            if fetch == "none":
                result = {"rowcount": cur.rowcount}
            elif fetch == "one":
                rows = _rows_to_dicts(cur)
                result = rows[0] if rows else None
            elif fetch == "scalar":
                row = cur.fetchone()
                result = row[0] if row else None
            elif fetch == "column":
                result = [r[0] for r in cur.fetchall()]
            else:
                result = _rows_to_dicts(cur)
            if commit:
                conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def execute_ddl(ds, ddl):
    """执行 DDL/DML 脚本并提交。"""
    with connection(ds) as conn:
        cur = conn.cursor()
        try:
            cur.execute(ddl)
            conn.commit()
            return {"rowcount": cur.rowcount}
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def call_procedure(ds, schema, name, args=None, kind="procedure", returns_rows=True):
    """调用存储过程/函数。

    procedure -> CALL schema.name(...)
    function  -> SELECT * FROM schema.name(...)
    """
    args = args or []
    placeholders = ", ".join(["%s"] * len(args))
    qualified = f'"{schema}"."{name}"' if schema else f'"{name}"'
    if kind == "function":
        sql = f"SELECT * FROM {qualified}({placeholders})"
    else:
        sql = f"CALL {qualified}({placeholders})"
    with connection(ds) as conn:
        cur = conn.cursor()
        try:
            cur.execute(sql, args)
            rows = _rows_to_dicts(cur) if returns_rows and cur.description else []
            conn.commit()
            return {"sql": sql, "rows": rows, "rowcount": cur.rowcount}
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


# ---------- 目录同步 ----------

LIST_PROC_SQL = """
SELECT n.nspname AS schema, p.proname AS name, p.prokind,
       pg_get_function_arguments(p.oid)  AS arguments,
       pg_get_function_result(p.oid)     AS result,
       pg_get_functiondef(p.oid)         AS ddl,
       d.description                     AS description
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
LEFT JOIN pg_description d ON d.objoid = p.oid
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND p.prokind IN ('p', 'f')
  AND (%(schema)s IS NULL OR n.nspname = %(schema)s)
ORDER BY n.nspname, p.proname
"""

DETAIL_PROC_SQL = """
SELECT p.oid, p.prokind, p.proargnames, p.proargmodes,
       pg_get_function_arguments(p.oid) AS arguments,
       pg_get_function_result(p.oid)    AS result,
       pg_get_functiondef(p.oid)        AS ddl,
       d.description                    AS description,
       (SELECT array_agg(format_type(u.typ, NULL) ORDER BY u.ord)
          FROM unnest(COALESCE(p.proallargtypes, p.proargtypes::oid[]))
               WITH ORDINALITY AS u(typ, ord)) AS arg_types
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
LEFT JOIN pg_description d ON d.objoid = p.oid
WHERE n.nspname = %(schema)s AND p.proname = %(name)s
ORDER BY p.oid
"""

LIST_SCHEMAS_SQL = """
SELECT nspname AS name FROM pg_namespace
WHERE nspname NOT IN ('pg_catalog', 'information_schema') AND nspname NOT LIKE 'pg_toast%'
ORDER BY nspname
"""

LIST_TABLES_SQL = """
SELECT table_schema AS schema, table_name AS name, table_type AS type
FROM information_schema.tables
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
  AND (%(schema)s IS NULL OR table_schema = %(schema)s)
ORDER BY table_schema, table_name
"""

LIST_COLUMNS_SQL = """
SELECT column_name, data_type, is_nullable, ordinal_position
FROM information_schema.columns
WHERE table_schema = %(schema)s AND table_name = %(table)s
ORDER BY ordinal_position
"""

MODE_MAP = {"i": "IN", "o": "OUT", "b": "INOUT", "v": "VARIADIC", "t": "TABLE"}


def list_schemas(ds):
    return query(ds, LIST_SCHEMAS_SQL, {"schema": None}, fetch="all")


def list_tables(ds, schema=None):
    return query(ds, LIST_TABLES_SQL, {"schema": schema}, fetch="all")


def list_columns(ds, schema, table):
    return query(ds, LIST_COLUMNS_SQL, {"schema": schema, "table": table}, fetch="all")


def fetch_definition(ds, schema, name):
    """从数据库里取回某个存储过程/函数的定义与参数。"""
    rows = query(ds, DETAIL_PROC_SQL, {"schema": schema, "name": name}, fetch="all")
    if not rows:
        return None
    row = rows[0]
    names = row["proargnames"] or []
    modes = row["proargmodes"] or []
    types = row["arg_types"] or []
    params = []
    for idx, pname in enumerate(names):
        if idx >= len(types):
            break
        mode = MODE_MAP.get(modes[idx], "IN") if idx < len(modes) else "IN"
        params.append({"name": pname or f"arg{idx + 1}", "mode": mode, "type": types[idx]})
    kind = "procedure" if row["prokind"] == "p" else "function"
    return {
        "kind": kind,
        "arguments": row["arguments"],
        "result": row["result"],
        "ddl": row["ddl"],
        "description": row["description"] or "",
        "params": params,
    }


def sync_procedures(ds, schemas=None, user=None):
    """把目标库里已有的存储过程同步进目录（不覆盖本地未下发的修改，只补新增/更新 DDL 版本）。"""
    schemas = schemas or [r["name"] for r in list_schemas(ds)]
    created, updated = [], []
    for schema in schemas:
        rows = query(ds, LIST_PROC_SQL, {"schema": schema}, fetch="all")
        for row in rows:
            detail = fetch_definition(ds, row["schema"], row["name"])
            if not detail:
                continue
            proc, is_new = StoredProcedure.objects.get_or_create(
                data_source=ds,
                schema=row["schema"],
                name=row["name"],
                signature=row["arguments"] or "",
                defaults={
                    "kind": detail["kind"],
                    "returns": detail["result"] or "",
                    "params": detail["params"],
                    "description": detail["description"],
                    "status": "deployed",
                },
            )
            if not is_new:
                proc.kind = detail["kind"]
                proc.returns = detail["result"] or ""
                proc.params = detail["params"]
                proc.status = "deployed"
            latest = proc.versions.order_by("-version").first()
            if latest is None or latest.ddl.strip() != detail["ddl"].strip():
                version = (latest.version if latest else 0) + 1
                ver = StoredProcedureVersion.objects.create(
                    procedure=proc,
                    version=version,
                    ddl=detail["ddl"],
                    change_note="由数据库同步",
                    status="deployed",
                    applied_at=timezone.now(),
                )
                proc.current_version = ver
                proc.deployed_at = timezone.now()
                updated.append(proc.id)
            else:
                proc.current_version = latest
            proc.save()
            if is_new:
                created.append(proc.id)
    return {"created": len(created), "updated": len(updated)}


def apply_procedure_version(version, user=None):
    """把某个版本的 DDL 下发到目标库。"""
    proc = version.procedure
    execute_ddl(proc.data_source, version.ddl)
    version.status = "deployed"
    version.applied_at = timezone.now()
    version.save(update_fields=["status", "applied_at", "updated_at"])

    detail = fetch_definition(proc.data_source, proc.schema, proc.name)
    if detail:
        proc.kind = detail["kind"]
        proc.signature = detail["arguments"] or ""
        proc.returns = detail["result"] or ""
        proc.params = detail["params"]
    proc.current_version = version
    proc.status = "deployed"
    proc.deployed_at = timezone.now()
    proc.save()
    return proc


def drop_procedure(proc):
    kind_word = "PROCEDURE" if proc.kind == "procedure" else "FUNCTION"
    execute_ddl(proc.data_source, f'DROP {kind_word} IF EXISTS "{proc.schema}"."{proc.name}"({proc.signature})')
    proc.status = "dropped"
    proc.save(update_fields=["status", "updated_at"])
    return proc


def ddl_checksum(ddl):
    return hashlib.md5((ddl or "").encode("utf-8")).hexdigest()
