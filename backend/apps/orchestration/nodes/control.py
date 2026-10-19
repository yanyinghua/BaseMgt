"""流程控制类节点：条件分支、循环、变量赋值、子流程、人工任务。"""
from ..context import compare, render_expr
from ..registry import register
from .base import BaseNode, NodeResult


@register
class BranchNode(BaseNode):
    """分支：按条件走不同出边。"""

    type = "branch"
    label = "条件分支"
    category = "流程控制"
    icon = "⑂"
    handles = ["true", "false"]
    config_schema = [
        {
            "key": "rules", "label": "判断规则", "type": "rules", "default": [],
            "help": "按顺序匹配，命中则走 handle 对应的出边",
        },
        {"key": "else_handle", "label": "未命中走", "type": "text", "default": "false"},
    ]

    def execute(self, ctx, config):
        for rule in config.get("rules") or []:
            left = render_expr(rule.get("var", ""), ctx.scope)
            right = ctx.render(rule.get("value"))
            try:
                hit = compare(left, rule.get("op", "eq"), right)
            except Exception as exc:
                raise ValueError(f"规则判断失败 [{rule.get('var')} {rule.get('op')}]: {exc}") from exc
            if hit:
                handle = rule.get("handle") or "true"
                ctx.log(f"命中规则 {rule.get('var')} {rule.get('op')} {right} -> {handle}")
                return NodeResult(output={"matched": handle}, handles=[handle])
        handle = config.get("else_handle") or "false"
        ctx.log(f"未命中任何规则 -> {handle}")
        return NodeResult(output={"matched": handle}, handles=[handle])


@register
class LoopNode(BaseNode):
    """循环：遍历数组，重复执行 body 分支。"""

    type = "loop"
    label = "循环"
    category = "流程控制"
    icon = "↻"
    handles = ["body", "done"]
    config_schema = [
        {"key": "source", "label": "数据源表达式", "type": "text", "default": "{{ vars.items }}"},
        {"key": "item_var", "label": "元素变量", "type": "text", "default": "item"},
        {"key": "index_var", "label": "索引变量", "type": "text", "default": ""},
        {"key": "max_iter", "label": "最大次数", "type": "number", "default": 500},
    ]

    def execute(self, ctx, config):
        items = render_expr(config.get("source") or "", ctx.scope)
        if items is None:
            items = []
        if not isinstance(items, (list, tuple)):
            items = [items]
        ctx.loop_items = list(items)
        ctx.log(f"循环 {len(ctx.loop_items)} 次")
        return NodeResult(output={"count": len(ctx.loop_items)}, handles=["body"])


@register
class TransformNode(BaseNode):
    """赋值：给上下文变量赋值，用于数据映射。"""

    type = "transform"
    label = "变量赋值"
    category = "流程控制"
    icon = "≔"
    config_schema = [
        {"key": "assignments", "label": "赋值列表", "type": "assignments", "default": [],
         "help": "每项 {var: '变量名', value: '表达式或常量'}"},
    ]

    def execute(self, ctx, config):
        values = {}
        for item in config.get("assignments") or []:
            name = item.get("var")
            if not name:
                continue
            value = ctx.render(item.get("value"))
            ctx.set_var(name, value)
            values[name] = value
        return NodeResult(output=values)


@register
class SubflowNode(BaseNode):
    """子流程：调用另一个编排定义。"""

    type = "subflow"
    label = "子流程"
    category = "流程控制"
    icon = "⊂"
    config_schema = [
        {"key": "definition_key", "label": "编排标识", "type": "text", "default": ""},
        {"key": "version", "label": "版本(空=最新)", "type": "number", "default": None},
        {"key": "input", "label": "入参映射", "type": "mapping", "default": {}},
        {"key": "assign_var", "label": "赋值变量", "type": "text", "default": ""},
        {"key": "continue_on_error", "label": "出错继续", "type": "switch", "default": False},
    ]

    def execute(self, ctx, config):
        from ..engine import run_definition_by_key
        from ..models import Definition

        key = config.get("definition_key")
        query = Definition.objects.filter(key=key, status="published")
        version = config.get("version")
        if version:
            query = query.filter(version=version)
        definition = query.order_by("-version").first()
        if definition is None:
            raise ValueError(f"未找到已发布的编排: {key}")
        payload = ctx.render(config.get("input") or {})
        ctx.log(f"调用子流程 {key} v{definition.version}")
        child = run_definition_by_key(key, payload, trigger="subflow", parent_run=ctx.run)
        if child.status != "success":
            raise RuntimeError(f"子流程执行失败: {child.error}")
        if config.get("assign_var"):
            ctx.set_var(config["assign_var"], child.output)
        return NodeResult(output=child.output, message=f"子流程 Run#{child.id}")


@register
class HumanTaskNode(BaseNode):
    """人工任务：生成待办并挂起运行，处理完成后继续。"""

    type = "human_task"
    label = "人工任务"
    category = "流程控制"
    icon = "☺"
    handles = ["approve", "reject"]
    config_schema = [
        {"key": "title", "label": "标题", "type": "text", "default": "待办"},
        {"key": "description", "label": "说明", "type": "textarea", "default": ""},
        {"key": "assignee", "label": "处理人(用户名)", "type": "text", "default": ""},
        {"key": "form_schema", "label": "表单字段", "type": "json", "default": []},
        {"key": "actions", "label": "可选动作", "type": "json", "default": ["approve", "reject"]},
        {"key": "output_var", "label": "结果变量", "type": "text", "default": "task"},
    ]

    def execute(self, ctx, config):
        from django.contrib.auth import get_user_model

        from ..models import HumanTask

        assignee = None
        username = ctx.render(config.get("assignee") or "")
        if username:
            assignee = get_user_model().objects.filter(username=username).first()
        task = HumanTask.objects.create(
            run=ctx.run,
            node_run=ctx.node_run,
            node_id=ctx.node_id,
            title=ctx.render(config.get("title") or "待办"),
            description=ctx.render(config.get("description") or ""),
            assignee=assignee,
            form_schema=config.get("form_schema") or [],
        )
        ctx.pending_task = task
        ctx.log(f"生成人工任务 #{task.id}，等待处理")
        return NodeResult(status="suspended", output={"task_id": task.id})
