"""主数据（MDM）接口：对象/字段/字典/审计/树形/Excel。"""
import io
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.catalog import services
from apps.catalog.models import StoredProcedure
from apps.core.response import fail, ok
from apps.iam.permissions import PermModelViewSet

from . import builder, ddl, generators
from .generators import editable_fields, has_field
from .models import Dictionary, DictionaryItem, EntityDefinition, EntityDdlLog, FieldDefinition
from .serializers import (
    DictionaryItemSerializer,
    DictionarySerializer,
    EntityDdlLogSerializer,
    EntitySerializer,
    FieldSerializer,
)

USER_MODEL = get_user_model()


def _query_rows(entity, params):
    """按元数据安全查询物理表（参数化 SQL，列名来自字段定义）。"""
    columns = [f.name for f in entity.fields_sorted()] or ["id"]
    select = ", ".join(f't."{c}"' for c in columns)
    where, values = [], []
    if has_field(entity, "is_deleted"):
        where.append("t.is_deleted = false")
    keyword = params.get("keyword")
    if keyword and (has_field(entity, "code") or has_field(entity, "name")):
        parts = [f't."{c}" ILIKE %s' for c in ("code", "name") if has_field(entity, c)]
        where.append("(" + " OR ".join(parts) + ")")
        values += [f"%{keyword}%"] * len(parts)
    status_value = params.get("status")
    if status_value and has_field(entity, "status"):
        where.append("t.status = %s")
        values.append(status_value)
    extra = params.get("filters") or {}
    if isinstance(extra, dict):
        for column, value in extra.items():
            if column in columns and value not in (None, ""):
                where.append(f't."{column}" = %s')
                values.append(value)
    parent = params.get("parent_id")
    if parent is not None and entity.tree_parent_field in columns:
        where.append(f't."{entity.tree_parent_field}"' + " = %s")
        values.append(parent)
    cond = (" WHERE " + " AND ".join(where)) if where else ""
    base = f'FROM {entity.schema}."{entity.table_name}" t{cond}'
    try:
        limit = min(int(params.get("limit") or 20), 200)
        offset = max(int(params.get("offset") or 0), 0)
    except (TypeError, ValueError):
        raise ValueError("limit/offset 必须为整数")
    rows = services.query(
        entity.data_source,
        f"SELECT {select} {base} ORDER BY t.id DESC LIMIT %s OFFSET %s",
        values + [limit, offset], fetch="all",
    )
    total = services.query(entity.data_source, f"SELECT count(*) AS total {base}", values, fetch="scalar")
    return rows, total or 0, columns


def _xlsx_response(workbook, filename):
    from openpyxl import Workbook  # noqa: F401  保证依赖提示清晰

    stream = io.BytesIO()
    workbook.save(stream)
    stream.seek(0)
    resp = HttpResponse(
        stream.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}.xlsx"
    return resp


class EntityDefinitionViewSet(PermModelViewSet):
    """主数据对象管理。"""

    queryset = EntityDefinition.objects.select_related("module", "data_source", "page")
    serializer_class = EntitySerializer
    perm_owner_paths = ("module",)

    def _user(self):
        user = self.request.user
        return user if user and user.is_authenticated else None

    def get_queryset(self):
        qs = super().get_queryset()
        for field in ("key", "category", "status", "module"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self._user(), updated_by=self._user())

    def perform_update(self, serializer):
        serializer.save(updated_by=self._user())

    @action(detail=True, methods=["get"])
    def fields(self, request, pk=None):
        entity = self.get_object()
        return ok(FieldSerializer(entity.fields_sorted(), many=True).data)

    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        """结构差异预览（不下发）。"""
        entity = self.get_object()
        need_create, sqls, notes = ddl.diff_sql(entity)
        return ok({"need_create": need_create, "sqls": sqls, "notes": notes})

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        """同步到数据库：建表或新增列（不会自动删除列）。"""
        entity = self.get_object()
        try:
            result = builder.sync_table(entity, user=self._user())
        except Exception as exc:  # noqa: BLE001
            return fail(f"同步失败: {exc}")
        return ok(result)

    @action(detail=True, methods=["post"])
    def procedures(self, request, pk=None):
        """按当前字段重新生成 CRUD 存储过程并下发。"""
        entity = self.get_object()
        try:
            created = builder.generate_procedures(entity, user=self._user())
        except Exception as exc:  # noqa: BLE001
            return fail(f"生成失败: {exc}")
        return ok({"procedures": created})

    @action(detail=True, methods=["post"])
    def generate(self, request, pk=None):
        """生成/刷新编排定义与页面。"""
        entity = self.get_object()
        include = request.data.get("include") or ("definitions", "pages")
        result = builder.generate_definitions(entity, self._user()) if "definitions" in include else []
        pages = builder.generate_pages(entity, self._user()) if "pages" in include else []
        return ok({"definitions": result, "pages": pages})

    @action(detail=True, methods=["post"])
    def bootstrap(self, request, pk=None):
        """一条龙：同步表 -> 存储过程 -> 编排 -> 页面。"""
        entity = self.get_object()
        include = request.data.get("include") or ("table", "procs", "definitions", "pages")
        try:
            result = builder.bootstrap_entity(entity, user=self._user(), include=tuple(include))
        except Exception as exc:  # noqa: BLE001
            return fail(f"执行失败: {exc}")
        return ok(result)

    @action(detail=True, methods=["get", "post"])
    def rows(self, request, pk=None):
        """查看物理表数据（分页）。"""
        entity = self.get_object()
        params = request.query_params if request.method == "GET" else (request.data or {})
        try:
            rows, total, columns = _query_rows(entity, params)
        except ValueError as exc:
            return fail(str(exc))
        except Exception as exc:  # noqa: BLE001
            return fail(f"查询失败（表可能尚未同步）: {exc}")
        return ok({"rows": rows, "total": total, "columns": columns})

    @action(detail=True, methods=["get"])
    def logs(self, request, pk=None):
        """结构变更记录。"""
        entity = self.get_object()
        return ok(EntityDdlLogSerializer(entity.ddl_logs.all()[:50], many=True).data)

    @action(detail=True, methods=["get"])
    def changes(self, request, pk=None):
        """字段级变更审计（谁在什么时候把哪条数据的哪个字段从什么改成什么）。"""
        entity = self.get_object()
        if not ddl.audit_table_exists(entity):
            return fail("尚未生成变更日志表，请先执行「同步表」")
        params = request.query_params
        where, values = ["entity_key = %s"], [entity.key]
        if params.get("record_id"):
            where.append("record_id = %s")
            values.append(params["record_id"])
        if params.get("field"):
            where.append("field_name = %s")
            values.append(params["field"])
        if params.get("operator"):
            where.append("operator = %s")
            values.append(params["operator"])
        limit = min(int(params.get("limit") or 100), 500)
        sql = (
            f"SELECT id, record_id, action, field_name, old_value, new_value, operator, changed_at "
            f"FROM {entity.audit_table} WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT %s"
        )
        try:
            rows = services.query(entity.data_source, sql, values + [limit], fetch="all")
        except Exception as exc:  # noqa: BLE001
            return fail(f"查询失败: {exc}")
        return ok({"rows": rows, "total": len(rows)})

    @action(detail=True, methods=["get"])
    def tree(self, request, pk=None):
        """层级树（如部门树）。"""
        entity = self.get_object()
        if not entity.tree_parent_field:
            return fail("该主数据未配置层级字段（options.tree_parent）")
        try:
            rows, _, _ = _query_rows(entity, {"limit": 200})
        except Exception as exc:  # noqa: BLE001
            return fail(f"查询失败: {exc}")
        label_field = entity.label_field or "name"
        parent_field = entity.tree_parent_field
        nodes = [
            {"id": r["id"], "label": r.get(label_field) or r.get("name") or r["id"],
             "parent": r.get(parent_field)}
            for r in rows
        ]
        return ok(build_tree(nodes))

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        """导出为 Excel（按当前查询条件）。"""
        from openpyxl import Workbook
        from openpyxl.styles import Font

        entity = self.get_object()
        # 注意：QueryDict 展开会得到列表，必须逐个取单值
        params = {key: request.query_params.get(key) for key in request.query_params.keys()}
        params["limit"] = 200
        try:
            rows, _, columns = _query_rows(entity, params)
        except Exception as exc:  # noqa: BLE001
            return fail(f"导出失败: {exc}")
        labels = {f.name: f.label for f in entity.fields_sorted()}
        wb = Workbook()
        ws = wb.active
        ws.append([labels.get(c, c) for c in columns])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in rows:
            ws.append([row.get(c) for c in columns])
        return _xlsx_response(wb, f"{entity.name}导出")

    @action(detail=True, methods=["get"])
    def template(self, request, pk=None):
        """下载导入模板（表头=字段中文名，含示例行说明）。"""
        from openpyxl import Workbook
        from openpyxl.styles import Font

        entity = self.get_object()
        fields = [f for f in editable_fields(entity)]
        wb = Workbook()
        ws = wb.active
        ws.append([f.label for f in fields])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        ws.append(["" for _ in fields])
        return _xlsx_response(wb, f"{entity.name}导入模板")

    @action(detail=True, methods=["post"], url_path="import")
    def import_rows(self, request, pk=None):
        """按模板导入：表头支持中文名或列名，逐行调用保存存储过程。"""
        from openpyxl import load_workbook

        entity = self.get_object()
        file = request.FILES.get("file")
        if not file:
            return fail("请选择要导入的文件")
        operator = getattr(self._user(), "username", "") or request.data.get("operator") or ""

        proc = (
            StoredProcedure.objects.filter(
                data_source=entity.data_source, schema=entity.schema, name=entity.proc_name("save")
            )
            .order_by("id")
            .first()
        )
        if proc is None:
            return fail("尚未生成保存存储过程，请先执行「一条龙重建」")

        wb = load_workbook(file, data_only=True)
        ws = wb.active
        headers = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
        by_name = {f.name: f for f in entity.fields_sorted()}
        by_label = {f.label: f for f in entity.fields_sorted()}
        mapping = {}
        for index, head in enumerate(headers):
            field = by_name.get(head) or by_label.get(head)
            if field:
                mapping[index] = field

        fields = editable_fields(entity)
        # 枚举/字典字段的合法值，用于导入时校验（空值不校验，交由默认值处理）
        enum_allowed = {}
        for field in entity.fields_sorted():
            if field.data_type != "enum":
                continue
            options = [o["value"] for o in generators.enum_options(field)]
            if options:
                enum_allowed[field.name] = options

        # 关联字段的合法主键，一次性预加载（按目标主数据的表取 id，未删除的）
        ref_allowed = {}
        for field in entity.fields_sorted():
            if field.data_type != "ref" or not field.ref_entity_id:
                continue
            ref = field.ref_entity
            where = " WHERE is_deleted = false" if has_field(ref, "is_deleted") else ""
            try:
                ids = services.query(
                    ref.data_source,
                    f'SELECT id FROM {ref.schema}."{ref.table_name}"{where}',
                    fetch="column",
                )
            except Exception:  # noqa: BLE001  目标表还没建，跳过校验
                continue
            ref_allowed[field.name] = {"ids": set(ids or []), "label": ref.name}

        result = {"total": 0, "success": 0, "failed": []}
        for row_index, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if row is None or all(v in (None, "") for v in row):
                continue
            result["total"] += 1
            values = {field.name: row[index] for index, field in mapping.items() if index < len(row)}

            # 枚举/字典校验：非法值不入库，作为失败行报出
            errors = []
            for name, allowed in enum_allowed.items():
                value = values.get(name)
                if value in (None, ""):
                    continue
                if not any(str(a) == str(value) for a in allowed):
                    errors.append(
                        f"{name}=“{value}” 不在可选值内（可选：{'/'.join(str(a) for a in allowed)}）"
                    )
            # 关联字段校验：必须指向目标主数据里真实存在且未删除的记录
            for name, meta in ref_allowed.items():
                value = values.get(name)
                if value in (None, ""):
                    continue
                try:
                    ref_id = int(value)
                except (TypeError, ValueError):
                    errors.append(f"{name}=“{value}” 不是合法ID（应为「{meta['label']}」的 id）")
                    continue
                if ref_id not in meta["ids"]:
                    errors.append(f"{name}={ref_id} 在「{meta['label']}」中不存在")

            if errors:
                result["failed"].append({
                    "row": row_index, "error": "；".join(errors), "code": values.get("code", "")
                })
                continue
            p_id = values.get("id") or None
            # 没有 id 时按编码定位已有记录，实现"按编码更新"，避免撞唯一约束
            if not p_id and values.get("code") and has_field(entity, "code"):
                try:
                    p_id = services.query(
                        entity.data_source,
                        f'SELECT id FROM {entity.schema}."{entity.table_name}" WHERE code = %s',
                        [values["code"]], fetch="scalar",
                    )
                except Exception:  # noqa: BLE001
                    p_id = None
            args = [p_id] + [values.get(f.name) for f in fields] + [operator]
            try:
                services.call_procedure(
                    entity.data_source, entity.schema, proc.name, args, kind="function"
                )
                result["success"] += 1
            except Exception as exc:  # noqa: BLE001
                result["failed"].append({"row": row_index, "error": str(exc), "code": values.get("code", "")})
        return ok(result)


def build_tree(nodes):
    """扁平列表 -> 嵌套树（parent 指向父 id）。"""
    by_id = {n["id"]: {**n, "children": []} for n in nodes}
    roots = []
    for node in nodes:
        parent_id = node.get("parent")
        if parent_id and parent_id in by_id and parent_id != node["id"]:
            by_id[parent_id]["children"].append(by_id[node["id"]])
        else:
            roots.append(by_id[node["id"]])
    return roots


class FieldDefinitionViewSet(PermModelViewSet):
    """字段与扩展字段管理。"""

    queryset = FieldDefinition.objects.select_related("entity", "ref_entity", "dictionary")
    serializer_class = FieldSerializer
    perm_owner_paths = ("entity__module",)

    def get_queryset(self):
        qs = super().get_queryset()
        entity_id = self.request.query_params.get("entity")
        if entity_id:
            qs = qs.filter(entity_id=entity_id)
        return qs.order_by("entity", "sort_order", "id")

    def perform_create(self, serializer):
        data = self.request.data
        if not data.get("is_system"):
            serializer.validated_data.setdefault("is_extended", True)
        serializer.save(created_by=self._user(), updated_by=self._user())

    def _user(self):
        user = self.request.user
        return user if user and user.is_authenticated else None


class DictionaryViewSet(PermModelViewSet):
    """统一字典：枚举值集中维护，字段引用后页面下拉自动跟着变。"""

    queryset = Dictionary.objects.prefetch_related("items")
    serializer_class = DictionarySerializer
    perm_owner_paths = ("module",)

    def get_queryset(self):
        qs = super().get_queryset()
        for field in ("key", "status", "module"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        return qs

    @action(detail=True, methods=["get"])
    def options(self, request, pk=None):
        dic = self.get_object()
        return ok(dic.options())


class DictionaryItemViewSet(PermModelViewSet):
    queryset = DictionaryItem.objects.select_related("dictionary")
    serializer_class = DictionaryItemSerializer
    perm_owner_paths = ("dictionary__module",)

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("dictionary"):
            qs = qs.filter(dictionary_id=self.request.query_params["dictionary"])
        return qs.order_by("dictionary", "sort_order", "id")
