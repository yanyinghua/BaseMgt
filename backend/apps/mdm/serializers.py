from rest_framework import serializers

from apps.mdm.models import (
    Dictionary,
    DictionaryItem,
    EntityDefinition,
    EntityDdlLog,
    FieldDefinition,
)


class DictionaryItemSerializer(serializers.ModelSerializer):
    dictionary_key = serializers.CharField(source="dictionary.key", read_only=True, default="")

    class Meta:
        model = DictionaryItem
        fields = [
            "id", "dictionary", "dictionary_key", "value", "label", "parent",
            "sort_order", "is_default", "status", "description", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class DictionarySerializer(serializers.ModelSerializer):
    items = DictionaryItemSerializer(many=True, read_only=True)
    item_count = serializers.SerializerMethodField()
    module_name = serializers.CharField(source="module.name", read_only=True, default="")

    class Meta:
        model = Dictionary
        fields = ["id", "key", "name", "description", "status", "module", "module_name",
                  "items", "item_count", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]

    def get_item_count(self, obj):
        return obj.items.count()


class FieldSerializer(serializers.ModelSerializer):
    ref_entity_key = serializers.CharField(source="ref_entity.key", read_only=True, default="")
    ref_entity_name = serializers.CharField(source="ref_entity.name", read_only=True, default="")
    dictionary_key = serializers.CharField(source="dictionary.key", read_only=True, default="")
    dictionary_options = serializers.SerializerMethodField()

    class Meta:
        model = FieldDefinition
        fields = [
            "id", "entity", "name", "label", "data_type", "length", "precision", "scale",
            "nullable", "unique", "indexed", "default_value", "enum_options",
            "dictionary", "dictionary_key", "dictionary_options",
            "ref_entity", "ref_entity_key", "ref_entity_name", "ref_display",
            "is_system", "is_extended", "visible_in_list", "queryable", "sort_order",
            "status", "description", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_dictionary_options(self, obj):
        from .generators import enum_options

        return enum_options(obj) if obj.data_type == "enum" else []


class EntitySerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(source="module.name", read_only=True, default="")
    data_source_key = serializers.CharField(source="data_source.key", read_only=True, default="")
    field_count = serializers.SerializerMethodField()
    extended_count = serializers.SerializerMethodField()
    is_tree = serializers.SerializerMethodField()
    tree_parent_field = serializers.SerializerMethodField()

    class Meta:
        model = EntityDefinition
        fields = [
            "id", "key", "name", "category", "schema", "table_name", "label_field",
            "module", "module_name", "data_source", "data_source_key", "options",
            "status", "revision", "synced_at", "description",
            "list_definition", "save_definition", "page",
            "field_count", "extended_count", "is_tree", "tree_parent_field",
            "created_at", "updated_at",
        ]
        read_only_fields = ["revision", "synced_at", "list_definition", "save_definition", "page",
                            "created_at", "updated_at"]

    def get_field_count(self, obj):
        return obj.fields.count()

    def get_extended_count(self, obj):
        return obj.fields.filter(is_extended=True).count()

    def get_is_tree(self, obj):
        return obj.is_tree

    def get_tree_parent_field(self, obj):
        return obj.tree_parent_field


class EntityDdlLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = EntityDdlLog
        fields = ["id", "entity", "revision", "action", "sql", "success", "message", "applied_by", "created_at"]
