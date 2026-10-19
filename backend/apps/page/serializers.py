from rest_framework import serializers

from .models import PageDefinition


class PageDefinitionSerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(source="module.name", read_only=True, default="")

    class Meta:
        model = PageDefinition
        fields = [
            "id", "key", "name", "module", "module_name", "page_type", "schema",
            "bindings", "status", "description", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
