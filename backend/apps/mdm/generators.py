"""按字段元数据生成 CRUD 存储过程 / 编排定义 / 页面 Schema。

所有产物都可重复执行：字段名变了重新生成即可覆盖同名存储过程。
"""
from apps.mdm.ddl import sql_type

EDITABLE_EXCLUDE = {"id", "created_at", "updated_at", "is_deleted", "created_by", "updated_by"}
LIST_EXCLUDE = {"is_deleted"}


def _q(text):
    return (text or "").replace("'", "''")


def drop_routine_sql(entity, name):
    """重建前的清理：同名过程/函数（含所有重载）先删掉。

    RETURNS TABLE 的列会随字段扩展而变，CREATE OR REPLACE 会报
    "cannot change return type of existing function"，所以先 DROP 再 CREATE。
    """
    return f"""
DO $bm_drop$ DECLARE r record; BEGIN
    FOR r IN SELECT p.oid::regprocedure AS sig
             FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname = '{entity.schema}' AND p.proname = '{name}' LOOP
        EXECUTE 'DROP ROUTINE IF EXISTS ' || r.sig || ' CASCADE';
    END LOOP;
END $bm_drop$;
"""


def _with_drop(entity, spec):
    spec = dict(spec)
    spec["ddl"] = drop_routine_sql(entity, spec["name"]) + spec["ddl"]
    return spec


def visible_fields(entity):
    fields = list(entity.fields_sorted())
    result = [f for f in fields if f.name not in LIST_EXCLUDE]
    if not any(f.name == "id" for f in result):
        id_field = next((f for f in fields if f.name == "id"), None)
        if id_field:
            result = [id_field] + result
    return result


def list_columns(entity):
    return [f for f in visible_fields(entity) if f.name != "id"] or [f for f in entity.fields_sorted() if f.name != "id"]


def editable_fields(entity):
    return [f for f in entity.fields_sorted() if f.name not in EDITABLE_EXCLUDE]


def has_field(entity, name):
    return entity.fields.filter(name=name, status="active").exists()


def _select_columns(entity, alias="t"):
    return ", ".join(f"{alias}.{f.name}" for f in visible_fields(entity))


def _returns_table(entity):
    return ", ".join(f'"{f.name}" {sql_type(f)}' for f in visible_fields(entity))


def _keyword_condition(entity):
    targets = [f.name for f in entity.fields_sorted() if f.queryable and f.data_type in ("char", "text")]
    parts = [f"{f} ILIKE '%'||p_keyword||'%'" for f in targets] or ["true"]
    return " OR ".join(parts)


def _filter_conditions(entity):
    conds = ["t.is_deleted = false"] if has_field(entity, "is_deleted") else []
    if has_field(entity, "code") or has_field(entity, "name"):
        conds.append(f"(p_keyword IS NULL OR p_keyword = '' OR {_keyword_condition(entity)})")
    if has_field(entity, "status"):
        conds.append("(p_status IS NULL OR p_status = '' OR t.status = p_status)")
    return conds


def build_search_proc(entity):
    name = entity.proc_name("search")
    conds = " AND ".join(_filter_conditions(entity)) or "true"
    return {
        "name": name,
        "kind": "function",
        "description": f"{entity.name}：分页查询",
        "ddl": f"""
CREATE OR REPLACE FUNCTION {entity.schema}.{name}(
    p_keyword text DEFAULT NULL,
    p_status text DEFAULT NULL,
    p_limit int DEFAULT 50,
    p_offset int DEFAULT 0)
RETURNS TABLE({_returns_table(entity)})
LANGUAGE sql AS $$
    SELECT {_select_columns(entity)}
    FROM {entity.qualified_table} t
    WHERE {conds}
    ORDER BY t.id DESC
    LIMIT COALESCE(p_limit, 50) OFFSET COALESCE(p_offset, 0);
$$;
""",
    }


def build_count_proc(entity):
    name = entity.proc_name("count")
    conds = " AND ".join(_filter_conditions(entity)) or "true"
    return {
        "name": name,
        "kind": "function",
        "description": f"{entity.name}：总数统计",
        "ddl": f"""
CREATE OR REPLACE FUNCTION {entity.schema}.{name}(
    p_keyword text DEFAULT NULL,
    p_status text DEFAULT NULL)
RETURNS bigint
LANGUAGE sql AS $$
    SELECT count(*) FROM {entity.qualified_table} t WHERE {conds};
$$;
""",
    }


def build_get_proc(entity):
    name = entity.proc_name("get")
    return {
        "name": name,
        "kind": "function",
        "description": f"{entity.name}：按主键取单条",
        "ddl": f"""
CREATE OR REPLACE FUNCTION {entity.schema}.{name}(p_id int)
RETURNS TABLE({_returns_table(entity)})
LANGUAGE sql AS $$
    SELECT {_select_columns(entity)}
    FROM {entity.qualified_table} t
    WHERE t.id = p_id;
$$;
""",
    }


def _audit_fields_array(entity):
    names = [f.name for f in editable_fields(entity)]
    if not names:
        return "ARRAY[]::text[]"
    return "ARRAY[" + ", ".join(f"'{n}'" for n in names) + "]::text[]"


def _audit_insert(entity, action, old_expr=None, new_expr=None):
    """生成一条字段级审计写入语句。"""
    columns = ["entity_key", "record_id", "action", "field_name"]
    selects = [f"'{entity.key}'", "v_id", f"'{action}'", "f"]
    if old_expr is not None:
        columns.append("old_value")
        selects.append(f"{old_expr} ->> f")
    if new_expr is not None:
        columns.append("new_value")
        selects.append(f"{new_expr} ->> f")
    columns.append("operator")
    selects.append("p_operator")
    where = " WHERE (v_old ->> f) IS DISTINCT FROM (v_new ->> f)" if action == "update" else ""
    return (
        f"        INSERT INTO {entity.audit_table} ({', '.join(columns)})\n"
        f"        SELECT {', '.join(selects)} FROM unnest(v_fields) AS f{where};"
    )


def build_save_proc(entity):
    name = entity.proc_name("save")
    fields = editable_fields(entity)
    audit = entity.option("audit", True)
    params = ",\n    ".join(f"p_{f.name} {sql_type(f)}" for f in fields)
    insert_cols = [f'"{f.name}"' for f in fields]
    # 传空值时回落到字段默认值，让前端/调用方可以只传关心的字段
    insert_vals = [
        f"COALESCE(p_{f.name}, {f.default_value})" if f.default_value else f"p_{f.name}"
        for f in fields
    ]
    # 更新语义：参数没传（NULL）就保持原值，避免"只改一个字段把其它字段清空"。
    # 代价是无法通过本接口把字段改回 NULL（需要单独置空接口）。
    set_clause = [f'"{f.name}" = COALESCE(p_{f.name}, "{f.name}")' for f in fields]
    need_operator = False

    if has_field(entity, "created_at"):
        insert_cols.append("created_at")
        insert_vals.append("now()")
    if has_field(entity, "updated_at"):
        insert_cols.append("updated_at")
        insert_vals.append("now()")
        set_clause.append("updated_at = now()")
    if has_field(entity, "created_by"):
        insert_cols.append("created_by")
        insert_vals.append("p_operator")
        need_operator = True
    if has_field(entity, "updated_by"):
        insert_cols.append("updated_by")
        insert_vals.append("p_operator")
        set_clause.append("updated_by = COALESCE(p_operator, updated_by)")
        need_operator = True

    operator_param = ",\n    p_operator varchar DEFAULT NULL" if need_operator else ""
    columns_sql = ", ".join(insert_cols)
    values_sql = ", ".join(insert_vals)
    sets_sql = ",\n           ".join(set_clause)

    audit_log = ""
    declare = "    v_id int;"
    if audit:
        declare = (
            "    v_id int;\n"
            "    v_old jsonb;\n"
            "    v_new jsonb;\n"
            f"    v_fields text[] := {_audit_fields_array(entity)};"
        )
        audit_log = f"""
        SELECT to_jsonb(t) INTO v_new FROM {entity.qualified_table} t WHERE t.id = v_id;
{_audit_insert(entity, 'insert', new_expr='v_new')}"""

    update_audit = ""
    if audit:
        update_audit = f"""
        SELECT to_jsonb(t) INTO v_old FROM {entity.qualified_table} t WHERE t.id = p_id;"""

    update_audit_after = ""
    if audit:
        update_audit_after = f"""
        SELECT to_jsonb(t) INTO v_new FROM {entity.qualified_table} t WHERE t.id = p_id;
{_audit_insert(entity, 'update', old_expr='v_old', new_expr='v_new')}"""

    return {
        "name": name,
        "kind": "function",
        "description": f"{entity.name}：新增/更新，返回 id" + ("（写字段级变更日志）" if audit else ""),
        "ddl": f"""
CREATE OR REPLACE FUNCTION {entity.schema}.{name}(
    p_id int,
    {params}{operator_param})
RETURNS int
LANGUAGE plpgsql AS $$
DECLARE
{declare}
BEGIN
    IF p_id IS NULL THEN
        INSERT INTO {entity.qualified_table} ({columns_sql})
        VALUES ({values_sql})
        RETURNING id INTO v_id;{audit_log}
    ELSE
        v_id := p_id;{update_audit}
        UPDATE {entity.qualified_table}
           SET {sets_sql}
         WHERE id = p_id;{update_audit_after}
    END IF;
    RETURN v_id;
END;
$$;
""",
    }


def build_delete_proc(entity):
    name = entity.proc_name("delete")
    audit = entity.option("audit", True)
    if has_field(entity, "is_deleted"):
        delete_sql = f"""
    UPDATE {entity.qualified_table}
       SET is_deleted = true,
           updated_at = now(),
           updated_by = COALESCE(p_operator, updated_by)
     WHERE id = p_id;"""
    else:
        delete_sql = f"""
    DELETE FROM {entity.qualified_table} WHERE id = p_id;"""

    declare = ""
    before = ""
    after = ""
    if audit:
        declare = f"""
DECLARE
    v_id int := p_id;
    v_old jsonb;
    v_fields text[] := {_audit_fields_array(entity)};"""
        before = f"""
    SELECT to_jsonb(t) INTO v_old FROM {entity.qualified_table} t WHERE t.id = p_id;"""
        after = "\n" + _audit_insert(entity, "delete", old_expr="v_old")

    return {
        "name": name,
        "kind": "procedure",
        "description": f"{entity.name}：删除（软删除优先）" + ("（写字段级变更日志）" if audit else ""),
        "ddl": f"""
CREATE OR REPLACE PROCEDURE {entity.schema}.{name}(
    IN p_id int, IN p_operator varchar DEFAULT NULL)
LANGUAGE plpgsql AS $${declare}
BEGIN{before}{delete_sql}{after}
END;
$$;
""",
    }


def build_standard_procs(entity):
    """生成标准 CRUD 存储过程（每次重建前先 DROP 同名过程，避免返回列变化导致失败）。"""
    return [
        _with_drop(entity, build_search_proc(entity)),
        _with_drop(entity, build_count_proc(entity)),
        _with_drop(entity, build_get_proc(entity)),
        _with_drop(entity, build_save_proc(entity)),
        _with_drop(entity, build_delete_proc(entity)),
    ]


# ---------- 编排定义 ----------


def build_list_graph(entity, procs):
    """列表查询编排：count + search。"""
    search_id = procs[f"{entity.proc_name('search')}"]
    count_id = procs[f"{entity.proc_name('count')}"]
    return {
        "nodes": [
            {"id": "s", "type": "start", "name": "开始", "config": {}, "position": {"x": 40, "y": 160}},
            {"id": "cnt", "type": "procedure", "name": "总数", "position": {"x": 200, "y": 80},
             "config": {"proc_id": count_id,
                        "args": ["{{ input.keyword }}", "{{ input.status }}"], "assign_var": "cnt"}},
            {"id": "q", "type": "procedure", "name": "查询列表", "position": {"x": 200, "y": 240},
             "config": {"proc_id": search_id,
                        "args": ["{{ input.keyword }}", "{{ input.status }}",
                                 "{{ input.limit }}", "{{ input.offset }}"], "assign_var": "res"}},
            {"id": "e", "type": "end", "name": "结束", "position": {"x": 420, "y": 160},
             "config": {"output": {
                 "rows": "{{ vars.res.rows }}",
                 "total": f"{{{{ vars.cnt.rows[0].{entity.proc_name('count')} }}}}",
             }}},
        ],
        "edges": [
            {"id": "e1", "source": "s", "sourceHandle": "default", "target": "cnt"},
            {"id": "e2", "source": "cnt", "sourceHandle": "default", "target": "q"},
            {"id": "e3", "source": "q", "sourceHandle": "default", "target": "e"},
        ],
    }


def build_save_graph(entity, procs):
    save_id = procs[entity.proc_name("save")]
    args = ["{{ input.id }}"] + [f"{{{{ input.{f.name} }}}}" for f in editable_fields(entity)] + ["{{ input.operator }}"]
    return {
        "nodes": [
            {"id": "s", "type": "start", "name": "开始", "config": {}, "position": {"x": 40, "y": 160}},
            {"id": "p", "type": "procedure", "name": "保存", "position": {"x": 220, "y": 160},
             "config": {"proc_id": save_id, "args": args, "assign_var": "saved"}},
            {"id": "e", "type": "end", "name": "结束", "position": {"x": 420, "y": 160},
             "config": {"output": {"id": f"{{{{ vars.saved.rows[0].{entity.proc_name('save')} }}}}"}}},
        ],
        "edges": [
            {"id": "e1", "source": "s", "sourceHandle": "default", "target": "p"},
            {"id": "e2", "source": "p", "sourceHandle": "default", "target": "e"},
        ],
    }


def build_delete_graph(entity, procs):
    del_id = procs[entity.proc_name("delete")]
    return {
        "nodes": [
            {"id": "s", "type": "start", "name": "开始", "config": {}, "position": {"x": 40, "y": 160}},
            {"id": "p", "type": "procedure", "name": "删除", "position": {"x": 220, "y": 160},
             "config": {"proc_id": del_id, "args": ["{{ input.id }}", "{{ input.operator }}"], "assign_var": "del"}},
            {"id": "e", "type": "end", "name": "结束", "position": {"x": 420, "y": 160},
             "config": {"output": {"id": "{{ input.id }}"}}},
        ],
        "edges": [
            {"id": "e1", "source": "s", "sourceHandle": "default", "target": "p"},
            {"id": "e2", "source": "p", "sourceHandle": "default", "target": "e"},
        ],
    }


# ---------- 页面 schema ----------


def page_type_of(field):
    mapping = {
        "char": "text", "text": "text", "int": "number", "bigint": "number",
        "decimal": "number", "date": "date", "datetime": "text", "bool": "text",
        "enum": "select", "json": "text", "ref": "ref",
    }
    return mapping.get(field.data_type, "text")


def build_fields_schema(entity, for_form=False):
    """生成页面 schema.fields。"""
    result = []
    if not for_form:
        result.append({"name": "keyword", "label": "关键字", "type": "text", "show": False, "query": True})
    for field in entity.fields_sorted():
        if for_form:
            if field.name in EDITABLE_EXCLUDE and field.name != "id":
                continue
        elif not field.visible_in_list and field.name != "id":
            continue
        item = {
            "name": field.name,
            "label": field.label,
            "type": page_type_of(field),
            "show": field.visible_in_list or for_form,
            "query": (not for_form) and field.queryable,
        }
        if field.data_type == "enum":
            item["options"] = enum_options(field)
            if field.dictionary_id:
                item["dictionary"] = field.dictionary.key
        if field.data_type == "ref" and field.ref_entity_id:
            item["refEntity"] = field.ref_entity.key
            item["refDisplay"] = field.ref_display or field.ref_entity.label_field
            item["refTree"] = field.ref_entity.is_tree
            item["refParentField"] = field.ref_entity.tree_parent_field
        result.append(item)
    return result


def enum_options(field):
    """枚举可选值：优先取引用的字典，其次取字段上写死的值。统一为 [{value,label}]。"""
    if field.dictionary_id:
        return [
            {"value": i.value, "label": i.label}
            for i in field.dictionary.items.filter(status="active").order_by("sort_order", "id")
        ]
    return [{"value": v, "label": v} for v in (field.enum_options or [])]
