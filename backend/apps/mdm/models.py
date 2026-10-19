"""主数据（MDM）元数据。

设计取向：**元数据描述 + 生成真实物理表**。
这样历史/新写的存储过程、报表、JOIN 都能直接作用于主数据表，而不是困在通用宽表里。

    EntityDefinition  一个主数据对象（如人员信息）-> 一张物理表
    FieldDefinition   字段定义（含扩展字段）-> 一个物理列 + ADD COLUMN 同步
    EntityDdlLog      每次结构变更的 SQL 留痕
"""
import re

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import DataSource
from apps.core.models import TimeStampedModel
from apps.orchestration.models import Definition
from apps.page.models import PageDefinition

IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

DATA_TYPES = [
    ("char", "文本"),
    ("text", "长文本"),
    ("int", "整数"),
    ("bigint", "大整数"),
    ("decimal", "金额/小数"),
    ("date", "日期"),
    ("datetime", "日期时间"),
    ("bool", "是/否"),
    ("enum", "枚举"),
    ("json", "JSON"),
    ("ref", "关联主数据"),
]


def validate_identifier(value):
    if not IDENT_RE.match(value or ""):
        raise ValidationError("只能用小写字母、数字、下划线，且以字母开头")


class Dictionary(TimeStampedModel):
    """统一字典：把类别、状态、等级等枚举值集中维护，字段直接引用。

    改字典不用改表结构、不用改存储过程，页面下拉与查询条件自动跟着变。
    """

    STATUS = [("active", "启用"), ("disabled", "停用")]

    module = models.ForeignKey(
        "catalog.Module", verbose_name="所属模块", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="dictionaries"
    )
    key = models.SlugField("标识", max_length=100, unique=True)
    name = models.CharField("名称", max_length=200)
    description = models.TextField("说明", blank=True, default="")
    status = models.CharField("状态", max_length=20, choices=STATUS, default="active")

    class Meta:
        verbose_name = "数据字典"
        verbose_name_plural = "数据字典"
        ordering = ["key"]

    def __str__(self):
        return f"{self.name}({self.key})"

    def options(self):
        return [{"value": i.value, "label": i.label} for i in self.items.filter(status="active").order_by("sort_order", "id")]


class DictionaryItem(TimeStampedModel):
    """字典项，支持父子层级（多级分类）。"""

    STATUS = [("active", "启用"), ("disabled", "停用")]

    dictionary = models.ForeignKey(Dictionary, verbose_name="字典", on_delete=models.CASCADE, related_name="items")
    value = models.CharField("存储值", max_length=100)
    label = models.CharField("显示名", max_length=200)
    parent = models.ForeignKey(
        "self", verbose_name="上级项", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    sort_order = models.IntegerField("排序", default=0)
    is_default = models.BooleanField("默认值", default=False)
    status = models.CharField("状态", max_length=20, choices=STATUS, default="active")
    description = models.CharField("说明", max_length=300, blank=True, default="")

    class Meta:
        verbose_name = "字典项"
        verbose_name_plural = "字典项"
        ordering = ["sort_order", "id"]
        unique_together = [("dictionary", "value")]

    def __str__(self):
        return f"{self.dictionary.key}:{self.value}"


class EntityDefinition(TimeStampedModel):
    """主数据对象定义。"""

    CATEGORIES = [
        ("org", "组织与人员"),
        ("partner", "合作伙伴"),
        ("product", "产品与物料"),
        ("asset", "资产"),
        ("other", "其他"),
    ]
    STATUS = [("draft", "草稿"), ("published", "已发布"), ("disabled", "停用")]

    module = models.ForeignKey(
        "catalog.Module", verbose_name="所属模块", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="entities"
    )
    data_source = models.ForeignKey(DataSource, verbose_name="数据源", on_delete=models.CASCADE, related_name="entities")
    key = models.SlugField("标识", max_length=100, unique=True, help_text="如 employee")
    name = models.CharField("名称", max_length=200, help_text="如 人员信息")
    schema = models.CharField("Schema", max_length=100, default="public")
    table_name = models.CharField("表名", max_length=100, validators=[validate_identifier])
    category = models.CharField("分类", max_length=20, choices=CATEGORIES, default="other")
    label_field = models.CharField("展示字段", max_length=100, default="name", help_text="下拉/标题取该列")
    # 能力开关：是否带编号、名称、状态、备注、 timestamps、软删除
    options = models.JSONField("能力开关", default=dict, blank=True,
                               help_text='{"code":true,"name":true,"status":true,"remark":true,"soft_delete":true}')
    status = models.CharField("状态", max_length=20, choices=STATUS, default="draft")
    revision = models.IntegerField("结构版本", default=0)
    synced_at = models.DateTimeField("最近同步时间", null=True, blank=True)
    description = models.TextField("说明", blank=True, default="")

    # 生成物
    list_definition = models.ForeignKey(
        Definition, verbose_name="查询编排", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+"
    )
    save_definition = models.ForeignKey(
        Definition, verbose_name="保存编排", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+"
    )
    page = models.ForeignKey(
        PageDefinition, verbose_name="默认页面", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        verbose_name = "主数据对象"
        verbose_name_plural = "主数据对象"
        ordering = ["category", "key"]

    def __str__(self):
        return f"{self.name}({self.key})"

    @property
    def qualified_table(self):
        return f"{self.schema}.{self.table_name}"

    def option(self, key, default=True):
        value = (self.options or {}).get(key, default)
        return default if value is None else value

    @property
    def tree_parent_field(self):
        """层级父字段列名（如 parent_id），为空表示非树形主数据。"""
        return (self.options or {}).get("tree_parent") or ""

    @property
    def is_tree(self):
        return bool(self.tree_parent_field) and self.fields.filter(
            name=self.tree_parent_field, status="active"
        ).exists()

    @property
    def audit_table(self):
        return f"{self.schema}.mdm_data_change_log"

    def fields_sorted(self):
        return self.fields.filter(status="active").order_by("sort_order", "id")

    def list_fields(self):
        return self.fields_sorted().filter(visible_in_list=True)

    def query_fields(self):
        return self.fields_sorted().filter(queryable=True)

    def proc_name(self, action):
        return f"sp_{self.key}_{action}"


class FieldDefinition(TimeStampedModel):
    """主数据字段定义（含后续扩展字段）。"""

    STATUS = [("active", "启用"), ("disabled", "停用")]

    entity = models.ForeignKey(EntityDefinition, verbose_name="主数据对象", on_delete=models.CASCADE, related_name="fields")
    name = models.CharField("列名", max_length=100, validators=[validate_identifier])
    label = models.CharField("中文名", max_length=200)
    data_type = models.CharField("类型", max_length=20, choices=DATA_TYPES, default="char")
    length = models.IntegerField("长度", default=64)
    precision = models.IntegerField("总位数", default=18)
    scale = models.IntegerField("小数位", default=2)
    nullable = models.BooleanField("可空", default=True)
    unique = models.BooleanField("唯一", default=False)
    indexed = models.BooleanField("建索引", default=False)
    default_value = models.CharField("默认值", max_length=200, blank=True, default="")
    enum_options = models.JSONField("枚举值", default=list, blank=True, help_text='["选项1","选项2"]')
    dictionary = models.ForeignKey(
        "Dictionary", verbose_name="引用字典", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="fields"
    )
    ref_entity = models.ForeignKey(
        EntityDefinition, verbose_name="关联主数据", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="referenced_by"
    )
    ref_display = models.CharField("关联显示字段", max_length=100, blank=True, default="",
                                   help_text="页面下拉展示的字段，默认取目标实体的展示字段")
    is_system = models.BooleanField("系统字段", default=False, help_text="由底座内置，不建议删除")
    is_extended = models.BooleanField("扩展字段", default=False, help_text="业务自建的扩展字段")
    visible_in_list = models.BooleanField("列表显示", default=True)
    queryable = models.BooleanField("可作查询条件", default=False)
    sort_order = models.IntegerField("排序", default=0)
    status = models.CharField("状态", max_length=20, choices=STATUS, default="active")
    description = models.CharField("说明", max_length=300, blank=True, default="")

    class Meta:
        verbose_name = "主数据字段"
        verbose_name_plural = "主数据字段"
        ordering = ["sort_order", "id"]
        unique_together = [("entity", "name")]

    def __str__(self):
        return f"{self.entity.key}.{self.name}"

    def clean(self):
        validate_identifier(self.name)


class EntityDdlLog(TimeStampedModel):
    """结构变更留痕：谁在什么时候把什么 SQL 下到了哪个库。"""

    ACTIONS = [("create", "建表"), ("alter", "变更"), ("index", "索引"), ("drop", "删除")]

    entity = models.ForeignKey(EntityDefinition, verbose_name="主数据对象", on_delete=models.CASCADE, related_name="ddl_logs")
    revision = models.IntegerField("结构版本", default=0)
    action = models.CharField("动作", max_length=20, choices=ACTIONS, default="alter")
    sql = models.TextField("SQL")
    success = models.BooleanField("成功", default=True)
    message = models.TextField("结果/错误", blank=True, default="")
    applied_by = models.CharField("执行人", max_length=100, blank=True, default="")

    class Meta:
        verbose_name = "结构变更记录"
        verbose_name_plural = "结构变更记录"
        ordering = ["-id"]
