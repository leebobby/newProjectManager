// 只开「能抓到真 bug」的规则，不做代码风格治理。
//
// 起因：VersionManagement.vue 用了 computed 却没 import，`vite build` 一路绿灯
// （Vite 不做 no-undef 检查），上线后该页 setup 抛 ReferenceError → 整页白屏，
// 而且此后 router-view 不再渲染任何页面，只有整页刷新能恢复。
// 一条 no-undef 就能在提交前拦住，所以这份配置的重点只有它。
//
// **不要顺手加风格类规则**（引号、分号、缩进、组件命名…）：23k 行存量代码
// 一次性冒出几百条 warning，之后就没人看 lint 输出了，等于把这道闸门关掉。
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'

export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  ...pluginVue.configs['flat/essential'],
  {
    files: ['**/*.{js,vue}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.browser },
    },
    rules: {
      // 漏 import / 拼错变量名 —— 这类错误运行时才炸，而且往往炸得很远
      'no-undef': 'error',
      // 用不到的 import 留着不致命，但常常是「改了一半」的痕迹，给个提示
      'no-unused-vars': ['warn', { args: 'none', caughtErrors: 'none' }],
      // 组件名必须多个词：是命名约定不是 bug，而它会让 lint 整体变红，
      // 红了几次之后这道闸门就没人看了。Login.vue 这种名字本身没问题。
      'vue/multi-word-component-names': 'off',
    },
  },
]
