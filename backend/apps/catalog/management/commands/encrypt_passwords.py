"""把历史明文数据源口令加密（幂等，已加密的会跳过）。

    python manage.py encrypt_passwords
"""
from django.core.management.base import BaseCommand

from apps.catalog.crypto import ENC_PREFIX
from apps.catalog.models import DataSource


class Command(BaseCommand):
    help = "加密数据源口令"

    def handle(self, *args, **options):
        count = 0
        for ds in DataSource.objects.all():
            if not ds.password or ds.password.startswith(ENC_PREFIX):
                continue
            ds.set_password(ds.password)
            ds.save(update_fields=["password"])
            count += 1
        self.stdout.write(self.style.SUCCESS(f"已加密 {count} 个数据源口令"))
