<template>
  <Layout>
    <div class="bm-page">
      <div class="bm-card">
        <div class="bm-toolbar">
          <strong>{{ page?.name || '页面' }}</strong>
          <el-tag size="small">{{ page?.page_type }}</el-tag>
          <span class="bm-muted">{{ page?.description }}</span>
        </div>

        <!-- 列表页 -->
        <template v-if="page?.page_type === 'list'">
          <el-form :inline="true" size="small">
            <el-form-item v-for="f in queryFields" :key="f.name" :label="f.label">
              <el-tree-select
                v-if="f.refTree"
                v-model="query[f.name]"
                :data="treeOptions(f)"
                :props="treeProps"
                node-key="value"
                check-strictly
                clearable
                filterable
              />
              <el-select v-else-if="f.type === 'ref' || f.type === 'select'" v-model="query[f.name]" clearable filterable>
                <el-option v-for="o in optionsOf(f)" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
              <el-input v-else v-model="query[f.name]" :type="f.type === 'number' ? 'number' : 'text'" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" size="small" :loading="loading" @click="loadData">查询</el-button>
            </el-form-item>
          </el-form>

          <el-row v-if="isTreePage" :gutter="12">
            <el-col :span="6">
              <div class="bm-toolbar">
                <strong>层级</strong>
                <el-button link type="primary" @click="selectedNode = null">全部</el-button>
              </div>
              <el-tree
                :data="rowTree"
                :props="treeProps"
                node-key="value"
                highlight-current
                default-expand-all
                @node-click="onTreeNode"
              />
            </el-col>
            <el-col :span="18">
              <el-table :data="filteredRows" size="small" v-loading="loading">
                <el-table-column v-for="c in showFields" :key="c.name" :prop="c.name" :label="c.label" show-overflow-tooltip>
                  <template #default="{ row }">{{ display(c, row[c.name]) }}</template>
                </el-table-column>
                <template #empty><span class="bm-muted">{{ error || '暂无数据' }}</span></template>
              </el-table>
            </el-col>
          </el-row>
          <el-table v-else :data="rows" size="small" v-loading="loading">
            <el-table-column v-for="c in showFields" :key="c.name" :prop="c.name" :label="c.label" show-overflow-tooltip>
              <template #default="{ row }">{{ display(c, row[c.name]) }}</template>
            </el-table-column>
            <template #empty><span class="bm-muted">{{ error || '暂无数据' }}</span></template>
          </el-table>

          <div class="bm-toolbar" style="margin-top: 8px">
            <el-button size="small" @click="prevPage" :disabled="offset === 0">上一页</el-button>
            <el-button size="small" @click="nextPage" :disabled="rows.length < limit">下一页</el-button>
            <span class="bm-muted">共 {{ total }} 条</span>
          </div>
        </template>

        <!-- 表单页 -->
        <template v-else-if="page?.page_type === 'form'">
          <el-form :model="form" label-width="140px" size="small" style="max-width: 620px">
            <el-form-item v-for="f in allFields" :key="f.name" :label="f.label">
              <el-tree-select
                v-if="f.refTree"
                v-model="form[f.name]"
                :data="treeOptions(f)"
                :props="treeProps"
                node-key="value"
                check-strictly
                clearable
                filterable
                style="width: 100%"
              />
              <el-select
                v-else-if="f.type === 'ref' || f.type === 'select'"
                v-model="form[f.name]"
                clearable
                filterable
                style="width: 100%"
              >
                <el-option v-for="o in optionsOf(f)" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
              <el-input v-else v-model="form[f.name]" :type="f.type === 'number' ? 'number' : 'text'" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="loading" @click="submit">提交</el-button>
              <el-button @click="resetForm">重填</el-button>
            </el-form-item>
          </el-form>
          <el-alert
            v-if="result"
            :title="JSON.stringify(result)"
            :type="status === 'success' ? 'success' : 'error'"
            show-icon
          />
        </template>

        <!-- 看板 / 报表：KPI 卡片 + 图表 +（报表）明细表 -->
        <template v-else-if="isDashboard || isReport">
          <el-row v-if="cards.length" :gutter="12">
            <el-col v-for="c in cards" :key="c.title" :span="6">
              <el-card shadow="never" style="margin-bottom: 12px">
                <div class="bm-muted">{{ c.title }}</div>
                <div style="font-size: 22px; font-weight: 700">
                  {{ cardValue(c)
                  }}<span v-if="c.unit" class="bm-muted" style="font-size: 12px; margin-left: 4px">{{ c.unit }}</span>
                </div>
                <router-link v-if="c.link" :to="c.link" class="bm-muted" style="font-size: 12px">
                  查看明细 →
                </router-link>
              </el-card>
            </el-col>
          </el-row>

          <el-row v-if="charts.length" :gutter="12">
            <el-col v-for="ch in charts" :key="ch.title" :span="12">
              <el-card shadow="never" style="margin-bottom: 12px">
                <div style="font-weight: 600; margin-bottom: 8px">{{ ch.title }}</div>
                <ChartView :type="ch.type" :data="chartData(ch)" />
              </el-card>
            </el-col>
          </el-row>

          <template v-if="isReport">
            <el-form v-if="queryFields.length" :inline="true" size="small">
              <el-form-item v-for="f in queryFields" :key="f.name" :label="f.label">
                <el-input v-model="query[f.name]" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" size="small" @click="loadData">查询</el-button>
              </el-form-item>
            </el-form>
            <div class="bm-toolbar">
              <el-button type="primary" size="small" @click="exportReport">导出 Excel</el-button>
              <span class="bm-muted">共 {{ total }} 条</span>
            </div>
            <el-table :data="rows" size="small" v-loading="loading">
              <el-table-column
                v-for="c in showFields"
                :key="c.name"
                :prop="c.name"
                :label="c.label"
                show-overflow-tooltip
              />
              <template #empty><span class="bm-muted">{{ error || '暂无数据' }}</span></template>
            </el-table>
          </template>
        </template>

        <el-empty v-else-if="!page" description="页面不存在或未发布" />
      </div>
    </div>
  </Layout>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import Layout from '../layout/Layout.vue'
import ChartView from '../components/ChartView.vue'
import { api, pages } from '../api'

const route = useRoute()
const page = ref(null)
const query = ref({})
const form = ref({})
const rows = ref([])
const loading = ref(false)
const error = ref('')
const result = ref(null)
const status = ref('')
const total = ref(0)
const limit = ref(20)
const offset = ref(0)
const refOptions = ref({})
const selectedNode = ref(null)
const treeProps = { label: 'label', children: 'children' }

const allFields = computed(() => (page.value?.schema || {}).fields || [])
const queryFields = computed(() => allFields.value.filter((f) => f.query))
const showFields = computed(() => {
  const visible = allFields.value.filter((f) => f.show !== false && !f.query)
  return visible.length ? visible : allFields.value
})
const isTreePage = computed(() => !!(page.value?.schema || {}).tree)

// ---- 看板 / 报表 ----
const schema = computed(() => page.value?.schema || {})
const cards = computed(() => schema.value.cards || [])
const charts = computed(() => schema.value.charts || [])
const isDashboard = computed(() => page.value?.page_type === 'dashboard')
const isReport = computed(() => page.value?.page_type === 'report')
const bindRows = ref({})

const loadBindRows = async () => {
  const keys = new Set()
  cards.value.forEach((c) => c.bind && keys.add(c.bind))
  charts.value.forEach((c) => c.bind && keys.add(c.bind))
  for (const key of keys) {
    if (bindRows.value[key]) continue
    try {
      const res = await api.openTrigger(key, { limit: 500, offset: 0 })
      bindRows.value[key] = (res.output || {}).rows || []
    } catch {
      bindRows.value[key] = []
    }
  }
}

const aggregate = (list, card) => {
  const metric = card.metric || 'count'
  if (metric === 'count') return list.length
  const values = list.map((r) => Number(r[card.field]) || 0)
  if (!values.length) return 0
  if (metric === 'sum') return values.reduce((a, b) => a + b, 0)
  if (metric === 'avg') return values.reduce((a, b) => a + b, 0) / values.length
  if (metric === 'max') return Math.max(...values)
  if (metric === 'min') return Math.min(...values)
  return 0
}

const rowsOf = (item) => (item.bind ? (bindRows.value[item.bind] || []) : rows.value)

const cardValue = (card) => {
  const value = aggregate(rowsOf(card), card)
  return Number.isInteger(value) ? value : Math.round(value * 100) / 100
}

const chartData = (chart) => {
  const agg = chart.agg || 'sum'
  const map = new Map()
  rowsOf(chart).forEach((r) => {
    const name = String(r[chart.labelField] ?? '未分类')
    const add = agg === 'count' ? 1 : Number(r[chart.valueField]) || 0
    map.set(name, (map.get(name) || 0) + add)
  })
  return [...map.entries()].map(([name, value]) => ({ name, value }))
}

const exportReport = () => {
  window.open(api.pageExportUrl(page.value.id, query.value), '_blank')
}

const normalize = (options) =>
  (options || []).map((o) => (o && typeof o === 'object' ? o : { value: o, label: o }))

const optionsOf = (field) => {
  if (field.type === 'select') return normalize(field.options)
  return refOptions.value[field.name] || []
}

const buildTree = (items) => {
  const byId = new Map(items.map((i) => [i.value, { ...i, children: [] }]))
  const roots = []
  for (const item of items) {
    const node = byId.get(item.value)
    if (item.parent && byId.has(item.parent) && item.parent !== item.value) {
      byId.get(item.parent).children.push(node)
    } else {
      roots.push(node)
    }
  }
  return roots
}

const treeOptions = (field) => buildTree(refOptions.value[field.name] || [])

const rowTree = computed(() => {
  const schema = page.value?.schema || {}
  return buildTree(
    rows.value.map((r) => ({
      value: r.id,
      label: r[schema.treeLabel || 'name'] ?? r.id,
      parent: r[schema.treeParentField || 'parent_id']
    }))
  )
})

const collectIds = (node, acc = new Set()) => {
  acc.add(node.value)
  ;(node.children || []).forEach((c) => collectIds(c, acc))
  return acc
}

const filteredRows = computed(() => {
  if (!selectedNode.value) return rows.value
  const ids = collectIds(selectedNode.value)
  return rows.value.filter((r) => ids.has(r.id))
})

const onTreeNode = (node) => {
  selectedNode.value = node
}

const display = (field, value) => {
  if (field.type === 'ref') {
    const hit = (refOptions.value[field.name] || []).find((o) => o.value === value)
    return hit ? hit.label : (value ?? '')
  }
  return value ?? ''
}

const load = async () => {
  const list = await pages.list({ key: route.params.key })
  page.value = list[0] || null
  if (page.value) {
    await loadRefOptions()
    if (page.value.page_type === 'list') await loadData()
    if (isDashboard.value || isReport.value) {
      await loadBindRows()
      if (isReport.value) await loadData()
    }
  }
}

const loadRefOptions = async () => {
  for (const field of allFields.value) {
    if (field.type !== 'ref' || !field.refEntity || refOptions.value[field.name]) continue
    try {
      const res = await api.openTrigger(`${field.refEntity}-list`, { limit: 200, offset: 0 })
      const list = (res.output || {}).rows || []
      const label = field.refDisplay || 'name'
      const parentField = field.refParentField || 'parent_id'
      refOptions.value[field.name] = list.map((r) => ({
        value: r.id,
        label: r[label] ?? r.name ?? r.id,
        parent: r[parentField] ?? null
      }))
    } catch {
      refOptions.value[field.name] = []
    }
  }
}

const loadData = async () => {
  if (!page.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await api.pageData(page.value.id, {
      action: 'list',
      payload: { ...query.value, limit: limit.value, offset: offset.value }
    })
    status.value = res.status
    const output = res.output || {}
    rows.value = output.rows || output.data || (Array.isArray(output) ? output : [])
    total.value = output.total || rows.value.length
    error.value = res.error || ''
  } finally {
    loading.value = false
  }
}

const nextPage = () => {
  offset.value += limit.value
  loadData()
}
const prevPage = () => {
  offset.value = Math.max(0, offset.value - limit.value)
  loadData()
}

const resetForm = () => {
  form.value = {}
  result.value = null
}

const submit = async () => {
  loading.value = true
  try {
    const res = await api.pageData(page.value.id, { action: 'submit', payload: form.value })
    status.value = res.status
    result.value = res.output
    error.value = res.error || ''
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(() => route.params.key, load)
</script>
