<template>
  <Layout>
    <div class="bm-page">
      <div class="bm-card">
        <div class="bm-toolbar">
          <strong>存储过程</strong>
          <el-select v-model="filterDs" clearable placeholder="数据源" style="width: 180px" @change="load">
            <el-option v-for="d in dsList" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
          <el-input v-model="keyword" placeholder="名称搜索" style="width: 180px" clearable @keyup.enter="load" />
          <el-button size="small" @click="load">查询</el-button>
          <el-button type="primary" size="small" @click="openCreate">新建</el-button>
        </div>
        <el-table :data="list" size="small">
          <el-table-column prop="qualified" label="名称" min-width="220" />
          <el-table-column prop="kind" label="类型" width="100" />
          <el-table-column prop="signature" label="参数" min-width="200" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'deployed' ? 'success' : 'info'">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="版本" width="80">
            <template #default="{ row }">v{{ row.latest_version }}</template>
          </el-table-column>
          <el-table-column label="操作" width="260">
            <template #default="{ row }">
              <el-button link type="primary" @click="openEditor(row)">编辑</el-button>
              <el-button link type="danger" @click="drop(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <el-drawer v-model="editorVisible" :title="current.name ? `${current.schema}.${current.name}` : '新建存储过程'" size="60%">
        <el-form :model="current" label-width="90px" size="small">
          <el-row :gutter="8">
            <el-col :span="8"><el-form-item label="数据源">
              <el-select v-model="current.data_source" style="width: 100%">
                <el-option v-for="d in dsList" :key="d.id" :label="d.name" :value="d.id" />
              </el-select>
            </el-form-item></el-col>
            <el-col :span="6"><el-form-item label="Schema"><el-input v-model="current.schema" /></el-form-item></el-col>
            <el-col :span="10"><el-form-item label="名称"><el-input v-model="current.name" /></el-form-item></el-col>
          </el-row>
          <el-form-item label="类型">
            <el-radio-group v-model="current.kind">
              <el-radio-button label="procedure">PROCEDURE</el-radio-button>
              <el-radio-button label="function">FUNCTION</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="DDL">
            <el-input v-model="ddl" type="textarea" :rows="16" class="bm-mono" />
          </el-form-item>
          <el-form-item label="变更说明"><el-input v-model="changeNote" /></el-form-item>
          <el-form-item label="参数">
            <el-input v-model="argsText" placeholder='调用参数，JSON 数组，如 [1, "abc"]' />
          </el-form-item>
        </el-form>
        <div class="bm-toolbar">
          <el-button type="primary" size="small" @click="saveVersion">保存新版本</el-button>
          <el-button type="success" size="small" @click="apply">下发到库</el-button>
          <el-button size="small" @click="pull">从库拉取</el-button>
          <el-button size="small" @click="callProc">调用测试</el-button>
        </div>
        <el-divider content-position="left">版本历史</el-divider>
        <el-table :data="versions" size="small" max-height="240">
          <el-table-column prop="version" label="版本" width="70" />
          <el-table-column prop="change_note" label="说明" />
          <el-table-column prop="status" label="状态" width="90" />
          <el-table-column prop="created_at" label="时间" width="170" />
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button link type="primary" @click="applyVersion(row)">下发</el-button>
              <el-button link @click="viewDdl(row)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-divider content-position="left">调用结果</el-divider>
        <pre class="bm-mono">{{ callResult }}</pre>
      </el-drawer>
    </div>
  </Layout>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Layout from '../layout/Layout.vue'
import { api, dataSources, procedures } from '../api'

const list = ref([])
const dsList = ref([])
const filterDs = ref(null)
const keyword = ref('')
const editorVisible = ref(false)
const current = ref({ schema: 'public', kind: 'procedure' })
const ddl = ref('')
const changeNote = ref('')
const argsText = ref('[]')
const versions = ref([])
const callResult = ref('')

const load = async () => {
  const params = {}
  if (filterDs.value) params.data_source = filterDs.value
  if (keyword.value) params.keyword = keyword.value
  const data = await procedures.list(params)
  list.value = data.map((p) => ({ ...p, qualified: `${p.schema}.${p.name}` }))
}

const openCreate = () => {
  current.value = { schema: 'public', kind: 'procedure', data_source: dsList.value[0]?.id }
  ddl.value = `-- 示例
CREATE OR REPLACE PROCEDURE public.xxx(IN p_id integer)
LANGUAGE plpgsql AS $$
BEGIN
  -- TODO
END;
$$;`
  versions.value = []
  editorVisible.value = true
}

const openEditor = async (row) => {
  current.value = { ...row }
  ddl.value = row.current_ddl || ''
  editorVisible.value = true
  versions.value = await api.procVersions(row.id)
}

const saveVersion = async () => {
  if (!current.value.id) {
    const created = await procedures.create({
      data_source: current.value.data_source,
      schema: current.value.schema,
      name: current.value.name,
      kind: current.value.kind
    })
    current.value = { ...current.value, id: created.id }
  }
  await api.procSaveVersion(current.value.id, { ddl: ddl.value, change_note: changeNote.value })
  ElMessage.success('已保存新版本')
  versions.value = await api.procVersions(current.value.id)
  load()
}

const apply = async () => {
  await saveVersion()
  const latest = versions.value[0]
  if (latest) await api.procApply(current.value.id, latest.id)
  ElMessage.success('已下发')
  load()
}

const applyVersion = async (ver) => {
  await api.procApply(current.value.id, ver.id)
  ElMessage.success(`v${ver.version} 已下发`)
  load()
}

const viewDdl = (ver) => {
  ddl.value = ver.ddl
}

const pull = async () => {
  const ver = await api.procPull(current.value.id)
  ddl.value = ver.ddl
  ElMessage.success('已拉取最新定义')
}

const callProc = async () => {
  let args = []
  try {
    args = JSON.parse(argsText.value || '[]')
  } catch {
    ElMessage.error('参数需为合法 JSON 数组')
    return
  }
  const res = await api.procCall(current.value.id, args)
  callResult.value = JSON.stringify(res, null, 2)
}

const drop = async (row) => {
  await ElMessageBox.confirm(`确认在数据库中删除 ${row.schema}.${row.name}？`, '提示', { type: 'warning' })
  await api.procDrop(row.id)
  load()
}

onMounted(async () => {
  dsList.value = await dataSources.list()
  await load()
})
</script>
