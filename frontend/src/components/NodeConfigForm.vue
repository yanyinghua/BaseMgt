<template>
  <el-form label-position="top" size="small">
    <el-form-item v-for="f in schema" :key="f.key">
      <template #label>
        <span>{{ f.label }}</span>
        <el-tooltip v-if="f.help" :content="f.help"><el-icon style="margin-left: 4px"><QuestionFilled /></el-icon></el-tooltip>
      </template>

      <el-input v-if="f.type === 'text' || f.type === 'procedure'" v-model="model[f.key]" :placeholder="f.default || ''" />
      <el-input v-else-if="f.type === 'textarea'" v-model="model[f.key]" type="textarea" :rows="3" />
      <el-input-number v-else-if="f.type === 'number'" v-model="model[f.key]" style="width: 100%" />
      <el-switch v-else-if="f.type === 'switch'" v-model="model[f.key]" />
      <el-select v-else-if="f.type === 'select'" v-model="model[f.key]" style="width: 100%">
        <el-option v-for="o in f.options" :key="o.value" :label="o.label" :value="o.value" />
      </el-select>
      <el-select v-else-if="f.type === 'datasource'" v-model="model[f.key]" clearable filterable style="width: 100%">
        <el-option v-for="d in dataSources" :key="d.id" :label="`${d.name}(${d.key})`" :value="d.key" />
      </el-select>
      <el-input
        v-else
        v-model="raw[f.key]"
        type="textarea"
        :rows="f.type === 'code' ? 8 : 4"
        class="bm-mono"
        :class="{ 'bm-invalid': invalid[f.key] }"
        @blur="applyJson(f)"
      />
    </el-form-item>
    <div class="bm-muted" style="font-size: 12px">
      提示：JSON 类字段支持 <span class="bm-mono">{{ sampleExpr }}</span> 表达式。
    </div>
  </el-form>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'

const props = defineProps({
  schema: { type: Array, default: () => [] },
  model: { type: Object, required: true },
  dataSources: { type: Array, default: () => [] }
})

const sampleExpr = '{{ vars.xxx }}'
const JSON_TYPES = ['json', 'code', 'mapping', 'rules', 'assignments']
const raw = reactive({})
const invalid = reactive({})

const isJson = (f) => JSON_TYPES.includes(f.type)

const initRaw = () => {
  props.schema.forEach((f) => {
    if (!isJson(f)) return
    const value = props.model[f.key]
    raw[f.key] = typeof value === 'string' ? value : JSON.stringify(value ?? f.default ?? null, null, 2)
  })
}
initRaw()
watch(() => props.model, initRaw, { deep: false })

const applyJson = (f) => {
  try {
    props.model[f.key] = JSON.parse(raw[f.key])
    invalid[f.key] = false
  } catch {
    invalid[f.key] = true
  }
}
</script>

<style scoped>
.bm-invalid :deep(textarea) {
  color: #f56c6c;
}
</style>
