import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '总览' } },
  { path: '/modules', name: 'modules', component: () => import('../views/ModuleList.vue'), meta: { title: '业务模块' } },
  { path: '/mdm', name: 'mdm', component: () => import('../views/MdmList.vue'), meta: { title: '企业主数据' } },
  { path: '/dict', name: 'dict', component: () => import('../views/DictList.vue'), meta: { title: '数据字典' } },
  { path: '/datasources', name: 'datasources', component: () => import('../views/DataSourceList.vue'), meta: { title: '数据源' } },
  { path: '/procedures', name: 'procedures', component: () => import('../views/ProcedureList.vue'), meta: { title: '存储过程' } },
  { path: '/definitions', name: 'definitions', component: () => import('../views/DefinitionList.vue'), meta: { title: '编排定义' } },
  {
    path: '/definitions/:id',
    name: 'designer',
    component: () => import('../views/DefinitionDesigner.vue'),
    meta: { title: '编排设计器', hidden: true }
  },
  { path: '/runs', name: 'runs', component: () => import('../views/RunList.vue'), meta: { title: '运行记录' } },
  { path: '/tasks', name: 'tasks', component: () => import('../views/HumanTaskList.vue'), meta: { title: '人工任务' } },
  { path: '/pages', name: 'pages', component: () => import('../views/PageList.vue'), meta: { title: '页面编排' } },
  { path: '/iam', name: 'iam', component: () => import('../views/IamAdmin.vue'), meta: { title: '权限管理', hidden: true } },
  { path: '/p/:key', name: 'page-runtime', component: () => import('../views/PageRuntime.vue'), meta: { title: '业务页面', hidden: true } }
]

export default createRouter({ history: createWebHistory(), routes })
