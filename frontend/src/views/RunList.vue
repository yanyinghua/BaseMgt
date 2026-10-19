<template>
  <Layout>
    <div class="bm-page">
      <div class="bm-card">
        <div class="bm-toolbar">
          <strong>运行记录</strong>
          <el-select v-model="status" clearable placeholder="状态" style="width: 140px" @change="load">
            <el-option v-for="s in statuses" :key="s" :label="s" :value="s" />
          </el-select>
          <el-button size="small" @click="load">刷新</el-button>
        </div>
        <el-table :data="list" size="small" @row-click="openDetail">
          <el-table-column prop="id" label="Run#" width="80" />
          <el-table-column prop="definition_name" label="编排" min-width="200" />
          <el-table-column prop="trigger" label="触发" width="90" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="{ success: 'success', failed: 'danger', running: 'primary', suspended: 'warning' }[row.status] || 'info'">
                {{ row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="duration_ms" label="耗时(ms)" width="100" />
          <el-table-column prop="started_at" label="开始时间" width="180" />
          <el-table-column label="操作" width="160">
            <template #default="{ row }">
              <el-button link type="primary" @click.stop="retry(row)">重跑</el-button>
              <el-button link type="danger" @click.stop="cancel(row)">取消</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <RunDetail v-model="visible" :run="current" />
    </div>
  </Layout>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import Layout from '../layout/Layout.vue'
import RunDetail from '../components/RunDetail.vue'
import { api, runs } from '../api'

const statuses = ['pending', 'running', 'success', 'failed', 'suspended', 'cancelled']
const list = ref([])
const visible = ref(false)
const current = ref(null)
const status = ref('')

const load = async () => {
  const params = {}
  if (status.value) params.status = status.value
  list.value = await runs.list(params)
}

const openDetail = async (row) => {
  current.value = await runs.get(row.id)
  visible.value = true
}

const retry = async (row) => {
  const submitted = await api.retryRun(row.id)
  current.value = ['pending', 'running'].includes(submitted.status) ? await api.waitRun(submitted.id) : submitted
  visible.value = true
  load()
}

const cancel = async (row) => {
  await api.cancelRun(row.id)
  ElMessage.success('已取消')
  load()
}

// 有未结束的运行时自动轮询刷新
let timer = null
const startPolling = () => {
  clearInterval(timer)
  timer = setInterval(async () => {
    const rows = await runs.list(status.value ? { status: status.value } : {})
    list.value = rows
    if (!rows.some((r) => ['pending', 'running'].includes(r.status))) clearInterval(timer)
  }, 3000)
}

onMounted(async () => {
  await load()
  if (list.value.some((r) => ['pending', 'running'].includes(r.status))) startPolling()
})
onUnmounted(() => clearInterval(timer))
</script>
