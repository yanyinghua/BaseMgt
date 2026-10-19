from rest_framework.routers import DefaultRouter

from .views import PageDefinitionViewSet

router = DefaultRouter()
router.register("pages", PageDefinitionViewSet, basename="page")

urlpatterns = router.urls
