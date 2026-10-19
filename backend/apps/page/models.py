"""页面与表单编排。

PageDefinition 保存页面的可视化 schema（字段/列/动作），
通过 bindings 把列表、表单提交等动作绑定到编排接口（/api/x/<key>），
从而实现"模块 = 页面 + 编排"的低代码装配。
"""
from django.db import models

from apps.core.models import TimeStampedModel
from apps.catalog.models import Module


class PageDefinition(TimeStampedModel):
    PAGE_TYPES = [("list", "列表页"), ("form", "表单页"), ("dashboard", "看板")]

    module = models.ForeignKey(
        Module, verbose_name="所属模块", null=True, blank=True, on_delete=models.SET_NULL, related_name="pages"
    )
    key = models.SlugField("标识", max_length=100, unique=True)
    name = models.CharField("名称", max_length=200)
    page_type = models.CharField("页面类型", max_length=20, choices=PAGE_TYPES, default="list")
    # 可视化设计器产出的 schema（字段/列/查询条件/按钮）
    schema = models.JSONField("页面 schema", default=dict, blank=True)
    # {"list":"编排key", "submit":"编排key", "detail":"编排key"}
    bindings = models.JSONField("编排绑定", default=dict, blank=True)
    status = models.CharField(
        "状态", max_length=20, default="draft",
        choices=[("draft", "草稿"), ("published", "已发布"), ("disabled", "停用")],
    )
    description = models.TextField("说明", blank=True, default="")

    class Meta:
        verbose_name = "页面定义"
        verbose_name_plural = "页面定义"
        ordering = ["key"]

    def __str__(self):
        return f"{self.name}({self.key})"
