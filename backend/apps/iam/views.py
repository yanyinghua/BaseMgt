from django.contrib.auth import authenticate, get_user_model, login, logout
from rest_framework import viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.response import fail, ok

from .access import ensure_builtin_roles, is_dev_mode, user_role_keys
from .models import DataScope, ObjectGrant, Role, UserRole
from .permissions import IsPrivileged, PermModelViewSet
from .serializers import RESOURCE_MODELS, DataScopeSerializer, GrantSerializer, RoleSerializer, UserRoleSerializer


class RoleViewSet(PermModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [IsPrivileged]

    @action(detail=False, methods=["post"])
    def init_builtin(self, request):
        ensure_builtin_roles()
        return ok({"created": True})


class UserRoleViewSet(PermModelViewSet):
    queryset = UserRole.objects.select_related("user", "role")
    serializer_class = UserRoleSerializer
    permission_classes = [IsPrivileged]


class GrantViewSet(PermModelViewSet):
    queryset = ObjectGrant.objects.select_related("role", "user")
    serializer_class = GrantSerializer
    permission_classes = [IsPrivileged]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get("model"):
            dotted = RESOURCE_MODELS.get(params["model"])
            if dotted:
                app_label, model = dotted.split(".")
                qs = qs.filter(content_type__app_label=app_label, content_type__model=model.lower())
        if params.get("object_id"):
            qs = qs.filter(object_id=params["object_id"])
        return qs

    @action(detail=False, methods=["get"])
    def resource_types(self, request):
        return ok([{"key": k, "value": v} for k, v in RESOURCE_MODELS.items()])


class DataScopeViewSet(PermModelViewSet):
    queryset = DataScope.objects.select_related("role")
    serializer_class = DataScopeSerializer
    permission_classes = [IsPrivileged]


@api_view(["GET"])
def me(request):
    """当前登录者信息；开发模式下按管理员处理。"""
    user = request.user
    authenticated = bool(user and user.is_authenticated)
    dev = is_dev_mode()
    roles = sorted(user_role_keys(user)) if authenticated else []
    return ok({
        # 开发模式下未登录也按已登录处理，避免本地调试被登录页挡住
        "authenticated": authenticated or dev,
        "username": user.username if authenticated else ("dev" if dev else ""),
        "is_superuser": bool(getattr(user, "is_superuser", False)) or dev,
        "roles": roles or (["admin"] if dev else []),
        "dev_mode": dev,
    })


@api_view(["POST"])
def login_view(request):
    username = request.data.get("username") or ""
    password = request.data.get("password") or ""
    user = authenticate(request, username=username, password=password)
    if user is None:
        return fail("用户名或密码错误")
    login(request, user)
    return ok({"username": user.username, "roles": sorted(user_role_keys(user)), "is_superuser": user.is_superuser})


@api_view(["POST"])
def logout_view(request):
    logout(request)
    return ok({"logout": True})


@api_view(["GET"])
def users(request):
    User = get_user_model()
    return ok(list(User.objects.values("id", "username", "is_superuser", "is_active")))


@api_view(["POST"])
@permission_classes([IsPrivileged])
def set_password(request):
    """管理员重置用户口令。"""
    User = get_user_model()
    user = User.objects.filter(pk=request.data.get("user_id")).first()
    if not user:
        return fail("用户不存在")
    user.set_password(request.data.get("password") or "")
    user.save()
    return ok({"updated": True})


login_view.permission_classes = [AllowAny]
logout_view.permission_classes = [AllowAny]
