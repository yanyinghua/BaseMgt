"""节点插件基类。"""
from ..registry import register  # noqa: F401  供子类使用


class NodeResult:
    """节点执行结果。

    status: ok / failed / suspended
    handles: 要走哪些出边（对应边的 sourceHandle）
    """

    def __init__(self, status="ok", output=None, handles=None, message="", error=None):
        self.status = status
        self.output = output
        self.handles = handles or ["default"]
        self.message = message
        self.error = error


class BaseNode:
    type = "base"
    label = "基础节点"
    category = "通用"
    icon = "◆"
    # 属性面板的字段描述，前端按 type 渲染控件
    config_schema = []
    handles = ["default"]

    def execute(self, ctx, config):
        raise NotImplementedError


def cfg(config, key, default=None):
    value = config.get(key, default)
    return default if value in (None, "") and default is not None else value


def resolve_data_source(config, ctx=None):
    """按配置取得数据源：优先 proc_id 关联的数据源，其次 datasource key，最后默认数据源。"""
    from apps.catalog import services

    key = (config or {}).get("datasource") or ""
    return services.get_data_source(key or None)
