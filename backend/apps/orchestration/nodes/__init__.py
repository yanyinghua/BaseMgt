"""节点插件汇总。新增节点在此 import 即自动注册。"""

from .start import StartNode, EndNode  # noqa: F401
from .db import SqlNode, ProcedureNode  # noqa: F401
from .http_script import HttpNode, ScriptNode  # noqa: F401
from .control import (  # noqa: F401
    BranchNode,
    HumanTaskNode,
    LoopNode,
    SubflowNode,
    TransformNode,
)
