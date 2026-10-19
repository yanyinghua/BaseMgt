from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import DefinitionViewSet, HumanTaskViewSet, RunViewSet, node_types, open_trigger

router = DefaultRouter()
router.register("definitions", DefinitionViewSet, basename="definition")
router.register("runs", RunViewSet, basename="run")
router.register("human-tasks", HumanTaskViewSet, basename="human-task")

urlpatterns = router.urls + [
    path("node-types", node_types),
    path("x/<str:key>", open_trigger),
]
