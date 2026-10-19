"""HTTP 调用与脚本节点。"""
import json

from ..registry import register
from .base import BaseNode, NodeResult

SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict, "enumerate": enumerate,
    "float": float, "int": int, "len": len, "list": list, "max": max, "min": min, "range": range,
    "round": round, "set": set, "sorted": sorted, "str": str, "sum": sum, "tuple": tuple, "zip": zip,
    "True": True, "False": False, "None": None,
}


@register
class HttpNode(BaseNode):
    """HTTP：调用外部接口（或另一个编排发布的接口）。"""

    type = "http"
    label = "HTTP 请求"
    category = "集成"
    icon = "⇄"
    config_schema = [
        {"key": "method", "label": "方法", "type": "select", "default": "POST",
         "options": [{"label": "GET", "value": "GET"}, {"label": "POST", "value": "POST"},
                     {"label": "PUT", "value": "PUT"}, {"label": "DELETE", "value": "DELETE"}]},
        {"key": "url", "label": "地址", "type": "text", "default": ""},
        {"key": "headers", "label": "请求头", "type": "json", "default": {}},
        {"key": "body", "label": "请求体", "type": "code", "lang": "json", "default": ""},
        {"key": "timeout", "label": "超时(秒)", "type": "number", "default": 30},
        {"key": "assign_var", "label": "赋值变量", "type": "text", "default": ""},
        {"key": "continue_on_error", "label": "出错继续", "type": "switch", "default": False},
    ]

    def execute(self, ctx, config):
        import requests

        method = (config.get("method") or "POST").upper()
        url = ctx.render(config.get("url") or "")
        headers = ctx.render(config.get("headers") or {})
        timeout = int(config.get("timeout") or 30)
        body = ctx.render(config.get("body") or "")
        kwargs = {"headers": headers, "timeout": timeout}
        if body:
            if isinstance(body, (dict, list)):
                kwargs["json"] = body
            else:
                try:
                    kwargs["json"] = json.loads(body)
                except (ValueError, TypeError):
                    kwargs["data"] = str(body)
        ctx.log(f"{method} {url}")
        resp = requests.request(method, url, **kwargs)
        try:
            data = resp.json()
        except ValueError:
            data = resp.text
        output = {"status_code": resp.status_code, "body": data}
        if config.get("assign_var"):
            ctx.set_var(config["assign_var"], output)
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {data}")
        return NodeResult(output=output)


@register
class ScriptNode(BaseNode):
    """脚本：执行一段 Python，可用 sql()/log() 等内置函数。

    可用变量：vars / input / node / env / item；把结果赋给 result。
    """

    type = "script"
    label = "Python 脚本"
    category = "集成"
    icon = "{ }"
    config_schema = [
        {"key": "code", "label": "代码", "type": "code", "lang": "python", "default": "# 结果放入 result\nresult = {'ok': True}"},
        {"key": "assign_var", "label": "赋值变量", "type": "text", "default": ""},
    ]

    def execute(self, ctx, config):
        from django.conf import settings

        if not getattr(settings, "BM_ENABLE_SCRIPT_NODE", False):
            raise PermissionError("脚本节点已被平台关闭（BM_ENABLE_SCRIPT_NODE=0）")

        def _sql(query, params=None, datasource=None, fetch="all"):
            from apps.catalog import services

            ds = services.get_data_source(datasource or (config.get("datasource") or None))
            return services.query(ds, query, params, fetch=fetch)

        def _call(schema, name, args=None, kind="procedure", datasource=None):
            from apps.catalog import services

            ds = services.get_data_source(datasource or (config.get("datasource") or None))
            return services.call_procedure(ds, schema, name, args or [], kind=kind)

        scope = ctx.scope
        sandbox = {
            "__builtins__": SAFE_BUILTINS,
            "vars": scope["vars"],
            "input": scope["input"],
            "node": scope["node"],
            "env": scope["env"],
            "item": scope.get("item"),
            "result": None,
            "log": ctx.log,
            "sql": _sql,
            "call": _call,
            "json": json,
            "set_var": ctx.set_var,
        }
        exec(compile(config.get("code") or "", "<script-node>", "exec"), sandbox)  # noqa: S102
        output = sandbox.get("result")
        if config.get("assign_var"):
            ctx.set_var(config["assign_var"], output)
        return NodeResult(output=output)
