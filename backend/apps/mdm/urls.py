from rest_framework.routers import DefaultRouter

from .views import (
    DictionaryItemViewSet,
    DictionaryViewSet,
    EntityDefinitionViewSet,
    FieldDefinitionViewSet,
)

router = DefaultRouter()
router.register("mdm/entities", EntityDefinitionViewSet, basename="mdm-entity")
router.register("mdm/fields", FieldDefinitionViewSet, basename="mdm-field")
router.register("mdm/dictionaries", DictionaryViewSet, basename="mdm-dictionary")
router.register("mdm/dict-items", DictionaryItemViewSet, basename="mdm-dict-item")

urlpatterns = router.urls
