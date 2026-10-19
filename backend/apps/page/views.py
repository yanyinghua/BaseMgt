from apps.iam.permissions import PermModelViewSet
from rest_framework.decorators import action

from apps.core.response import fail, ok
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
