<template>
  <Layout>
    <div class="bm-page">
      <div class="bm-card">
        <div class="bm-toolbar">
          <strong>编排定义</strong>
          <el-select v-model="filterKind" clearable placeholder="类型" style="width: 150px" @change="load">
            <el-option label="服务/接口编排" value="service" />
            <el-option label="业务流程编排" value="flow" />
            <el-option label="数据管道/定时" value="pipeline" />
          </el-select>
          <el-button type="primary" size="small" @click="openCreate">新建编排</el-button>
        </div>
        <el-table :data="list" size="small">
          <el-table-column prop="key" label="标识" width="160" />
          <el-table-column prop="name" label="名称" min-width="180" />
          <el-table-column prop="kind" label="类型" width="130">
            <template #default="{ row }">{{ kindLabel(row.kind) }}</template>
          </el-table-column>
          <el-table-column prop="version" label="版本" width="70" />
          <el-table-column prop="status" label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'published' ? 'success' : 'info'">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="trigger_type" label="触发" width="90" />
          <el-table-column prop="last_run_at" label="最近运行" width="170" />
          <el-table-column label="操作" width="280">
            <template #default="{ row }">
              <el-button link type="primary" @click="$router.push(`/definitions/${row.id}`)">设计</el-button>
              <el-button link type="success" @click="publish(row)">发布</el-button>
              <el-button link @click="clone(row)">新版本</el-button>
              <el-button link type="danger" @click="remove(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-dialog v-model="visible" title="新建编排" width="480">
        <el-form :model="form" label-width="90px">
          <el-form-item label="标识"><el-input v-model="form.key" placeholder="如 order-create" /></el-form-item>
          <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="类型">
            <el-select v-model="form.kind" style="width: 100%">
              <el-option label="服务/接口编排" value="service" />
              <el-option label="业务流程编排" value="flow" />
              <el-option label="数据管道/定时" value="pipeline" />
            </el-select>
          </el-form-item>
          <el-form-item label="所属模块">
            <el-select v-model="form.module" clearable style="width: 100%">
              <el-option v-for="m in moduleList" :key="m.id" :label="m.name" :value="m.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="说明"><el-input v-model="form.description" type="textarea" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="visible = false">取消</el-button>
          <el-button type="primary" @click="create">创建</el-button>
        </template>
      </el-dialog>
    </div>
  </Layout>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Layout from '../layout/Layout.vue'
import { api, definitions, modules } from '../api'

const list = ref([])
const moduleList = ref([])
const visible = ref(false)
const filterKind = ref('')
const form = ref({ kind: 'service' })

const kindLabel = (k) => ({ service: '服务/接口', flow: '业务流程', pipeline: '数据管道' }[k] || k)

const load = async () => {
  const params = {}
  if (filterKind.value) params.kind = filterKind.value
  list.value = await definitions.list(params)
}

const openCreate = () => {
  form.value = { kind: 'service' }
  visible.value = true
}

const create = async () => {
  const data = await definitions.create({ ...form.value, graph: { nodes: [], edges: [] }, trigger: { type: 'manual' } })
  ElMessage.success('已创建')
  visible.value = false
  load()
  window.location.href = `/definitions/${data.id}`
}

const publish = async (row) => {
  await api.publishDefinition(row.id)
  ElMessage.success('已发布')
  load()
}

const clone = async (row) => {
  await api.cloneDefinition(row.id)
  ElMessage.success('已生成新版本')
  load()
}

const remove = async (row) => {
  await ElMessageBox.confirm(`确认删除编排 ${row.name}？`, '提示', { type: 'warning' })
  await definitions.remove(row.id)
  load()
}

onMounted(async () => {
  moduleList.value = await modules.list()
  await load()
})
</script>
