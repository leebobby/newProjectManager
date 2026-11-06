import fs from 'node:fs/promises'
import { expect, test } from '@playwright/test'

test('A 图完整展示超过 150 项任务，层级与缩放不裁掉页面或导出内容', async ({ page }, testInfo) => {
  test.setTimeout(180000)
  page.setDefaultTimeout(10000)
  const login = await page.request.post('/api/auth/login', { data: { username: 'admin', password: 'admin123' } })
  expect(login.ok()).toBeTruthy()
  const headers = { Authorization: `Bearer ${(await login.json()).access_token}` }
  const post = async (path, data) => {
    const response = await page.request.post('/api' + path, { headers, data })
    expect(response.ok(), await response.text()).toBeTruthy()
    return response.json()
  }
  const special = await post('/specials', { name: `完整A图-${Date.now()}` })
  let plan
  try {
    plan = await post('/wbs/plans', { name: 'A 图完整内容验证', kind: 'special', special_id: special.id })
    const finalName = '最后一个工作包的完整内容' + '长名称验证'.repeat(25)
    for (let stage = 1; stage <= 2; stage++) {
      const root = await post(`/wbs/plans/${plan.id}/items`, { name: `阶段 ${stage}` })
      const parentId = root.items.find(row => row.name === `阶段 ${stage}`).id
      for (let index = 1; index <= 80; index++) {
        await post(`/wbs/plans/${plan.id}/items`, {
          name: stage === 2 && index === 80 ? finalName : `阶段 ${stage} 任务 ${index}`,
          parent_id: parentId, man_days: 1, planned_start: '2026-11-01', planned_end: '2026-12-01',
        })
      }
    }
    const response = await page.request.get(`/api/wbs/plans/${plan.id}/timeline`, { headers })
    const spec = await response.json()
    expect(spec.row_count).toBe(162)
    expect(spec.skipped).toBe(0)
    await page.goto('/login')
    await page.getByPlaceholder('用户名').fill('admin')
    await page.getByPlaceholder('密码').fill('admin123')
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page.locator('.el-main')).toBeVisible()
    await page.goto(`/wbs/${plan.id}`)
    await page.getByRole('button', { name: '预览 A 图', exact: true }).click()
    const chart = page.locator('.wt-wrap')
    const tasks = chart.locator('.wt-task-box')
    await expect(tasks).toHaveCount(162)
    await expect(chart.locator('.wt-count')).toContainText('162 项任务')
    await expect(tasks.last()).toContainText(finalName)
    await expect(tasks.last().locator('text').first()).toHaveText('2.80 ' + finalName)
    const viewport = chart.getByRole('region', { name: 'A 图完整内容' })
    expect(await viewport.evaluate(el => el.scrollHeight > el.clientHeight)).toBeTruthy()
    expect(await viewport.evaluate(el => el.scrollWidth > el.clientWidth)).toBeTruthy()
    await viewport.evaluate(el => el.scrollTo(el.scrollWidth, el.scrollHeight))
    await expect(tasks.last()).toBeInViewport()
    await chart.getByRole('button', { name: '适应宽度', exact: true }).click()
    await expect.poll(() => viewport.evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1)
    const previewWidth = +(await chart.locator('.wt-svg').getAttribute('width'))
    expect(previewWidth).toBeLessThan(spec.width)
    for (const kind of ['SVG', 'PNG']) {
      const downloading = page.waitForEvent('download')
      await chart.getByRole('button', { name: `导出 ${kind}`, exact: true }).click()
      const download = await downloading
      const file = testInfo.outputPath(`complete.${kind.toLowerCase()}`)
      await download.saveAs(file)
      expect(await download.failure()).toBeNull()
      const bytes = await fs.readFile(file)
      if (kind === 'SVG') {
        expect(bytes.toString()).toContain(finalName)
        const exported = await page.evaluate(xml => {
          const svg = new DOMParser().parseFromString(xml, 'image/svg+xml').documentElement
          return { width: +svg.getAttribute('width'), height: +svg.getAttribute('height'),
            count: svg.querySelectorAll('.wt-task-box').length }
        }, bytes.toString())
        expect(exported).toEqual({ width: spec.width, height: spec.height, count: 162 })
      } else {
        const scale = Math.min(2, 16384 / Math.max(spec.width, spec.height), Math.sqrt(24000000 / (spec.width * spec.height)))
        expect(bytes.readUInt32BE(16)).toBe(Math.floor(spec.width * scale))
        expect(bytes.readUInt32BE(20)).toBe(Math.floor(spec.height * scale))
      }
    }
    const depth = chart.locator('.el-select').filter({ has: page.getByRole('combobox', { name: 'A 图展示层级' }) })
    await depth.click()
    await page.getByRole('option', { name: '展示到第 1 层', exact: true }).click()
    await expect(tasks).toHaveCount(2)
    await expect(chart.locator('.wt-note')).toContainText('另有 160 行')
    await depth.click()
    await page.getByRole('option', { name: '展示全部层级', exact: true }).click()
    await expect(tasks).toHaveCount(162)
    await chart.getByRole('button', { name: '原始大小', exact: true }).click()
    await expect(chart.locator('.wt-svg')).toHaveAttribute('width', String(spec.width))
    await chart.screenshot({ path: testInfo.outputPath('complete-preview.png') })
  } finally {
    if (plan) await page.request.delete(`/api/wbs/plans/${plan.id}`, { headers })
    await page.request.delete(`/api/specials/${special.id}`, { headers })
  }
})
