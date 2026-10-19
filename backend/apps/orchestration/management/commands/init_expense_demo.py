"""一键搭建「员工报销管理」示例模块。

完整链路：建表 -> 示例数据 -> 存储过程入目录并下发 -> 编排定义发布 -> 页面发布 -> 侧边栏可见。

    python manage.py init_expense_demo
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.catalog import services
from apps.catalog.models import DataSource, Module, StoredProcedure, StoredProcedureVersion
from apps.orchestration.models import Definition
from apps.page.models import PageDefinition

MODULE_KEY = "expense"

TABLE_DDL = """
CREATE TABLE IF NOT EXISTS public.expense_claim (
    id            serial PRIMARY KEY,
    claim_no      varchar(32) UNIQUE,
    applicant     varchar(50) NOT NULL,
    dept          varchar(50),
    category      varchar(20),
    amount        numeric(12,2) NOT NULL DEFAULT 0,
    reason        text,
    status        varchar(20) NOT NULL DEFAULT 'submitted',
    submitted_at  timestamp DEFAULT now(),
    approved_by   varchar(50),
    approved_at   timestamp,
    comment       text
);
"""

SEED_SQL = """
INSERT INTO public.expense_claim(claim_no, applicant, dept, category, amount, reason, status) VALUES
 ('BX20260001','张三','销售部','差旅',3200.00,'客户拜访差旅费','submitted'),
 ('BX20260002','李四','技术部','办公',860.50,'购买键鼠套装','submitted'),
 ('BX20260003','王五','市场部','餐饮',6800.00,'行业会议客户招待','submitted'),
 ('BX20260004','张三','销售部','交通',1250.00,'市内交通费','approved'),
 ('BX20260005','赵六','技术部','培训',15000.00,'外部技术培训报名','approved')
ON CONFLICT (claim_no) DO NOTHING;
"""

PROCEDURES = {
    "sp_expense_search": {
        "kind": "function",
        "description": "报销单查询：关键字/状态/申请人/日期区间",
        "ddl": """
CREATE OR REPLACE FUNCTION public.sp_expense_search(
    p_keyword text DEFAULT NULL,
    p_status text DEFAULT NULL,
    p_applicant text DEFAULT NULL,
    p_date_from text DEFAULT NULL,
    p_date_to text DEFAULT NULL)
RETURNS TABLE(
    id int, claim_no varchar, applicant varchar, dept varchar, category varchar,
    amount numeric, reason text, status varchar, submitted_at timestamp,
    approved_by varchar, comment text)
LANGUAGE sql AS $$
    SELECT c.id, c.claim_no, c.applicant, c.dept, c.category, c.amount,
           c.reason, c.status, c.submitted_at, c.approved_by, c.comment
    FROM public.expense_claim c
    WHERE (p_keyword   IS NULL OR p_keyword   = '' OR c.claim_no ILIKE '%'||p_keyword||'%'
                                 OR c.applicant ILIKE '%'||p_keyword||'%'
                                 OR c.reason ILIKE '%'||p_keyword||'%')
      AND (p_status    IS NULL OR p_status    = '' OR c.status = p_status)
      AND (p_applicant IS NULL OR p_applicant = '' OR c.applicant = p_applicant)
      AND (p_date_from IS NULL OR p_date_from = '' OR c.submitted_at::date >= NULLIF(p_date_from,'')::date)
      AND (p_date_to   IS NULL OR p_date_to   = '' OR c.submitted_at::date <= NULLIF(p_date_to,'')::date)
    ORDER BY c.id DESC;
$$;
""",
    },
    "sp_expense_save": {
        "kind": "function",
        "description": "报销单新增/更新，返回 id；单号留空自动生成",
        "ddl": """
CREATE OR REPLACE FUNCTION public.sp_expense_save(
    p_id int, p_claim_no varchar, p_applicant varchar, p_dept varchar,
    p_category varchar, p_amount numeric, p_reason text)
RETURNS int
LANGUAGE plpgsql AS $$
DECLARE
    v_id int;
    v_no varchar(32);
BEGIN
    IF p_claim_no IS NULL OR p_claim_no = '' THEN
        v_no := 'BX' || to_char(now(), 'YYYY')
                || lpad((COALESCE((SELECT max(id) FROM public.expense_claim), 0) + 1)::text, 4, '0');
    ELSE
        v_no := p_claim_no;
    END IF;

    IF p_id IS NULL THEN
        INSERT INTO public.expense_claim(claim_no, applicant, dept, category, amount, reason, status, submitted_at)
        VALUES (v_no, p_applicant, p_dept, p_category, p_amount, p_reason, 'submitted', now())
        RETURNING id INTO v_id;
    ELSE
        UPDATE public.expense_claim
           SET claim_no   = v_no,
               applicant  = COALESCE(p_applicant, applicant),
               dept       = COALESCE(p_dept, dept),
               category   = COALESCE(p_category, category),
               amount     = COALESCE(p_amount, amount),
               reason     = COALESCE(p_reason, reason)
         WHERE id = p_id;
        v_id := p_id;
    END IF;
    RETURN v_id;
END;
$$;
""",
    },
    "sp_expense_set_status": {
        "kind": "procedure",
        "description": "置报销单状态（approved/rejected）并写入审批人与意见",
        "ddl": """
CREATE OR REPLACE PROCEDURE public.sp_expense_set_status(
    IN p_id int, IN p_status varchar, IN p_approver varchar, IN p_comment text)
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE public.expense_claim
       SET status      = p_status,
           approved_by = COALESCE(p_approver, approved_by),
           approved_at = now(),
           comment     = COALESCE(p_comment, comment)
     WHERE id = p_id;
END;
$$;
""",
    },
    "sp_expense_summary": {
        "kind": "function",
        "description": "按状态+类别汇总报销金额",
        "ddl": """
CREATE OR REPLACE FUNCTION public.sp_expense_summary(p_applicant text DEFAULT NULL)
RETURNS TABLE(status varchar, category varchar, cnt bigint, total numeric)
LANGUAGE sql AS $$
    SELECT status, category, count(*) AS cnt, sum(amount) AS total
    FROM public.expense_claim
    WHERE p_applicant IS NULL OR p_applicant = '' OR applicant = p_applicant
    GROUP BY status, category
    ORDER BY status, category;
$$;
""",
    },
}

PAGES = [
    {
        "key": "expense-list",
        "name": "报销单列表",
        "page_type": "list",
        "bindings": {"list": "expense-list"},
        "fields": [
            {"name": "keyword", "label": "关键字", "type": "text", "show": False, "query": True},
            {"name": "applicant", "label": "申请人", "type": "text", "show": False, "query": True},
            {"name": "status", "label": "状态", "type": "text", "show": False, "query": True},
            {"name": "date_from", "label": "提交日期起", "type": "text", "show": False, "query": True},
            {"name": "date_to", "label": "提交日期止", "type": "text", "show": False, "query": True},
            {"name": "id", "label": "ID", "type": "number", "show": True, "query": False},
            {"name": "claim_no", "label": "单号", "type": "text", "show": True, "query": False},
            {"name": "applicant", "label": "申请人", "type": "text", "show": True, "query": False},
            {"name": "dept", "label": "部门", "type": "text", "show": True, "query": False},
            {"name": "category", "label": "类别", "type": "text", "show": True, "query": False},
            {"name": "amount", "label": "金额", "type": "number", "show": True, "query": False},
            {"name": "reason", "label": "事由", "type": "text", "show": True, "query": False},
            {"name": "status", "label": "状态", "type": "text", "show": True, "query": False},
            {"name": "submitted_at", "label": "提交时间", "type": "text", "show": True, "query": False},
        ],
    },
    {
        "key": "expense-form",
        "name": "填写报销单",
        "page_type": "form",
        "bindings": {"submit": "expense-save"},
        "fields": [
            {"name": "id", "label": "单据ID(留空=新增)", "type": "number", "show": True, "query": False},
            {"name": "claim_no", "label": "单号(留空自动生成)", "type": "text", "show": True, "query": False},
            {"name": "applicant", "label": "申请人", "type": "text", "show": True, "query": False},
            {"name": "dept", "label": "部门", "type": "text", "show": True, "query": False},
            {"name": "category", "label": "类别", "type": "text", "show": True, "query": False},
            {"name": "amount", "label": "金额", "type": "number", "show": True, "query": False},
            {"name": "reason", "label": "事由", "type": "text", "show": True, "query": False},
        ],
    },
]


class Command(BaseCommand):
    help = "搭建「员工报销管理」示例模块"

    def handle(self, *args, **options):
        User = get_user_model()
        user = User.objects.filter(is_superuser=True).first()

        ds = DataSource.objects.filter(is_default=True, status="active").first() or DataSource.objects.first()
        if ds is None:
            self.stdout.write(self.style.ERROR("没有可用数据源，请先执行 seed_demo 或登记数据源"))
            return

        module, _ = Module.objects.get_or_create(
            key=MODULE_KEY,
            defaults={"name": "员工报销管理", "description": "示例模块：存储过程 + 编排 + 页面完整链路"},
        )

        services.execute_ddl(ds, TABLE_DDL)
        services.execute_ddl(ds, SEED_SQL)
        self.stdout.write(self.style.SUCCESS(f"数据表就绪: public.expense_claim -> {ds.key}"))

        procs = {}
        for name, spec in PROCEDURES.items():
            proc, _ = StoredProcedure.objects.get_or_create(
                data_source=ds, schema="public", name=name, signature="",
                defaults={"kind": spec["kind"], "module": module, "description": spec["description"]},
            )
            proc.kind = spec["kind"]
            proc.module = module
            proc.description = spec["description"]
            latest = proc.versions.order_by("-version").first()
            version = (latest.version if latest else 0) + 1
            ver = StoredProcedureVersion.objects.create(
                procedure=proc, version=version, ddl=spec["ddl"], change_note="初始化", created_by=user
            )
            services.apply_procedure_version(ver, user)
            procs[name] = proc
            self.stdout.write(self.style.SUCCESS(f"存储过程已下发: {spec['kind']} public.{name} v{version}"))

        self._build_definitions(module, procs)

        for spec in PAGES:
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

        self.stdout.write(self.style.SUCCESS(
            "\n完成。可用入口：\n"
            "  列表页     前端侧边栏「员工报销管理 → 报销单列表」 或 /p/expense-list\n"
            "  表单页     /p/expense-form\n"
            "  查询接口   POST /api/x/expense-list   {\"applicant\":\"张三\"}\n"
            "  保存接口   POST /api/x/expense-save   {\"applicant\":\"孙七\",\"amount\":6800,\"reason\":\"差旅\"}\n"
            "  审批流     POST /api/x/expense-approve {\"id\":1}   >5000 元会挂起成人工待办\n"
            "  汇总接口   POST /api/x/expense-summary {}\n"
            "  人工待办   前端「人工任务」页处理，或 POST /api/human-tasks/{id}/complete/"
        ))

    # ---------- 编排定义 ----------

    def _build_definitions(self, module, procs):
        search_id, save_id = procs["sp_expense_search"].id, procs["sp_expense_save"].id
        status_id = procs["sp_expense_set_status"].id
        summary_id = procs["sp_expense_summary"].id

        def proc_node(node_id, name, proc_id, args, assign_var, position):
            return {
                "id": node_id, "type": "procedure", "name": name, "position": position,
                "config": {"proc_id": proc_id, "args": args, "assign_var": assign_var},
            }

        definitions = [
            {
                "key": "expense-list", "name": "报销单列表查询", "kind": "service",
                "input_schema": [
                    {"name": "keyword", "label": "关键字", "type": "text", "default": ""},
                    {"name": "status", "label": "状态", "type": "text", "default": ""},
                    {"name": "applicant", "label": "申请人", "type": "text", "default": ""},
                ],
                "graph": {
                    "nodes": [
                        {"id": "s", "type": "start", "name": "开始", "config": {}, "position": {"x": 40, "y": 140}},
                        proc_node("q", "查询报销单", search_id,
                                  ["{{ input.keyword }}", "{{ input.status }}", "{{ input.applicant }}",
                                   "{{ input.date_from }}", "{{ input.date_to }}"], "res", {"x": 240, "y": 140}),
                        {"id": "e", "type": "end", "name": "结束", "position": {"x": 460, "y": 140},
                         "config": {"output": {"rows": "{{ vars.res.rows }}"}}},
                    ],
                    "edges": [
                        {"id": "e1", "source": "s", "sourceHandle": "default", "target": "q"},
                        {"id": "e2", "source": "q", "sourceHandle": "default", "target": "e"},
                    ],
                },
            },
            {
                "key": "expense-save", "name": "报销单保存", "kind": "service",
                "input_schema": [
                    {"name": "id", "label": "单据ID", "type": "number", "default": None},
                    {"name": "claim_no", "label": "单号", "type": "text", "default": ""},
                    {"name": "applicant", "label": "申请人", "type": "text", "default": ""},
                    {"name": "amount", "label": "金额", "type": "number", "default": 0},
                ],
                "graph": {
                    "nodes": [
                        {"id": "s", "type": "start", "name": "开始", "config": {}, "position": {"x": 40, "y": 140}},
                        proc_node("p", "保存报销单", save_id,
                                  ["{{ input.id }}", "{{ input.claim_no }}", "{{ input.applicant }}",
                                   "{{ input.dept }}", "{{ input.category }}", "{{ input.amount }}",
                                   "{{ input.reason }}"], "saved", {"x": 240, "y": 140}),
                        {"id": "e", "type": "end", "name": "结束", "position": {"x": 460, "y": 140},
                         "config": {"output": {"id": "{{ vars.saved.rows[0].sp_expense_save }}"}}},
                    ],
                    "edges": [
                        {"id": "e1", "source": "s", "target": "p"},
                        {"id": "e2", "source": "p", "target": "e"},
                    ],
                },
            },
            {
                "key": "expense-summary", "name": "报销汇总统计", "kind": "service",
                "input_schema": [{"name": "applicant", "label": "申请人", "type": "text", "default": ""}],
                "graph": {
                    "nodes": [
                        {"id": "s", "type": "start", "name": "开始", "config": {}, "position": {"x": 40, "y": 140}},
                        proc_node("p", "汇总金额", summary_id, ["{{ input.applicant }}"], "sum", {"x": 240, "y": 140}),
                        {"id": "e", "type": "end", "name": "结束", "position": {"x": 460, "y": 140},
                         "config": {"output": {"rows": "{{ vars.sum.rows }}"}}},
                    ],
                    "edges": [
                        {"id": "e1", "source": "s", "target": "p"},
                        {"id": "e2", "source": "p", "target": "e"},
                    ],
                },
            },
            {
                # 业务流程编排：>5000 元挂起人工审批，否则自动通过
                "key": "expense-approve", "name": "报销单审批流", "kind": "flow",
                "input_schema": [
                    {"name": "id", "label": "单据ID", "type": "number", "default": None},
                    {"name": "operator", "label": "操作人", "type": "text", "default": ""},
                ],
                "graph": {
                    "nodes": [
                        {"id": "s", "type": "start", "name": "开始", "config": {}, "position": {"x": 40, "y": 200}},
                        {"id": "q", "type": "sql", "name": "取单据金额", "position": {"x": 200, "y": 200},
                         "config": {"sql": "select id, applicant, amount from public.expense_claim where id = {{ input.id }}",
                                    "fetch": "one", "assign_var": "claim"}},
                        {"id": "b", "type": "branch", "name": "金额是否>5000", "position": {"x": 380, "y": 200},
                         "config": {"rules": [{"var": "{{ vars.claim.amount }}", "op": "gt", "value": 5000, "handle": "true"}],
                                    "else_handle": "false"}},
                        {"id": "h", "type": "human_task", "name": "经理审批", "position": {"x": 570, "y": 110},
                         "config": {"title": "报销审批：{{ vars.claim.applicant }} 报销 {{ vars.claim.amount }} 元",
                                    "description": "单号 {{ input.id }}，请核对后处理",
                                    "form_schema": [{"name": "comment", "label": "审批意见", "type": "textarea"}],
                                    "actions": ["approve", "reject"], "output_var": "task"}},
                        proc_node("pa", "置为通过", status_id,
                                  ["{{ input.id }}", "approved", "{{ input.operator }}", "{{ vars.task.comment }}"],
                                  "r1", {"x": 780, "y": 60}),
                        proc_node("pr", "置为驳回", status_id,
                                  ["{{ input.id }}", "rejected", "{{ input.operator }}", "{{ vars.task.comment }}"],
                                  "r2", {"x": 780, "y": 180}),
                        proc_node("auto", "小额自动通过", status_id,
                                  ["{{ input.id }}", "approved", "system", "金额未超阈值，系统自动通过"],
                                  "r3", {"x": 570, "y": 330}),
                        {"id": "e", "type": "end", "name": "结束", "position": {"x": 980, "y": 200},
                         "config": {"output": {"id": "{{ input.id }}", "mode": "{{ vars.task.action }}"}}},
                    ],
                    "edges": [
                        {"id": "e1", "source": "s", "sourceHandle": "default", "target": "q"},
                        {"id": "e2", "source": "q", "sourceHandle": "default", "target": "b"},
                        {"id": "e3", "source": "b", "sourceHandle": "true", "target": "h"},
                        {"id": "e4", "source": "b", "sourceHandle": "false", "target": "auto"},
                        {"id": "e5", "source": "h", "sourceHandle": "approve", "target": "pa"},
                        {"id": "e6", "source": "h", "sourceHandle": "reject", "target": "pr"},
                        {"id": "e7", "source": "pa", "sourceHandle": "default", "target": "e"},
                        {"id": "e8", "source": "pr", "sourceHandle": "default", "target": "e"},
                        {"id": "e9", "source": "auto", "sourceHandle": "default", "target": "e"},
                    ],
                },
            },
        ]

        for spec in definitions:
            definition, created = Definition.objects.get_or_create(
                key=spec["key"], version=1,
                defaults={"name": spec["name"], "kind": spec["kind"], "module": module, "status": "published"},
            )
            definition.name = spec["name"]
            definition.kind = spec["kind"]
            definition.module = module
            definition.status = "published"
            definition.graph = spec["graph"]
            definition.input_schema = spec["input_schema"]
            definition.trigger = {"type": "http", "method": "POST", "path": spec["key"], "enabled": True}
            definition.description = spec.get("description", "")
            definition.save()
            self.stdout.write(self.style.SUCCESS(
                f"编排已发布: {spec['kind']} {spec['key']} ({'新建' if created else '更新'})"
            ))
