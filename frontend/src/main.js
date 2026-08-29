import { createApp } from 'vue'
import ElementPlus, { ElMessage } from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'

const app = createApp(App)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(ElementPlus)
app.use(router)

// 组件 setup/render 里抛异常时，Vue 默认只往控制台写一行，页面上是**一片空白**，
// 而且之后点别的菜单也不再渲染——现象是「进了某个页面之后整个系统就没反应了，
// 刷新一下又好」，看着完全不像是那个页面的错。少写一个 import 就够触发
// （VersionManagement 漏 import computed 就是这么来的）。
// 这里兜一层：控制台留完整堆栈，页面弹一条能照着报的提示，别让它静默白屏。
app.config.errorHandler = (err, _instance, info) => {
  console.error(`[Vue] ${info}`, err)
  // grouping：同一条错误往往连着触发好几次，不合并会糊满整屏
  ElMessage({ type: 'error', message: `页面出错：${err?.message || err}（${info}）`,
              grouping: true, duration: 6000 })
}
// 没人 catch 的 Promise 同理：默认连控制台那一行都容易被忽略
window.addEventListener('unhandledrejection', (e) => {
  console.error('[unhandledrejection]', e.reason)
})

app.mount('#app')
