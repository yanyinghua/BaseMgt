"""搭建看板与报表示例（页面渲染器的 dashboard / report 两种类型）。

看板与报表**不需要新的后端接口**：页面 schema 里声明「取哪个编排的数据 + 怎么聚合」，
前端取回 rows 后本地算出 KPI 卡片与图表。要换指标，改页面 schema 即可。

    python manage.py init_dashboard_demo
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.mdm import builder
from apps.orchestration.models import Definition
from apps.page.models import PageDefinition

PAGES = [
    {
        "key": "mdm-overview",
        "name": "主数据总览看板",
        "page_type": "dashboard",
        "description": "各主数据对象的数量与分布",
        "bindings": {},
        "schema": {
            "cards": [
                {"title": "人员数", "bind": "employee-list", "metric": "count", "link": "/p/employee-list"},
                {"title": "部门数", "bind": "department-list", "metric": "count", "link": "/p/department-list"},
                {"title": "供应商数", "bind": "supplier-list", "metric": "count", "link": "/p/supplier-list"},
                {"title": "客户数", "bind": "customer-list", "metric": "count", "link": "/p/customer-list"},
                {"title": "产品数", "bind": "product-list", "metric": "count", "link": "/p/product-list"},
                {"title": "原材料数", "bind": "material-list", "metric": "count", "link": "/p/material-list"},
                {"title": "资产数", "bind": "asset-list", "metric": "count", "link": "/p/asset-list"},
                {"title": "资产原值", "bind": "asset-list", "metric": "sum", "field": "buy_amount",
                 "unit": "元", "link": "/p/asset-list"},
            ],
            "charts": [
                {"title": "资产类别分布（按原值）", "type": "pie", "bind": "asset-list",
                 "labelField": "category", "valueField": "buy_amount", "agg": "sum"},
                {"title": "供应商类别分布", "type": "bar", "bind": "supplier-list",
                 "labelField": "category", "valueField": "id", "agg": "count"},
                {"title": "人员在职状态", "type": "pie", "bind": "employee-list",
                 "labelField": "job_status", "valueField": "id", "agg": "count"},
            ],
        },
    },
    {
        "key": "inventory-report",
        "name": "库存台账报表",
        "page_type": "report",
        "description": "库存明细 + 总量/总金额 + 按物料金额分布（数据来自采购入库累加）",
        "bindings": {"list": "inventory-list"},
        "schema": {
            "fields": [
                {"name": "code", "label": "库存编码", "type": "text", "show": True, "query": True},
                {"name": "name", "label": "物料名称", "type": "text", "show": True, "query": True},
                {"name": "material_id", "label": "物料ID", "type": "number", "show": True, "query": False},
                {"name": "warehouse_id", "label": "仓库ID", "type": "number", "show": True, "query": False},
                {"name": "qty", "label": "现存数量", "type": "number", "show": True, "query": False},
                {"name": "amount", "label": "现存金额", "type": "number", "show": True, "query": False},
                {"name": "last_in_at", "label": "最近入库", "type": "text", "show": True, "query": False},
            ],
            "cards": [
                {"title": "物料种类", "metric": "count"},
                {"title": "库存总数量", "metric": "sum", "field": "qty"},
                {"title": "库存总金额", "metric": "sum", "field": "amount", "unit": "元"},
            ],
            "charts": [
                {"title": "各物料库存金额", "type": "bar", "labelField": "name",
                 "valueField": "amount", "agg": "sum"},
            ],
        },
    },
    {
        "key": "expense-report",
        "name": "报销汇总报表",
        "page_type": "report",
        "description": "按状态+类别汇总报销金额（数据来自 sp_expense_summary 存储过程）",
        "bindings": {"list": "expense-summary"},
        "schema": {
            "fields": [
                {"name": "status", "label": "状态", "type": "text", "show": True, "query": True},
                {"name": "category", "label": "类别", "type": "text", "show": True, "query": True},
                {"name": "cnt", "label": "单据数", "type": "number", "show": True, "query": False},
                {"name": "total", "label": "金额合计", "type": "number", "show": True, "query": False},
            ],
            "cards": [
                {"title": "汇总行数", "metric": "count"},
                {"title": "单据数", "metric": "sum", "field": "cnt", "unit": "单"},
                {"title": "报销总额", "metric": "sum", "field": "total", "unit": "元"},
            ],
            "charts": [
                {"title": "各类别报销金额", "type": "bar", "labelField": "category",
                 "valueField": "total", "agg": "sum"},
                {"title": "各状态报销金额", "type": "pie", "labelField": "status",
                 "valueField": "total", "agg": "sum"},
            ],
        },
    },
]


class Command(BaseCommand):
    help = "搭建看板与报表示例"

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(is_superuser=True).first()
        module = builder.ensure_module("bi", "经营分析")

        for spec in PAGES:
            # 报表依赖的编排不存在时跳过并提示（先跑 init_purchase_demo / init_expense_demo）
            needed = {c.get("bind") for c in spec["schema"].get("cards", []) if c.get("bind")}
            needed |= {c.get("bind") for c in spec["schema"].get("charts", []) if c.get("bind")}
            if spec["bindings"].get("list"):
                needed.add(spec["bindings"]["list"])
            missing = [
                key for key in needed
                if key and not Definition.objects.filter(key=key, status="published").exists()
            ]
            if missing:
                self.stdout.write(self.style.WARNING(
                    f"跳过 {spec['key']}：缺少已发布编排 {', '.join(sorted(missing))}"
                ))
                continue

            page, created = PageDefinition.objects.get_or_create(
                key=spec["key"],
                defaults={"name": spec["name"], "page_type": spec["page_type"],
                          "module": module, "status": "published"},
            )
            page.name = spec["name"]
            page.page_type = spec["page_type"]
            page.module = module
            page.status = "published"
            page.description = spec.get("description", "")
            page.schema = spec["schema"]
            page.bindings = spec["bindings"]
            page.save()
            self.stdout.write(self.style.SUCCESS(
                f"{'[新建]' if created else '[已更新]'} {spec['page_type']:<9} /p/{page.key}  {page.name}"
            ))

        self.stdout.write(self.style.SUCCESS(
            "\n看板与报表就绪，侧边栏「经营分析」下可见：\n"
            "  /p/mdm-overview       主数据总览看板（KPI 卡片 + 饼图/柱状图）\n"
            "  /p/inventory-report   库存台账报表（明细表 + 汇总卡片 + 图表 + 导出）\n"
            "  /p/expense-report     报销汇总报表\n"
            "指标与图表都在页面 schema 里声明（前端本地聚合），改指标不需要改后端接口"
        ))
