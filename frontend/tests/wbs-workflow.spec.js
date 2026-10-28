import fs from 'node:fs/promises'
import { expect, test } from '@playwright/test'

test('普通用户填报责任人、完成度、富文本与问题风险，并切换 A 图依赖模式', async ({ page }, testInfo) => {
  test.setTimeout(90000)
  page.setDefaultTimeout(10000)
  const login = await page.request.post('/api/auth/login', { data: { username: 'admin', password: 'admin123' } })
  const headers = { Authorization: `Bearer ${(await login.json()).access_token}` }
  const post = async (path, data) => {
    const response = await page.request.post('/api' + path, { headers, data })
    expect(response.ok(), await response.text()).toBeTruthy()
    return response.json()
  }
  const key = `wbs${Date.now()}`
  const created = []
  let plan
  try {
    const department = await post('/resource-groups', { code: key + 'd', name: '填报测试部门', kind: 'dept' })
    created.push(['/resource-groups', department.id])
    const group = await post('/resource-groups', { code: key + 'g', name: '填报测试PL组', kind: 'pl', parent_id: department.id })
    created.push(['/resource-groups', group.id])
    const user = await post('/users', { username: key, full_name: '填报回归责任人', password: 'TestWbs123!', group_id: group.id })
    created.push(['/users', user.id])
    const special = await post('/specials', { name: key })
    created.push(['/specials', special.id])
    plan = await post('/wbs/plans', { name: '填报优化验证', kind: 'special', special_id: special.id })
    created.push(['/wbs/plans', plan.id])
    for (const name of ['准备', '验证', '交付']) {
      plan = await post(`/wbs/plans/${plan.id}/items`, { name, man_days: 1, planned_start: '2026-10-01', planned_end: '2026-10-20' })
    }
    const target = plan.items[2]
    await page.goto('/login')
    await page.getByPlaceholder('用户名').fill(key)
    await page.getByPlaceholder('密码').fill('TestWbs123!')
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page.locator('.el-main')).toBeVisible()
    await page.goto('/wbs')
    await page.locator('.el-table .nm').filter({ hasText: '填报优化验证' }).click()
    await expect(page).toHaveURL(new RegExp(`/wbs/${plan.id}$`))
    const row = page.locator('.wbs-table .el-table__body tr').nth(2)
    await expect(row.getByRole('textbox', { name: '任务完成度' })).toBeVisible()
    const owner = row.locator('.el-select').filter({ has: page.getByRole('combobox', { name: '任务责任人' }) })
    await owner.click()
    await page.getByRole('combobox', { name: '任务责任人' }).nth(2).fill('填报回归')
    await page.getByRole('option', { name: '填报回归责任人', exact: true }).click()
    await expect(row).toContainText('填报测试PL组')
    await row.getByRole('textbox', { name: '任务完成度' }).fill('100')
    await row.getByRole('textbox', { name: '任务完成度' }).press('Tab')
    await expect(row.locator('.status')).toContainText('已完成')
    await row.getByRole('button', { name: '详情', exact: true }).click()
    const drawer = page.getByRole('dialog', { name: '交付', exact: true })
    await drawer.locator('[contenteditable=true]').fill('第一轮验证完成')
    await drawer.locator('[contenteditable=true]').press('ControlOrMeta+a')
    await drawer.getByTitle('加粗 (Ctrl+B)', { exact: true }).click()
    const predecessor = drawer.locator('.el-select').filter({ has: page.getByRole('combobox', { name: '前置任务' }) })
    await predecessor.click()
    await page.getByRole('option', { name: '1 准备', exact: true }).click()
    await page.getByRole('option', { name: '2 验证', exact: true }).click()
    await page.keyboard.press('Escape')
    await drawer.getByRole('button', { name: '添加问题或风险' }).click()
    await drawer.getByPlaceholder('问题或风险描述').fill('接口响应待验证')
    await drawer.getByPlaceholder('责任人', { exact: true }).fill('现场负责人')
    await drawer.getByPlaceholder('处理进展').fill('已安排复验')
    await drawer.getByRole('button', { name: '保存', exact: true }).click()
    await expect(drawer).not.toBeVisible()
    await page.reload()
    await row.getByRole('button', { name: '详情', exact: true }).click()
    await expect(drawer.locator('[contenteditable=true]')).toContainText('第一轮验证完成')
    await expect(drawer.locator('[contenteditable=true] b, [contenteditable=true] strong, [contenteditable=true] span[style*="font-weight"]'))
      .toHaveCSS('font-weight', '700')
    await expect(drawer.getByPlaceholder('问题或风险描述')).toHaveValue('接口响应待验证')
    await expect(drawer.getByPlaceholder('处理进展')).toHaveValue('已安排复验')
    const detail = await (await page.request.get(`/api/wbs/plans/${plan.id}`, { headers })).json()
    expect(detail.items.find(item => item.id === target.id).predecessors).toHaveLength(2)
    await drawer.getByRole('button', { name: '关闭', exact: true }).click()
    await page.getByRole('button', { name: '预览 A 图', exact: true }).click()
    const diagram = page.locator('.wt-wrap')
    await expect(diagram.locator('.wt-dependency')).toHaveCount(2)
    const mode = diagram.locator('.el-select').filter({ has: page.getByRole('combobox', { name: '依赖关系显示' }) })
    for (const [label, arrowCount, marker] of [['显示依赖箭头', 2, 'url(#wt-arrow)'], ['仅显示依赖连线', 2, null], ['隐藏依赖关系', 0, null]]) {
      await mode.click()
      await page.getByRole('option', { name: label, exact: true }).click()
      await expect(diagram.locator('.wt-dependency')).toHaveCount(arrowCount)
      if (arrowCount) {
        if (marker) await expect(diagram.locator('.wt-dependency').first()).toHaveAttribute('marker-end', marker)
        else await expect(diagram.locator('.wt-dependency').first()).not.toHaveAttribute('marker-end')
      }
      await expect(diagram.getByRole('button', { name: '导出 SVG', exact: true })).toBeEnabled()
      const downloading = page.waitForEvent('download')
      await diagram.getByRole('button', { name: '导出 SVG', exact: true }).click()
      const download = await downloading
      const filename = testInfo.outputPath(label + '.svg')
      await download.saveAs(filename)
      const svg = await fs.readFile(filename, 'utf8')
      expect((svg.match(/class="wt-dependency"/g) || [])).toHaveLength(arrowCount)
      expect((svg.match(/marker-end="url\(#wt-arrow\)"/g) || [])).toHaveLength(marker ? 2 : 0)
    }
    await page.getByRole('dialog', { name: 'A 图（时间轴嵌套框图）', exact: true })
      .getByRole('button', { name: 'Close this dialog' }).click()
    const exporting = page.waitForRequest(request => request.url().includes('/export.xlsx'))
    const downloading = page.waitForEvent('download')
    await page.getByRole('button', { name: '导出 Excel', exact: true }).click()
    expect(new URL((await exporting).url()).searchParams.get('dependency_mode')).toBe('hidden')
    expect(await (await downloading).failure()).toBeNull()
  } finally {
    for (const [path, id] of created.reverse()) await page.request.delete(`/api${path}/${id}`, { headers })
  }
})
