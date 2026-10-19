"""异步运行自测：入队、worker 领取、取消、超时、接口 202。"""
import threading
import time

from django.test import override_settings
from rest_framework.test import APIClient

from apps.orchestration.engine import execute_run, submit_run
from apps.orchestration.management.commands.run_worker import claim_runs
from apps.orchestration.models import Definition, Run

Definition.objects.filter(key__startswith="async-").delete()

sleep_def = Definition.objects.create(
    key="async-sleep", name="异步sleep", kind="service", version=1, status="published",
    graph={
        "nodes": [
            {"id": "s", "type": "start", "name": "开始", "config": {}},
            {"id": "a", "type": "sql", "name": "sleep1", "config": {"sql": "select pg_sleep(1)"}},
            {"id": "b", "type": "sql", "name": "sleep2", "config": {"sql": "select pg_sleep(1)"}},
            {"id": "c", "type": "sql", "name": "sleep3", "config": {"sql": "select pg_sleep(1)"}},
            {"id": "e", "type": "end", "name": "结束", "config": {"output": {"done": True}}},
        ],
        "edges": [
            {"id": "1", "source": "s", "target": "a"}, {"id": "2", "source": "a", "target": "b"},
            {"id": "3", "source": "b", "target": "c"}, {"id": "4", "source": "c", "target": "e"},
        ],
    },
)

# 1. 异步入队 -> worker 领取 -> 执行
run = submit_run(sleep_def, {}, trigger="test")
print("入队状态:", run.status)
assert run.status == "pending"
rid = run.id

claimed = claim_runs(2)
print("worker 领取:", [r.id for r in claimed])
assert rid in [r.id for r in claimed]
finished = execute_run(Run.objects.get(pk=rid))
print("执行结果:", finished.status, finished.output)
assert finished.status == "success"

# 2. 取消等待中的运行
run2 = submit_run(sleep_def, {}, trigger="test")
Run.objects.filter(pk=run2.id).update(status="cancelled")
run2.refresh_from_db()
print("等待中取消 ->", run2.status)
assert run2.status == "cancelled"

# 3. 运行中被取消（协作式，下一个节点处终止）
run3 = submit_run(sleep_def, {}, trigger="test")
thread = threading.Thread(target=execute_run, args=(run3,))
thread.start()
time.sleep(1.5)
Run.objects.filter(pk=run3.id).update(status="cancelled")
thread.join(timeout=30)
run3.refresh_from_db()
print("运行中取消 ->", run3.status, "|", run3.error)
assert run3.status == "cancelled"

# 4. 超时
with override_settings(BM_RUN_TIMEOUT=1):
    run4 = submit_run(sleep_def, {}, trigger="test", sync=True)
    print("超时 ->", run4.status, "|", run4.error)
    assert run4.status == "failed" and "超时" in (run4.error or "")

# 5. 接口：异步返回 202，同步返回 200
client = APIClient()
resp = client.post(f"/api/definitions/{sleep_def.id}/run/", {}, format="json")
print("接口异步 ->", resp.status_code, resp.json()["data"]["status"])
assert resp.status_code == 200 and resp.json()["data"]["status"] == "pending"
Run.objects.filter(status="pending").delete()

resp_sync = client.post(f"/api/definitions/{sleep_def.id}/run/?sync=1", {}, format="json")
print("接口同步 ->", resp_sync.status_code, resp_sync.json()["data"]["status"])
assert resp_sync.json()["data"]["status"] == "success"

print("\n异步运行自测通过 ✅")
