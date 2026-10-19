import io
from urllib.parse import quote

from django.http import HttpResponse
from rest_framework.decorators import action

from apps.core.response import fail, ok
from apps.iam.permissions import PermModelViewSet
from apps.orchestration.engine import run_definition_by_key
from apps.orchestration.serializers import RunDetailSerializer

from .models import PageDefinition
from .serializers import PageDefinitionSerializer


class PageDefinitionViewSet(PermModelViewSet):
    perm_owner_paths = ("module",)
    queryset = PageDefinition.objects.select_related("module")
    serializer_class = PageDefinitionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        for field in ("module", "page_type", "status", "key"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        return qs

    @action(detail=True, methods=["post"])
    def data(self, request, pk=None):
        """按 bindings 调用绑定的编排接口。

        body: {"action": "list|submit|detail", "payload": {...}}
        """
        page = self.get_object()
        action_name = request.data.get("action") or "list"
        key = (page.bindings or {}).get(action_name)
        if not key:
            return fail(f"页面未绑定 {action_name} 对应的编排")
        try:
            run = run_definition_by_key(key, request.data.get("payload") or {}, trigger=f"page:{action_name}")
        except ValueError as exc:
            return fail(str(exc))
        data = RunDetailSerializer(run).data
        return ok({"status": run.status, "output": run.output, "error": run.error, "run": data})

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        """报表导出：跑一遍绑定的 list 编排，把结果写成 Excel。"""
        from openpyxl import Workbook
        from openpyxl.styles import Font

        page = self.get_object()
        key = (page.bindings or {}).get("list")
        if not key:
            return fail("页面未绑定 list 对应的编排")

        params = {k: request.query_params.get(k) for k in request.query_params.keys()}
        params.setdefault("limit", 200)
        try:
            run = run_definition_by_key(key, params, trigger="page:export")
        except ValueError as exc:
            return fail(str(exc))
        if run.status != "success":
            return fail(f"取数失败: {run.error}")

        rows = (run.output or {}).get("rows") or []
        fields = (page.schema or {}).get("fields") or []
        columns = [f["name"] for f in fields if f.get("show", True)]
        if not columns and rows:
            columns = list(rows[0].keys())
        labels = {f["name"]: f.get("label", f["name"]) for f in fields}

        wb = Workbook()
        ws = wb.active
        ws.append([labels.get(c, c) for c in columns])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in rows:
            ws.append([row.get(c) for c in columns])

        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)
        resp = HttpResponse(
            stream.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(page.name)}.xlsx"
        return resp
