"""企业主数据预置定义。

每类主数据 = 标准基础字段（编号/名称/状态/备注/审计/软删） + 该类业务常用字段。
字段不够就在前端「主数据」页继续加，加完点同步即可生成物理列。
"""
STANDARD_OPTIONS = {"code": True, "name": True, "status": True, "remark": True, "soft_delete": True}


def standard_fields(code_label="编号", name_label="名称"):
    """所有主数据共有的基础字段。"""
    return [
        {"name": "id", "label": "主键", "type": "int", "visible": True, "nullable": False, "system": True},
        {"name": "code", "label": code_label, "type": "char", "length": 64, "unique": True,
         "nullable": False, "queryable": True, "visible": True, "system": True,
         "description": "业务编号，唯一"},
        {"name": "name", "label": name_label, "type": "char", "length": 200,
         "nullable": False, "queryable": True, "visible": True, "system": True},
        {"name": "status", "label": "状态", "type": "enum", "length": 20, "default": "'active'",
         "dict": "record_status", "queryable": True, "visible": True, "system": True,
         "description": "active 启用 / disabled 停用"},
        {"name": "remark", "label": "备注", "type": "text", "visible": True, "system": True},
        {"name": "is_deleted", "label": "已删除", "type": "bool", "default": "false",
         "visible": False, "system": True},
        {"name": "created_by", "label": "创建人", "type": "char", "length": 64, "visible": False, "system": True},
        {"name": "updated_by", "label": "更新人", "type": "char", "length": 64, "visible": False, "system": True},
        {"name": "created_at", "label": "创建时间", "type": "datetime", "visible": False, "system": True},
        {"name": "updated_at", "label": "更新时间", "type": "datetime", "visible": False, "system": True},
    ]


def _spec(key, name, category, description, code_label, name_label, fields, options=None):
    merged = dict(STANDARD_OPTIONS)
    merged.update(options or {})
    return {
        "key": key,
        "name": name,
        "category": category,
        "table_name": f"mdm_{key}",
        "label_field": "name",
        "description": description,
        "options": merged,
        "fields": standard_fields(code_label, name_label) + fields,
    }


# 统一字典：枚举值集中维护，字段引用字典而不是写死在字段上
DICTIONARIES = [
    {"key": "record_status", "name": "记录状态", "items": [("active", "启用"), ("disabled", "停用")]},
    {"key": "gender", "name": "性别", "items": ["男", "女", "未知"]},
    {"key": "job_status", "name": "在职状态", "items": ["在职", "试用", "休假", "离职"]},
    {"key": "asset_category", "name": "资产类别",
     "items": ["电子设备", "办公家具", "车辆", "机器设备", "房屋建筑", "其他"]},
    {"key": "asset_status", "name": "资产状态", "items": ["在用", "闲置", "维修", "报废"]},
    {"key": "supplier_category", "name": "供应类别", "items": ["原材料", "设备", "办公", "服务", "其他"]},
    {"key": "customer_category", "name": "客户类别", "items": ["经销商", "代理商", "终端客户", "内部单位"]},
    {"key": "partner_level", "name": "合作伙伴等级", "items": ["A", "B", "C", "D"]},
    {"key": "product_category", "name": "产品分类", "items": ["整机", "配件", "耗材", "软件", "服务"]},
    {"key": "material_category", "name": "物料分类", "items": ["钢材", "塑料", "电子件", "包装", "化工", "其他"]},
    {"key": "unit", "name": "计量单位", "items": ["个", "台", "套", "kg", "吨", "米", "平方米", "升", "箱"]},
]


PRESETS = [
    _spec(
        "department", "部门信息", "org", "组织部门，支持上级部门自关联", "部门编码", "部门名称",
        [
            {"name": "parent_id", "label": "上级部门", "type": "ref", "ref": "department",
             "ref_display": "name", "visible": True},
            {"name": "leader", "label": "部门负责人", "type": "char", "length": 50},
            {"name": "phone", "label": "联系电话", "type": "char", "length": 32},
            {"name": "location", "label": "办公地点", "type": "char", "length": 100},
        ],
        options={"tree_parent": "parent_id"},
    ),
    _spec(
        "employee", "人员信息", "org", "员工花名册，关联所属部门", "工号", "姓名",
        [
            {"name": "dept_id", "label": "所属部门", "type": "ref", "ref": "department",
             "ref_display": "name", "visible": True, "indexed": True},
            {"name": "job_status", "label": "在职状态", "type": "enum", "length": 20, "default": "'在职'",
             "dict": "job_status", "queryable": True, "visible": True},
            {"name": "position", "label": "岗位", "type": "char", "length": 50},
            {"name": "gender", "label": "性别", "type": "enum", "length": 10, "dict": "gender"},
            {"name": "phone", "label": "手机", "type": "char", "length": 32},
            {"name": "email", "label": "邮箱", "type": "char", "length": 100},
            {"name": "id_no", "label": "证件号码", "type": "char", "length": 32},
            {"name": "entry_date", "label": "入职日期", "type": "date"},
            {"name": "leave_date", "label": "离职日期", "type": "date"},
        ],
    ),
    _spec(
        "supplier", "供应商信息", "partner", "采购业务的基础档案", "供应商编码", "供应商名称",
        [
            {"name": "short_name", "label": "简称", "type": "char", "length": 100},
            {"name": "category", "label": "供应类别", "type": "enum", "length": 32,
             "dict": "supplier_category", "queryable": True, "visible": True},
            {"name": "level", "label": "供应商等级", "type": "enum", "length": 10, "default": "'B'",
             "dict": "partner_level"},
            {"name": "contact", "label": "联系人", "type": "char", "length": 50},
            {"name": "phone", "label": "联系电话", "type": "char", "length": 32},
            {"name": "address", "label": "地址", "type": "char", "length": 200},
            {"name": "tax_no", "label": "纳税人识别号", "type": "char", "length": 50},
            {"name": "bank_name", "label": "开户行", "type": "char", "length": 100},
            {"name": "bank_account", "label": "银行账号", "type": "char", "length": 50},
            {"name": "payment_term", "label": "结算方式", "type": "char", "length": 50},
        ],
    ),
    _spec(
        "customer", "客户信息", "partner", "销售业务的基础档案", "客户编码", "客户名称",
        [
            {"name": "short_name", "label": "简称", "type": "char", "length": 100},
            {"name": "category", "label": "客户类别", "type": "enum", "length": 32,
             "dict": "customer_category", "queryable": True, "visible": True},
            {"name": "level", "label": "客户等级", "type": "enum", "length": 10, "default": "'B'",
             "dict": "partner_level"},
            {"name": "contact", "label": "联系人", "type": "char", "length": 50},
            {"name": "phone", "label": "联系电话", "type": "char", "length": 32},
            {"name": "address", "label": "地址", "type": "char", "length": 200},
            {"name": "tax_no", "label": "纳税人识别号", "type": "char", "length": 50},
            {"name": "credit_limit", "label": "信用额度", "type": "decimal", "precision": 18, "scale": 2},
            {"name": "sales_owner", "label": "负责业务员", "type": "ref", "ref": "employee",
             "ref_display": "name", "visible": True},
        ],
    ),
    _spec(
        "product", "产品信息", "product", "成品档案，销售与库存的基础", "产品编码", "产品名称",
        [
            {"name": "spec", "label": "规格型号", "type": "char", "length": 100},
            {"name": "unit", "label": "单位", "type": "enum", "length": 20, "default": "'个'", "dict": "unit"},
            {"name": "category", "label": "产品分类", "type": "enum", "length": 50, "dict": "product_category", "queryable": True},
            {"name": "brand", "label": "品牌", "type": "char", "length": 50},
            {"name": "barcode", "label": "条码", "type": "char", "length": 50},
            {"name": "sale_price", "label": "销售单价", "type": "decimal", "precision": 18, "scale": 2},
            {"name": "cost_price", "label": "成本价", "type": "decimal", "precision": 18, "scale": 2},
            {"name": "shelf_life", "label": "保质期(天)", "type": "int"},
        ],
    ),
    _spec(
        "material", "原材料信息", "product", "物料档案，采购与库存的基础", "物料编码", "物料名称",
        [
            {"name": "spec", "label": "规格型号", "type": "char", "length": 100},
            {"name": "unit", "label": "单位", "type": "enum", "length": 20, "default": "'个'", "dict": "unit"},
            {"name": "category", "label": "物料分类", "type": "enum", "length": 50, "dict": "material_category", "queryable": True},
            {"name": "purchase_price", "label": "采购单价", "type": "decimal", "precision": 18, "scale": 2},
            {"name": "safety_stock", "label": "安全库存", "type": "decimal", "precision": 18, "scale": 3},
            {"name": "shelf_life", "label": "保质期(天)", "type": "int"},
            {"name": "warehouse", "label": "默认仓库", "type": "char", "length": 50},
        ],
    ),
    _spec(
        "asset", "资产信息", "asset", "固定资产台账", "资产编码", "资产名称",
        [
            {"name": "category", "label": "资产类别", "type": "enum", "length": 32,
             "dict": "asset_category",
             "queryable": True, "visible": True},
            {"name": "asset_status", "label": "资产状态", "type": "enum", "length": 20, "default": "'在用'",
             "dict": "asset_status", "queryable": True, "visible": True},
            {"name": "spec", "label": "规格型号", "type": "char", "length": 100},
            {"name": "buy_date", "label": "购置日期", "type": "date"},
            {"name": "buy_amount", "label": "购置金额", "type": "decimal", "precision": 18, "scale": 2},
            {"name": "depreciation_rate", "label": "月折旧率(%)", "type": "decimal", "precision": 5, "scale": 2},
            {"name": "location", "label": "存放地点", "type": "char", "length": 100},
            {"name": "dept_id", "label": "使用部门", "type": "ref", "ref": "department", "ref_display": "name"},
            {"name": "custodian", "label": "保管人", "type": "ref", "ref": "employee", "ref_display": "name"},
            {"name": "warranty_date", "label": "保修到期日", "type": "date"},
        ],
    ),
]
