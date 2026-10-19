from rest_framework.routers import DefaultRouter

from .views import DataSourceViewSet, ModuleViewSet, StoredProcedureViewSet

router = DefaultRouter()
router.register("modules", ModuleViewSet, basename="module")
router.register("datasources", DataSourceViewSet, basename="datasource")
router.register("procedures", StoredProcedureViewSet, basename="procedure")

urlpatterns = router.urls
