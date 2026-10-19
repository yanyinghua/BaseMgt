"""上下文与表达式解析。

约定命名空间：
    {{ input.xxx }}        入参
    {{ vars.xxx }}         运行期变量
    {{ node.<节点ID>.xxx }} 节点输出
    {{ item }} / {{ vars.item }}  循环当前元素
    {{ env.xxx }}          环境信息（触发人、时间等）

只做路径取值，不做 eval，避免注入风险。
"""
import datetime
import decimal
import re
import uuid

EXPR_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)((?:[.][A-Za-z0-9_]+|\[\d+\])*)\s*\}\}")

_MISSING = object()


def _path_parts(path):
    parts = []
    for token in re.findall(r"[.][A-Za-z0-9_]+|\[\d+\]", path):
        if token.startswith("."):
            parts.append(token[1:])
        else:
            parts.append(int(token[1:-1]))
    return parts


def lookup(scope, expr):
    """按 a.b[0].c 形式在 scope 中取值，取不到返回 None。"""
    match = EXPR_PATTERN.fullmatch(expr.strip())
    if not match:
        return _MISSING
    root, rest = match.group(1), match.group(2)
    if root not in scope:
        return _MISSING
    cur = scope[root]
    for part in _path_parts(rest):
        try:
            if isinstance(part, int) or (isinstance(cur, list) and str(part).isdigit()):
                cur = cur[int(part)]
            elif isinstance(cur, dict):
                cur = cur.get(part, _MISSING)
            else:
                cur = getattr(cur, part, _MISSING)
        except (KeyError, IndexError, TypeError):
            return _MISSING
        if cur is _MISSING:
            return _MISSING
    return cur


def json_safe(value):
    """把 DB 返回的 Decimal/datetime/UUID/bytes 转成 JSON 可序列化对象。"""
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", "replace")
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def render_value(value, scope):
    """递归渲染：整串是表达式时保留原始类型，否则做字符串插值。"""
    if isinstance(value, str):
        stripped = value.strip()
        if EXPR_PATTERN.fullmatch(stripped):
            found = lookup(scope, stripped)
            return None if found is _MISSING else json_safe(found)
        def repl(m):
            found = lookup(scope, m.group(0))
            return "" if found is _MISSING else _to_text(found)
        return EXPR_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: render_value(v, scope) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [render_value(v, scope) for v in value]
    return value


def _to_text(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        import json
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def render_expr(expr, scope):
    """渲染单个表达式字符串（用于分支判断等），返回 Python 对象。"""
    found = lookup(scope, str(expr))
    return None if found is _MISSING else json_safe(found)


def compare(left, op, right):
    """分支判断：只支持有限运算符，不使用 eval。"""
    ops = {
        "eq": lambda: _eq(left, right),
        "ne": lambda: not _eq(left, right),
        "gt": lambda: _num(left) > _num(right),
        "gte": lambda: _num(left) >= _num(right),
        "lt": lambda: _num(left) < _num(right),
        "lte": lambda: _num(left) <= _num(right),
        "in": lambda: left in _as_list(right),
        "not_in": lambda: left not in _as_list(right),
        "contains": lambda: right in _to_text(left),
        "is_empty": lambda: left in (None, "", [], {}),
        "not_empty": lambda: left not in (None, "", [], {}),
        "is_true": lambda: bool(left) is True,
        "is_false": lambda: not left,
    }
    if op not in ops:
        raise ValueError(f"不支持的运算符: {op}")
    return ops[op]()


def _eq(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return bool(left) == bool(right)
    try:
        return _num(left) == _num(right)
    except (TypeError, ValueError):
        return _to_text(left) == _to_text(right)


def _num(value):
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    return float(str(value))


def _as_list(value):
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return [value]
