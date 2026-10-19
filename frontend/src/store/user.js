import { defineStore } from 'pinia'
import { api } from '../api'

export const useUserStore = defineStore('user', {
  state: () => ({ me: null, loaded: false }),
  getters: {
    authenticated: (s) => !!s.me?.authenticated,
    isAdmin: (s) => !!s.me?.is_superuser || (s.me?.roles || []).includes('admin'),
    devMode: (s) => !!s.me?.dev_mode
  },
  actions: {
    async load() {
      this.me = await api.me()
      this.loaded = true
      return this.me
    },
    async login(username, password) {
      this.me = await api.login(username, password)
      await this.load()
      return this.me
    },
    async logout() {
      await api.logout()
      this.me = null
    }
  }
})
