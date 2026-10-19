"""初始化企业基础主数据。

按 presets 定义 7 类主数据（部门/人员/供应商/客户/产品/原材料/资产），
建物理表、生成 CRUD 存储过程、生成编排与页面。

    python manage.py init_master_data
    python manage.py init_master_data --keys employee supplier
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.catalog.models import DataSource
from apps.mdm import builder
from apps.mdm.presets import PRESETS


class Command(BaseCommand):
    help = "初始化企业主数据（MDM）"

    def add_arguments(self, parser):
        parser.add_argument("--keys", nargs="*", help="只初始化指定的主数据，如 employee supplier")
        parser.add_argument("--resync", action="store_true", help="强制重新生成存储过程/编排/页面")

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(is_superuser=True).first()
        ds = DataSource.objects.filter(is_default=True, status="active").first() or DataSource.objects.first()
        if ds is None:
            self.stdout.write(self.style.ERROR("没有可用数据源"))
            return
        module = builder.ensure_module()
        dicts = builder.create_dictionaries(module=module, user=user)
        self.stdout.write(self.style.SUCCESS(f"数据字典就绪：{len(dicts)} 个（{', '.join(dicts)}）"))

        wanted = set(options.get("keys") or [])
        for preset in PRESETS:
            if wanted and preset["key"] not in wanted:
                continue
            entity, created = builder.create_or_update_entity(preset, data_source=ds, module=module, user=user)
            result = builder.bootstrap_entity(entity, user=user)
            if options["resync"]:
                pass
            self.stdout.write(self.style.SUCCESS(
                f"{'[新建]' if created else '[已存在]'} {entity.name} -> {entity.qualified_table} "
                f"字段 {entity.fields.count()} 个，存储过程 {len(result.get('procedures', []))} 个，"
                f"编排 {len(result.get('definitions', []))} 个，页面 {len(result.get('pages', []))} 个"
            ))

        self.stdout.write(self.style.SUCCESS(
            "\n主数据就绪。可用入口：\n"
            "  接口   POST /api/x/{key}-list   /api/x/{key}-save   /api/x/{key}-delete\n"
            "  页面   /p/{key}-list（列表）  /p/{key}-form（登记）\n"
            "  管理   前端「主数据」页：加字段 -> 同步表 -> 重新生成存储过程/页面"
        ))
