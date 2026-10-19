from rest_framework import serializers

from .models import DataSource, Module, StoredProcedure, StoredProcedureVersion


class ModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = [
            "id", "key", "name", "parent", "icon", "sort_order", "status",
            "description", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class DataSourceSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = DataSource
        fields = [
            "id", "key", "name", "engine", "host", "port", "database", "username",
            "password", "has_password", "options", "is_default", "status", "remark",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_has_password(self, obj):
        return bool(obj.password)

    def create(self, validated_data):
        raw = validated_data.pop("password", None)
        instance = DataSource(**validated_data)
        instance.set_password(raw or "")
        instance.save()
        return instance

    def update(self, instance, validated_data):
        # 前端不回传口令（空串）时保持原值
        raw = validated_data.pop("password", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if raw:
            instance.set_password(raw)
        instance.save()
        return instance


class StoredProcedureVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoredProcedureVersion
        fields = ["id", "procedure", "version", "ddl", "change_note", "status", "applied_at", "created_at"]
        read_only_fields = ["procedure", "status", "applied_at", "created_at"]


class StoredProcedureSerializer(serializers.ModelSerializer):
    data_source_key = serializers.CharField(source="data_source.key", read_only=True)
    module_name = serializers.CharField(source="module.name", read_only=True, default="")
    current_ddl = serializers.CharField(source="current_version.ddl", read_only=True, default="")
    latest_version = serializers.SerializerMethodField()

    class Meta:
        model = StoredProcedure
        fields = [
            "id", "module", "module_name", "data_source", "data_source_key", "schema", "name",
            "kind", "signature", "returns", "params", "description", "status",
            "current_version", "current_ddl", "latest_version", "deployed_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["status", "current_version", "deployed_at", "created_at", "updated_at"]

    def get_latest_version(self, obj):
        ver = obj.versions.order_by("-version").first()
        return ver.version if ver else 0
