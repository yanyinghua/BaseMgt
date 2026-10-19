<template>
  <Layout>
    <div class="bm-page">
      <div class="bm-card">
        <div class="bm-toolbar">
          <strong>企业主数据</strong>
          <el-select v-model="category" clearable placeholder="分类" style="width: 150px" @change="load">
            <el-option v-for="c in categories" :key="c.value" :label="c.label" :value="c.value" />
          </el-select>
          <el-button size="small" @click="load">刷新</el-button>
          <span class="bm-muted">
            元数据驱动：加字段 → 同步表 → 重建 CRUD 存储过程/编排/页面，全程不用写代码
          </span>
        </div>
        <el-table :data="list" size="small">
          <el-table-column prop="key" label="标识" width="130" />
          <el-table-column prop="name" label="名称" width="140" />
          <el-table-column label="分类" width="110">
            <template #default="{ row }">{{ categoryLabel(row.category) }}</template>
          </el-table-column>
          <el-table-column prop="table_name" label="物理表" width="180" />
          <el-table-column label="字段" width="90">
            <template #default="{ row }">
              {{ row.field_count }}<span v-if="row.extended_count" class="bm-muted">(+{{ row.extended_count }})</span>
            </template>
          </el-table-column>
          <el-table-column prop="revision" label="结构版本" width="90" />
          <el-table-column prop="synced_at" label="最近同步" width="170" />
          <el-table-column label="操作" width="420">
            <template #default="{ row }">
              <el-button link type="primary" @click="openFields(row)">字段</el-button>
              <el-button link @click="openPreview(row)">结构差异</el-button>
              <el-button link type="success" @click="sync(row)">同步表</el-button>
              <el-button link type="success" @click="bootstrap(row)">一条龙重建</el-button>
              <el-button link @click="openRows(row)">数据</el-button>
              <el-button link type="warning" @click="openChanges(row)">审计</el-button>
              <el-button link v-if="row.is_tree" @click="openTree(row)">层级</el-button>
              <el-button link @click="openLogs(row)">结构记录</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 字段 -->
      <el-drawer v-model="fieldVisible" :title="`字段定义 - ${current.name || ''}`" size="70%">
        <div class="bm-toolbar">
          <el-button type="primary" size="small" @click="addField">新增字段</el-button>
          <span class="bm-muted">新增字段后需「同步表」才会生成物理列；再「一条龙重建」更新存储过程与页面</span>
        </div>
        <el-table :data="fields" size="small">
          <el-table-column prop="name" label="列名" width="140" />
          <el-table-column prop="label" label="中文名" width="140" />
          <el-table-column label="类型" width="110">
            <template #default="{ row }">{{ typeLabel(row.data_type) }}</template>
          </el-table-column>
          <el-table-column label="可空" width="60">
            <template #default="{ row }">{{ row.nullable ? '是' : '否' }}</template>
          </el-table-column>
          <el-table-column label="唯一" width="60">
            <template #default="{ row }">{{ row.unique ? '是' : '' }}</template>
          </el-table-column>
          <el-table-column prop="default_value" label="默认值" width="100" />
          <el-table-column label="关联" width="120">
            <template #default="{ row }">{{ row.ref_entity_key || '' }}</template>
          </el-table-column>
          <el-table-column label="列表" width="60">
            <template #default="{ row }">{{ row.visible_in_list ? '√' : '' }}</template>
          </el-table-column>
          <el-table-column label="查询" width="60">
            <template #default="{ row }">{{ row.queryable ? '√' : '' }}</template>
          </el-table-column>
          <el-table-column label="标记" width="120">
            <template #default="{ row }">
              <el-tag v-if="row.is_system" size="small">系统</el-tag>
              <el-tag v-if="row.is_extended" size="small" type="warning">扩展</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button link @click="editField(row)">编辑</el-button>
              <el-button link type="danger" @click="removeField(row)" :disabled="row.is_system">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-drawer>

      <!-- 字段编辑 -->
      <el-dialog v-model="fieldDialog" :title="fieldForm.id ? '编辑字段' : '新增字段'" width="520">
        <el-form :model="fieldForm" label-width="100px" size="small">
          <el-form-item label="列名"><el-input v-model="fieldForm.name" :disabled="!!fieldForm.id" placeholder="小写字母/数字/下划线" /></el-form-item>
          <el-form-item label="中文名"><el-input v-model="fieldForm.label" /></el-form-item>
          <el-form-item label="类型">
            <el-select v-model="fieldForm.data_type" style="width: 100%">
              <el-option v-for="t in dataTypes" :key="t.value" :label="t.label" :value="t.value" />
            </el-select>
          </el-form-item>
          <el-row :gutter="8">
            <el-col :span="8"><el-form-item label="长度"><el-input v-model.number="fieldForm.length" type="number" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="总位数"><el-input v-model.number="fieldForm.precision" type="number" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="小数位"><el-input v-model.number="fieldForm.scale" type="number" /></el-form-item></el-col>
          </el-row>
          <el-form-item label="默认值"><el-input v-model="fieldForm.default_value" placeholder="SQL 字面量，如 'active' / 0" /></el-form-item>
          <el-form-item label="关联主数据" v-if="fieldForm.data_type === 'ref'">
            <el-select v-model="fieldForm.ref_entity" clearable style="width: 100%">
              <el-option v-for="e in list" :key="e.id" :label="e.name" :value="e.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="关联显示列" v-if="fieldForm.data_type === 'ref'">
            <el-input v-model="fieldForm.ref_display" placeholder="默认取目标实体的展示字段" />
          </el-form-item>
          <el-form-item label="枚举值" v-if="fieldForm.data_type === 'enum'">
            <el-input v-model="enumText" placeholder="逗号分隔，如 在用,闲置,报废" />
          </el-form-item>
          <el-form-item label="属性">
            <el-checkbox v-model="fieldForm.nullable">可空</el-checkbox>
            <el-checkbox v-model="fieldForm.unique">唯一</el-checkbox>
            <el-checkbox v-model="fieldForm.indexed">建索引</el-checkbox>
            <el-checkbox v-model="fieldForm.visible_in_list">列表显示</el-checkbox>
            <el-checkbox v-model="fieldForm.queryable">可作查询条件</el-checkbox>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="fieldDialog = false">取消</el-button>
          <el-button type="primary" @click="saveField">保存</el-button>
        </template>
      </el-dialog>

      <!-- 结构差异 -->
      <el-drawer v-model="previewVisible" :title="`结构差异 - ${current.name || ''}`" size="50%">
        <el-tag v-if="preview.need_create" type="warning">表尚未创建</el-tag>
        <div class="bm-toolbar" style="margin-top: 8px">
          <el-button type="success" size="small" @click="sync(current)">执行同步</el-button>
        </div>
        <pre v-for="(s, i) in preview.sqls" :key="i" class="bm-mono bm-sql">{{ s }}</pre>
        <div v-if="!preview.sqls?.length" class="bm-muted">结构与元数据一致，无需变更</div>
        <el-divider content-position="left">提示</el-divider>
        <div v-for="(n, i) in preview.notes" :key="i" class="bm-muted">{{ n }}</div>
      </el-drawer>

      <!-- 数据 -->
      <el-drawer v-model="rowsVisible" :title="`数据 - ${current.name || ''}`" size="70%">
        <div class="bm-toolbar">
          <el-input v-model="rowKeyword" placeholder="关键字" style="width: 180px" clearable />
          <el-button type="primary" size="small" @click="loadRows">查询</el-button>
          <span class="bm-muted">共 {{ rowTotal }} 条</span>
          <span style="margin-left: auto" />
          <el-button size="small" @click="downloadTemplate">下载导入模板</el-button>
          <el-button size="small" @click="downloadExport">导出 Excel</el-button>
          <el-upload
            :show-file-list="false"
            :before-upload="onImportFile"
            accept=".xlsx,.xls"
            style="display: inline-block"
          >
            <el-button size="small" type="success">导入 Excel</el-button>
          </el-upload>
        </div>
        <el-table :data="rows" size="small" max-height="480">
          <el-table-column v-for="c in rowColumns" :key="c" :prop="c" :label="c" show-overflow-tooltip />
        </el-table>
        <div v-if="importResult" class="bm-muted" style="margin-top: 8px">
          导入结果：共 {{ importResult.total }} 行，成功 {{ importResult.success }} 行，
          失败 {{ importResult.failed.length }} 行
          <el-button link type="primary" v-if="importResult.failed.length" @click="showImportErrors">
            查看失败明细
          </el-button>
        </div>
      </el-drawer>

      <!-- 字段级变更审计 -->
      <el-drawer v-model="changesVisible" :title="`变更审计 - ${current.name || ''}`" size="70%">
        <div class="bm-toolbar">
          <el-input v-model="changeRecordId" placeholder="记录ID" style="width: 140px" clearable />
          <el-input v-model="changeField" placeholder="字段名" style="width: 140px" clearable />
          <el-button type="primary" size="small" @click="loadChanges">查询</el-button>
          <span class="bm-muted">记录谁在什么时候把哪个字段从什么改成什么</span>
        </div>
        <el-table :data="changes" size="small" max-height="520">
          <el-table-column prop="changed_at" label="时间" width="170" />
          <el-table-column prop="operator" label="操作人" width="100" />
          <el-table-column prop="record_id" label="记录ID" width="80" />
          <el-table-column label="动作" width="80">
            <template #default="{ row }">
              <el-tag size="small" :type="{ insert: 'success', update: 'warning', delete: 'danger' }[row.action]">
                {{ row.action }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="field_name" label="字段" width="140" />
          <el-table-column label="原值" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.old_value ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="新值" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">{{ row.new_value ?? '-' }}</template>
          </el-table-column>
        </el-table>
      </el-drawer>

      <!-- 层级树 -->
      <el-drawer v-model="treeVisible" :title="`层级结构 - ${current.name || ''}`" size="40%">
        <el-tree :data="treeData" :props="{ label: 'label', children: 'children' }" default-expand-all node-key="id" />
      </el-drawer>

      <!-- 变更记录 -->
      <el-drawer v-model="logVisible" :title="`结构变更记录 - ${current.name || ''}`" size="55%">
        <el-table :data="logs" size="small">
          <el-table-column prop="revision" label="版本" width="70" />
          <el-table-column prop="action" label="动作" width="80" />
          <el-table-column prop="success" label="结果" width="70">
            <template #default="{ row }">
              <el-tag size="small" :type="row.success ? 'success' : 'danger'">{{ row.success ? '成功' : '失败' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="applied_by" label="执行人" width="100" />
          <el-table-column prop="sql" label="SQL" show-overflow-tooltip />
          <el-table-column prop="created_at" label="时间" width="170" />
        </el-table>
      </el-drawer>
    </div>
  </Layout>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Layout from '../layout/Layout.vue'
import { api, mdmEntities, mdmFields } from '../api'

const categories = [
  { label: '组织与人员', value: 'org' },
  { label: '合作伙伴', value: 'partner' },
  { label: '产品与物料', value: 'product' },
  { label: '资产', value: 'asset' },
  { label: '其他', value: 'other' }
]
const dataTypes = [
  { label: '文本', value: 'char' }, { label: '长文本', value: 'text' },
  { label: '整数', value: 'int' }, { label: '大整数', value: 'bigint' },
  { label: '金额/小数', value: 'decimal' }, { label: '日期', value: 'date' },
  { label: '日期时间', value: 'datetime' }, { label: '是/否', value: 'bool' },
  { label: '枚举', value: 'enum' }, { label: 'JSON', value: 'json' },
  { label: '关联主数据', value: 'ref' }
]

const list = ref([])
const category = ref('')
const current = ref({})
const fields = ref([])
const fieldVisible = ref(false)
const fieldDialog = ref(false)
const fieldForm = ref({})
const enumText = ref('')
const previewVisible = ref(false)
const preview = ref({})
const rowsVisible = ref(false)
const rows = ref([])
const rowColumns = ref([])
const rowKeyword = ref('')
const rowTotal = ref(0)
const logVisible = ref(false)
const logs = ref([])
// 变更审计
const changesVisible = ref(false)
const changes = ref([])
const changeRecordId = ref('')
const changeField = ref('')
// 层级
const treeVisible = ref(false)
const treeData = ref([])
// Excel
const importResult = ref(null)

const categoryLabel = (v) => (categories.find((c) => c.value === v) || {}).label || v
const typeLabel = (v) => (dataTypes.find((t) => t.value === v) || {}).label || v

const load = async () => {
  const params = {}
  if (category.value) params.category = category.value
  list.value = await mdmEntities.list(params)
}

const openFields = async (row) => {
  current.value = row
  fields.value = await api.mdmEntityFields(row.id)
  fieldVisible.value = true
}

const addField = () => {
  fieldForm.value = {
    entity: current.value.id, name: '', label: '', data_type: 'char',
    length: 64, precision: 18, scale: 2, nullable: true, unique: false, indexed: false,
    default_value: '', visible_in_list: true, queryable: false, is_extended: true
  }
  enumText.value = ''
  fieldDialog.value = true
}

const editField = (row) => {
  fieldForm.value = { ...row }
  enumText.value = (row.enum_options || []).join(',')
  fieldDialog.value = true
}

const saveField = async () => {
  const payload = { ...fieldForm.value }
  payload.enum_options = enumText.value ? enumText.value.split(',').map((s) => s.trim()).filter(Boolean) : []
  if (payload.id) await mdmFields.update(payload.id, payload)
  else await mdmFields.create(payload)
  ElMessage.success('已保存（记得同步表）')
  fieldDialog.value = false
  fields.value = await api.mdmEntityFields(current.value.id)
  load()
}

const removeField = async (row) => {
  await ElMessageBox.confirm(`确认删除字段 ${row.name}？（物理列不会自动删除）`, '提示', { type: 'warning' })
  await mdmFields.remove(row.id)
  fields.value = await api.mdmEntityFields(current.value.id)
  load()
}

const openPreview = async (row) => {
  current.value = row
  preview.value = await api.mdmPreview(row.id)
  previewVisible.value = true
}

const sync = async (row) => {
  const res = await api.mdmSync(row.id)
  ElMessage.success(res.applied ? `已执行 ${res.applied} 条结构变更` : '结构与元数据一致，无需变更')
  previewVisible.value = false
  load()
}

const bootstrap = async (row) => {
  const res = await api.mdmBootstrap(row.id)
  ElMessage.success(
    `已同步 ${res.table.applied} 条结构变更，重建 ${res.procedures.length} 个存储过程、` +
    `${res.definitions.length} 个编排、${res.pages.length} 个页面`
  )
  load()
}

const openRows = async (row) => {
  current.value = row
  rowKeyword.value = ''
  rowsVisible.value = true
  await loadRows()
}

const loadRows = async () => {
  const res = await api.mdmRows(current.value.id, { keyword: rowKeyword.value, limit: 50 })
  rows.value = res.rows
  rowColumns.value = res.columns
  rowTotal.value = res.total
}

const openLogs = async (row) => {
  current.value = row
  logs.value = await api.mdmLogs(row.id)
  logVisible.value = true
}

// ---- 字段级变更审计 ----
const openChanges = async (row) => {
  current.value = row
  changeRecordId.value = ''
  changeField.value = ''
  changesVisible.value = true
  await loadChanges()
}

const loadChanges = async () => {
  try {
    const res = await api.mdmChanges(current.value.id, {
      record_id: changeRecordId.value,
      field: changeField.value,
      limit: 200
    })
    changes.value = res.rows || []
  } catch {
    changes.value = []
  }
}

// ---- 层级树 ----
const openTree = async (row) => {
  current.value = row
  treeVisible.value = true
  try {
    treeData.value = await api.mdmTree(row.id)
  } catch {
    treeData.value = []
  }
}

// ---- Excel 导入导出 ----
const downloadTemplate = () => {
  window.open(api.mdmTemplateUrl(current.value.id), '_blank')
}

const downloadExport = () => {
  window.open(api.mdmExportUrl(current.value.id, { keyword: rowKeyword.value }), '_blank')
}

const onImportFile = async (file) => {
  try {
    const res = await api.mdmImport(current.value.id, file)
    importResult.value = res
    ElMessage.success(`导入完成：成功 ${res.success} 行，失败 ${res.failed.length} 行`)
    await loadRows()
  } finally {
    return false // 阻止 el-upload 自动上传
  }
}

const showImportErrors = () => {
  const detail = importResult.value.failed
    .map((f) => `第${f.row}行 ${f.code ? '(' + f.code + ')' : ''}：${f.error}`)
    .join('\n')
  ElMessageBox.alert(detail || '无', '导入失败明细', { type: 'warning' })
}

onMounted(load)
</script>

<style scoped>
.bm-sql {
  background: #f7f8fa;
  border: 1px solid var(--bm-border);
  border-radius: 4px;
  padding: 8px;
  white-space: pre-wrap;
  max-height: 320px;
  overflow: auto;
}
</style>
