<template>
  <div class="login">
    <el-card class="login__card">
      <h3 style="margin-top: 0">BaseMgt 业务底座</h3>
      <el-form @keyup.enter="submit">
        <el-form-item label="用户名"><el-input v-model="form.username" autofocus /></el-form-item>
        <el-form-item label="口令"><el-input v-model="form.password" type="password" /></el-form-item>
      </el-form>
      <el-button type="primary" style="width: 100%" :loading="loading" @click="submit">登录</el-button>
      <div class="bm-muted" style="margin-top: 12px; font-size: 12px">
        未开启鉴权（BM_AUTH_DISABLED=1）时无需登录。
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useUserStore } from '../store/user'

const store = useUserStore()
const form = ref({ username: '', password: '' })
const loading = ref(false)

const submit = async () => {
  loading.value = true
  try {
    await store.login(form.value.username, form.value.password)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login__card {
  width: 360px;
}
</style>
