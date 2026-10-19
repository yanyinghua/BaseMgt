from django.apps import AppConfig


class OrchestrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.orchestration"
    verbose_name = "业务编排"

    def ready(self):
        # 注册全部节点插件
        from . import nodes  # noqa: F401
