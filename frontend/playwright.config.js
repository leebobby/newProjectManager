// 冒烟测试的运行配置：自己把后端和前端拉起来，跑完再关掉。
//
// 为什么要有这一层：CI 里的 `vite build` 只证明「包能打出来」，证明不了「打出来的
// 包点得开」。VersionManagement.vue 漏 import 那次，build 是绿的、后端 197 个测试
// 也是绿的，而线上那一页白屏、并且进过之后整个前端都不再渲染。
import fs from 'node:fs'
import { defineConfig, devices } from '@playwright/test'

// 后端解释器：开发容器用 .venv，部署指南建的是 venv，CI 里直接就是 python。
// 猜一遍比要求每个人配环境变量省事，猜不中时最后那个 'python' 也能在 CI 上跑通。
const BACKEND_PY = [
  '.venv/bin/python',
  'venv/bin/python',
  'venv/Scripts/python.exe',
].find((p) => fs.existsSync(`../backend/${p}`)) || 'python'

export default defineConfig({
  testDir: './tests',
  // 冒烟用例之间会互相抢同一个后端（同一个 admin、同一份 app.db），串行跑
  workers: 1,
  // 失败重跑一次：这里断言的是"页面渲染出来了"，偶发的慢启动不该变成红灯；
  // 真坏了的话重跑一次照样红
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `${BACKEND_PY} -m uvicorn main:app --port 8000`,
      cwd: '../backend',
      url: 'http://127.0.0.1:8000/docs',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: 'npm run dev -- --port 5173',
      url: 'http://127.0.0.1:5173/',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
})
