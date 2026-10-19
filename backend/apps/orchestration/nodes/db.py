"""数据库类节点：SQL 查询、存储过程调用。"""
from ..registry import register
from .base import BaseNode, NodeResult, resolve_data_source


@register
class SqlNode(BaseNode):
    """SQL：在指定数据源上执行 SQL，结果可赋值给变量。"""

    type = "sql"
    label = "SQL 查询"
    category = "数据"
    icon = "⟢"
    config_schema = [
        {"key": "datasource", "label": "数据源", "type": "datasource", "default": ""},
        {"key": "sql", "label": "SQL", "type": "code", "lang": "sql", "default": ""},
        {"key": "params", "label": "参数", "type": "json", "default": [], "help": "按顺序替换 %s，支持表达式"},
        {"key": "scope_key", "label": "数据范围(行级)", "type": "text", "default": "",
         "help": "留空不限制；填写后在结果外层按角色数据范围追加 WHERE"},
        {"key": "fetch", "label": "取数方式", "type": "select", "default": "all",
         "options": [{"label": "多行", "value": "all"}, {"label": "单行", "value": "one"},
                     {"label": "标量", "value": "scalar"}, {"label": "不取", "value": "none"}]},
        {"key": "assign_var", "label": "赋值变量", "type": "text", "default": ""},
        {"key": "continue_on_error", "label": "出错继续", "type": "switch", "default": False},
    ]

    def execute(self, ctx, config):
        from apps.catalog import services

        ds = resolve_data_source(config, ctx)
        sql = ctx.render(config.get("sql") or "")
        params = ctx.render(config.get("params") or [])
        fetch = config.get("fetch") or "all"
        scope = ctx.row_scope(config.get("scope_key"))
        if scope:
            sql = f"SELECT * FROM ({sql.rstrip().rstrip(';')}) __bm_scope WHERE {scope}"
            ctx.log(f"应用数据范围: {scope}")
        ctx.log(f"[{ds.key}] {sql}")
        result = services.query(ds, sql, params or None, fetch=fetch)
        if config.get("assign_var"):
            ctx.set_var(config["assign_var"], result)
        return NodeResult(output={"rows": result, "rowcount": len(result) if isinstance(result, list) else None})


@register
class ProcedureNode(BaseNode):
    """存储过程：CALL schema.proc(...) 或 SELECT * FROM schema.func(...)。"""

    type = "procedure"
    label = "存储过程"
    category = "数据"
    icon = "⚙"
    config_schema = [
        {"key": "proc_id", "label": "目录中的存储过程", "type": "procedure", "default": ""},
        {"key": "datasource", "label": "数据源", "type": "datasource", "default": ""},
        {"key": "schema", "label": "Schema", "type": "text", "default": "public"},
        {"key": "name", "label": "名称", "type": "text", "default": ""},
        {"key": "kind", "label": "类型", "type": "select", "default": "procedure",
         "options": [{"label": "PROCEDURE", "value": "procedure"}, {"label": "FUNCTION", "value": "function"}]},
        {"key": "args", "label": "参数", "type": "json", "default": [], "help": "位置参数数组，支持表达式"},
        {"key": "assign_var", "label": "赋值变量", "type": "text", "default": ""},
        {"key": "continue_on_error", "label": "出错继续", "type": "switch", "default": False},
    ]

    def execute(self, ctx, config):
        from apps.catalog import services
        from apps.catalog.models import StoredProcedure

        ds = None
        schema = config.get("schema") or "public"
        name = config.get("name") or ""
        kind = config.get("kind") or "procedure"
        if config.get("proc_id"):
            proc = StoredProcedure.objects.select_related("data_source").get(pk=config["proc_id"])
            ds = proc.data_source
            schema, name, kind = proc.schema, proc.name, proc.kind
        if ds is None:
            ds = resolve_data_source(config, ctx)
        args = ctx.render(config.get("args") or [])
        ctx.log(f"CALL {schema}.{name}({args})")
        result = services.call_procedure(ds, schema, name, args or [], kind=kind)
        if config.get("assign_var"):
            ctx.set_var(config["assign_var"], result)
        return NodeResult(output=result)
