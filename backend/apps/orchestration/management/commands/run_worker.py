"""编排运行 worker：消费 pending 状态的 Run 并执行。

    python manage.py run_worker --workers 2 --interval 2
    python manage.py run_worker --once          # 处理完当前队列即退出
"""
import time

from concurrent.futures import ThreadPoolExecutor
from django.db import connections, transaction
from django.core.management.base import BaseCommand

from apps.orchestration.engine import execute_run
from apps.orchestration.models import Run


def claim_runs(limit):
    """原子领取待执行运行（PG 行锁 + skip_locked，可多 worker 并发）。"""
    claimed = []
    with transaction.atomic():
        queryset = (
            Run.objects.select_for_update(skip_locked=True)
            .filter(status="pending")
            .order_by("id")[:limit]
        )
        ids = [r.id for r in queryset]
        if not ids:
            return []
        Run.objects.filter(id__in=ids).update(status="running")
        claimed = list(Run.objects.filter(id__in=ids))
    return claimed


def _run(run_id):
    try:
        run = Run.objects.get(pk=run_id)
        result = execute_run(run)
        return f"Run#{run_id} -> {result.status}"
    except Exception as exc:  # noqa: BLE001
        return f"Run#{run_id} -> worker异常 {exc}"
    finally:
        connections.close_all()


class Command(BaseCommand):
    help = "编排运行 worker"

    def add_arguments(self, parser):
        parser.add_argument("--workers", type=int, default=2, help="并发线程数")
        parser.add_argument("--interval", type=int, default=2, help="空闲时轮询间隔（秒）")
        parser.add_argument("--once", action="store_true", help="处理一轮后退出")

    def handle(self, *args, **options):
        workers = max(1, options["workers"])
        interval = max(1, options["interval"])
        self.stdout.write(self.style.SUCCESS(f"worker 启动，并发 {workers}，轮询 {interval}s"))
        pool = ThreadPoolExecutor(max_workers=workers)
        try:
            while True:
                runs = claim_runs(workers)
                if runs:
                    for msg in pool.map(_run, [r.id for r in runs]):
                        self.stdout.write(msg)
                elif options["once"]:
                    break
                else:
                    time.sleep(interval)
        finally:
            pool.shutdown(wait=False)
