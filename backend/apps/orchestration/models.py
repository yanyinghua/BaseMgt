"""编排领域模型。

Definition 编排定义（图）——节点与连线以 JSON 存放，便于画布自由编辑
Run        一次执行实例
NodeRun    节点级执行记录（日志/输入输出/耗时）
HumanTask  人工任务（业务流程编排里的待办）
"""
from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel
from apps.catalog.models import Module

KIND_CHOICES = [
    ("service", "服务/接口编排"),
    ("flow", "业务流程编排"),
    ("pipeline", "数据管道/定时任务"),
]

STATUS_DRAFT, STATUS_PUBLISHED, STATUS_DISABLED = "draft", "published", "disabled"


class Definition(TimeStampedModel):
    """一个可编排的业务单元。发布后可通过触发器运行。"""

    module = models.ForeignKey(
        Module, verbose_name="所属模块", null=True, blank=True, on_delete=models.SET_NULL, related_name="definitions"
    )
    key = models.SlugField("标识", max_length=100)
    name = models.CharField("名称", max_length=200)
    kind = models.CharField("编排类型", max_length=20, choices=KIND_CHOICES, default="service")
    version = models.IntegerField("版本", default=1)
    status = models.CharField(
        "状态", max_length=20, default=STATUS_DRAFT,
        choices=[(STATUS_DRAFT, "草稿"), (STATUS_PUBLISHED, "已发布"), (STATUS_DISABLED, "停用")],
    )
    # {"nodes":[{"id","type","name","config","position":{x,y}}], "edges":[{"id","source","sourceHandle","target"}]}
    graph = models.JSONField("流程图", default=dict, blank=True)
    # {"type":"manual|http|cron", "method":"POST", "path":"", "cron":"", "enabled":true}
    trigger = models.JSONField("触发器", default=dict, blank=True)
    # [{"name","label","type","required","default"}] 入参声明，用于生成调用表单与校验
    input_schema = models.JSONField("入参定义", default=list, blank=True)
    output_schema = models.JSONField("出参定义", default=dict, blank=True)
    description = models.TextField("说明", blank=True, default="")
    last_run_at = models.DateTimeField("最近运行时间", null=True, blank=True)
    last_schedule_at = models.DateTimeField("最近调度时间", null=True, blank=True)

    class Meta:
        verbose_name = "编排定义"
        verbose_name_plural = "编排定义"
        ordering = ["key", "-version"]
        unique_together = [("key", "version")]

    def __str__(self):
        return f"{self.name} v{self.version}"

    @property
    def nodes(self):
        return (self.graph or {}).get("nodes", [])

    @property
    def edges(self):
        return (self.graph or {}).get("edges", [])

    def find_start_node(self):
        for node in self.nodes:
            if node.get("type") in ("start", "trigger"):
                return node["id"]
        return self.nodes[0]["id"] if self.nodes else None

    def trigger_type(self):
        return (self.trigger or {}).get("type", "manual")


class Run(TimeStampedModel):
    """编排运行实例。"""

    STATUS_CHOICES = [
        ("pending", "等待中"),
        ("running", "运行中"),
        ("success", "成功"),
        ("failed", "失败"),
        ("suspended", "挂起"),
        ("cancelled", "已取消"),
    ]

    definition = models.ForeignKey(Definition, verbose_name="编排定义", on_delete=models.CASCADE, related_name="runs")
    parent_run = models.ForeignKey(
        "self", verbose_name="父运行", null=True, blank=True, on_delete=models.CASCADE, related_name="sub_runs"
    )
    status = models.CharField("状态", max_length=20, default="pending", choices=STATUS_CHOICES)
    trigger = models.CharField("触发方式", max_length=20, default="manual")
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="触发人", null=True, blank=True, on_delete=models.SET_NULL
    )
    # 执行时的定义快照，避免定义改动影响历史运行
    graph_snapshot = models.JSONField("流程快照", default=dict, blank=True)
    # 上下文：{"input":{}, "vars":{}, "node":{}, "env":{}}
    vars = models.JSONField("上下文", default=dict, blank=True)
    input = models.JSONField("入参", default=dict, blank=True)
    output = models.JSONField("出参", default=dict, blank=True)
    error = models.TextField("错误信息", blank=True, default="")
    current_node_id = models.CharField("挂起节点", max_length=100, blank=True, default="")
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    duration_ms = models.IntegerField("耗时(ms)", default=0)

    class Meta:
        verbose_name = "运行实例"
        verbose_name_plural = "运行实例"
        ordering = ["-id"]
        indexes = [models.Index(fields=["definition", "-id"]), models.Index(fields=["status"])]

    def __str__(self):
        return f"Run#{self.id} {self.definition.key}"


class NodeRun(TimeStampedModel):
    """节点执行记录。"""

    STATUS_CHOICES = [("running", "运行中"), ("success", "成功"), ("failed", "失败"), ("skipped", "跳过")]

    run = models.ForeignKey(Run, verbose_name="运行实例", on_delete=models.CASCADE, related_name="node_runs")
    node_id = models.CharField("节点ID", max_length=100)
    node_type = models.CharField("节点类型", max_length=50, blank=True, default="")
    node_name = models.CharField("节点名称", max_length=200, blank=True, default="")
    order = models.IntegerField("执行序号", default=0)
    status = models.CharField("状态", max_length=20, default="running", choices=STATUS_CHOICES)
    config = models.JSONField("节点配置", default=dict, blank=True)
    input = models.JSONField("输入", default=dict, blank=True)
    output = models.JSONField("输出", default=dict, blank=True)
    logs = models.JSONField("日志", default=list, blank=True)
    error = models.TextField("错误", blank=True, default="")
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    duration_ms = models.IntegerField("耗时(ms)", default=0)

    class Meta:
        verbose_name = "节点运行记录"
        verbose_name_plural = "节点运行记录"
        ordering = ["order", "id"]


class HumanTask(TimeStampedModel):
    """人工任务：业务流程编排挂起时产生的待办。"""

    STATUS_CHOICES = [("pending", "待处理"), ("done", "已处理")]

    run = models.ForeignKey(Run, verbose_name="运行实例", on_delete=models.CASCADE, related_name="human_tasks")
    node_run = models.ForeignKey(
        NodeRun, verbose_name="节点记录", null=True, blank=True, on_delete=models.SET_NULL, related_name="human_tasks"
    )
    node_id = models.CharField("节点ID", max_length=100, blank=True, default="")
    title = models.CharField("标题", max_length=200)
    description = models.TextField("说明", blank=True, default="")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="处理人",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="human_tasks",
    )
    form_schema = models.JSONField("表单定义", default=list, blank=True)
    status = models.CharField("状态", max_length=20, default="pending", choices=STATUS_CHOICES)
    action = models.CharField("处理结果(动作)", max_length=50, blank=True, default="")
    result = models.JSONField("结果数据", default=dict, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="处理人(实际)",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="decided_tasks",
    )
    decided_at = models.DateTimeField("处理时间", null=True, blank=True)

    class Meta:
        verbose_name = "人工任务"
        verbose_name_plural = "人工任务"
        ordering = ["-id"]
