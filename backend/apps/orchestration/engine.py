"""编排执行引擎。

按"当前节点 -> 决定出边 -> 下一节点"的方式解释执行图，天然支持
分支、循环、人工任务挂起/恢复与子流程。
"""
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

from . import registry
from .context import json_safe, render_value
from .models import HumanTask, NodeRun, Run


class RunError(Exception):
    """运行期业务异常（节点失败等）。"""


class RunCancelled(RunError):
    """运行被取消。"""


class RunTimeout(RunError):
    """运行超时。"""


class NodeContext:
    """传给节点插件的执行上下文。"""

    def __init__(self, runner, node_run, node):
        self.runner = runner
        self.run = runner.run
        self.node_run = node_run
        self.node_id = node.get("id")
        self.node_type = node.get("type")
        self.scope = runner.scope
        self.loop_items = []
        self.pending_task = None

    def render(self, value):
        return render_value(value, self.scope)

    def set_var(self, name, value):
        self.runner.set_var(name, value)

    def log(self, message, level="info"):
        self.runner.log(message, level)

    def row_scope(self, scope_key):
        """数据行级过滤片段（来自角色数据范围），特权用户返回 None 表示不限制。"""
        return self.runner.row_scope(scope_key)


class Runner:
    def __init__(self, run):
        self.run = run
        self.graph = run.graph_snapshot or {}
        self.nodes = {n["id"]: n for n in self.graph.get("nodes", [])}
        self.edges = self.graph.get("edges", [])
        self.out_edges = defaultdict(list)
        self.in_degree = Counter()
        for edge in self.edges:
            self.out_edges[edge.get("source")].append(edge)
            self.in_degree[edge.get("target")] += 1
        self.scope = run.vars or {"input": {}, "vars": {}, "node": {}, "env": {}}
        self.scope.setdefault("input", run.input or {})
        self.scope.setdefault("vars", {})
        self.scope.setdefault("node", {})
        self.scope.setdefault("env", {})
        self.scope["env"].update({
            "run_id": run.id,
            "definition": run.definition.key,
            "now": timezone.now().isoformat(),
            "trigger": run.trigger,
        })
        self.steps = 0
        self.status = "running"
        self._logs = []
        self._current_node_run = None
        self.max_steps = getattr(settings, "BM_MAX_RUN_STEPS", 2000)
        self.last_loop_items = []
        timeout = int(getattr(settings, "BM_RUN_TIMEOUT", 0) or 0)
        self.deadline = (timezone.now() + timedelta(seconds=timeout)) if timeout > 0 else None

    # ---------- 对外入口 ----------

    def start(self):
        self.run.status = "running"
        self.run.started_at = timezone.now()
        self.run.save(update_fields=["status", "started_at", "updated_at"])
        try:
            node_id = self.run.current_node_id or self._find_start()
            if not node_id:
                raise RunError("流程图为空或缺少开始节点")
            self.walk(node_id)
            if self.status == "running":
                self._finish("success")
        except RunCancelled as exc:
            self._finish("cancelled", str(exc))
        except RunTimeout as exc:
            self._finish("failed", str(exc))
        except Exception as exc:  # noqa: BLE001
            detail = str(exc) or traceback.format_exc(limit=3)
            self._finish("failed", detail)
        return self.run

    def resume(self, action="approve", output=None):
        """人工任务处理完成后继续执行。"""
        node_id = self.run.current_node_id
        node = self.nodes.get(node_id) or {}
        config = node.get("config") or {}

        task = HumanTask.objects.filter(run=self.run, node_id=node_id, status="pending").order_by("-id").first()
        if task:
            task.status = "done"
            task.action = action
            task.result = output or {}
            task.decided_at = timezone.now()
            task.decided_by = getattr(self, "_user", None)
            task.save()

        payload = {"action": action, **(output or {})}
        self.scope["node"][node_id] = payload
        if config.get("output_var"):
            self.set_var(config["output_var"], payload)

        self.run.status = "running"
        self.run.current_node_id = ""
        self.run.save(update_fields=["status", "current_node_id", "updated_at"])
        try:
            targets = self.targets(node_id, [action])
            for extra in targets[1:]:
                self.walk(extra, stop_at_join=True)
            if targets:
                self.walk(targets[0])
            if self.status == "running":
                self._finish("success")
        except Exception as exc:  # noqa: BLE001
            self._finish("failed", str(exc))
        return self.run

    # ---------- 执行循环 ----------

    def walk(self, node_id, stop_ids=frozenset(), stop_at_join=False):
        while node_id:
            if node_id in stop_ids:
                return
            if stop_at_join and self.in_degree.get(node_id, 0) > 1:
                return  # 汇聚节点交由主流程执行，避免重复
            self._check_control()
            if self.steps >= self.max_steps:
                raise RunError(f"执行步数超过上限 {self.max_steps}，可能存在死循环")

            node = self.nodes.get(node_id)
            if node is None:
                raise RunError(f"节点不存在: {node_id}")

            result = self.exec_node(node)
            if result.status == "suspended":
                self._suspend(node_id)
                return

            if node.get("type") == "loop":
                body = self.targets(node_id, ["body"])
                done = self.targets(node_id, ["done"])
                config = node.get("config") or {}
                max_iter = int(config.get("max_iter") or 500)
                items = self.last_loop_items[:max_iter]
                for index, item in enumerate(items):
                    self.scope["item"] = json_safe(item)
                    if config.get("item_var"):
                        self.set_var(config["item_var"], item)
                    if config.get("index_var"):
                        self.set_var(config["index_var"], index)
                    if body:
                        self.walk(body[0], stop_ids | {node_id})
                node_id = done[0] if done else None
                continue

            targets = self.targets(node_id, result.handles)
            if not targets:
                return
            for extra in targets[1:]:
                self.walk(extra, stop_ids, stop_at_join=True)
            node_id = targets[0]

    def exec_node(self, node):
        from .nodes.base import NodeResult

        self.steps += 1
        node_id = node["id"]
        config = node.get("config") or {}
        node_run = NodeRun.objects.create(
            run=self.run,
            node_id=node_id,
            node_type=node.get("type", ""),
            node_name=node.get("name", ""),
            order=self.steps,
            status="running",
            config=config,
            started_at=timezone.now(),
        )
        self._current_node_run = node_run
        self._logs = []
        ctx = NodeContext(self, node_run, node)
        started = time.time()
        try:
            handler_cls = registry.get_node_class(node.get("type", ""))
            result = handler_cls().execute(ctx, config)
            output = json_safe(result.output)
        except Exception as exc:  # noqa: BLE001
            self._close_node_run(node_run, "failed", started, error=str(exc))
            self.log(f"节点执行失败: {exc}", level="error")
            if config.get("continue_on_error"):
                output = {"error": str(exc)}
                result = NodeResult(output=output)
            else:
                raise RunError(f"[{node.get('name') or node.get('type')}] {exc}") from exc

        self.scope["node"][node_id] = output
        self.last_loop_items = ctx.loop_items
        if result.status == "suspended":
            self._close_node_run(node_run, "running", started, output=output)
            return result
        self._close_node_run(node_run, "success", started, output=output)
        self.run.vars = self.scope
        self.run.save(update_fields=["vars", "updated_at"])
        return result

    # ---------- 辅助 ----------

    def _check_control(self):
        """协作式取消与超时：读库判断运行是否被外部取消。"""
        if self.deadline and timezone.now() > self.deadline:
            raise RunTimeout("运行超时")
        status = Run.objects.filter(pk=self.run.pk).values_list("status", flat=True).first()
        if status == "cancelled":
            raise RunCancelled("运行已被取消")

    def _find_start(self):
        for node in self.graph.get("nodes", []):
            if node.get("type") in ("start", "trigger"):
                return node["id"]
        nodes = self.graph.get("nodes", [])
        return nodes[0]["id"] if nodes else None

    def targets(self, node_id, handles):
        wanted = {h or "default" for h in (handles or [])}
        result = []
        for edge in self.out_edges.get(node_id, []):
            handle = edge.get("sourceHandle") or "default"
            if handle in wanted:
                result.append(edge.get("target"))
        return result

    def set_var(self, name, value):
        value = json_safe(value)
        parts = str(name).split(".")
        cursor = self.scope["vars"]
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
            if not isinstance(cursor, dict):
                return
        cursor[parts[-1]] = value

    def log(self, message, level="info"):
        entry = {"t": datetime.now().strftime("%H:%M:%S"), "level": level, "message": str(message)}
        self._logs.append(entry)

    def row_scope(self, scope_key):
        from apps.iam.access import row_scope_for_user

        return row_scope_for_user(self.run.triggered_by, scope_key)

    def _close_node_run(self, node_run, status, started, output=None, error=""):
        node_run.status = status
        node_run.output = output if output is not None else {}
        node_run.logs = self._logs
        node_run.error = error
        node_run.finished_at = timezone.now()
        node_run.duration_ms = int((time.time() - started) * 1000)
        node_run.save()

    def _suspend(self, node_id):
        self.status = "suspended"
        self.run.status = "suspended"
        self.run.current_node_id = node_id
        self.run.vars = self.scope
        self.run.save(update_fields=["status", "current_node_id", "vars", "updated_at"])

    def _finish(self, status, error=""):
        self.status = status
        self.run.status = status
        self.run.error = error
        self.run.vars = self.scope
        self.run.finished_at = timezone.now()
        if self.run.started_at:
            self.run.duration_ms = int((self.run.finished_at - self.run.started_at).total_seconds() * 1000)
        self.run.save(update_fields=["status", "error", "vars", "finished_at", "duration_ms", "updated_at"])
        self.run.definition.last_run_at = timezone.now()
        self.run.definition.save(update_fields=["last_run_at"])


# ---------- 便捷入口 ----------


def submit_run(definition, input_data=None, trigger="manual", user=None, parent_run=None, sync=False):
    """创建一次运行。默认按 BM_ASYNC_RUN 决定同步执行还是入队由 worker 执行。"""
    run = Run.objects.create(
        definition=definition,
        parent_run=parent_run,
        status="pending",
        trigger=trigger,
        triggered_by=user,
        input=json_safe(input_data or {}),
        graph_snapshot=definition.graph or {},
        vars={"input": json_safe(input_data or {}), "vars": {}, "node": {}, "env": {}},
        started_at=timezone.now(),
    )
    from django.conf import settings as _s

    if sync or parent_run is not None or not getattr(_s, "BM_ASYNC_RUN", False):
        return execute_run(run)
    return run


def execute_run(run):
    """真正执行（供 worker、子流程、同步调用使用）。"""
    runner = Runner(run)
    return runner.start()


def run_definition_by_key(key, input_data=None, trigger="manual", user=None, parent_run=None):
    from .models import Definition

    definition = Definition.objects.filter(key=key, status="published").order_by("-version").first()
    if definition is None:
        raise ValueError(f"未找到已发布的编排定义: {key}")
    return submit_run(definition, input_data, trigger=trigger, user=user, parent_run=parent_run, sync=True)


def resume_run(run, action="approve", output=None, user=None):
    runner = Runner(run)
    runner._user = user
    return runner.resume(action=action, output=output)
