from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    DataScopeViewSet,
    GrantViewSet,
    RoleViewSet,
    UserRoleViewSet,
    login_view,
    logout_view,
    me,
    set_password,
    users,
)

router = DefaultRouter()
router.register("roles", RoleViewSet, basename="role")
router.register("user-roles", UserRoleViewSet, basename="user-role")
router.register("grants", GrantViewSet, basename="grant")
router.register("data-scopes", DataScopeViewSet, basename="data-scope")

urlpatterns = router.urls + [
    path("me", me),
    path("users", users),
    path("auth/login", login_view),
    path("auth/logout", logout_view),
    path("auth/set-password", set_password),
]
