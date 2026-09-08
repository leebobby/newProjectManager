/**
 * 全局共享的 WBS 列表，给左侧二级菜单用（同 store/specials.js）。
 * 登录后由 App.vue 拉一次；新建 / 改名 / 删除之后再拉一次。
 */
import { reactive } from 'vue'
import { wbsApi } from '../api'

const state = reactive({
  list: [],
  loaded: false,
})

export const wbs = state

export async function reloadWbs() {
  try {
    const { data } = await wbsApi.listPlans()
    state.list = data
    state.loaded = true
  } catch {
    // 静默：未登录或后端不可用时不阻塞 UI
    state.list = []
    state.loaded = true
  }
}

export function clearWbs() {
  state.list = []
  state.loaded = false
}
