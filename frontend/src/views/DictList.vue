<template>
  <Layout>
    <div class="bm-page">
      <div class="bm-card">
        <div class="bm-toolbar">
          <strong>统一字典</strong>
          <el-button type="primary" size="small" @click="addDict">新增字典</el-button>
          <span class="bm-muted">
            枚举值集中维护：字段引用字典后，页面下拉与查询条件自动跟着变，不用改表结构
          </span>
        </div>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-table :data="list" size="small" highlight-current-row @current-change="onSelect">
              <el-table-column prop="key" label="标识" width="130" />
              <el-table-column prop="name" label="名称" />
              <el-table-column label="项" width="60">
                <template #default="{ row }">{{ row.item_count }}</template>
              </el-table-column>
              <el-table-column label="操作" width="110">
                <template #default="{ row }">
                  <el-button link @click="editDict(row)">编辑</el-button>
                  <el-button link type="danger" @click="removeDict(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-col>

          <el-col :span="16">
            <div class="bm-toolbar">
              <strong>{{ current?.name ? `字典项 - ${current.name}` : '选择左侧字典' }}</strong>
              <el-button type="primary" size="small" :disabled="!current" @click="addItem">新增字典项</el-button>
            </div>
            <el-table :data="items" size="small">
              <el-table-column prop="value" label="存储值" width="160" />
              <el-table-column prop="label" label="显示名" width="180" />
              <el-table-column label="上级" width="140">
                <template #default="{ row }">{{ parentLabel(row) }}</template>
              </el-table-column>
              <el-table-column prop="sort_order" label="排序" width="80" />
              <el-table-column label="默认" width="60">
                <template #default="{ row }">{{ row.is_default ? '√' : '' }}</template>
              </el-table-column>
              <el-table-column prop="status" label="状态" width="80" />
              <el-table-column label="操作" width="110">
                <template #default="{ row }">
                  <el-button link @click="editItem(row)">编辑</el-button>
                  <el-button link type="danger" @click="removeItem(row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-col>
        </el-row>
      </div>

      <el-dialog v-model="dictDialog" :title="dictForm.id ? '编辑字典' : '新增字典'" width="440">
        <el-form :model="dictForm" label-width="80px" size="small">
          <el-form-item label="标识"><el-input v-model="dictForm.key" placeholder="如 asset_category" /></el-form-item>
          <el-form-item label="名称"><el-input v-model="dictForm.name" /></el-form-item>
          <el-form-item label="说明"><el-input v-model="dictForm.description" type="textarea" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="dictDialog = false">取消</el-button>
          <el-button type="primary" @click="saveDict">保存</el-button>
        </template>
      </el-dialog>

      <el-dialog v-model="itemDialog" :title="itemForm.id ? '编辑字典项' : '新增字典项'" width="440">
        <el-form :model="itemForm" label-width="90px" size="small">
          <el-form-item label="存储值"><el-input v-model="itemForm.value" /></el-form-item>
          <el-form-item label="显示名"><el-input v-model="itemForm.label" /></el-form-item>
          <el-form-item label="上级项">
            <el-select v-model="itemForm.parent" clearable style="width: 100%">
              <el-option v-for="i in items" :key="i.id" :label="i.label" :value="i.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="排序"><el-input v-model.number="itemForm.sort_order" type="number" /></el-form-item>
          <el-form-item label="默认值"><el-switch v-model="itemForm.is_default" /></el-form-item>
          <el-form-item label="状态">
            <el-select v-model="itemForm.status"><el-option label="启用" value="active" /><el-option label="停用" value="disabled" /></el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="itemDialog = false">取消</el-button>
          <el-button type="primary" @click="saveItem">保存</el-button>
        </template>
      </el-dialog>
    </div>
  </Layout>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Layout from '../layout/Layout.vue'
import { dictItems, dictionaries } from '../api'

const list = ref([])
const items = ref([])
const current = ref(null)

const dictDialog = ref(false)
const itemDialog = ref(false)
const dictForm = ref({})
const itemForm = ref({})

const load = async () => {
  list.value = await dictionaries.list()
  if (!current.value && list.value.length) current.value = list.value[0]
  await loadItems()
}

const loadItems = async () => {
  items.value = current.value ? await dictItems.list({ dictionary: current.value.id }) : []
}

const onSelect = async (row) => {
  current.value = row
  await loadItems()
}

const parentLabel = (row) => (items.value.find((i) => i.id === row.parent) || {}).label || ''

const addDict = () => {
  dictForm.value = { key: '', name: '', description: '' }
  dictDialog.value = true
}
const editDict = (row) => {
  dictForm.value = { ...row }
  dictDialog.value = true
}
const saveDict = async () => {
  if (dictForm.value.id) await dictionaries.update(dictForm.value.id, dictForm.value)
  else await dictionaries.create(dictForm.value)
  ElMessage.success('已保存')
  dictDialog.value = false
  await load()
}
const removeDict = async (row) => {
  await ElMessageBox.confirm(`确认删除字典 ${row.name}？`, '提示', { type: 'warning' })
  await dictionaries.remove(row.id)
  current.value = null
  await load()
}

const addItem = () => {
  itemForm.value = { dictionary: current.value.id, value: '', label: '', parent: null, sort_order: 0, is_default: false, status: 'active' }
  itemDialog.value = true
}
const editItem = (row) => {
  itemForm.value = { ...row }
  itemDialog.value = true
}
const saveItem = async () => {
  if (itemForm.value.id) await dictItems.update(itemForm.value.id, itemForm.value)
  else await dictItems.create(itemForm.value)
  ElMessage.success('已保存')
  itemDialog.value = false
  await load()
}
const removeItem = async (row) => {
  await ElMessageBox.confirm(`确认删除字典项 ${row.label}？`, '提示', { type: 'warning' })
  await dictItems.remove(row.id)
  await load()
}

onMounted(load)
</script>
