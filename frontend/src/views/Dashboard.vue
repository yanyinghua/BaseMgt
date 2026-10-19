<template>
  <Layout>
    <div class="bm-page">
      <el-row :gutter="12">
        <el-col v-for="c in cards" :key="c.title" :span="6">
          <el-card shadow="never" style="margin-bottom: 12px">
            <div class="bm-muted">{{ c.title }}</div>
            <div style="font-size: 24px; font-weight: 700">{{ c.value }}</div>
          </el-card>
        </el-col>
      </el-row>

      <div class="bm-card">
        <div class="bm-toolbar"><strong>最近运行</strong></div>
        <el-table :data="recentRuns" size="small">
          <el-table-column prop="id" label="Run#" width="80" />
          <el-table-column prop="definition_name" label="编排" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="duration_ms" label="耗时(ms)" width="100" />
          <el-table-column prop="created_at" label="时间" width="180" />
        </el-table>
      </div>

      <div class="bm-card" style="margin-top: 12px">
        <div class="bm-toolbar"><strong>快速开始</strong></div>
        <ol class="bm-muted" style="line-height: 2">
          <li>数据源：登记业务库连接（默认示例已指向本地 basemgt）。</li>
          <li>存储过程：新建/同步存储过程，编辑 DDL 后「下发」到目标库。</li>
          <li>编排定义：新建 service 编排，在画布里拖入「存储过程」节点并连线。</li>
          <li>发布后通过 <span class="bm-mono">POST /api/x/&lt;key&gt;</span> 调用，或在前台「运行」调试。</li>
          <li>页面编排：把列表/表单绑定到编排接口，即得到一个新的业务模块页面。</li>
        </ol>
      </div>
    </div>
  </Layout>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import Layout from '../layout/Layout.vue'
import { definitions, modules, procedures, runs } from '../api'

const cards = ref([])
const recentRuns = ref([])

const statusType = (s) => ({ success: 'success', failed: 'danger', running: 'primary', suspended: 'warning' }[s] || 'info')

onMounted(async () => {
  const [m, p, d, r] = await Promise.all([
    modules.list(),
    procedures.list(),
    definitions.list(),
    runs.list({})
  ])
  cards.value = [
    { title: '业务模块', value: m.length },
    { title: '存储过程', value: p.length },
    { title: '编排定义', value: d.length },
    { title: '运行记录', value: r.length }
  ]
  recentRuns.value = r.slice(0, 10)
})
</script>
