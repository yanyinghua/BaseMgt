"""元数据层：业务模块、数据源、存储过程目录。

这三类对象是"持续开发管理系统"的骨架：
- Module          业务模块（菜单/功能包），新增模块即在此登记
- DataSource      外部数据库连接，编排节点通过 key 引用
- StoredProcedure 存储过程目录 + 版本，支持在线编写、下发、调用
"""
from django.db import models

from apps.core.models import TimeStampedModel

from .crypto import decrypt_password, encrypt_password


class Module(TimeStampedModel):
    """业务模块。一个模块下挂若干编排定义与页面定义。"""

    key = models.SlugField("模块标识", max_length=100, unique=True)
    name = models.CharField("模块名称", max_length=100)
    parent = models.ForeignKey(
        "self",
        verbose_name="上级模块",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    icon = models.CharField("图标", max_length=50, blank=True, default="")
    sort_order = models.IntegerField("排序", default=0)
    status = models.CharField(
        "状态", max_length=20, default="active", choices=[("active", "启用"), ("disabled", "停用")]
    )
    description = models.TextField("说明", blank=True, default="")

    class Meta:
        verbose_name = "业务模块"
        verbose_name_plural = "业务模块"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.name}({self.key})"


class DataSource(TimeStampedModel):
    """外部数据源。编排的 SQL / 存储过程节点按 key 引用数据源。"""

    ENGINE_CHOICES = [
        ("postgres", "PostgreSQL"),
        ("mysql", "MySQL"),
    ]

    key = models.SlugField("数据源标识", max_length=100, unique=True)
    name = models.CharField("名称", max_length=100)
    engine = models.CharField("类型", max_length=20, choices=ENGINE_CHOICES, default="postgres")
    host = models.CharField("主机", max_length=200, default="127.0.0.1")
    port = models.IntegerField("端口", default=5432)
    database = models.CharField("库名", max_length=100)
    username = models.CharField("用户名", max_length=100, blank=True, default="")
    # 口令以 Fernet 密文（enc: 前缀）存储，读取请用 get_password()
    password = models.TextField("口令", blank=True, default="")
    options = models.JSONField("连接参数", blank=True, default=dict)
    is_default = models.BooleanField("默认数据源", default=False)
    status = models.CharField(
        "状态", max_length=20, default="active", choices=[("active", "启用"), ("disabled", "停用")]
    )
    remark = models.TextField("备注", blank=True, default="")

    class Meta:
        verbose_name = "数据源"
        verbose_name_plural = "数据源"
        ordering = ["-is_default", "key"]

    def __str__(self):
        return f"{self.name}({self.key})"

    def save(self, *args, **kwargs):
        if self.is_default:
            DataSource.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    def set_password(self, raw):
        self.password = encrypt_password(raw)

    def get_password(self):
        return decrypt_password(self.password)


class StoredProcedure(TimeStampedModel):
    """存储过程目录条目（逻辑对象）。DDL 内容保存在版本表里。"""

    KIND_CHOICES = [("procedure", "PROCEDURE"), ("function", "FUNCTION")]
    STATUS_CHOICES = [
        ("draft", "未下发"),
        ("deployed", "已下发"),
        ("dropped", "已删除"),
    ]

    module = models.ForeignKey(
        Module, verbose_name="所属模块", null=True, blank=True, on_delete=models.SET_NULL, related_name="procedures"
    )
    data_source = models.ForeignKey(
        DataSource, verbose_name="数据源", on_delete=models.CASCADE, related_name="procedures"
    )
    schema = models.CharField("Schema", max_length=100, default="public")
    name = models.CharField("名称", max_length=200)
    kind = models.CharField("类型", max_length=20, choices=KIND_CHOICES, default="procedure")
    signature = models.TextField("参数签名", blank=True, default="")
    returns = models.TextField("返回类型", blank=True, default="")
    params = models.JSONField("参数定义", blank=True, default=list)
    description = models.TextField("说明", blank=True, default="")
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default="draft")
    current_version = models.ForeignKey(
        "StoredProcedureVersion",
        verbose_name="当前版本",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    deployed_at = models.DateTimeField("最近下发时间", null=True, blank=True)

    class Meta:
        verbose_name = "存储过程"
        verbose_name_plural = "存储过程"
        ordering = ["schema", "name"]
        unique_together = [("data_source", "schema", "name", "signature")]

    def __str__(self):
        return f"{self.schema}.{self.name}"

    @property
    def qualified_name(self):
        return f"{self.schema}.{self.name}"


class StoredProcedureVersion(TimeStampedModel):
    """存储过程版本。每次保存生成新版本，下发时把 DDL 执行到目标库。"""

    STATUS_CHOICES = [("draft", "未下发"), ("deployed", "已下发")]

    procedure = models.ForeignKey(
        StoredProcedure, verbose_name="存储过程", on_delete=models.CASCADE, related_name="versions"
    )
    version = models.IntegerField("版本号")
    ddl = models.TextField("DDL 脚本")
    change_note = models.CharField("变更说明", max_length=500, blank=True, default="")
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default="draft")
    applied_at = models.DateTimeField("下发时间", null=True, blank=True)

    class Meta:
        verbose_name = "存储过程版本"
        verbose_name_plural = "存储过程版本"
        ordering = ["-version"]
        unique_together = [("procedure", "version")]

    def __str__(self):
        return f"{self.procedure.name} v{self.version}"
