"""权限判定与 queryset 过滤。"""
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from .models import DataScope, ObjectGrant, Role, UserRole

ADMIN_ROLE_KEY = "admin"


def is_dev_mode():
    return getattr(settings, "BM_AUTH_DISABLED", False)


def is_privileged(user):
    """超级用户、内置 admin 角色，或开发模式（关闭鉴权）下视为拥有全部权限。"""
    if user is None:
        return is_dev_mode()
    if not getattr(user, "is_authenticated", False):
        return is_dev_mode()
    if getattr(user, "is_superuser", False):
        return True
    return user_role_keys(user).intersection({ADMIN_ROLE_KEY})


def user_role_keys(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return set()
    return set(UserRole.objects.filter(user=user).values_list("role__key", flat=True))


def owner_of(obj):
    """对象的上级对象（用于权限继承）；没有上级则返回 None。"""
    if obj is None:
        return None
    if hasattr(obj, "module_id"):
        return obj.module
    if hasattr(obj, "definition_id"):  # Run -> Definition -> Module
        return obj.definition
    if hasattr(obj, "run_id"):  # HumanTask -> Run -> Definition -> Module
        return obj.run
    return None


def _ancestors(obj):
    seen = set()
    cur = obj
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        yield cur
        cur = owner_of(cur)


def grant_ids(user, model, action):
    """某模型上被直接授予 action（或 admin）的对象 id 集合。"""
    if user is None or not getattr(user, "is_authenticated", False):
        return set()
    ct = ContentType.objects.get_for_model(model)
    query = ObjectGrant.objects.filter(content_type=ct)
    role_ids = UserRole.objects.filter(user=user).values_list("role_id", flat=True)
    query = query.filter(Q(role_id__in=list(role_ids)) | Q(user=user))
    ids = set()
    for actions, object_id in query.values_list("actions", "object_id"):
        if action in (actions or []) or "admin" in (actions or []):
            ids.add(object_id)
    return ids


def has_perm(user, action, obj=None):
    """是否有某动作权限：对象本身或其祖先链上任一被授权即可。"""
    if is_privileged(user):
        return True
    if obj is None:
        return False
    for node in _ancestors(obj):
        if node.pk in grant_ids(user, type(node), action):
            return True
    return False


def _related_model(model, path):
    cur = model
    for part in path.split("__"):
        cur = cur._meta.get_field(part).related_model
    return cur


def filter_queryset(user, qs, action="read", owner_paths=()):
    """按授权过滤 queryset：直接授权 + 上级对象授权（owner_paths 如 ['module']）。"""
    if is_privileged(user):
        return qs
    q = Q(pk__in=grant_ids(user, qs.model, action))
    for path in owner_paths:
        try:
            target_model = _related_model(qs.model, path)
        except Exception:  # noqa: BLE001
            continue
        ids = grant_ids(user, target_model, action)
        q |= Q(**{f"{path}__in": ids})
    return qs.filter(q).distinct()


def row_scope_for_user(user, scope_key):
    """数据行级：返回 SQL 过滤片段（多角色用 OR 合并），特权用户返回 None 表示不限制。"""
    if not scope_key:
        return None
    if is_privileged(user):
        return None
    role_ids = UserRole.objects.filter(user=user).values_list("role_id", flat=True) if (
        user and user.is_authenticated
    ) else []
    filters = list(
        DataScope.objects.filter(key=scope_key, role_id__in=list(role_ids)).values_list("filter_sql", flat=True)
    )
    if not filters:
        return None
    return " OR ".join(f"({f})" for f in filters)


def ensure_builtin_roles():
    """创建内置角色，返回 {key: Role}。"""
    defaults = [
        ("admin", "管理员", "全部权限"),
        ("developer", "开发者", "可设计编排、编写存储过程"),
        ("operator", "操作员", "可运行编排、处理待办"),
        ("viewer", "只读", "仅查看"),
    ]
    roles = {}
    for key, name, desc in defaults:
        role, _ = Role.objects.get_or_create(key=key, defaults={"name": name, "description": desc, "is_builtin": True})
        role.is_builtin = True
        role.save(update_fields=["is_builtin"])
        roles[key] = role
    return roles
