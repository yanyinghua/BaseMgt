from django.utils import timezone
from rest_framework import status
from apps.iam.permissions import PermModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.response import fail, ok

from . import services
from .models import DataSource, Module, StoredProcedure, StoredProcedureVersion
from .serializers import (
    DataSourceSerializer,
    ModuleSerializer,
    StoredProcedureSerializer,
    StoredProcedureVersionSerializer,
)


class AuditMixin:
    """写入创建人/更新人；未登录场景（BM_AUTH_DISABLED）留空。"""

    def _user(self):
        user = self.request.user
        return user if user and user.is_authenticated else None

    def perform_create(self, serializer):
        serializer.save(created_by=self._user(), updated_by=self._user())

    def perform_update(self, serializer):
        serializer.save(updated_by=self._user())


class ModuleViewSet(AuditMixin, PermModelViewSet):
    perm_owner_paths = ()
    queryset = Module.objects.all()
    serializer_class = ModuleSerializer

    def get_queryset(self):
        from django.db.models import Q

        qs = super().get_queryset()
        keyword = self.request.query_params.get("keyword")
        if keyword:
            qs = qs.filter(Q(name__icontains=keyword) | Q(key__icontains=keyword))
        return qs


class DataSourceViewSet(AuditMixin, PermModelViewSet):
    perm_owner_paths = ()
    queryset = DataSource.objects.all()
    serializer_class = DataSourceSerializer

    @action(detail=False, methods=["post"])
    def test(self, request):
        """测试连通性（不落库）。"""
        ds = DataSource(**{
            "key": request.data.get("key") or "__test__",
            "name": request.data.get("name") or "test",
            "engine": request.data.get("engine", "postgres"),
            "host": request.data.get("host", "127.0.0.1"),
            "port": int(request.data.get("port") or 5432),
            "database": request.data.get("database", ""),
            "username": request.data.get("username", ""),
            "password": request.data.get("password", ""),
            "options": request.data.get("options") or {},
        })
        if request.data.get("id"):
            ds = DataSource.objects.get(pk=request.data["id"])
        try:
            rows = services.query(ds, "select version() as version", fetch="one", reuse=False)
            return ok({"ok": True, "version": rows["version"] if rows else ""})
        except Exception as exc:
            return fail(f"连接失败: {exc}")

    @action(detail=True, methods=["get"])
    def schemas(self, request, pk=None):
        ds = self.get_object()
        return ok(services.list_schemas(ds))

    @action(detail=True, methods=["get"])
    def tables(self, request, pk=None):
        ds = self.get_object()
        schema = request.query_params.get("schema")
        return ok(services.list_tables(ds, schema))

    @action(detail=True, methods=["get"])
    def columns(self, request, pk=None):
        ds = self.get_object()
        return ok(services.list_columns(ds, request.query_params.get("schema", "public"),
                                        request.query_params.get("table", "")))

    @action(detail=True, methods=["post"])
    def sql(self, request, pk=None):
        """在线执行 SQL（开发辅助）。

        默认只读：仅 SELECT/WITH/EXPLAIN 等，且禁止多语句与 DDL；
        需要写操作请在 .env 中设置 BM_SQL_CONSOLE_WRITE=1。
        """
        from django.conf import settings

        from .sql_guard import check_sql

        ds = self.get_object()
        sql = request.data.get("sql", "").strip()
        if not sql:
            return fail("sql 不能为空")
        allowed, reason = check_sql(sql, allow_write=getattr(settings, "BM_SQL_CONSOLE_WRITE", False))
        if not allowed:
            return fail(reason)
        try:
            params = request.data.get("params") or None
            start = timezone.now()
            rows = services.query(ds, sql, params, fetch=request.data.get("fetch", "all"))
            cost = int((timezone.now() - start).total_seconds() * 1000)
            return ok({"rows": rows, "cost_ms": cost})
        except Exception as exc:
            return fail(f"执行失败: {exc}")

    @action(detail=True, methods=["post"])
    def sync_procedures(self, request, pk=None):
        """把库里已有的存储过程同步到目录。"""
        ds = self.get_object()
        schemas = request.data.get("schemas") or None
        try:
            result = services.sync_procedures(ds, schemas, self._user())
            return ok(result)
        except Exception as exc:
            return fail(f"同步失败: {exc}")


class StoredProcedureViewSet(AuditMixin, PermModelViewSet):
    perm_owner_paths = ("module",)
    queryset = StoredProcedure.objects.select_related("data_source", "module", "current_version")
    serializer_class = StoredProcedureSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        for field in ("data_source", "module", "schema", "status"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        keyword = self.request.query_params.get("keyword")
        if keyword:
            qs = qs.filter(name__icontains=keyword)
        return qs

    @action(detail=True, methods=["get", "post"])
    def versions(self, request, pk=None):
        proc = self.get_object()
        if request.method == "GET":
            return ok(StoredProcedureVersionSerializer(proc.versions.all(), many=True).data)
        latest = proc.versions.order_by("-version").first()
        version = (latest.version if latest else 0) + 1
        ver = StoredProcedureVersion.objects.create(
            procedure=proc,
            version=version,
            ddl=request.data.get("ddl", ""),
            change_note=request.data.get("change_note", ""),
            created_by=self._user(),
        )
        proc.current_version = ver
        proc.save(update_fields=["current_version", "updated_at"])
        return ok(StoredProcedureVersionSerializer(ver).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="versions/(?P<version_id>[^/.]+)/apply")
    def apply_version(self, request, pk=None, version_id=None):
        proc = self.get_object()
        ver = StoredProcedureVersion.objects.get(pk=version_id, procedure=proc)
        try:
            services.apply_procedure_version(ver, self._user())
            return ok({"applied": True, "version": ver.version})
        except Exception as exc:
            return fail(f"下发失败: {exc}")

    @action(detail=True, methods=["post"])
    def pull(self, request, pk=None):
        """从数据库取回最新定义，作为新版本保存。"""
        proc = self.get_object()
        detail = services.fetch_definition(proc.data_source, proc.schema, proc.name)
        if not detail:
            return fail("数据库中未找到该存储过程", http_status=status.HTTP_404_NOT_FOUND)
        latest = proc.versions.order_by("-version").first()
        version = (latest.version if latest else 0) + 1
        ver = StoredProcedureVersion.objects.create(
            procedure=proc,
            version=version,
            ddl=detail["ddl"],
            change_note="从数据库拉取",
            status="deployed",
            applied_at=timezone.now(),
            created_by=self._user(),
        )
        proc.kind = detail["kind"]
        proc.signature = detail["arguments"] or ""
        proc.returns = detail["result"] or ""
        proc.params = detail["params"]
        proc.current_version = ver
        proc.status = "deployed"
        proc.save()
        return ok(StoredProcedureVersionSerializer(ver).data)

    @action(detail=True, methods=["post"])
    def call(self, request, pk=None):
        """在线调用（测试用）。args 为位置参数数组。"""
        proc = self.get_object()
        try:
            result = services.call_procedure(
                proc.data_source, proc.schema, proc.name,
                request.data.get("args") or [], kind=proc.kind,
            )
            return ok(result)
        except Exception as exc:
            return fail(f"调用失败: {exc}")

    @action(detail=True, methods=["post"])
    def drop(self, request, pk=None):
        proc = self.get_object()
        try:
            services.drop_procedure(proc)
            return ok({"dropped": True})
        except Exception as exc:
            return fail(f"删除失败: {exc}")
