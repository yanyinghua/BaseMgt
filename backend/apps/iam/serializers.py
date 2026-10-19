from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from .models import DataScope, ObjectGrant, Role, UserRole

# 前端授权时可选择的资源类型
RESOURCE_MODELS = {
    "module": "catalog.Module",
    "definition": "orchestration.Definition",
    "procedure": "catalog.StoredProcedure",
    "page": "page.PageDefinition",
    "datasource": "catalog.DataSource",
}


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "key", "name", "description", "is_builtin", "created_at"]
        read_only_fields = ["created_at"]


class UserRoleSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    role_key = serializers.CharField(source="role.key", read_only=True)
    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model = UserRole
        fields = ["id", "user", "username", "role", "role_key", "role_name"]


class GrantSerializer(serializers.ModelSerializer):
    target_model = serializers.CharField(write_only=True, required=False)
    content_type_model = serializers.CharField(source="content_type.model", read_only=True)
    target_name = serializers.SerializerMethodField()
    role_key = serializers.CharField(source="role.key", read_only=True, default="")
    username = serializers.CharField(source="user.username", read_only=True, default="")

    class Meta:
        model = ObjectGrant
        fields = [
            "id", "content_type", "content_type_model", "target_model", "object_id",
            "target_name", "role", "role_key", "user", "username", "actions", "created_at",
        ]
        read_only_fields = ["content_type", "created_at"]

    def get_target_name(self, obj):
        return str(obj.target) if obj.target else f"#{obj.object_id}"

    def validate(self, attrs):
        if not attrs.get("role") and not attrs.get("user"):
            raise serializers.ValidationError("角色与用户至少填一个")
        return attrs

    def create(self, validated_data):
        model_key = validated_data.pop("target_model", None)
        ct = validated_data.pop("content_type", None)
        if ct is None:
            dotted = RESOURCE_MODELS.get(model_key)
            if not dotted:
                raise serializers.ValidationError({"target_model": f"未知资源类型: {model_key}"})
            app_label, model = dotted.split(".")
            ct = ContentType.objects.get(app_label=app_label, model=model.lower())
        return ObjectGrant.objects.create(content_type=ct, **validated_data)


class DataScopeSerializer(serializers.ModelSerializer):
    role_key = serializers.CharField(source="role.key", read_only=True)

    class Meta:
        model = DataScope
        fields = ["id", "key", "role", "role_key", "filter_sql", "description"]
