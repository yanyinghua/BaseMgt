"""权限自测：角色授权、对象继承、queryset 过滤、数据行级范围、接口鉴权。"""
from django.contrib.auth import get_user_model
from django.test import override_settings

from apps.catalog.models import Module
from apps.iam.access import ensure_builtin_roles, filter_queryset, has_perm, row_scope_for_user
from apps.iam.models import DataScope, ObjectGrant, UserRole
from apps.orchestration.models import Definition

User = get_user_model()

roles = ensure_builtin_roles()
admin = User.objects.get(username="admin")

u1, _ = User.objects.get_or_create(username="u1", defaults={"is_active": True})
u1.set_password("u1pass")
u1.save()
u1.bm_roles.all().delete()
UserRole.objects.create(user=u1, role=roles["viewer"])

demo = Module.objects.get(key="demo")
other, _ = Module.objects.get_or_create(key="other", defaults={"name": "另一个模块"})
from django.contrib.contenttypes.models import ContentType

ObjectGrant.objects.filter(content_type__model="module").delete()
ct = ContentType.objects.get_for_model(Module)
ObjectGrant.objects.update_or_create(
    content_type=ct, object_id=demo.id, role=roles["viewer"], defaults={"actions": ["read"]}
)

print("has_perm read  demo :", has_perm(u1, "read", demo))
print("has_perm write demo :", has_perm(u1, "write", demo))
print("has_perm read  other:", has_perm(u1, "read", other))
assert has_perm(u1, "read", demo) and not has_perm(u1, "write", demo) and not has_perm(u1, "read", other)

# 编排权限继承模块
defi = Definition.objects.get(key="demo-calc")
print("继承: 编排 read :", has_perm(u1, "read", defi), "| run :", has_perm(u1, "run", defi))
assert has_perm(u1, "read", defi) and not has_perm(u1, "run", defi)

qs = filter_queryset(u1, Definition.objects.all(), "read", ("module",))
print("可见编排:", list(qs.values_list("key", flat=True)))
assert "demo-calc" in [d.key for d in qs] or qs.filter(key="demo-calc").exists()

wq = filter_queryset(u1, Definition.objects.all(), "write", ("module",))
print("可写编排数:", wq.count())
assert wq.count() == 0

aq = filter_queryset(admin, Definition.objects.all(), "read", ("module",))
print("管理员可见编排数:", aq.count())
assert aq.count() == Definition.objects.count()

# 数据行级
DataScope.objects.update_or_create(
    key="sales", role=roles["viewer"], defaults={"filter_sql": "dept_id = 7"}
)
print("行级范围 u1:", row_scope_for_user(u1, "sales"), "| admin:", row_scope_for_user(admin, "sales"))
assert row_scope_for_user(u1, "sales") == "(dept_id = 7)"
assert row_scope_for_user(admin, "sales") is None

# 接口鉴权（关闭开发模式后）
with override_settings(BM_AUTH_DISABLED=False):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=u1)
    r = client.get("/api/definitions/")
    keys = [d["key"] for d in r.json()["data"]] if r.status_code == 200 else r.status_code
    print("u1 GET /api/definitions:", keys)
    assert isinstance(keys, list) and "demo-calc" in keys

    # 无模块授权的用户
    u2, _ = User.objects.get_or_create(username="u2", defaults={"is_active": True})
    client2 = APIClient()
    client2.force_authenticate(user=u2)
    r2 = client2.get("/api/definitions/")
    print("u2 GET /api/definitions:", [d["key"] for d in r2.json()["data"]])
    assert r2.json()["data"] == []

    # 只读用户不能发布
    r3 = client.post(f"/api/definitions/{defi.id}/publish/")
    # 无写权限时该编排对其不可见（404），等同于拒绝
    print("u1 publish ->", r3.status_code, r3.json().get("message"))
    assert r3.status_code in (403, 404)

    # 管理员可以
    cadmin = APIClient()
    cadmin.force_authenticate(user=admin)
    r4 = cadmin.post(f"/api/definitions/{defi.id}/publish/")
    print("admin publish ->", r4.status_code)
    assert r4.status_code == 200

    # 未登录访问
    anon = APIClient()
    r5 = anon.get("/api/definitions/")
    print("匿名 GET /api/definitions ->", r5.status_code)
    assert r5.status_code in (401, 403)


# 开发模式（BM_AUTH_DISABLED=1）下匿名按管理员处理
from rest_framework.test import APIClient as _C

r6 = _C().get("/api/definitions/")
print("开发模式匿名 ->", r6.status_code, "可见数:", len(r6.json().get("data") or []))
assert r6.status_code == 200 and len(r6.json()["data"]) == Definition.objects.count()

print("\n权限自测通过 ✅")
