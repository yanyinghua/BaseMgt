<template>
  <el-container class="bm-shell">
    <el-aside width="200px" class="bm-aside">
      <div class="bm-logo">BaseMgt<span>业务底座</span></div>
      <el-menu :default-active="active" router>
        <el-menu-item v-for="m in menus" :key="m.path" :index="m.path">
          <span>{{ m.title }}</span>
        </el-menu-item>
        <el-sub-menu v-for="g in modulePages" :key="g.module.key" :index="`m-${g.module.id}`">
          <template #title><span>{{ g.module.name }}</span></template>
          <el-menu-item v-for="p in g.pages" :key="p.key" :index="`/p/${p.key}`">{{ p.name }}</el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="bm-header">
        <strong>{{ currentTitle }}</strong>
        <span style="margin-left: auto; display: flex; align-items: center; gap: 8px">
          <el-tag v-if="user.devMode" size="small" type="warning">未鉴权(开发模式)</el-tag>
          <span class="bm-muted">{{ user.me?.username }}</span>
          <el-button link size="small" @click="onLogout">退出</el-button>
        </span>
      </el-header>
      <el-main class="bm-main">
        <slot />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { modules, pages } from '../api'
import { useUserStore } from '../store/user'

const route = useRoute()
const user = useUserStore()
const modulePages = ref([])

const allMenus = [
  { path: '/', title: '总览' },
  { path: '/modules', title: '业务模块' },
  { path: '/mdm', title: '企业主数据' },
  { path: '/dict', title: '数据字典' },
  { path: '/datasources', title: '数据源' },
  { path: '/procedures', title: '存储过程' },
  { path: '/definitions', title: '编排定义' },
  { path: '/runs', title: '运行记录' },
  { path: '/tasks', title: '人工任务' },
  { path: '/pages', title: '页面编排' },
  { path: '/iam', title: '权限管理', admin: true }
]

const menus = computed(() => allMenus.filter((m) => !m.admin || user.isAdmin))
const active = computed(() => route.path)
const currentTitle = computed(() => route.meta?.title || '')

const onLogout = async () => {
  await user.logout()
  location.reload()
}

onMounted(async () => {
  try {
    const [mods, pubPages] = await Promise.all([modules.list(), pages.list({ status: 'published' })])
    modulePages.value = mods
      .map((m) => ({ module: m, pages: pubPages.filter((p) => p.module === m.id) }))
      .filter((g) => g.pages.length)
  } catch {
    modulePages.value = []
  }
})
</script>

<style scoped>
.bm-shell {
  height: 100%;
}
.bm-aside {
  background: #fff;
  border-right: 1px solid var(--bm-border);
  overflow: auto;
}
.bm-logo {
  padding: 16px;
  font-size: 18px;
  font-weight: 700;
  border-bottom: 1px solid var(--bm-border);
}
.bm-logo span {
  display: block;
  font-size: 12px;
  font-weight: 400;
  color: #909399;
}
.bm-header {
  display: flex;
  align-items: center;
  background: #fff;
  border-bottom: 1px solid var(--bm-border);
}
.bm-main {
  padding: 0;
  overflow: auto;
}
</style>
