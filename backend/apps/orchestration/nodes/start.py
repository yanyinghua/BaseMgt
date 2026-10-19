"""开始节点：运行入口，把入参放进上下文。"""

from ..registry import register
from .base import BaseNode, NodeResult


@register
class StartNode(BaseNode):
    """开始：运行的入口节点。"""

    type = "start"
    label = "开始"
    category = "流程控制"
    icon = "▶"
    config_schema = [
        {"key": "note", "label": "备注", "type": "text", "default": ""},
    ]

    def execute(self, ctx, config):
        ctx.log(f"开始执行，入参: {ctx.scope.get('input')}")
        return NodeResult(output=ctx.scope.get("input"))


@register
class EndNode(BaseNode):
    """结束：定义运行输出。"""

    type = "end"
    label = "结束"
    category = "流程控制"
    icon = "■"
    handles = []
    config_schema = [
        {
            "key": "output", "label": "输出映射", "type": "mapping", "default": {},
            "help": "如 {'code': '{{ vars.code }}', 'data': '{{ vars.rows }}'}",
        },
        {"key": "message", "label": "结束说明", "type": "text", "default": ""},
    ]

    def execute(self, ctx, config):
        output = ctx.render(config.get("output") or {})
        ctx.run.output = output
        ctx.run.save(update_fields=["output", "updated_at"])
        return NodeResult(output=output, handles=[], message=config.get("message") or "结束")
