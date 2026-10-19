<template>
  <Login v-if="store.loaded && !store.authenticated" />
  <router-view v-else-if="store.loaded" />
</template>

<script setup>
import { onMounted } from 'vue'
import Login from './views/Login.vue'
import { useUserStore } from './store/user'

const store = useUserStore()

onMounted(async () => {
  try {
    await store.load()
  } catch {
    store.loaded = true
  }
})
</script>
