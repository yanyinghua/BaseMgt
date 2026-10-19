"""DRF 权限类与 ViewSet 基类。"""
from django.conf import settings
from rest_framework import permissions, status
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from apps.core.response import ok

from .access import filter_queryset, has_perm

DEFAULT_ACTION_MAP = {
    "list": "read",
    "retrieve": "read",
    "create": "write",
    "update": "write",
    "partial_update": "write",
    "destroy": "write",
    "publish": "write",
    "unpublish": "write",
    "clone": "write",
    "run": "run",
    "retry": "run",
    "cancel": "run",
    "complete": "run",
    "validate": "read",
    "versions": "write",
    "apply_version": "write",
    "drop": "admin",
    "call": "run",
    "pull": "write",
    "data": "run",
    "sql": "run",
    "test": "read",
    "schemas": "read",
    "tables": "read",
    "columns": "read",
    "sync_procedures": "write",
    "runs": "read",
}


class BaseMgtPermission(permissions.BasePermission):
    """按 view.perm_action_map 把 DRF action 映射成 read/write/run/admin。"""

    def has_permission(self, request, view):
        from .access import is_dev_mode

        if not getattr(request.user, "is_authenticated", False) and not is_dev_mode():
            return False
        action = getattr(view, "action", None)
        need = getattr(view, "perm_action_map", {}).get(action) or DEFAULT_ACTION_MAP.get(action)
        if need is None:
            return True
        if action == "create":
            obj = self._target_object(request, view)
            if obj is None:
                # 无归属对象（如新建模块/角色）：需要全局权限
                return has_perm(request.user, need, None)
            return has_perm(request.user, need, obj)
        return True  # 对象级在 has_object_permission 里判；列表在 queryset 过滤

    def has_object_permission(self, request, view, obj):
        action = getattr(view, "action", None)
        need = getattr(view, "perm_action_map", {}).get(action) or DEFAULT_ACTION_MAP.get(action)
        if need is None:
            return True
        return has_perm(request.user, need, obj)

    def _target_object(self, request, view):
        """新建时按请求体里的归属字段推断授权对象。"""
        from apps.catalog.models import Module

        module_id = request.data.get("module")
        if module_id:
            return Module.objects.filter(pk=module_id).first()
        return None


class IsPrivileged(permissions.BasePermission):
    """仅超级用户 / admin 角色 / 开发模式可用。"""

    def has_permission(self, request, view):
        from .access import is_privileged

        if is_privileged(request.user):
            return True
        return False


class PermQuerysetMixin:
    """按授权过滤 queryset，并把 CRUD 响应统一成 {code,message,data}。"""

    permission_classes = [BaseMgtPermission]
    perm_action_map = DEFAULT_ACTION_MAP
    # 上级对象路径，用于权限继承，如 Definition 填 ['module']，Run 填 ['definition', 'definition__module']
    perm_owner_paths = ()

    def get_queryset(self):
        qs = super().get_queryset()
        action = getattr(self, "action", None)
        need = self.perm_action_map.get(action, "read")
        return filter_queryset(self.request.user, qs, need, self.perm_owner_paths)

    # ---- 统一响应信封 ----
    def list(self, request, *args, **kwargs):
        return ok(super().list(request, *args, **kwargs).data)

    def retrieve(self, request, *args, **kwargs):
        return ok(super().retrieve(request, *args, **kwargs).data)

    def create(self, request, *args, **kwargs):
        return ok(super().create(request, *args, **kwargs).data, http_status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        return ok(super().update(request, *args, **kwargs).data)

    def partial_update(self, request, *args, **kwargs):
        return ok(super().partial_update(request, *args, **kwargs).data)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return ok({"deleted": True})


class PermModelViewSet(PermQuerysetMixin, ModelViewSet):
    """带对象级授权过滤的 ModelViewSet 基类。"""


class PermReadOnlyModelViewSet(PermQuerysetMixin, ReadOnlyModelViewSet):
    """带对象级授权过滤的只读 ViewSet 基类。"""


def dev_mode_enabled():
    return getattr(settings, "BM_AUTH_DISABLED", False)
