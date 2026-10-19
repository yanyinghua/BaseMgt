"""引擎自测：循环 + 分支 + 人工任务挂起/恢复 + 子流程。"""
from apps.orchestration.engine import execute_run, resume_run, submit_run

def start_run(*args, **kwargs):
    """自测里一律同步执行。"""
    kwargs["sync"] = True
    return submit_run(*args, **kwargs)
from apps.orchestration.models import Definition, HumanTask

Definition.objects.filter(key__startswith="test-").delete()

mk = lambda **kw: Definition.objects.create(**kw)

# ---------- 1. 循环：items 累加 ----------
loop_def = mk(
    key="test-loop", name="循环测试", kind="service", version=1, status="published",
    graph={
        "nodes": [
            {"id": "s", "type": "start", "name": "开始", "config": {}},
            {"id": "init", "type": "transform", "name": "初始化",
             "config": {"assignments": [
                 {"var": "items", "value": {"": ""}},  # 占位，下面用脚本设置
                 {"var": "total", "value": 0}]}},
            {"id": "loop", "type": "loop", "name": "遍历",
             "config": {"source": "{{ vars.items }}", "item_var": "item", "max_iter": 10}},
            {"id": "add", "type": "script", "name": "累加",
             "config": {"code": "vars['total'] = vars['total'] + item"}},
            {"id": "e", "type": "end", "name": "结束", "config": {"output": {"total": "{{ vars.total }}"}}},
        ],
        "edges": [
            {"id": "1", "source": "s", "target": "init"},
            {"id": "2", "source": "init", "target": "loop"},
            {"id": "3", "source": "loop", "sourceHandle": "body", "target": "add"},
            {"id": "4", "source": "add", "target": "loop"},
            {"id": "5", "source": "loop", "sourceHandle": "done", "target": "e"},
        ],
    },
)
# 用脚本节点初始化 items（覆盖 init 里的占位赋值）
loop_def.graph["nodes"][1]["config"] = {"assignments": [
    {"var": "items", "value": [1, 2, 3, 4]},
    {"var": "total", "value": 0}]}
loop_def.save()
run = start_run(loop_def, {}, trigger="test")
print("LOOP  ->", run.status, run.output, run.error)
assert run.status == "success" and run.output == {"total": 10}, (run.status, run.output, run.error)

# ---------- 2. 分支 ----------
branch_def = mk(
    key="test-branch", name="分支测试", kind="service", version=1, status="published",
    graph={
        "nodes": [
            {"id": "s", "type": "start", "name": "开始", "config": {}},
            {"id": "b", "type": "branch", "name": "判断",
             "config": {"rules": [{"var": "{{ input.amount }}", "op": "gt", "value": 100, "handle": "true"}],
                        "else_handle": "false"}},
            {"id": "t", "type": "transform", "name": "大额", "config": {"assignments": [{"var": "level", "value": "high"}]}},
            {"id": "f", "type": "transform", "name": "小额", "config": {"assignments": [{"var": "level", "value": "low"}]}},
            {"id": "e", "type": "end", "name": "结束", "config": {"output": {"level": "{{ vars.level }}"}}},
        ],
        "edges": [
            {"id": "1", "source": "s", "target": "b"},
            {"id": "2", "source": "b", "sourceHandle": "true", "target": "t"},
            {"id": "3", "source": "b", "sourceHandle": "false", "target": "f"},
            {"id": "4", "source": "t", "target": "e"},
            {"id": "5", "source": "f", "target": "e"},
        ],
    },
)
r1 = start_run(branch_def, {"amount": 500}, trigger="test")
r2 = start_run(branch_def, {"amount": 50}, trigger="test")
print("BRANCH->", r1.output, r2.output)
assert r1.output == {"level": "high"} and r2.output == {"level": "low"}

# ---------- 3. 人工任务：挂起 -> 恢复 ----------
flow_def = mk(
    key="test-flow", name="审批流测试", kind="flow", version=1, status="published",
    graph={
        "nodes": [
            {"id": "s", "type": "start", "name": "开始", "config": {}},
            {"id": "h", "type": "human_task", "name": "经理审批",
             "config": {"title": "请审批 {{ input.title }}", "actions": ["approve", "reject"], "output_var": "task"}},
            {"id": "ok", "type": "transform", "name": "通过", "config": {"assignments": [{"var": "result", "value": "approved"}]}},
            {"id": "no", "type": "transform", "name": "驳回", "config": {"assignments": [{"var": "result", "value": "rejected"}]}},
            {"id": "e", "type": "end", "name": "结束", "config": {"output": {"result": "{{ vars.result }}"}}},
        ],
        "edges": [
            {"id": "1", "source": "s", "target": "h"},
            {"id": "2", "source": "h", "sourceHandle": "approve", "target": "ok"},
            {"id": "3", "source": "h", "sourceHandle": "reject", "target": "no"},
            {"id": "4", "source": "ok", "target": "e"},
            {"id": "5", "source": "no", "target": "e"},
        ],
    },
)
run = start_run(flow_def, {"title": "报销单"}, trigger="test")
task = HumanTask.objects.filter(run=run).first()
print("FLOW  ->", run.status, "待办:", task.title if task else None, "| 当前节点:", run.current_node_id)
assert run.status == "suspended" and task and task.status == "pending"
run = resume_run(run, action="approve", output={"comment": "同意"})
print("RESUME->", run.status, run.output, "任务状态:", HumanTask.objects.get(pk=task.id).status)
assert run.status == "success" and run.output == {"result": "approved"}

# ---------- 4. 子流程 ----------
sub_def = mk(
    key="test-subflow", name="子流程调用", kind="service", version=1, status="published",
    graph={
        "nodes": [
            {"id": "s", "type": "start", "name": "开始", "config": {}},
            {"id": "call", "type": "subflow", "name": "调用循环",
             "config": {"definition_key": "test-loop", "input": {}, "assign_var": "sub"}},
            {"id": "e", "type": "end", "name": "结束", "config": {"output": {"total": "{{ vars.sub.total }}"}}},
        ],
        "edges": [{"id": "1", "source": "s", "target": "call"}, {"id": "2", "source": "call", "target": "e"}],
    },
)
run = start_run(sub_def, {}, trigger="test")
print("SUB   ->", run.status, run.output, run.error)
assert run.status == "success" and run.output == {"total": 10}

# ---------- 5. 失败与 continue_on_error ----------
err_def = mk(
    key="test-error", name="错误测试", kind="service", version=1, status="published",
    graph={
        "nodes": [
            {"id": "s", "type": "start", "name": "开始", "config": {}},
            {"id": "sql", "type": "sql", "name": "错误SQL",
             "config": {"sql": "select * from not_exist_table", "continue_on_error": True}},
            {"id": "e", "type": "end", "name": "结束", "config": {"output": {"err": "{{ node.sql.error }}"}}},
        ],
        "edges": [{"id": "1", "source": "s", "target": "sql"}, {"id": "2", "source": "sql", "target": "e"}],
    },
)
run = start_run(err_def, {}, trigger="test")
print("ERROR ->", run.status, str(run.output)[:80])
assert run.status == "success" and "not_exist_table" in str(run.output)

print("\n全部引擎自测通过 ✅")
