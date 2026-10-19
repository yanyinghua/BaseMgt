<template>
  <div class="bm-node" :class="{ 'bm-node--sel': data.selected }">
    <Handle type="target" :position="Position.Left" />
    <div class="bm-node__title">
      <span class="bm-node__icon">{{ data.icon }}</span>{{ data.label }}
    </div>
    <div class="bm-node__sub bm-mono">{{ data.name || data.type }}</div>
    <Handle
      v-for="(h, i) in data.handles"
      :id="h"
      :key="h"
      type="source"
      :position="Position.Right"
      :style="{ top: handleTop(i, data.handles.length) }"
    >
      <span v-if="data.handles.length > 1" class="bm-node__handle bm-mono">{{ h }}</span>
    </Handle>
  </div>
</template>

<script setup>
import { Handle, Position } from '@vue-flow/core'

defineProps({ data: { type: Object, required: true } })

const handleTop = (index, total) => `${((index + 1) * 100) / (total + 1)}%`
</script>

<style scoped>
.bm-node {
  min-width: 140px;
  padding: 8px 12px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  position: relative;
}
.bm-node--sel {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.25);
}
.bm-node__title {
  font-size: 13px;
  font-weight: 600;
}
.bm-node__icon {
  margin-right: 4px;
  color: #409eff;
}
.bm-node__sub {
  color: #909399;
  margin-top: 2px;
}
.bm-node__handle {
  position: absolute;
  left: 14px;
  top: -8px;
  font-size: 10px;
  color: #909399;
}
</style>
