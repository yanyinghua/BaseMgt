import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({ baseURL: '/api', timeout: 60000 })

http.interceptors.response.use(
  (res) => {
    const body = res.data
    if (body && typeof body === 'object' && 'code' in body) {
      if (body.code === 0) return body.data
      ElMessage.error(body.message || '请求失败')
      return Promise.reject(new Error(body.message || '请求失败'))
    }
    return body
  },
  (err) => {
    ElMessage.error(err?.response?.data?.message || err.message || '网络异常')
    return Promise.reject(err)
  }
)

const rest = (path) => ({
  list: (params) => http.get(path, { params }),
  get: (id) => http.get(`${path}/${id}/`),
  create: (data) => http.post(`${path}/`, data),
  update: (id, data) => http.patch(`${path}/${id}/`, data),
  remove: (id) => http.delete(`${path}/${id}/`)
})

export const modules = rest('/modules')
export const pages = rest('/pages')
export const definitions = rest('/definitions')
export const runs = rest('/runs')
export const humanTasks = rest('/human-tasks')
export const procedures = rest('/procedures')
export const dataSources = rest('/datasources')
export const mdmEntities = rest('/mdm/entities')
export const mdmFields = rest('/mdm/fields')
export const dictionaries = rest('/mdm/dictionaries')
export const dictItems = rest('/mdm/dict-items')

const qs = (params = {}) => {
  const usp = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') usp.append(k, v)
  })
  const s = usp.toString()
  return s ? `?${s}` : ''
}

export const roles = rest('/roles')
export const userRoles = rest('/user-roles')
export const grants = rest('/grants')
export const dataScopes = rest('/data-scopes')

export const api = {
  nodeTypes: () => http.get('/node-types'),

  // 登录与权限
  me: () => http.get('/me'),
  login: (username, password) => http.post('/auth/login', { username, password }),
  logout: () => http.post('/auth/logout'),
  users: () => http.get('/users'),
  setPassword: (userId, password) => http.post('/auth/set-password', { user_id: userId, password }),
  grantResourceTypes: () => http.get('/grants/resource_types/'),
  initRoles: () => http.post('/roles/init_builtin/'),

  // 轮询等待运行结束
  async waitRun(runId, { timeout = 120000, interval = 1000 } = {}) {
    const started = Date.now()
    while (Date.now() - started < timeout) {
      const run = await runs.get(runId)
      if (!['pending', 'running'].includes(run.status)) return run
      await new Promise((r) => setTimeout(r, interval))
    }
    return runs.get(runId)
  },

  // 数据源
  testDataSource: (data) => http.post('/datasources/test/', data),
  dsSchemas: (id) => http.get(`/datasources/${id}/schemas/`),
  dsTables: (id, schema) => http.get(`/datasources/${id}/tables/`, { params: { schema } }),
  dsColumns: (id, schema, table) => http.get(`/datasources/${id}/columns/`, { params: { schema, table } }),
  dsSql: (id, data) => http.post(`/datasources/${id}/sql/`, data),
  dsSyncProcedures: (id, schemas) => http.post(`/datasources/${id}/sync_procedures/`, { schemas }),

  // 存储过程
  procVersions: (id) => http.get(`/procedures/${id}/versions/`),
  procSaveVersion: (id, data) => http.post(`/procedures/${id}/versions/`, data),
  procApply: (id, versionId) => http.post(`/procedures/${id}/versions/${versionId}/apply/`),
  procPull: (id) => http.post(`/procedures/${id}/pull/`),
  procCall: (id, args) => http.post(`/procedures/${id}/call/`, { args }),
  procDrop: (id) => http.post(`/procedures/${id}/drop/`),

  // 编排
  publishDefinition: (id) => http.post(`/definitions/${id}/publish/`),
  unpublishDefinition: (id) => http.post(`/definitions/${id}/unpublish/`),
  cloneDefinition: (id) => http.post(`/definitions/${id}/clone/`),
  runDefinition: (id, payload) => http.post(`/definitions/${id}/run/`, payload),
  validateDefinition: (id) => http.post(`/definitions/${id}/validate/`),
  definitionRuns: (id, limit = 20) => http.get(`/definitions/${id}/runs/`, { params: { limit } }),

  // 运行
  retryRun: (id) => http.post(`/runs/${id}/retry/`),
  cancelRun: (id) => http.post(`/runs/${id}/cancel/`),

  // 人工任务
  completeTask: (id, data) => http.post(`/human-tasks/${id}/complete/`, data),

  // 页面
  pageData: (id, data) => http.post(`/pages/${id}/data/`, data),

  // 主数据
  mdmPreview: (id) => http.get(`/mdm/entities/${id}/preview/`),
  mdmSync: (id) => http.post(`/mdm/entities/${id}/sync/`),
  mdmProcedures: (id) => http.post(`/mdm/entities/${id}/procedures/`),
  mdmGenerate: (id, include) => http.post(`/mdm/entities/${id}/generate/`, { include }),
  mdmBootstrap: (id) => http.post(`/mdm/entities/${id}/bootstrap/`, {}),
  mdmRows: (id, params) => http.get(`/mdm/entities/${id}/rows/`, { params }),
  mdmChanges: (id, params) => http.get(`/mdm/entities/${id}/changes/`, { params }),
  mdmTree: (id) => http.get(`/mdm/entities/${id}/tree/`),
  mdmExportUrl: (id, params = {}) => `/api/mdm/entities/${id}/export/${qs(params)}`,
  mdmTemplateUrl: (id) => `/api/mdm/entities/${id}/template/`,
  mdmImport: (id, file, operator = '') => {
    const form = new FormData()
    form.append('file', file)
    if (operator) form.append('operator', operator)
    return http.post(`/mdm/entities/${id}/import/`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000
    })
  },
  mdmDictOptions: (id) => http.get(`/mdm/dictionaries/${id}/options/`),
  mdmEntityFields: (id) => http.get(`/mdm/entities/${id}/fields/`),
  mdmLogs: (id) => http.get(`/mdm/entities/${id}/logs/`),

  // 对外接口（已发布的服务编排）
  openTrigger: (key, payload) => http.post(`/x/${key}`, payload)
}

export default http
