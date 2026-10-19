<template>
  <Layout>
    <div class="bm-page">
      <div class="bm-card">
        <div class="bm-toolbar">
          <strong>业务模块</strong>
          <el-button type="primary" size="small" @click="openCreate">新增模块</el-button>
        </div>
        <el-table :data="list" size="small" row-key="id">
          <el-table-column prop="key" label="标识" width="180" />
          <el-table-column prop="name" label="名称" width="200" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="说明" />
          <el-table-column label="操作" width="140">
            <template #default="{ row }">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" @click="remove(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-dialog v-model="visible" :title="form.id ? '编辑模块' : '新增模块'" width="480">
        <el-form :model="form" label-width="80px">
          <el-form-item label="标识"><el-input v-model="form.key" placeholder="如 finance" /></el-form-item>
          <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="上级"><el-input v-model="form.parent" type="number" placeholder="可留空" /></el-form-item>
          <el-form-item label="图标"><el-input v-model="form.icon" /></el-form-item>
          <el-form-item label="排序"><el-input v-model="form.sort_order" type="number" /></el-form-item>
          <el-form-item label="状态">
            <el-select v-model="form.status"><el-option label="启用" value="active" /><el-option label="停用" value="disabled" /></el-select>
          </el-form-item>
          <el-form-item label="说明"><el-input v-model="form.description" type="textarea" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="visible = false">取消</el-button>
          <el-button type="primary" @click="save">保存</el-button>
        </template>
      </el-dialog>
    </div>
  </Layout>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Layout from '../layout/Layout.vue'
import { modules } from '../api'

const list = ref([])
const visible = ref(false)
const form = ref({})

const load = async () => (list.value = await modules.list())
const openCreate = () => {
  form.value = { status: 'active', sort_order: 0 }
  visible.value = true
}
const openEdit = (row) => {
  form.value = { ...row }
  visible.value = true
}
const save = async () => {
  if (form.value.id) await modules.update(form.value.id, form.value)
  else await modules.create(form.value)
  ElMessage.success('已保存')
  visible.value = false
  load()
}
const remove = async (row) => {
  await ElMessageBox.confirm(`确认删除模块 ${row.name}？`, '提示', { type: 'warning' })
  await modules.remove(row.id)
  load()
}
onMounted(load)
</script>
