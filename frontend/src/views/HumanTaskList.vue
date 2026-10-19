<template>
  <Layout>
    <div class="bm-page">
      <div class="bm-card">
        <div class="bm-toolbar">
          <strong>人工任务</strong>
          <el-select v-model="status" clearable placeholder="状态" style="width: 140px" @change="load">
            <el-option label="待处理" value="pending" />
            <el-option label="已处理" value="done" />
          </el-select>
          <el-button size="small" @click="load">刷新</el-button>
        </div>
        <el-table :data="list" size="small">
          <el-table-column prop="id" label="#" width="60" />
          <el-table-column prop="title" label="标题" min-width="200" />
          <el-table-column prop="definition_name" label="所属编排" min-width="160" />
          <el-table-column prop="assignee_name" label="处理人" width="100" />
          <el-table-column prop="status" label="状态" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'pending' ? 'warning' : 'success'">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="创建时间" width="180" />
          <el-table-column label="操作" width="180">
            <template #default="{ row }">
              <template v-if="row.status === 'pending'">
                <el-button link type="success" @click="complete(row, 'approve')">通过</el-button>
                <el-button link type="danger" @click="complete(row, 'reject')">驳回</el-button>
              </template>
              <span v-else class="bm-muted">{{ row.action }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </Layout>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Layout from '../layout/Layout.vue'
import { api, humanTasks } from '../api'

const list = ref([])
const status = ref('pending')

const load = async () => {
  const params = {}
  if (status.value) params.status = status.value
  list.value = await humanTasks.list(params)
}

const complete = async (row, action) => {
  const comment = await ElMessageBox.prompt('处理意见', action === 'approve' ? '通过' : '驳回', {
    inputPlaceholder: '可留空',
    inputValue: ''
  }).catch(() => null)
  if (!comment) return
  const run = await api.completeTask(row.id, { action, result: { comment: comment.value } })
  ElMessage.success(`已处理，流程继续执行（Run#${run.id} ${run.status}）`)
  load()
}

onMounted(load)
</script>
