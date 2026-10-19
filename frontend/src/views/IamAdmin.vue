<template>
  <Layout>
    <div class="bm-page">
      <div class="bm-card">
        <el-tabs v-model="tab">
          <!-- 角色 -->
          <el-tab-pane label="角色" name="roles">
            <div class="bm-toolbar">
              <el-button size="small" @click="initBuiltin">初始化内置角色</el-button>
              <el-button type="primary" size="small" @click="openRole()">新增角色</el-button>
            </div>
            <el-table :data="roleList" size="small">
              <el-table-column prop="key" label="标识" width="140" />
              <el-table-column prop="name" label="名称" width="160" />
              <el-table-column prop="description" label="说明" />
              <el-table-column label="内置" width="80">
                <template #default="{ row }"><el-tag v-if="row.is_builtin" size="small">内置</el-tag></template>
              </el-table-column>
              <el-table-column label="操作" width="120">
                <template #default="{ row }">
                  <el-button link @click="openRole(row)">编辑</el-button>
                  <el-button link type="danger" @click="remove(roles, row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <!-- 用户角色 -->
          <el-tab-pane label="用户角色" name="userRoles">
            <div class="bm-toolbar">
              <el-button type="primary" size="small" @click="openUserRole()">分配角色</el-button>
            </div>
            <el-table :data="userRoleList" size="small">
              <el-table-column prop="username" label="用户" width="160" />
              <el-table-column prop="role_name" label="角色" width="180" />
              <el-table-column prop="role_key" label="标识" width="140" />
              <el-table-column label="操作" width="100">
                <template #default="{ row }">
                  <el-button link type="danger" @click="remove(userRoles, row)">移除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <!-- 对象授权 -->
          <el-tab-pane label="对象授权" name="grants">
            <div class="bm-toolbar">
              <el-select v-model="grantFilter.model" clearable placeholder="资源类型" style="width: 160px" @change="loadGrants">
                <el-option v-for="r in resourceTypes" :key="r.key" :label="r.key" :value="r.key" />
              </el-select>
              <el-button type="primary" size="small" @click="openGrant()">新增授权</el-button>
              <span class="bm-muted">编排/页面/存储过程的权限会继承自所属模块</span>
            </div>
            <el-table :data="grantList" size="small">
              <el-table-column prop="content_type_model" label="资源" width="120" />
              <el-table-column prop="target_name" label="对象" min-width="180" />
              <el-table-column label="授予给" width="160">
                <template #default="{ row }">{{ row.role_key || row.username }}</template>
              </el-table-column>
              <el-table-column label="动作" width="220">
                <template #default="{ row }">
                  <el-tag v-for="a in row.actions" :key="a" size="small" style="margin-right: 4px">{{ a }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="100">
                <template #default="{ row }">
                  <el-button link type="danger" @click="remove(grants, row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <!-- 数据范围 -->
          <el-tab-pane label="数据范围" name="scopes">
            <div class="bm-toolbar">
              <el-button type="primary" size="small" @click="openScope()">新增范围</el-button>
              <span class="bm-muted">SQL 节点填同样的「数据范围」标识后，会按角色条件自动追加 WHERE</span>
            </div>
            <el-table :data="scopeList" size="small">
              <el-table-column prop="key" label="范围标识" width="160" />
              <el-table-column prop="role_key" label="角色" width="140" />
              <el-table-column prop="filter_sql" label="过滤条件" min-width="240" />
              <el-table-column prop="description" label="说明" />
              <el-table-column label="操作" width="140">
                <template #default="{ row }">
                  <el-button link @click="openScope(row)">编辑</el-button>
                  <el-button link type="danger" @click="remove(dataScopes, row)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <!-- 用户 -->
          <el-tab-pane label="用户" name="users">
            <el-table :data="userList" size="small">
              <el-table-column prop="id" label="ID" width="60" />
              <el-table-column prop="username" label="用户名" width="160" />
              <el-table-column label="超级用户" width="90">
                <template #default="{ row }"><el-tag v-if="row.is_superuser" size="small">是</el-tag></template>
              </el-table-column>
              <el-table-column label="操作" width="160">
                <template #default="{ row }">
                  <el-button link type="primary" @click="resetPassword(row)">重置口令</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </div>

      <!-- 角色 -->
      <el-dialog v-model="roleVisible" :title="roleForm.id ? '编辑角色' : '新增角色'" width="440">
        <el-form :model="roleForm" label-width="80px">
          <el-form-item label="标识"><el-input v-model="roleForm.key" /></el-form-item>
          <el-form-item label="名称"><el-input v-model="roleForm.name" /></el-form-item>
          <el-form-item label="说明"><el-input v-model="roleForm.description" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="roleVisible = false">取消</el-button>
          <el-button type="primary" @click="saveRole">保存</el-button>
        </template>
      </el-dialog>

      <!-- 用户角色 -->
      <el-dialog v-model="urVisible" title="分配角色" width="440">
        <el-form label-width="80px">
          <el-form-item label="用户">
            <el-select v-model="urForm.user" filterable style="width: 100%">
              <el-option v-for="u in userList" :key="u.id" :label="u.username" :value="u.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="角色">
            <el-select v-model="urForm.role" style="width: 100%">
              <el-option v-for="r in roleList" :key="r.id" :label="`${r.name}(${r.key})`" :value="r.id" />
            </el-select>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="urVisible = false">取消</el-button>
          <el-button type="primary" @click="saveUserRole">保存</el-button>
        </template>
      </el-dialog>

      <!-- 授权 -->
      <el-dialog v-model="grantVisible" title="新增授权" width="480">
        <el-form :model="grantForm" label-width="90px">
          <el-form-item label="资源类型">
            <el-select v-model="grantForm.target_model" style="width: 100%">
              <el-option v-for="r in resourceTypes" :key="r.key" :label="r.key" :value="r.key" />
            </el-select>
          </el-form-item>
          <el-form-item label="对象ID"><el-input v-model.number="grantForm.object_id" type="number" /></el-form-item>
          <el-form-item label="角色">
            <el-select v-model="grantForm.role" clearable style="width: 100%">
              <el-option v-for="r in roleList" :key="r.id" :label="`${r.name}(${r.key})`" :value="r.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="用户">
            <el-select v-model="grantForm.user" clearable style="width: 100%">
              <el-option v-for="u in userList" :key="u.id" :label="u.username" :value="u.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="动作">
            <el-checkbox-group v-model="grantForm.actions">
              <el-checkbox label="read" /><el-checkbox label="write" />
              <el-checkbox label="run" /><el-checkbox label="admin" />
            </el-checkbox-group>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="grantVisible = false">取消</el-button>
          <el-button type="primary" @click="saveGrant">保存</el-button>
        </template>
      </el-dialog>

      <!-- 数据范围 -->
      <el-dialog v-model="scopeVisible" title="数据范围" width="480">
        <el-form :model="scopeForm" label-width="90px">
          <el-form-item label="范围标识"><el-input v-model="scopeForm.key" placeholder="如 sales" /></el-form-item>
          <el-form-item label="角色">
            <el-select v-model="scopeForm.role" style="width: 100%">
              <el-option v-for="r in roleList" :key="r.id" :label="`${r.name}(${r.key})`" :value="r.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="过滤条件"><el-input v-model="scopeForm.filter_sql" placeholder="dept_id = 7" /></el-form-item>
          <el-form-item label="说明"><el-input v-model="scopeForm.description" /></el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="scopeVisible = false">取消</el-button>
          <el-button type="primary" @click="saveScope">保存</el-button>
        </template>
      </el-dialog>
    </div>
  </Layout>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import Layout from '../layout/Layout.vue'
import { api, dataScopes, grants, roles, userRoles } from '../api'

const tab = ref('roles')
const roleList = ref([])
const userRoleList = ref([])
const grantList = ref([])
const scopeList = ref([])
const userList = ref([])
const resourceTypes = ref([])
const grantFilter = ref({ model: '' })

const roleVisible = ref(false)
const urVisible = ref(false)
const grantVisible = ref(false)
const scopeVisible = ref(false)
const roleForm = ref({})
const urForm = ref({})
const grantForm = ref({ actions: ['read'] })
const scopeForm = ref({})

const loadAll = async () => {
  roleList.value = await roles.list()
  userRoleList.value = await userRoles.list()
  scopeList.value = await dataScopes.list()
  userList.value = await api.users()
  await loadGrants()
}

const loadGrants = async () => {
  const params = {}
  if (grantFilter.value.model) params.model = grantFilter.value.model
  grantList.value = await grants.list(params)
}

const remove = async (resource, row) => {
  await ElMessageBox.confirm('确认删除？', '提示', { type: 'warning' })
  await resource.remove(row.id)
  ElMessage.success('已删除')
  loadAll()
}

const initBuiltin = async () => {
  await api.initRoles()
  ElMessage.success('内置角色已就绪')
  loadAll()
}

const openRole = (row) => {
  roleForm.value = row ? { ...row } : { key: '', name: '', description: '' }
  roleVisible.value = true
}
const saveRole = async () => {
  if (roleForm.value.id) await roles.update(roleForm.value.id, roleForm.value)
  else await roles.create(roleForm.value)
  roleVisible.value = false
  loadAll()
}

const openUserRole = () => {
  urForm.value = { user: null, role: null }
  urVisible.value = true
}
const saveUserRole = async () => {
  await userRoles.create(urForm.value)
  urVisible.value = false
  loadAll()
}

const openGrant = () => {
  grantForm.value = { target_model: 'module', object_id: null, role: null, user: null, actions: ['read'] }
  grantVisible.value = true
}
const saveGrant = async () => {
  await grants.create(grantForm.value)
  grantVisible.value = false
  loadAll()
}

const openScope = (row) => {
  scopeForm.value = row ? { ...row } : { key: '', role: null, filter_sql: '', description: '' }
  scopeVisible.value = true
}
const saveScope = async () => {
  if (scopeForm.value.id) await dataScopes.update(scopeForm.value.id, scopeForm.value)
  else await dataScopes.create(scopeForm.value)
  scopeVisible.value = false
  loadAll()
}

const resetPassword = async (row) => {
  const { value } = await ElMessageBox.prompt(`重置 ${row.username} 的口令`, '重置口令', { inputType: 'password' })
  await api.setPassword(row.id, value)
  ElMessage.success('已重置')
}

onMounted(async () => {
  resourceTypes.value = await api.grantResourceTypes()
  await loadAll()
})
</script>
