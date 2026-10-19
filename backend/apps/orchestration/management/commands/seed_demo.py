"""初始化演示数据：模块、数据源、存储过程、一个服务编排并发布。

    python manage.py seed_demo
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.catalog import services
from apps.catalog.models import DataSource, Module, StoredProcedure, StoredProcedureVersion
from apps.orchestration.models import Definition

DEMO_DDL = """CREATE OR REPLACE FUNCTION public.bm_demo_calc(p_qty integer, p_price numeric)
RETURNS TABLE(qty integer, price numeric, amount numeric)
LANGUAGE sql AS $$
    SELECT p_qty, p_price, p_qty * p_price;
$$;
"""


class Command(BaseCommand):
    help = "生成 BaseMgt 演示数据"

    def handle(self, *args, **options):
        from apps.iam.access import ensure_builtin_roles
        from apps.iam.models import UserRole

        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username="admin", defaults={"is_staff": True, "is_superuser": True}
        )
        user.is_staff = user.is_superuser = True
        user.set_password("admin123")
        user.save()

        roles = ensure_builtin_roles()
        UserRole.objects.get_or_create(user=user, role=roles["admin"])
        UserRole.objects.get_or_create(user=user, role=roles["developer"])

        module, _ = Module.objects.get_or_create(
            key="demo", defaults={"name": "演示模块", "description": "用于验证编排链路"}
        )

        ds, _ = DataSource.objects.get_or_create(
            key="default",
            defaults={
                "name": "本地默认库",
                "engine": "postgres",
                "host": "127.0.0.1",
                "port": 5433,
                "database": "basemgt",
                "username": "basemgt",
                "password": "",
                "is_default": True,
            },
        )

        proc, created = StoredProcedure.objects.get_or_create(
            data_source=ds, schema="public", name="bm_demo_calc", signature="",
            defaults={"kind": "function", "module": module, "description": "演示：金额计算函数", "status": "draft"},
        )
        version, vcreated = StoredProcedureVersion.objects.get_or_create(
            procedure=proc, version=1, defaults={"ddl": DEMO_DDL, "change_note": "初始版本"}
        )
        try:
            services.apply_procedure_version(version, user)
            self.stdout.write(self.style.SUCCESS("存储过程已下发: public.bm_demo_calc"))
        except Exception as exc:  # noqa: BLE001
            self.stdout.write(self.style.WARNING(f"存储过程下发失败：{exc}"))

        graph = {
            "nodes": [
                {"id": "start_1", "type": "start", "name": "开始", "config": {}, "position": {"x": 60, "y": 140}},
                {
                    "id": "proc_1", "type": "procedure", "name": "计算金额",
                    "config": {
                        "proc_id": proc.id,
                        "args": ["{{ input.qty }}", "{{ input.price }}"],
                        "assign_var": "calc",
                    },
                    "position": {"x": 260, "y": 140},
                },
                {
                    "id": "end_1", "type": "end", "name": "结束",
                    "config": {"output": {"amount": "{{ node.proc_1.rows[0].amount }}"}},
                    "position": {"x": 480, "y": 140},
                },
            ],
            "edges": [
                {"id": "e1", "source": "start_1", "sourceHandle": "default", "target": "proc_1"},
                {"id": "e2", "source": "proc_1", "sourceHandle": "default", "target": "end_1"},
            ],
        }
        definition, _ = Definition.objects.get_or_create(
            key="demo-calc", version=1,
            defaults={
                "name": "金额计算（演示）",
                "kind": "service",
                "module": module,
                "graph": graph,
                "trigger": {"type": "http", "method": "POST", "path": "demo-calc", "enabled": True},
                "input_schema": [
                    {"name": "qty", "label": "数量", "type": "number", "required": True, "default": 3},
                    {"name": "price", "label": "单价", "type": "number", "required": True, "default": 12.5},
                ],
                "status": "published",
                "description": "调用存储过程 public.bm_demo_calc 计算金额",
            },
        )
        definition.graph = graph
        definition.status = "published"
        definition.save()

        # 列表数据源示例：SQL 节点取数 -> 结束节点输出 rows
        from apps.page.models import PageDefinition

        list_def, _ = Definition.objects.get_or_create(
            key="demo-rows", version=1,
            defaults={"name": "示例列表取数", "kind": "service", "module": module, "status": "published"},
        )
        list_def.module = module
        list_def.status = "published"
        list_def.graph = {
            "nodes": [
                {"id": "s", "type": "start", "name": "开始", "config": {}},
                {
                    "id": "q", "type": "sql", "name": "查询",
                    "config": {"sql": "select * from (values (1,'张三'),(2,'李四'),(3,'王五')) t(id,name)", "assign_var": "rows"},
                },
                {
                    "id": "e", "type": "end", "name": "结束",
                    "config": {"output": {"rows": "{{ vars.rows }}"}},
                },
            ],
            "edges": [
                {"id": "1", "source": "s", "target": "q"},
                {"id": "2", "source": "q", "target": "e"},
            ],
        }
        list_def.trigger = {"type": "http", "method": "POST", "path": "demo-rows", "enabled": True}
        list_def.save()

        page, _ = PageDefinition.objects.get_or_create(
            key="demo-emp",
            defaults={"name": "人员列表（示例）", "page_type": "list", "module": module, "status": "published"},
        )
        page.module = module
        page.status = "published"
        page.schema = {
            "fields": [
                {"name": "id", "label": "编号", "type": "number", "show": True, "query": False},
                {"name": "name", "label": "姓名", "type": "text", "show": True, "query": True},
            ]
        }
        page.bindings = {"list": "demo-rows"}
        page.save()

        self.stdout.write(self.style.SUCCESS(
            "演示数据就绪。测试：\n"
            "  curl -X POST http://127.0.0.1:8000/api/x/demo-calc -H 'Content-Type: application/json' "
            "-d '{\"qty\":3,\"price\":12.5}'\n"
            "  后台账号：admin / admin123"
        ))
