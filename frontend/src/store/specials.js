/**
 * 全局共享的"启用中的专项"列表，给左侧子菜单和路由用。
 * 登录后由 App.vue 触发一次拉取，admin 新增/编辑专项后再次拉取。
 */
import { reactive } from 'vue'
import { specialApi } from '../api'

const state = reactive({
  list: [],
  loaded: false,
})

export const specials = state

export async function reloadSpecials() {
  try {
    const { data } = await specialApi.list(false)
    state.list = data
    state.loaded = true
  } catch {
    // 静默：未登录或后端不可用时不阻塞 UI
    state.list = []
    state.loaded = true
  }
}

export function clearSpecials() {
  state.list = []
  state.loaded = false
}
