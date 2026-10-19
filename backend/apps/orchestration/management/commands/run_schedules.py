"""定时调度：扫描带 cron 触发器的已发布编排并触发运行。

    python manage.py run_schedules --interval 30
    python manage.py run_schedules --once
"""
import time

from croniter import croniter
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.orchestration.engine import submit_run
from apps.orchestration.models import Definition


class Command(BaseCommand):
    help = "按 cron 表达式触发编排运行"

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=30, help="轮询间隔（秒）")
        parser.add_argument("--once", action="store_true", help="只扫描一轮后退出")

    def handle(self, *args, **options):
        interval = max(5, options["interval"])
        self.stdout.write(self.style.SUCCESS(f"调度器启动，轮询间隔 {interval}s"))
        while True:
            self.scan()
            if options["once"]:
                break
            time.sleep(interval)

    def scan(self):
        now = timezone.now()
        definitions = Definition.objects.filter(status="published")
        for definition in definitions:
            trigger = definition.trigger or {}
            if trigger.get("type") != "cron" or not trigger.get("enabled", True):
                continue
            expr = trigger.get("cron") or ""
            if not expr or not croniter.is_valid(expr):
                self.stdout.write(self.style.WARNING(f"{definition.key}: cron 表达式无效 -> {expr}"))
                continue
            base = definition.last_schedule_at or definition.created_at or now
            try:
                next_run = croniter(expr, base).get_next(timezone.datetime)
            except Exception as exc:  # noqa: BLE001
                self.stdout.write(self.style.WARNING(f"{definition.key}: {exc}"))
                continue
            if timezone.is_naive(next_run):
                next_run = timezone.make_aware(next_run)
            if next_run > now:
                continue
            run = submit_run(definition, {}, trigger="cron")
            definition.last_schedule_at = now
            definition.save(update_fields=["last_schedule_at", "updated_at"])
            self.stdout.write(
                self.style.SUCCESS(f"触发 {definition.key} v{definition.version} -> Run#{run.id} ({run.status})")
            )
