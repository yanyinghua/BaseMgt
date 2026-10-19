<template>
  <el-drawer :model-value="modelValue" :title="`Run#${run?.id} ${run?.definition_name || ''}`" size="55%" @update:model-value="$emit('update:modelValue', $event)">
    <el-descriptions :column="2" border size="small">
      <el-descriptions-item label="状态">
        <el-tag size="small" :type="statusType(run?.status)">{{ run?.status }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="触发方式">{{ run?.trigger }}</el-descriptions-item>
      <el-descriptions-item label="耗时">{{ run?.duration_ms }} ms</el-descriptions-item>
      <el-descriptions-item label="开始时间">{{ run?.started_at }}</el-descriptions-item>
    </el-descriptions>

    <el-alert v-if="run?.error" :title="run.error" type="error" show-icon style="margin: 12px 0" />

    <el-divider content-position="left">输出</el-divider>
    <pre class="bm-mono bm-json">{{ pretty(run?.output) }}</pre>

    <el-divider content-position="left">节点执行</el-divider>
    <el-table :data="run?.node_runs || []" size="small" row-key="id">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div style="padding: 8px">
            <div><strong>日志</strong></div>
            <div v-for="(l, i) in row.logs || []" :key="i" class="bm-mono">
              [{{ l.t }}] {{ l.level }}: {{ l.message }}
            </div>
            <div style="margin-top: 8px"><strong>输出</strong></div>
            <pre class="bm-mono bm-json">{{ pretty(row.output) }}</pre>
            <div v-if="row.error" style="color: #f56c6c">{{ row.error }}</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="order" label="#" width="50" />
      <el-table-column prop="node_name" label="节点" width="140" />
      <el-table-column prop="node_type" label="类型" width="110" />
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }"><el-tag size="small" :type="statusType(row.status)">{{ row.status }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="duration_ms" label="耗时(ms)" width="90" />
    </el-table>
  </el-drawer>
</template>

<script setup>
defineProps({ modelValue: Boolean, run: { type: Object, default: null } })
defineEmits(['update:modelValue'])

const pretty = (v) => JSON.stringify(v ?? null, null, 2)
const statusType = (s) => ({ success: 'success', failed: 'danger', running: 'primary', suspended: 'warning' }[s] || 'info')
</script>

<style scoped>
.bm-json {
  background: #f7f8fa;
  border: 1px solid var(--bm-border);
  border-radius: 4px;
  padding: 8px;
  max-height: 240px;
  overflow: auto;
  white-space: pre-wrap;
}
</style>
