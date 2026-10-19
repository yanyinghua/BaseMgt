"""节点类型注册表。

新增一种节点 = 写一个继承 BaseNode 的类 + 在 nodes/__init__.py 里 register。
前端画布通过 /api/node-types 拉取配置 schema 自动渲染属性面板。
"""
from collections import OrderedDict

_REGISTRY = OrderedDict()


class NodeMeta:
    def __init__(self, type, name, category, icon="", description="", config_schema=None, handles=None):
        self.type = type
        self.name = name
        self.category = category
        self.icon = icon
        self.description = description
        self.config_schema = config_schema or []
        self.handles = handles or ["default"]

    def to_dict(self):
        return {
            "type": self.type,
            "name": self.name,
            "category": self.category,
            "icon": self.icon,
            "description": self.description,
            "config_schema": self.config_schema,
            "handles": self.handles,
        }


def register(node_cls):
    meta = NodeMeta(
        type=node_cls.type,
        name=getattr(node_cls, "label", node_cls.type),
        category=getattr(node_cls, "category", "通用"),
        icon=getattr(node_cls, "icon", ""),
        description=(node_cls.__doc__ or "").strip().split("\n")[0],
        config_schema=getattr(node_cls, "config_schema", []),
        handles=getattr(node_cls, "handles", ["default"]),
    )
    _REGISTRY[node_cls.type] = node_cls
    node_cls.meta = meta
    return node_cls


def get_node_class(type):
    if type not in _REGISTRY:
        raise ValueError(f"未注册的节点类型: {type}")
    return _REGISTRY[type]


def all_types():
    return {t: cls.meta.to_dict() for t, cls in _REGISTRY.items()}


def grouped_types():
    groups = OrderedDict()
    for type_, cls in _REGISTRY.items():
        groups.setdefault(cls.meta.category, []).append(cls.meta.to_dict())
    return groups
