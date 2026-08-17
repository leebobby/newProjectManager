import { computed, reactive } from 'vue'

const TOKEN_KEY = 'apm_token'
const USER_KEY = 'apm_user'
// 跨 tab 同步用：写到 localStorage 的变化会触发其它 tab 的 storage 事件
const LOGOUT_SIGNAL_KEY = 'apm_logout_signal'

const state = reactive({
  token: localStorage.getItem(TOKEN_KEY) || '',
  user: JSON.parse(localStorage.getItem(USER_KEY) || 'null'),
})

export const auth = {
  state,
  isLoggedIn: computed(() => !!state.token),
  isAdmin: computed(() => state.user?.role === 'admin'),

  setSession(token, user) {
    state.token = token
    state.user = user
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  },

  setUser(user) {
    state.user = user
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  },

  clear() {
    state.token = ''
    state.user = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  },

  // 主动登出：广播给其它 tab
  signalLogout(reason = 'manual') {
    this.clear()
    try {
      localStorage.setItem(LOGOUT_SIGNAL_KEY, `${reason}:${Date.now()}`)
    } catch {
      // 配额或隐私模式异常忽略
    }
  },
}

/**
 * 在应用入口初始化一次：
 * 1) 监听 storage 事件，其它 tab 退出时本 tab 也清掉会话
 * 2) 同 tab 内手动调用 auth.signalLogout() 也会同步给其它 tab
 *
 * @param {() => void} onLogout 触发本 tab 跳转登录页的回调
 */
export function installCrossTabAuth(onLogout) {
  window.addEventListener('storage', (e) => {
    if (e.key === LOGOUT_SIGNAL_KEY && e.newValue) {
      // 其它 tab 退出了：清本 tab 会话并跳转
      if (state.token) auth.clear()
      onLogout && onLogout('cross-tab')
      return
    }
    // token 被其它 tab 直接清掉的兜底（清缓存、手动改 localStorage 等）
    if (e.key === TOKEN_KEY && !e.newValue && state.token) {
      auth.clear()
      onLogout && onLogout('token-cleared')
    }
  })
}
