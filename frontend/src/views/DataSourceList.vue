<template>
  <Layout>
    <div class="bm-page">
      <div class="bm-card">
        <div class="bm-toolbar">
          <strong>数据源</strong>
          <el-button type="primary" size="small" @click="openCreate">新增</el-button>
        </div>
        <el-table :data="list" size="small">
          <el-table-column prop="key" label="标识" width="140" />
          <el-table-column prop="name" label="名称" width="160" />
          <el-table-column prop="engine" label="类型" width="100" />
          <el-table-column label="连接" min-width="240">
            <template #default="{ row }">
              <span class="bm-mono">{{ row.host }}:{{ row.port }}/{{ row.database }}</span>
            </template>
          </el-table-column>
          <el-table-column label="默认" width="80">
            <template #default="{ row }"><el-tag v-if="row.is_default" size="small">默认</el-tag></template>
          </el-table-column>
          <el-table-column label="操作" width="320">
            <template #default="{ row }">
              <el-button link type="primary" @click="testConn(row)">测试</el-button>
              <el-button link type="primary" @click="openSql(row)">SQL</el-button>
              <el-button link type="primary" @click="syncProc(row)">同步存储过程</el-button>
              <el-button link @click="openEdit(row)">编辑</el-button>
              <el-button link type="danger" @click="remove(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-dialog v-model="visible" :title="form.id ? '编辑数据源' : '新增数据源'" width="560">
        <el-form :model="form" label-width="100px">
          <el-form-item label="标识"><el-input v-model="form.key" /></el-form-item>
          <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
          <el-form-item label="类型">
            <el-select v-model="form.engine">
              <el-option label="PostgreSQL" value="postgres" />
              <el-option label="MySQL" value="mysql" />
            </el-select>
          </el-form-item>
          <el-row :gutter="8">
            <el-col :span="16"><el-form-item label="主机"><el-input v-model="form.host" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="端口"><el-input v-model.number="form.port" type="number" /></el-form-item></el-col>
          </el-row>
          <el-form-item label="库名"><el-input v-model="form.database" /></el-form-item>
          <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
          <el-form-item label="口令"><el-input v-model="form.password" type="password" placeholder="留空表示不修改" /></el-form-item>
          <el-form-item label="默认数据源"><el-switch v-model="form.is_default" /></el-form-item>
          <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="visible = false">取消</el-button>
          <el-button @click="testConn(form)">测试连接</el-button>
          <el-button type="primary" @click="save">保存</el-button>
        </template>
      </el-dialog>

      <el-drawer v-model="sqlVisible" title="SQL 控制台" size="55%">
        <el-input v-model="sql" type="textarea" :rows="8" class="bm-mono" placeholder="select * from xxx limit 10" />
        <div class="bm-toolbar" style="margin-top: 8px">
          <el-button type="primary" size="small" @click="execSql">执行</el-button>
          <span class="bm-muted">{{ sqlResult.cost_ms ? `耗时 ${sqlResult.cost_ms}ms` : '' }}</span>
        </div>
        <el-table :data="sqlResult.rows || []" size="small" max-height="420">
          <el-table-column v-for="col in sqlColumns" :key="col" :prop="col" :label="col" show-overflow-tooltip />
        </el-table>
      </el-drawer>
    </div>
  </Layout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Layout from '../layout/Layout.vue'
import { api, dataSources } from '../api'

const list = ref([])
const visible = ref(false)
const form = ref({})
const sqlVisible = ref(false)
const sql = ref('')
const sqlResult = ref({ rows: [] })
const currentDs = ref(null)

const sqlColumns = computed(() => Object.keys((sqlResult.value.rows || [])[0] || {}))

const load = async () => (list.value = await dataSources.list())
const openCreate = () => {
  form.value = { engine: 'postgres', host: '127.0.0.1', port: 5432, is_default: false }
  visible.value = true
}
const openEdit = (row) => {
  form.value = { ...row, password: '' }
  visible.value = true
}
const save = async () => {
  if (form.value.id) await dataSources.update(form.value.id, form.value)
  else await dataSources.create(form.value)
  ElMessage.success('已保存')
  visible.value = false
  load()
}
const remove = async (row) => {
  await ElMessageBox.confirm(`确认删除数据源 ${row.name}？`, '提示', { type: 'warning' })
  await dataSources.remove(row.id)
  load()
}
const testConn = async (row) => {
  const res = await api.testDataSource(row)
  ElMessage.success(`连接成功：${res.version}`)
}
const openSql = (row) => {
  currentDs.value = row
  sqlVisible.value = true
}
const execSql = async () => {
  sqlResult.value = await api.dsSql(currentDs.value.id, { sql: sql.value })
}
const syncProc = async (row) => {
  const res = await api.dsSyncProcedures(row.id, null)
  ElMessage.success(`同步完成：新增 ${res.created}，更新 ${res.updated}`)
}
onMounted(load)
</script>
