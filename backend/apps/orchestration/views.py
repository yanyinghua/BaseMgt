from django.apps import apps as django_apps
from django.utils import timezone
from rest_framework import status
from apps.iam.permissions import PermModelViewSet, PermReadOnlyModelViewSet
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from apps.core.response import fail, ok

from . import registry
from .engine import resume_run, submit_run
from .models import Definition, HumanTask, Run
from .serializers import (
    DefinitionListSerializer,
    DefinitionSerializer,
    HumanTaskSerializer,
    RunDetailSerializer,
    RunListSerializer,
)


class DefinitionViewSet(PermModelViewSet):
    perm_owner_paths = ("module",)
    queryset = Definition.objects.select_related("module")
    serializer_class = DefinitionSerializer

    def _user(self):
        user = self.request.user
        return user if user and user.is_authenticated else None

    def get_serializer_class(self):
        if self.action == "list":
            return DefinitionListSerializer
        return DefinitionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        for field in ("kind", "status", "module"):
            value = params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        keyword = params.get("keyword")
        if keyword:
            qs = qs.filter(key__icontains=keyword) | qs.filter(name__icontains=keyword)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self._user(), updated_by=self._user())

    def perform_update(self, serializer):
        serializer.save(updated_by=self._user())

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """发布：置为 published，之后可被触发器调用。"""
        definition = self.get_object()
        errors = validate_graph(definition.graph)
        if errors:
            return fail("流程校验不通过", data=errors)
        definition.status = "published"
        definition.save(update_fields=["status", "updated_at"])
        return ok({"published": True, "id": definition.id})

    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        definition = self.get_object()
        definition.status = "draft"
        definition.save(update_fields=["status", "updated_at"])
        return ok({"published": False})

    @action(detail=True, methods=["post"])
    def clone(self, request, pk=None):
        """另存为新版本（草稿）。"""
        definition = self.get_object()
        latest = Definition.objects.filter(key=definition.key).order_by("-version").first()
        new_version = (latest.version if latest else definition.version) + 1
        clone = Definition.objects.create(
            module=definition.module,
            key=definition.key,
            name=definition.name,
            kind=definition.kind,
            version=new_version,
            status="draft",
            graph=definition.graph,
            trigger=definition.trigger,
            input_schema=definition.input_schema,
            output_schema=definition.output_schema,
            description=definition.description,
            created_by=self._user(),
            updated_by=self._user(),
        )
        return ok(DefinitionSerializer(clone).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        """运行一次。

        默认按 BM_ASYNC_RUN 异步执行（立即返回 run_id，前端轮询 /api/runs/{id}）；
        加 ?sync=1 可同步等待执行结果。
        """
        definition = self.get_object()
        sync = request.query_params.get("sync") in ("1", "true", "True")
        run = submit_run(definition, request.data or {}, trigger="manual", user=self._user(), sync=sync)
        return ok(RunDetailSerializer(run).data)

    @action(detail=True, methods=["post"])
    def validate(self, request, pk=None):
        definition = self.get_object()
        errors = validate_graph(definition.graph)
        return ok({"valid": not errors, "errors": errors})

    @action(detail=True, methods=["get"])
    def runs(self, request, pk=None):
        definition = self.get_object()
        runs = definition.runs.all()[: int(request.query_params.get("limit", 20))]
        return ok(RunListSerializer(runs, many=True).data)


def validate_graph(graph):
    """流程图静态校验：节点类型是否已注册、连线端点是否存在。"""
    errors = []
    nodes = (graph or {}).get("nodes", [])
    edges = (graph or {}).get("edges", [])
    if not nodes:
        return ["流程图为空"]
    node_ids = {n.get("id") for n in nodes}
    has_start = False
    for node in nodes:
        node_type = node.get("type")
        if node_type in ("start", "trigger"):
            has_start = True
        try:
            registry.get_node_class(node_type)
        except ValueError as exc:
            errors.append(f"节点 {node.get('id')}: {exc}")
    if not has_start:
        errors.append("缺少开始节点")
    for edge in edges:
        if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
            errors.append(f"连线 {edge.get('id')} 指向了不存在的节点")
    return errors


@api_view(["GET"])
def node_types(request):
    """节点类型元数据，供画布与属性面板使用。"""
    return ok({"types": registry.all_types(), "groups": registry.grouped_types()})


class RunViewSet(PermReadOnlyModelViewSet):
    perm_owner_paths = ("definition", "definition__module")
    queryset = Run.objects.select_related("definition")
    serializer_class = RunListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        for field in ("definition", "status"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        return qs

    def get_serializer_class(self):
        if self.action == "retrieve":
            return RunDetailSerializer
        return RunListSerializer

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        run = self.get_object()
        sync = request.query_params.get("sync") in ("1", "true", "True")
        new_run = submit_run(
            run.definition, run.input or {}, trigger="retry", user=self._request_user(), sync=sync
        )
        return ok(RunDetailSerializer(new_run).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """取消：等待中直接置为已取消；运行中由引擎协作式检查后终止。"""
        run = self.get_object()
        if run.status in ("success", "failed", "cancelled"):
            return fail("运行已结束，无法取消")
        run.status = "cancelled"
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at", "updated_at"])
        return ok({"cancelled": True, "note": "运行中的实例会在下一个节点处终止"})

    def _request_user(self):
        user = self.request.user
        return user if user and user.is_authenticated else None


class HumanTaskViewSet(PermModelViewSet):
    perm_owner_paths = ("run__definition", "run__definition__module")
    queryset = HumanTask.objects.select_related("run", "run__definition", "assignee")
    serializer_class = HumanTaskSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("assignee"):
            qs = qs.filter(assignee__username=params["assignee"])
        if params.get("mine"):
            user = self.request.user
            if user and user.is_authenticated:
                qs = qs.filter(assignee=user)
        return qs

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        """处理人工任务并继续流程。action 决定走哪条出边。"""
        task = self.get_object()
        if task.status != "pending":
            return fail("任务已处理")
        action_name = request.data.get("action") or "approve"
        result = request.data.get("result") or {}
        user = request.user if request.user and request.user.is_authenticated else None
        run = resume_run(task.run, action=action_name, output={**result, "action": action_name}, user=user)
        return ok(RunDetailSerializer(run).data)


@api_view(["GET", "POST"])
def open_trigger(request, key):
    """对外暴露的编排接口：/api/x/<key>"""
    definition = Definition.objects.filter(key=key, status="published").order_by("-version").first()
    if definition is None:
        return fail(f"未找到已发布的编排: {key}", http_status=status.HTTP_404_NOT_FOUND)
    trigger_type = definition.trigger_type()
    if trigger_type not in ("http", "manual"):
        return fail(f"编排 {key} 未开启 HTTP 触发", http_status=status.HTTP_405_METHOD_NOT_ALLOWED)
    method = (definition.trigger or {}).get("method", "POST").upper()
    if method == "GET" and request.method != "GET":
        return fail("该接口只支持 GET", http_status=status.HTTP_405_METHOD_NOT_ALLOWED)
    payload = dict(request.query_params) if request.method == "GET" else (request.data or {})
    user = request.user if request.user and request.user.is_authenticated else None
    # 对外接口默认同步返回执行结果（调用方通常只关心结果）；加 ?async=1 改为入队
    async_mode = request.query_params.get("async") in ("1", "true", "True")
    run = submit_run(definition, payload, trigger="http", user=user, sync=not async_mode)

    if run.status == "pending":  # 已入队，返回 202 让调用方按 run_id 轮询
        return Response(
            {"code": 0, "message": "accepted",
             "data": {"run_id": run.id, "status": "pending", "output": None}},
            status=status.HTTP_202_ACCEPTED,
        )
    if run.status == "suspended":  # 挂在人工任务上，等待处理
        return Response(
            {"code": 0, "message": "等待人工处理",
             "data": {"run_id": run.id, "status": "suspended", "task_id": None,
                      "pending_tasks": [t.id for t in run.human_tasks.filter(status="pending")]}},
            status=status.HTTP_202_ACCEPTED,
        )
    http_status = status.HTTP_200_OK if run.status == "success" else status.HTTP_500_INTERNAL_SERVER_ERROR
    return Response(
        {"code": 0 if run.status == "success" else 1,
         "message": run.error or "success",
         "data": {"run_id": run.id, "status": run.status, "output": run.output}},
        status=http_status,
    )
