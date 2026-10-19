<template>
  <Layout>
    <div class="bm-page">
      <div class="bm-card">
        <div class="bm-toolbar">
          <strong>页面与表单编排</strong>
          <el-button type="primary" size="small" @click="openCreate">新建页面</el-button>
        </div>
        <el-table :data="list" size="small">
          <el-table-column prop="key" label="标识" width="160" />
          <el-table-column prop="name" label="名称" min-width="160" />
          <el-table-column prop="page_type" label="类型" width="100" />
          <el-table-column prop="module_name" label="模块" width="120" />
          <el-table-column prop="status" label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'published' ? 'success' : 'info'">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDesigner(row)">设计</el-button>
              <el-button link type="danger" @click="remove(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-dialog v-model="visible" :title="form.id ? '编辑页面' : '新建页面'" width="520">
        <el-form :model="form" label-width="90px">
          <el-form-item label="标识"><el-input v-model="form.key" /></el-form-item>
          <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="类型">
            <el-select v-model="form.page_type" style="width: 100%">
              <el-option label="列表页" value="list" />
              <el-option label="表单页" value="form" />
              <el-option label="看板" value="dashboard" />
              <el-option label="报表" value="report" />
            </el-select>
          </el-form-item>
          <el-form-item label="所属模块">
            <el-select v-model="form.module" clearable style="width: 100%">
              <el-option v-for="m in moduleList" :key="m.id" :label="m.name" :value="m.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="状态">
            <el-select v-model="form.status"><el-option label="草稿" value="draft" /><el-option label="已发布" value="published" /></el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="visible = false">取消</el-button>
          <el-button type="primary" @click="saveMeta">保存</el-button>
        </template>
      </el-dialog>

      <el-drawer v-model="designerVisible" :title="`设计：${current.name || ''}`" size="60%">
        <el-tabs v-model="tab">
          <el-tab-pane label="字段/列" name="fields">
            <div class="bm-toolbar">
              <el-button size="small" @click="addField">新增字段</el-button>
              <span class="bm-muted">列表页：勾选「显示」即成为列，勾选「查询」即成为查询条件</span>
            </div>
            <el-table :data="fields" size="small">
              <el-table-column label="字段名" width="160">
                <template #default="{ row }"><el-input v-model="row.name" size="small" /></template>
              </el-table-column>
              <el-table-column label="标题" width="160">
                <template #default="{ row }"><el-input v-model="row.label" size="small" /></template>
              </el-table-column>
              <el-table-column label="类型" width="130">
                <template #default="{ row }">
                  <el-select v-model="row.type" size="small">
                    <el-option label="文本" value="text" />
                    <el-option label="数字" value="number" />
                    <el-option label="日期" value="date" />
                    <el-option label="下拉" value="select" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="显示" width="70">
                <template #default="{ row }"><el-checkbox v-model="row.show" /></template>
              </el-table-column>
              <el-table-column label="查询" width="70">
                <template #default="{ row }"><el-checkbox v-model="row.query" /></template>
              </el-table-column>
              <el-table-column label="操作" width="80">
                <template #default="{ $index }">
                  <el-button link type="danger" @click="fields.splice($index, 1)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane label="编排绑定" name="bindings">
            <el-form label-width="120px" size="small">
              <el-form-item label="列表查询编排">
                <el-select v-model="bindings.list" clearable filterable allow-create style="width: 100%">
                  <el-option v-for="d in defList" :key="d.id" :label="`${d.key} (v${d.version})`" :value="d.key" />
                </el-select>
              </el-form-item>
              <el-form-item label="提交编排">
                <el-select v-model="bindings.submit" clearable filterable allow-create style="width: 100%">
                  <el-option v-for="d in defList" :key="d.id" :label="`${d.key} (v${d.version})`" :value="d.key" />
                </el-select>
              </el-form-item>
              <el-form-item label="明细编排">
                <el-select v-model="bindings.detail" clearable filterable allow-create style="width: 100%">
                  <el-option v-for="d in defList" :key="d.id" :label="`${d.key} (v${d.version})`" :value="d.key" />
                </el-select>
              </el-form-item>
            </el-form>
            <div class="bm-muted">绑定的是已发布编排的标识（key），页面通过 <span class="bm-mono">POST /api/pages/{id}/data</span> 取数。</div>
          </el-tab-pane>

          <el-tab-pane label="预览" name="preview">
            <div class="bm-toolbar">
              <el-button size="small" type="primary" @click="preview">加载数据</el-button>
              <span class="bm-muted">{{ previewResult.error || previewResult.status || '' }}</span>
            </div>
            <el-form :inline="true" size="small">
              <el-form-item v-for="f in fields.filter((x) => x.query)" :key="f.name" :label="f.label">
                <el-input v-model="query[f.name]" />
              </el-form-item>
            </el-form>
            <el-table :data="previewRows" size="small">
              <el-table-column v-for="c in fields.filter((x) => x.show)" :key="c.name" :prop="c.name" :label="c.label" />
            </el-table>
          </el-tab-pane>
        </el-tabs>

        <div class="bm-toolbar" style="margin-top: 12px">
          <el-button type="primary" size="small" @click="saveDesign">保存</el-button>
        </div>
      </el-drawer>
    </div>
  </Layout>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Layout from '../layout/Layout.vue'
import { api, definitions, modules, pages } from '../api'

const list = ref([])
const moduleList = ref([])
const defList = ref([])
const visible = ref(false)
const designerVisible = ref(false)
const form = ref({ page_type: 'list', status: 'draft' })
const current = ref({})
const fields = ref([])
const bindings = ref({})
const tab = ref('fields')
const query = ref({})
const previewResult = ref({})
const previewRows = ref([])

const load = async () => (list.value = await pages.list())

const openCreate = () => {
  form.value = { page_type: 'list', status: 'draft' }
  visible.value = true
}

const saveMeta = async () => {
  if (form.value.id) await pages.update(form.value.id, form.value)
  else await pages.create(form.value)
  ElMessage.success('已保存')
  visible.value = false
  load()
}

const remove = async (row) => {
  await ElMessageBox.confirm(`确认删除页面 ${row.name}？`, '提示', { type: 'warning' })
  await pages.remove(row.id)
  load()
}

const addField = () => fields.value.push({ name: '', label: '', type: 'text', show: true, query: false })

const openDesigner = async (row) => {
  current.value = row
  fields.value = (row.schema || {}).fields || []
  bindings.value = { ...(row.bindings || {}) }
  query.value = {}
  previewRows.value = []
  previewResult.value = {}
  tab.value = 'fields'
  designerVisible.value = true
}

const saveDesign = async () => {
  await pages.update(current.value.id, { schema: { fields: fields.value }, bindings: bindings.value })
  ElMessage.success('已保存')
  load()
}

const preview = async () => {
  const res = await api.pageData(current.value.id, { action: 'list', payload: query.value })
  previewResult.value = res
  const output = res.output || {}
  previewRows.value = output.rows || output.data || (Array.isArray(output) ? output : [])
}

onMounted(async () => {
  moduleList.value = await modules.list()
  defList.value = await definitions.list()
  await load()
})
</script>
