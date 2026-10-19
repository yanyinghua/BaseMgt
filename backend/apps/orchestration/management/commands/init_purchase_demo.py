"""搭建「采购入库」示例：多主数据联动 + 事务边界 + 审计。

演示的不是又一个 CRUD，而是：
    供应商(主数据) + 原材料(主数据) + 仓库(主数据) → 入库过账 → 库存台账(主数据)
一次入库在一个存储过程事务里完成：校验主数据有效性 → 写入库单 → upsert 库存 → 写字段级审计。

    python manage.py init_purchase_demo
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.catalog import services
from apps.catalog.models import DataSource, StoredProcedure, StoredProcedureVersion
from apps.mdm import builder
from apps.mdm.presets import PRESETS
from apps.orchestration.models import Definition
from apps.page.models import PageDefinition

INBOUND_DDL = """
CREATE TABLE IF NOT EXISTS public.mdm_inbound (
    id           serial PRIMARY KEY,
    inbound_no   varchar(32) UNIQUE,
    supplier_id  integer NOT NULL,
    material_id  integer NOT NULL,
    warehouse_id integer NOT NULL,
    qty          numeric(18,3) NOT NULL,
    price        numeric(18,2) DEFAULT 0,
    amount       numeric(18,2) DEFAULT 0,
    status       varchar(20) DEFAULT 'approved',
    operator     varchar(64),
    remark       text,
    inbound_at   timestamp DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mdm_inbound_supplier ON public.mdm_inbound (supplier_id);
CREATE INDEX IF NOT EXISTS idx_mdm_inbound_material ON public.mdm_inbound (material_id);
"""

PROCEDURES = {
    "sp_inbound_apply": {
        "kind": "function",
        "description": "采购入库过账：校验主数据 -> 写入库单 -> upsert 库存 -> 写审计（单事务）",
        "ddl": """
CREATE OR REPLACE FUNCTION public.sp_inbound_apply(
    p_supplier_id int, p_material_id int, p_warehouse_id int,
    p_qty numeric, p_price numeric,
    p_operator varchar DEFAULT NULL, p_remark text DEFAULT NULL)
RETURNS int
LANGUAGE plpgsql AS $$
DECLARE
    v_id int;
    v_inv_id int;
    v_inv_code varchar(200);
    v_amount numeric(18,2);
    v_material_name varchar(200);
    v_material_code varchar(64);
    v_warehouse_code varchar(64);
    v_old jsonb;
    v_new jsonb;
BEGIN
    SELECT name, code INTO v_material_name, v_material_code
      FROM public.mdm_material WHERE id = p_material_id AND is_deleted = false;
    IF v_material_name IS NULL THEN
        RAISE EXCEPTION '物料不存在或已停用: %', p_material_id;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM public.mdm_supplier
         WHERE id = p_supplier_id AND is_deleted = false AND status = 'active') THEN
        RAISE EXCEPTION '供应商不存在或已停用: %', p_supplier_id;
    END IF;

    SELECT code INTO v_warehouse_code
      FROM public.mdm_warehouse
     WHERE id = p_warehouse_id AND is_deleted = false AND status = 'active';
    IF v_warehouse_code IS NULL THEN
        RAISE EXCEPTION '仓库不存在或已停用: %', p_warehouse_id;
    END IF;

    IF p_qty IS NULL OR p_qty <= 0 THEN
        RAISE EXCEPTION '入库数量必须大于 0';
    END IF;

    v_amount := p_qty * COALESCE(p_price, 0);
    v_inv_code := v_material_code || '-' || v_warehouse_code;

    INSERT INTO public.mdm_inbound(
        inbound_no, supplier_id, material_id, warehouse_id,
        qty, price, amount, status, operator, remark, inbound_at)
    VALUES (
        'IN' || to_char(now(), 'YYYYMMDD')
             || lpad((COALESCE((SELECT max(id) FROM public.mdm_inbound), 0) + 1)::text, 4, '0'),
        p_supplier_id, p_material_id, p_warehouse_id,
        p_qty, COALESCE(p_price, 0), v_amount, 'approved', p_operator, p_remark, now())
    RETURNING id INTO v_id;

    -- 库存 upsert：同一物料+仓库（code 唯一）累加数量与金额
    SELECT to_jsonb(t) INTO v_old FROM public.mdm_inventory t WHERE t.code = v_inv_code;

    INSERT INTO public.mdm_inventory(
        code, name, status, material_id, warehouse_id, qty, amount, last_in_at,
        created_at, updated_at, created_by, updated_by)
    VALUES (
        v_inv_code, v_material_name, 'active', p_material_id, p_warehouse_id,
        p_qty, v_amount, now(), now(), now(), p_operator, p_operator)
    ON CONFLICT (code) DO UPDATE
       SET qty       = public.mdm_inventory.qty + EXCLUDED.qty,
           amount    = public.mdm_inventory.amount + EXCLUDED.amount,
           last_in_at = now(),
           updated_at = now(),
           updated_by = COALESCE(EXCLUDED.updated_by, public.mdm_inventory.updated_by)
    RETURNING id INTO v_inv_id;

    SELECT to_jsonb(t) INTO v_new FROM public.mdm_inventory t WHERE t.id = v_inv_id;

    -- 字段级审计：库存变化
    INSERT INTO public.mdm_data_change_log(entity_key, record_id, action, field_name, old_value, new_value, operator)
    SELECT 'inventory', v_inv_id,
           CASE WHEN v_old IS NULL THEN 'insert' ELSE 'update' END,
           f, v_old ->> f, v_new ->> f, p_operator
    FROM unnest(ARRAY['qty', 'amount', 'last_in_at']::text[]) AS f
    WHERE (v_old ->> f) IS DISTINCT FROM (v_new ->> f);

    -- 字段级审计：入库单
    INSERT INTO public.mdm_data_change_log(entity_key, record_id, action, field_name, new_value, operator)
    SELECT 'inbound', v_id, 'insert', f,
           (SELECT to_jsonb(t) FROM public.mdm_inbound t WHERE t.id = v_id) ->> f,
           p_operator
    FROM unnest(ARRAY['inbound_no', 'supplier_id', 'material_id', 'warehouse_id',
                      'qty', 'price', 'amount']::text[]) AS f;

    RETURN v_id;
END;
$$;
""",
    },
    "sp_inbound_list": {
        "kind": "function",
        "description": "入库单查询（联供应商/物料/仓库名称）",
        "ddl": """
CREATE OR REPLACE FUNCTION public.sp_inbound_list(
    p_keyword text DEFAULT NULL, p_supplier_id int DEFAULT NULL,
    p_limit int DEFAULT 50, p_offset int DEFAULT 0)
RETURNS TABLE(
    id int, inbound_no varchar, supplier_name varchar, material_name varchar,
    warehouse_name varchar, qty numeric, price numeric, amount numeric,
    status varchar, operator varchar, inbound_at timestamp)
LANGUAGE sql AS $$
    SELECT i.id, i.inbound_no, s.name, m.name, w.name,
           i.qty, i.price, i.amount, i.status, i.operator, i.inbound_at
    FROM public.mdm_inbound i
    LEFT JOIN public.mdm_supplier  s ON s.id = i.supplier_id
    LEFT JOIN public.mdm_material  m ON m.id = i.material_id
    LEFT JOIN public.mdm_warehouse w ON w.id = i.warehouse_id
    WHERE (p_keyword IS NULL OR p_keyword = ''
           OR i.inbound_no ILIKE '%'||p_keyword||'%'
           OR m.name ILIKE '%'||p_keyword||'%')
      AND (p_supplier_id IS NULL OR i.supplier_id = p_supplier_id)
    ORDER BY i.id DESC
    LIMIT COALESCE(p_limit, 50) OFFSET COALESCE(p_offset, 0);
$$;
""",
    },
}


def _proc_id(ds, name):
    return (StoredProcedure.objects.filter(data_source=ds, schema="public", name=name)
            .order_by("id").values_list("id", flat=True).first())


class Command(BaseCommand):
    help = "搭建「采购入库」示例（多主数据联动）"

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(is_superuser=True).first()
        ds = DataSource.objects.filter(is_default=True, status="active").first() or DataSource.objects.first()
        if ds is None:
            self.stdout.write(self.style.ERROR("没有可用数据源，请先执行 seed_demo"))
            return

        module = builder.ensure_module("purchase", "采购管理")
        builder.create_dictionaries(module=module, user=user)

        # 1. 主数据：仓库 + 库存台账（走 MDM 生成器，得到表 + CRUD + 页面）
        for preset in PRESETS:
            if preset["key"] not in ("warehouse", "inventory"):
                continue
            entity, created = builder.create_or_update_entity(preset, data_source=ds, module=module, user=user)
            builder.bootstrap_entity(entity, user=user)
            self.stdout.write(self.style.SUCCESS(
                f"{'[新建]' if created else '[已存在]'} 主数据 {entity.name} -> {entity.qualified_table}"
            ))

        # 2. 业务表：入库单
        services.execute_ddl(ds, INBOUND_DDL)
        self.stdout.write(self.style.SUCCESS("业务表就绪: public.mdm_inbound"))

        # 3. 业务存储过程
        for name, spec in PROCEDURES.items():
            proc = (StoredProcedure.objects.filter(data_source=ds, schema="public", name=name)
                    .order_by("id").first())
            if proc is None:
                proc = StoredProcedure.objects.create(
                    data_source=ds, schema="public", name=name, signature="", kind=spec["kind"],
                    module=module, description=spec["description"],
                )
            proc.kind = spec["kind"]
            proc.module = module
            proc.description = spec["description"]
            latest = proc.versions.order_by("-version").first()
            ver = StoredProcedureVersion.objects.create(
                procedure=proc, version=(latest.version if latest else 0) + 1,
                ddl=spec["ddl"], change_note="采购入库示例", created_by=user,
            )
            services.apply_procedure_version(ver, user)
            self.stdout.write(self.style.SUCCESS(f"存储过程已下发: {name} v{ver.version}"))

        self._build_definitions(module, ds)
        self._build_pages(module)

        self.stdout.write(self.style.SUCCESS(
            "\n采购入库就绪。可用入口：\n"
            "  入库过账  POST /api/x/purchase-inbound  "
            "{\"supplier_id\":1,\"material_id\":1,\"warehouse_id\":1,\"qty\":100,\"price\":5.2,\"operator\":\"admin\"}\n"
            "  入库查询  POST /api/x/purchase-inbound-list  {\"limit\":20}\n"
            "  页面      /p/purchase-inbound-form（填单）  /p/purchase-inbound-list（查询）\n"
            "  库存      /p/inventory-list  （入库后自动累加）"
        ))

    # ---------- 编排 ----------

    def _build_definitions(self, module, ds):
        apply_id = _proc_id(ds, "sp_inbound_apply")
        list_id = _proc_id(ds, "sp_inbound_list")
        supplier_id = _proc_id(ds, "sp_supplier_get")

        specs = [
            {
                "key": "purchase-inbound",
                "name": "采购入库过账",
                "kind": "service",
                "graph": {
                    "nodes": [
                        {"id": "s", "type": "start", "name": "开始", "config": {}, "position": {"x": 40, "y": 200}},
                        {"id": "chk", "type": "sql", "name": "校验供应商", "position": {"x": 200, "y": 200},
                         "config": {
                             "sql": "select id, name, status from public.mdm_supplier "
                                    "where id = {{ input.supplier_id }} and is_deleted = false",
                             "fetch": "one", "assign_var": "supplier"}},
                        {"id": "b", "type": "branch", "name": "供应商可用?", "position": {"x": 380, "y": 200},
                         "config": {"rules": [{"var": "{{ vars.supplier.status }}", "op": "eq",
                                               "value": "active", "handle": "true"}],
                                    "else_handle": "false"}},
                        {"id": "apply", "type": "procedure", "name": "入库过账", "position": {"x": 580, "y": 120},
                         "config": {"proc_id": apply_id,
                                    "args": ["{{ input.supplier_id }}", "{{ input.material_id }}",
                                             "{{ input.warehouse_id }}", "{{ input.qty }}",
                                             "{{ input.price }}", "{{ input.operator }}",
                                             "{{ input.remark }}"],
                                    "assign_var": "apply"}},
                        {"id": "msg", "type": "transform", "name": "拒绝原因", "position": {"x": 580, "y": 320},
                         "config": {"assignments": [
                             {"var": "msg", "value": "供应商不存在或已停用，无法入库"}]}},
                        {"id": "ok", "type": "end", "name": "成功", "position": {"x": 800, "y": 120},
                         "config": {"output": {
                             "ok": True,
                             "inbound_id": "{{ vars.apply.rows[0].sp_inbound_apply }}"}}},
                        {"id": "fail", "type": "end", "name": "拒绝", "position": {"x": 800, "y": 320},
                         "config": {"output": {"ok": False, "message": "{{ vars.msg }}"}}},
                    ],
                    "edges": [
                        {"id": "e1", "source": "s", "sourceHandle": "default", "target": "chk"},
                        {"id": "e2", "source": "chk", "sourceHandle": "default", "target": "b"},
                        {"id": "e3", "source": "b", "sourceHandle": "true", "target": "apply"},
                        {"id": "e4", "source": "b", "sourceHandle": "false", "target": "msg"},
                        {"id": "e5", "source": "apply", "sourceHandle": "default", "target": "ok"},
                        {"id": "e6", "source": "msg", "sourceHandle": "default", "target": "fail"},
                    ],
                },
                "input_schema": [
                    {"name": "supplier_id", "label": "供应商", "type": "number", "required": True},
                    {"name": "material_id", "label": "物料", "type": "number", "required": True},
                    {"name": "warehouse_id", "label": "仓库", "type": "number", "required": True},
                    {"name": "qty", "label": "数量", "type": "number", "required": True},
                    {"name": "price", "label": "单价", "type": "number", "required": True},
                    {"name": "operator", "label": "操作人", "type": "text", "default": ""},
                ],
            },
            {
                "key": "purchase-inbound-list",
                "name": "入库单查询",
                "kind": "service",
                "graph": {
                    "nodes": [
                        {"id": "s", "type": "start", "name": "开始", "config": {}, "position": {"x": 40, "y": 160}},
                        {"id": "q", "type": "procedure", "name": "查询入库单", "position": {"x": 220, "y": 160},
                         "config": {"proc_id": list_id,
                                    "args": ["{{ input.keyword }}", "{{ input.supplier_id }}",
                                             "{{ input.limit }}", "{{ input.offset }}"],
                                    "assign_var": "res"}},
                        {"id": "e", "type": "end", "name": "结束", "position": {"x": 420, "y": 160},
                         "config": {"output": {"rows": "{{ vars.res.rows }}"}}},
                    ],
                    "edges": [
                        {"id": "e1", "source": "s", "sourceHandle": "default", "target": "q"},
                        {"id": "e2", "source": "q", "sourceHandle": "default", "target": "e"},
                    ],
                },
                "input_schema": [{"name": "keyword", "label": "关键字", "type": "text", "default": ""}],
            },
        ]

        for spec in specs:
            definition, created = Definition.objects.get_or_create(
                key=spec["key"], version=1,
                defaults={"name": spec["name"], "kind": spec["kind"], "module": module, "status": "published"},
            )
            definition.name = spec["name"]
            definition.kind = spec["kind"]
            definition.module = module
            definition.status = "published"
            definition.graph = spec["graph"]
            definition.input_schema = spec.get("input_schema", [])
            definition.trigger = {"type": "http", "method": "POST", "path": spec["key"], "enabled": True}
            definition.save()
            self.stdout.write(self.style.SUCCESS(f"编排已发布: {spec['key']}"))

    # ---------- 页面 ----------

    def _build_pages(self, module):
        pages = [
            {
                "key": "purchase-inbound-form",
                "name": "采购入库单",
                "page_type": "form",
                "bindings": {"submit": "purchase-inbound"},
                "fields": [
                    {"name": "supplier_id", "label": "供应商", "type": "ref", "refEntity": "supplier",
                     "refDisplay": "name", "show": True, "query": False},
                    {"name": "material_id", "label": "物料", "type": "ref", "refEntity": "material",
                     "refDisplay": "name", "show": True, "query": False},
                    {"name": "warehouse_id", "label": "仓库", "type": "ref", "refEntity": "warehouse",
                     "refDisplay": "name", "show": True, "query": False},
                    {"name": "qty", "label": "数量", "type": "number", "show": True, "query": False},
                    {"name": "price", "label": "单价", "type": "number", "show": True, "query": False},
                    {"name": "remark", "label": "备注", "type": "text", "show": True, "query": False},
                ],
            },
            {
                "key": "purchase-inbound-list",
                "name": "入库单查询",
                "page_type": "list",
                "bindings": {"list": "purchase-inbound-list"},
                "fields": [
                    {"name": "keyword", "label": "关键字", "type": "text", "show": False, "query": True},
                    {"name": "id", "label": "ID", "type": "number", "show": True, "query": False},
                    {"name": "inbound_no", "label": "入库单号", "type": "text", "show": True, "query": False},
                    {"name": "supplier_name", "label": "供应商", "type": "text", "show": True, "query": False},
                    {"name": "material_name", "label": "物料", "type": "text", "show": True, "query": False},
                    {"name": "warehouse_name", "label": "仓库", "type": "text", "show": True, "query": False},
                    {"name": "qty", "label": "数量", "type": "number", "show": True, "query": False},
                    {"name": "price", "label": "单价", "type": "number", "show": True, "query": False},
                    {"name": "amount", "label": "金额", "type": "number", "show": True, "query": False},
                    {"name": "operator", "label": "操作人", "type": "text", "show": True, "query": False},
                    {"name": "inbound_at", "label": "入库时间", "type": "text", "show": True, "query": False},
                ],
            },
        ]
        for spec in pages:
            page, _ = PageDefinition.objects.get_or_create(
                key=spec["key"],
                defaults={"name": spec["name"], "page_type": spec["page_type"], "module": module, "status": "published"},
            )
            page.name = spec["name"]
            page.page_type = spec["page_type"]
            page.module = module
            page.status = "published"
            page.schema = {"fields": spec["fields"]}
            page.bindings = spec["bindings"]
            page.save()
            self.stdout.write(self.style.SUCCESS(f"页面已发布: /p/{page.key}"))
