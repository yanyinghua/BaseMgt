"""主数据自测：Excel 导入的枚举/字典校验与按编码 upsert。

    python manage.py shell -c "exec(open('scripts/mdm_import_selftest.py').read())"
"""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook
from rest_framework.test import APIClient

from apps.catalog import services
from apps.mdm.models import EntityDefinition

CODES = ["BMIMP1", "BMIMP2", "BMIMP3"]

entity = EntityDefinition.objects.get(key="supplier")
labels = {f.name: f.label for f in entity.fields_sorted()}
editable = [
    f for f in entity.fields_sorted()
    if f.name not in ("id", "created_at", "updated_at", "is_deleted", "created_by", "updated_by")
]
header = [f.label for f in editable]

wb = Workbook()
ws = wb.active
ws.append(header)


def add_row(code, category, name):
    values = {labels["code"]: code, labels["name"]: name, labels["category"]: category}
    ws.append([values.get(h) for h in header])


# BMIMP1/BMIMP3 合法（在 supplier_category 字典内），BMIMP2 非法
add_row(CODES[0], "原材料", "导入自测-合法1")
add_row(CODES[1], "不存在的类别", "导入自测-非法")
add_row(CODES[2], "设备", "导入自测-合法2")

buf = io.BytesIO()
wb.save(buf)
buf.seek(0)
upload = SimpleUploadedFile(
    "import.xlsx", buf.read(),
    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

client = APIClient()
resp = client.post(f"/api/mdm/entities/{entity.id}/import/", {"file": upload}, format="multipart")
data = resp.json()["data"]
print("导入结果: total=%s success=%s failed=%s" % (data["total"], data["success"], len(data["failed"])))
for item in data["failed"]:
    print("  失败行 %s (code=%s): %s" % (item["row"], item["code"], item["error"]))

rows = services.query(
    entity.data_source,
    "select code, category from public.mdm_supplier where code = any(%s)",
    [CODES], fetch="all",
)
print("实际入库:", [(r["code"], r["category"]) for r in rows])

assert data["total"] == 3 and data["success"] == 2 and len(data["failed"]) == 1, data
assert "不在可选值内" in data["failed"][0]["error"]
assert [r["code"] for r in rows] == [CODES[0], CODES[2]], "非法行不应入库"

# 按编码 upsert：改 BMIMP1 的联系人，不应新增记录
add_row(CODES[0], "原材料", "导入自测-合法1(更新)")
buf2 = io.BytesIO()
wb.save(buf2)
buf2.seek(0)
upload2 = SimpleUploadedFile(
    "import2.xlsx", buf2.read(),
    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
resp2 = client.post(f"/api/mdm/entities/{entity.id}/import/", {"file": upload2}, format="multipart")
data2 = resp2.json()["data"]
count = services.query(
    entity.data_source,
    "select count(*) from public.mdm_supplier where code = %s", [CODES[0]], fetch="scalar",
)
print("按编码导入后 BMIMP1 记录数:", count)
assert count == 1, "按编码导入应更新而非新增"

# ---- 关联字段校验：人员.所属部门 必须引用真实存在的部门 ----
emp = EntityDefinition.objects.get(key="employee")
labels_e = {f.name: f.label for f in emp.fields_sorted()}
editable_e = [
    f for f in emp.fields_sorted()
    if f.name not in ("id", "created_at", "updated_at", "is_deleted", "created_by", "updated_by")
]
header_e = [f.label for f in editable_e]

dept_ids = services.query(
    emp.data_source,
    "select id from public.mdm_department where is_deleted = false order by id limit 1",
    fetch="column",
)
assert dept_ids, "需要至少一个部门作为关联目标"

wb3 = Workbook(); ws3 = wb3.active; ws3.append(header_e)


def add_emp(code, name, dept):
    values = {labels_e["code"]: code, labels_e["name"]: name, labels_e["dept_id"]: dept}
    ws3.append([values.get(h) for h in header_e])


add_emp("BME1", "关联自测-合法", dept_ids[0])
add_emp("BME2", "关联自测-非法部门", 999999)

buf3 = io.BytesIO(); wb3.save(buf3); buf3.seek(0)
upload3 = SimpleUploadedFile(
    "emp.xlsx", buf3.read(),
    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
resp3 = client.post(f"/api/mdm/entities/{emp.id}/import/", {"file": upload3}, format="multipart")
data3 = resp3.json()["data"]
print("人员导入: total=%s success=%s failed=%s" % (data3["total"], data3["success"], len(data3["failed"])))
for item in data3["failed"]:
    print("  失败行 %s (code=%s): %s" % (item["row"], item["code"], item["error"]))

emp_rows = services.query(
    emp.data_source,
    "select code, dept_id from public.mdm_employee where code = any(%s)", [["BME1", "BME2"]], fetch="all",
)
print("实际入库:", [(r["code"], r["dept_id"]) for r in emp_rows])

assert data3["total"] == 2 and data3["success"] == 1 and len(data3["failed"]) == 1, data3
assert "不存在" in data3["failed"][0]["error"]
assert [r["code"] for r in emp_rows] == ["BME1"], "非法关联行不应入库"

# 清理自测数据
services.query(
    entity.data_source,
    "delete from public.mdm_supplier where code = any(%s)", [CODES], fetch="none",
)
services.query(
    emp.data_source,
    "delete from public.mdm_employee where code = any(%s)", [["BME1", "BME2"]], fetch="none",
)
print("\n主数据导入自测通过 ✅")
