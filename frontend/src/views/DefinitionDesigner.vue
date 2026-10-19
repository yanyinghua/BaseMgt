<template>
  <div class="designer">
    <div class="designer__bar">
      <el-button size="small" @click="$router.push('/definitions')">返回</el-button>
      <el-input v-model="form.name" size="small" style="width: 200px" placeholder="名称" />
      <el-input v-model="form.key" size="small" style="width: 160px" placeholder="标识" />
      <el-select v-model="form.kind" size="small" style="width: 140px">
        <el-option label="服务/接口编排" value="service" />
        <el-option label="业务流程编排" value="flow" />
        <el-option label="数据管道/定时" value="pipeline" />
      </el-select>
      <el-tag size="small" :type="form.status === 'published' ? 'success' : 'info'">{{ form.status }}</el-tag>
      <span style="margin-left: auto" />
      <el-button size="small" @click="triggerVisible = true">触发设置</el-button>
      <el-button size="small" @click="validate">校验</el-button>
      <el-button size="small" type="primary" @click="save">保存</el-button>
      <el-button size="small" type="success" @click="publish">发布</el-button>
      <el-button size="small" type="warning" @click="runVisible = true">运行</el-button>
    </div>

    <div class="designer__body">
      <aside class="designer__left">
        <div v-for="(items, category) in groups" :key="category" class="palette">
          <div class="palette__title">{{ category }}</div>
          <div
            v-for="item in items"
            :key="item.type"
            class="palette__item"
            draggable="true"
            @dragstart="onDragStart($event, item.type)"
          >
            <span>{{ item.icon }}</span>{{ item.name }}
          </div>
        </div>
      </aside>

      <main class="designer__canvas" @drop="onDrop" @dragover.prevent>
        <VueFlow v-model:nodes="nodes" v-model:edges="edges" :fit-view-on-init="true" @node-click="onNodeClick" @connect="onConnect">
          <template #node-bm="props"><BmNode v-bind="props" /></template>
          <Background />
        </VueFlow>
      </main>

      <aside class="designer__right">
        <template v-if="selected">
          <div class="bm-toolbar">
            <strong>{{ selected.data.label }}</strong>
            <el-button link type="danger" @click="removeSelected">删除节点</el-button>
          </div>
          <el-form size="small" label-position="top">
            <el-form-item label="节点名称">
              <el-input v-model="selected.data.name" />
            </el-form-item>
          </el-form>
          <NodeConfigForm
            :schema="schemaOf(selected.data.type)"
            :model="selected.data.config"
            :data-sources="dsList"
          />
        </template>
        <el-empty v-else description="拖入左侧节点，或点选画布中的节点" />
      </aside>
    </div>

    <el-dialog v-model="triggerVisible" title="触发设置" width="480">
      <el-form label-width="100px" size="small">
        <el-form-item label="触发方式">
          <el-select v-model="trigger.type">
            <el-option label="手动" value="manual" />
            <el-option label="HTTP 接口" value="http" />
            <el-option label="定时任务" value="cron" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="trigger.type === 'http'" label="方法">
          <el-select v-model="trigger.method"><el-option label="POST" value="POST" /><el-option label="GET" value="GET" /></el-select>
        </el-form-item>
        <el-form-item v-if="trigger.type === 'cron'" label="cron">
          <el-input v-model="trigger.cron" placeholder="*/5 * * * *" />
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="trigger.enabled" /></el-form-item>
        <div v-if="trigger.type === 'http'" class="bm-muted">
          发布后调用地址：<span class="bm-mono">POST /api/x/{{ form.key }}</span>
        </div>
        <div v-if="trigger.type === 'cron'" class="bm-muted">
          需要后台常驻调度：<span class="bm-mono">python manage.py run_schedules</span>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="triggerVisible = false">取消</el-button>
        <el-button type="primary" @click="triggerVisible = false">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="runVisible" title="运行调试" width="520">
      <el-input v-model="payloadText" type="textarea" :rows="8" class="bm-mono" />
      <template #footer>
        <el-button @click="runVisible = false">取消</el-button>
        <el-button type="primary" @click="doRun">执行</el-button>
      </template>
    </el-dialog>

    <RunDetail v-model="resultVisible" :run="lastRun" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'

import BmNode from '../components/BmNode.vue'
import NodeConfigForm from '../components/NodeConfigForm.vue'
import RunDetail from '../components/RunDetail.vue'
import { api, dataSources, definitions } from '../api'

const route = useRoute()
const definitionId = route.params.id
const { screenToFlowCoordinate } = useVueFlow()

const form = ref({ name: '', key: '', kind: 'service', status: 'draft', description: '' })
const trigger = ref({ type: 'manual', method: 'POST', cron: '', enabled: true })
const nodes = ref([])
const edges = ref([])
const groups = ref({})
const typeMap = ref({})
const dsList = ref([])
const selectedId = ref('')
const triggerVisible = ref(false)
const runVisible = ref(false)
const resultVisible = ref(false)
const payloadText = ref('{}')
const lastRun = ref(null)

const selected = computed(() => nodes.value.find((n) => n.id === selectedId.value))
const schemaOf = (type) => typeMap.value[type]?.config_schema || []

const defaultConfig = (meta) => {
  const cfg = {}
  ;(meta.config_schema || []).forEach((f) => {
    if (f.default !== undefined) cfg[f.key] = f.default
  })
  return cfg
}

const toFlow = (graph) => {
  const g = graph || {}
  nodes.value = (g.nodes || []).map((n) => {
    const meta = typeMap.value[n.type] || {}
    return {
      id: n.id,
      type: 'bm',
      position: n.position || { x: 0, y: 0 },
      data: {
        type: n.type,
        label: meta.name || n.type,
        icon: meta.icon || '◆',
        handles: meta.handles || ['default'],
        name: n.name || meta.name || n.type,
        config: n.config || {}
      }
    }
  })
  edges.value = (g.edges || []).map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    sourceHandle: e.sourceHandle || 'default',
    animated: true
  }))
}

const load = async () => {
  const meta = await api.nodeTypes()
  groups.value = meta.groups
  typeMap.value = meta.types
  dsList.value = await dataSources.list()
  const data = await definitions.get(definitionId)
  form.value = { ...data }
  trigger.value = { type: 'manual', method: 'POST', cron: '', enabled: true, ...(data.trigger || {}) }
  payloadText.value = JSON.stringify(
    Object.fromEntries((data.input_schema || []).map((f) => [f.name, f.default ?? ''])),
    null,
    2
  )
  toFlow(data.graph)
}

const onDragStart = (event, type) => {
  event.dataTransfer.setData('application/bm-node', type)
  event.dataTransfer.effectAllowed = 'move'
}

const onDrop = (event) => {
  const type = event.dataTransfer.getData('application/bm-node')
  if (!type) return
  const position = screenToFlowCoordinate({ x: event.clientX, y: event.clientY })
  const meta = typeMap.value[type]
  const id = `${type}_${Date.now()}`
  nodes.value.push({
    id,
    type: 'bm',
    position,
    data: { type, label: meta.name, icon: meta.icon, handles: meta.handles, name: meta.name, config: defaultConfig(meta) }
  })
  selectedId.value = id
}

const onConnect = (conn) => {
  edges.value.push({
    id: `e_${conn.source}_${conn.target}_${Date.now()}`,
    source: conn.source,
    target: conn.target,
    sourceHandle: conn.sourceHandle || 'default',
    animated: true
  })
}

const onNodeClick = ({ node }) => {
  selectedId.value = node.id
}

const removeSelected = () => {
  const id = selectedId.value
  nodes.value = nodes.value.filter((n) => n.id !== id)
  edges.value = edges.value.filter((e) => e.source !== id && e.target !== id)
  selectedId.value = ''
}

const currentGraph = () => ({
  nodes: nodes.value.map((n) => ({
    id: n.id,
    type: n.data.type,
    name: n.data.name,
    config: n.data.config,
    position: n.position
  })),
  edges: edges.value.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    sourceHandle: e.sourceHandle || 'default'
  }))
})

const save = async () => {
  await definitions.update(definitionId, {
    name: form.value.name,
    key: form.value.key,
    kind: form.value.kind,
    description: form.value.description,
    trigger: trigger.value,
    graph: currentGraph()
  })
  ElMessage.success('已保存')
}

const validate = async () => {
  await save()
  const res = await api.validateDefinition(definitionId)
  if (res.valid) ElMessage.success('校验通过')
  else ElMessage.error(`校验不通过：${res.errors.join('；')}`)
}

const publish = async () => {
  await save()
  await api.publishDefinition(definitionId)
  form.value.status = 'published'
  ElMessage.success('已发布')
}

const doRun = async () => {
  let payload = {}
  try {
    payload = JSON.parse(payloadText.value || '{}')
  } catch {
    ElMessage.error('入参需为合法 JSON')
    return
  }
  await save()
  const submitted = await api.runDefinition(definitionId, payload)
  runVisible.value = false
  lastRun.value = submitted
  resultVisible.value = true
  // 异步模式下轮询直到结束
  if (['pending', 'running'].includes(submitted.status)) {
    lastRun.value = await api.waitRun(submitted.id)
  }
}

onMounted(load)
</script>

<style scoped>
.designer {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.designer__bar {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 12px;
  background: #fff;
  border-bottom: 1px solid var(--bm-border);
}
.designer__body {
  flex: 1;
  display: flex;
  min-height: 0;
}
.designer__left {
  width: 180px;
  background: #fff;
  border-right: 1px solid var(--bm-border);
  overflow: auto;
  padding: 8px;
}
.designer__right {
  width: 340px;
  background: #fff;
  border-left: 1px solid var(--bm-border);
  overflow: auto;
  padding: 12px;
}
.designer__canvas {
  flex: 1;
  min-width: 0;
  position: relative;
}
.palette__title {
  font-size: 12px;
  color: #909399;
  margin: 8px 0 4px;
}
.palette__item {
  padding: 6px 8px;
  border: 1px solid var(--bm-border);
  border-radius: 4px;
  margin-bottom: 6px;
  cursor: grab;
  font-size: 13px;
  background: #fafafa;
}
.palette__item:hover {
  border-color: #409eff;
  color: #409eff;
}
</style>
