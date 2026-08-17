/**
 * 闲置自动登出 + 多 tab 时间共享。
 *
 * 行为：
 * - 任何 tab 上发生用户活动（鼠标移动、点击、按键、滚动、触摸）
 *   都会写入 localStorage 的 lastActiveAt，其它 tab 监听 storage 同步更新。
 * - 这样多开时，只要任意一个 tab 在使用，所有 tab 都不会被判定为闲置。
 * - 闲置超过 idleMs 阈值时调用 onIdle()（一般是登出 + 跳登录页）。
 *
 * 写入做了节流（每 5s 最多一次），避免高频 mousemove 把 localStorage 写炸。
 */

const LAST_ACTIVE_KEY = 'apm_last_active_at'
const WRITE_THROTTLE_MS = 5000

export function startIdleWatcher({ idleMs = 15 * 60 * 1000, onIdle, isActive }) {
  let lastWrite = 0
  let timerId = null

  function getLastActive() {
    const v = Number(localStorage.getItem(LAST_ACTIVE_KEY) || 0)
    return v || Date.now()
  }

  function touch() {
    if (!isActive || !isActive()) return
    const now = Date.now()
    // 内存中是 now；为了节流写 localStorage
    if (now - lastWrite > WRITE_THROTTLE_MS) {
      try {
        localStorage.setItem(LAST_ACTIVE_KEY, String(now))
      } catch {
        // ignore
      }
      lastWrite = now
    }
  }

  function check() {
    if (!isActive || !isActive()) return
    const idle = Date.now() - getLastActive()
    if (idle >= idleMs) {
      onIdle && onIdle(idle)
    }
  }

  function onStorage(e) {
    // 其它 tab 更新了活动时间——不需要做什么，因为下次 check 会读到新值。
    // 这里留作扩展点。
    if (e.key === LAST_ACTIVE_KEY) {
      // no-op
    }
  }

  const events = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart', 'click']
  events.forEach(ev => window.addEventListener(ev, touch, { passive: true }))
  window.addEventListener('storage', onStorage)

  // 初始化首个时间戳
  touch()
  timerId = setInterval(check, 30 * 1000)

  return function stop() {
    events.forEach(ev => window.removeEventListener(ev, touch))
    window.removeEventListener('storage', onStorage)
    if (timerId) clearInterval(timerId)
  }
}
