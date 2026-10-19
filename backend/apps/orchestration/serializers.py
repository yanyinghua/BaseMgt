from rest_framework import serializers

from .models import Definition, HumanTask, NodeRun, Run


class DefinitionListSerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(source="module.name", read_only=True, default="")
    node_count = serializers.SerializerMethodField()
    trigger_type = serializers.SerializerMethodField()

    class Meta:
        model = Definition
        fields = [
            "id", "key", "name", "kind", "version", "status", "module", "module_name",
            "trigger", "trigger_type", "node_count", "description", "last_run_at",
            "created_at", "updated_at",
        ]

    def get_node_count(self, obj):
        return len(obj.nodes)

    def get_trigger_type(self, obj):
        return obj.trigger_type()


class DefinitionSerializer(DefinitionListSerializer):
    graph = serializers.JSONField()
    input_schema = serializers.JSONField()
    output_schema = serializers.JSONField()

    class Meta(DefinitionListSerializer.Meta):
        fields = DefinitionListSerializer.Meta.fields + ["graph", "input_schema", "output_schema"]


class NodeRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = NodeRun
        fields = [
            "id", "node_id", "node_type", "node_name", "order", "status",
            "config", "input", "output", "logs", "error",
            "started_at", "finished_at", "duration_ms",
        ]


class RunListSerializer(serializers.ModelSerializer):
    definition_key = serializers.CharField(source="definition.key", read_only=True)
    definition_name = serializers.CharField(source="definition.name", read_only=True)

    class Meta:
        model = Run
        fields = [
            "id", "definition", "definition_key", "definition_name", "status", "trigger",
            "started_at", "finished_at", "duration_ms", "error", "created_at",
        ]


class RunDetailSerializer(RunListSerializer):
    node_runs = NodeRunSerializer(many=True, read_only=True)
    graph_snapshot = serializers.JSONField(read_only=True)

    class Meta(RunListSerializer.Meta):
        fields = RunListSerializer.Meta.fields + ["input", "output", "vars", "graph_snapshot", "node_runs"]


class HumanTaskSerializer(serializers.ModelSerializer):
    definition_name = serializers.CharField(source="run.definition.name", read_only=True)
    assignee_name = serializers.CharField(source="assignee.username", read_only=True, default="")

    class Meta:
        model = HumanTask
        fields = [
            "id", "run", "node_id", "title", "description", "assignee", "assignee_name",
            "form_schema", "status", "action", "result", "definition_name",
            "created_at", "decided_at",
        ]
        read_only_fields = ["run", "node_id", "status", "action", "result", "decided_at", "created_at"]
