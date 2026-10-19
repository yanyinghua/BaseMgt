"""权限模型。

四个动作：read / write / run / admin（admin 隐含其它三个）。
授权粒度：
    Role         角色（内置 admin 拥有全部权限）
    UserRole     用户-角色
    ObjectGrant  对象级授权：给某个具体对象（模块/编排/存储过程/页面/数据源…）授予动作
    DataScope    数据行级范围：角色在某类数据上的过滤条件，SQL 节点可注入

编排、页面、存储过程的权限继承自所属模块（见 access.owner_of）。
"""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.core.models import TimeStampedModel

ACTIONS = ["read", "write", "run", "admin"]


class Role(TimeStampedModel):
    key = models.SlugField("角色标识", max_length=50, unique=True)
    name = models.CharField("角色名称", max_length=100)
    description = models.CharField("说明", max_length=300, blank=True, default="")
    is_builtin = models.BooleanField("内置角色", default=False)

    class Meta:
        verbose_name = "角色"
        verbose_name_plural = "角色"
        ordering = ["key"]

    def __str__(self):
        return f"{self.name}({self.key})"


class UserRole(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="用户", on_delete=models.CASCADE, related_name="bm_roles"
    )
    role = models.ForeignKey(Role, verbose_name="角色", on_delete=models.CASCADE, related_name="user_roles")

    class Meta:
        verbose_name = "用户角色"
        verbose_name_plural = "用户角色"
        unique_together = [("user", "role")]

    def __str__(self):
        return f"{self.user} -> {self.role.key}"


class ObjectGrant(TimeStampedModel):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.BigIntegerField("对象ID")
    target = GenericForeignKey("content_type", "object_id")
    role = models.ForeignKey(
        Role, verbose_name="角色", null=True, blank=True, on_delete=models.CASCADE, related_name="grants"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="用户", null=True, blank=True, on_delete=models.CASCADE, related_name="bm_grants"
    )
    actions = models.JSONField("动作", default=list, help_text="read/write/run/admin")

    class Meta:
        verbose_name = "对象授权"
        verbose_name_plural = "对象授权"
        indexes = [models.Index(fields=["content_type", "object_id"])]

    def __str__(self):
        who = self.role.key if self.role else (self.user.username if self.user else "-")
        return f"{who}: {self.content_type.model}#{self.object_id} {self.actions}"


class DataScope(TimeStampedModel):
    """数据行级范围：某角色在某类数据上的过滤条件（SQL 片段，由管理员维护）。"""

    key = models.SlugField("范围标识", max_length=50, help_text="与 SQL 节点的 scope_key 对应")
    role = models.ForeignKey(Role, verbose_name="角色", on_delete=models.CASCADE, related_name="data_scopes")
    filter_sql = models.TextField("过滤条件", help_text="如 dept_id = 5；同一 key 多角色之间用 OR 合并")
    description = models.CharField("说明", max_length=300, blank=True, default="")

    class Meta:
        verbose_name = "数据范围"
        verbose_name_plural = "数据范围"
        ordering = ["key", "role"]

    def __str__(self):
        return f"{self.key}:{self.role.key}"
