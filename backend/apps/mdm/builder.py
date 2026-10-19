"""把元数据落地：建表/加列 + 生成 CRUD 存储过程 + 编排 + 页面。"""
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.catalog import services
from apps.catalog.models import DataSource, Module, StoredProcedure, StoredProcedureVersion
from apps.orchestration.models import Definition
from apps.page.models import PageDefinition

from . import ddl, generators
from .models import Dictionary, DictionaryItem, EntityDefinition, EntityDdlLog, FieldDefinition


def create_or_update_entity(spec, data_source=None, module=None, user=None):
    """按 spec 创建/刷新主数据对象及其字段定义（不落物理表）。"""
    ds = data_source or (DataSource.objects.filter(is_default=True, status="active").first()
                         or DataSource.objects.first())
    entity, created = EntityDefinition.objects.get_or_create(
        key=spec["key"],
        defaults={
            "data_source": ds,
            "name": spec["name"],
            "category": spec.get("category", "other"),
            "table_name": spec.get("table_name") or f"mdm_{spec['key']}",
            "label_field": spec.get("label_field", "name"),
            "schema": spec.get("schema", "public"),
            "options": spec.get("options") or {},
            "description": spec.get("description", ""),
            "module": module,
            "created_by": user,
        },
    )
    entity.name = spec["name"]
    entity.category = spec.get("category", entity.category)
    entity.label_field = spec.get("label_field", entity.label_field)
    entity.description = spec.get("description", entity.description)
    if spec.get("options"):
        # 能力开关（树形、审计等）以现有配置为基础合并，保证重复执行幂等
        merged = dict(entity.options or {})
        merged.update(spec["options"])
        entity.options = merged
    if module is not None:
        entity.module = module
    entity.save()

    existing = {f.name: f for f in entity.fields.all()}
    for index, field_spec in enumerate(spec.get("fields", [])):
        defaults = {
            "label": field_spec.get("label", field_spec["name"]),
            "data_type": field_spec.get("type", "char"),
            "length": field_spec.get("length", 64),
            "precision": field_spec.get("precision", 18),
            "scale": field_spec.get("scale", 2),
            "nullable": field_spec.get("nullable", True),
            "unique": field_spec.get("unique", False),
            "indexed": field_spec.get("indexed", False),
            "default_value": field_spec.get("default", ""),
            "enum_options": field_spec.get("enum", []),
            "ref_display": field_spec.get("ref_display", ""),
            "dictionary": Dictionary.objects.filter(key=field_spec["dict"]).first()
            if field_spec.get("dict")
            else None,
            "is_system": field_spec.get("system", False) or field_spec.get("standard", False),
            "is_extended": field_spec.get("extended", False),
            "visible_in_list": field_spec.get("visible", True),
            "queryable": field_spec.get("queryable", False),
            "description": field_spec.get("description", ""),
            "sort_order": field_spec.get("sort_order", index * 10),
        }
        ref_key = field_spec.get("ref")
        if ref_key:
            defaults["ref_entity"] = EntityDefinition.objects.filter(key=ref_key).first()
        field = existing.get(field_spec["name"])
        if field is None:
            FieldDefinition.objects.create(entity=entity, name=field_spec["name"], **defaults)
        else:
            for key, value in defaults.items():
                setattr(field, key, value)
            field.save()
    return entity, created


def create_dictionaries(module=None, user=None):
    """创建/刷新预置字典（幂等）。"""
    from .presets import DICTIONARIES

    created = []
    for spec in DICTIONARIES:
        dic, _ = Dictionary.objects.get_or_create(
            key=spec["key"],
            defaults={"name": spec["name"], "module": module, "created_by": user},
        )
        dic.name = spec["name"]
        if module is not None:
            dic.module = module
        dic.save()
        for index, item in enumerate(spec["items"]):
            value, label = item if isinstance(item, (list, tuple)) else (item, item)
            DictionaryItem.objects.get_or_create(
                dictionary=dic, value=value,
                defaults={"label": label, "sort_order": index * 10, "created_by": user},
            )
        created.append(dic.key)
    return created


def ensure_audit_table(entity, user=None):
    """确保字段级变更日志表存在（所有主数据共用一张）。"""
    if not entity.option("audit", True):
        return False
    if ddl.audit_table_exists(entity):
        return False
    sql = ddl.audit_table_sql(entity)
    try:
        services.execute_ddl(entity.data_source, sql)
        EntityDdlLog.objects.create(
            entity=entity, revision=entity.revision, action="create", sql=sql,
            success=True, message="变更日志表", applied_by=getattr(user, "username", ""),
        )
    except Exception as exc:  # noqa: BLE001
        EntityDdlLog.objects.create(
            entity=entity, revision=entity.revision, action="create", sql=sql,
            success=False, message=str(exc), applied_by=getattr(user, "username", ""),
        )
        raise
    return True


def sync_table(entity, user=None, dry_run=False):
    """把字段元数据同步到物理表。返回 {'need_create', 'sqls', 'notes', 'applied'}。"""
    need_create, sqls, notes = ddl.diff_sql(entity)
    result = {"need_create": need_create, "sqls": sqls, "notes": notes, "applied": 0}
    if dry_run or not sqls:
        return result

    operator = getattr(user, "username", "") if user else ""
    for sql in sqls:
        try:
            services.execute_ddl(entity.data_source, sql)
            EntityDdlLog.objects.create(
                entity=entity, revision=entity.revision + 1,
                action="create" if need_create else "alter", sql=sql, success=True, applied_by=operator,
            )
            result["applied"] += 1
        except Exception as exc:  # noqa: BLE001
            EntityDdlLog.objects.create(
                entity=entity, revision=entity.revision + 1,
                action="create" if need_create else "alter", sql=sql, success=False,
                message=str(exc), applied_by=operator,
            )
            raise
    if result["applied"]:
        entity.revision += 1
        entity.synced_at = timezone.now()
        entity.save(update_fields=["revision", "synced_at", "updated_at"])
    return result


def generate_procedures(entity, user=None):
    """生成 CRUD 存储过程并下发到目标库，同时登记进存储过程目录。"""
    created = []
    for spec in generators.build_standard_procs(entity):
        # 按 (数据源, schema, 名称) 定位，不按参数签名——字段变化会改变签名，
        # 但仍应落在同一条目录记录上
        proc = (
            StoredProcedure.objects.filter(
                data_source=entity.data_source, schema=entity.schema, name=spec["name"]
            )
            .order_by("id")
            .first()
        )
        if proc is None:
            proc = StoredProcedure.objects.create(
                data_source=entity.data_source, schema=entity.schema, name=spec["name"], signature="",
                kind=spec["kind"], module=entity.module, description=spec["description"],
            )
        proc.kind = spec["kind"]
        proc.module = entity.module
        proc.description = spec["description"]
        latest = proc.versions.order_by("-version").first()
        version = (latest.version if latest else 0) + 1
        ver = StoredProcedureVersion.objects.create(
            procedure=proc, version=version, ddl=spec["ddl"],
            change_note=f"{entity.name} 自动生成 v{version}", created_by=user,
        )
        services.apply_procedure_version(ver, user)
        created.append({"name": spec["name"], "kind": spec["kind"], "version": version})
    return created


def _proc_ids(entity):
    return {
        p.name: p.id
        for p in StoredProcedure.objects.filter(data_source=entity.data_source, schema=entity.schema)
        if p.name.startswith(f"sp_{entity.key}_")
    }


def generate_definitions(entity, user=None):
    """生成 list / save / delete 三个编排定义并发布。"""
    procs = _proc_ids(entity)
    specs = [
        (f"{entity.key}-list", f"{entity.name}查询", "service", generators.build_list_graph(entity, procs)),
        (f"{entity.key}-save", f"{entity.name}保存", "service", generators.build_save_graph(entity, procs)),
        (f"{entity.key}-delete", f"{entity.name}删除", "service", generators.build_delete_graph(entity, procs)),
    ]
    created = []
    for key, name, kind, graph in specs:
        definition, _ = Definition.objects.get_or_create(
            key=key, version=1,
            defaults={"name": name, "kind": kind, "module": entity.module, "status": "published"},
        )
        definition.name = name
        definition.kind = kind
        definition.module = entity.module
        definition.graph = graph
        definition.status = "published"
        definition.trigger = {"type": "http", "method": "POST", "path": key, "enabled": True}
        definition.input_schema = [
            {"name": "keyword", "label": "关键字", "type": "text", "default": ""},
            {"name": "operator", "label": "操作人", "type": "text", "default": ""},
        ]
        definition.save()
        if key.endswith("-list"):
            entity.list_definition = definition
        if key.endswith("-save"):
            entity.save_definition = definition
        created.append(key)
    entity.save(update_fields=["list_definition", "save_definition", "updated_at"])
    return created


def generate_pages(entity, user=None):
    """生成列表页与表单页并发布（key: <entity>-list / <entity>-form）。"""
    created = []
    for suffix, name, page_type, fields in [
        ("-list", f"{entity.name}列表", "list", generators.build_fields_schema(entity, for_form=False)),
        ("-form", f"{entity.name}登记", "form", generators.build_fields_schema(entity, for_form=True)),
    ]:
        key = f"{entity.key}{suffix}"
        page, _ = PageDefinition.objects.get_or_create(
            key=key,
            defaults={"name": name, "page_type": page_type, "module": entity.module, "status": "published"},
        )
        page.name = name
        page.page_type = page_type
        page.module = entity.module
        page.status = "published"
        schema = {"fields": fields}
        if page_type == "list" and entity.is_tree:
            schema.update({
                "tree": True,
                "treeParentField": entity.tree_parent_field,
                "treeLabel": entity.label_field or "name",
            })
        page.schema = schema
        page.bindings = {"list": f"{entity.key}-list"} if page_type == "list" else {"submit": f"{entity.key}-save"}
        page.save()
        if page_type == "list":
            entity.page = page
        created.append(key)
    entity.save(update_fields=["page", "updated_at"])
    return created


def bootstrap_entity(entity, user=None, include=("table", "procs", "definitions", "pages")):
    """一条龙：同步物理表 -> 生成存储过程 -> 生成编排 -> 生成页面。"""
    result = {}
    if "table" in include:
        result["table"] = sync_table(entity, user=user)
    ensure_audit_table(entity, user=user)  # 字段级变更日志表
    if "procs" in include:
        result["procedures"] = generate_procedures(entity, user=user)
    if "definitions" in include:
        result["definitions"] = generate_definitions(entity, user=user)
    if "pages" in include:
        result["pages"] = generate_pages(entity, user=user)
    entity.status = "published"
    entity.save(update_fields=["status", "updated_at"])
    return result


def ensure_module(key="mdm", name="主数据"):
    module, _ = Module.objects.get_or_create(key=key, defaults={"name": name, "description": "企业基础数据"})
    return module
