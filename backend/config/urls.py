from django.contrib import admin
from django.urls import include, path
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.response import ok


@api_view(["GET"])
def health(request):
    return ok({"status": "up", "service": "BaseMgt"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health", health),
    path("api/", include("apps.iam.urls")),
    path("api/", include("apps.mdm.urls")),
    path("api/", include("apps.catalog.urls")),
    path("api/", include("apps.orchestration.urls")),
    path("api/", include("apps.page.urls")),
]
