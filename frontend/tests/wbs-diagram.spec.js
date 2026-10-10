import fs from 'node:fs/promises'
import { expect, test } from '@playwright/test'

// 使用现有界面和真实 API 验证框图、层级裁剪及三种导出；只创建并清理自己的示例。
test('调试框图保留原样式，只显示名称和责任人，并共用月份参考轴', async ({ page }, testInfo) => {
  test.setTimeout(60000)
  page.setDefaultTimeout(10000)
  const login = await page.request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin123' },
  })
  expect(login.ok()).toBeTruthy()
  const headers = { Authorization: `Bearer ${(await login.json()).access_token}` }
  const create = async (path, data) => {
    const response = await page.request.post(`/api${path}`, { headers, data })
    expect(response.ok()).toBeTruthy()
    return response.json()
  }
  const usersResponse = await page.request.get('/api/users/options', { headers })
  const owner = (await usersResponse.json()).find(user => user.username === 'admin')
  const ownerName = owner.full_name || owner.username
  const special = await create('/specials', { name: `框图回归-${Date.now()}` })
  let plan
  try {
    plan = await create('/wbs/plans', { name: '框图排版回归', kind: 'special', special_id: special.id })
    const add = data => create(`/wbs/plans/${plan.id}/items`, data)
    let detail = await add({ name: '调试准备', owner_user_id: owner.id })
    const stage = detail.items.find(item => item.name === '调试准备').id
    detail = await add({ name: '视觉标定', parent_id: stage, owner_user_id: owner.id })
    const group = detail.items.find(item => item.name === '视觉标定').id
    await add({ name: '精度验证', parent_id: group, owner_user_id: owner.id, status: '进行中',
      man_days: 3, progress_pct: 60, planned_start: '2026-10-01', planned_end: '2026-10-03' })
    await add({ name: '环境验证', parent_id: group, owner_user_id: owner.id,
      planned_start: '2026-12-01', planned_end: '2026-12-20' })
    await add({ name: '整机验证', owner_user_id: owner.id, planned_start: '2026-12-01', planned_end: '2026-12-20' })

    await page.goto('/login')
    await page.getByPlaceholder('用户名').fill('admin')
    await page.getByPlaceholder('密码').fill('admin123')
    await page.getByRole('button').first().click()
    await expect(page.locator('.el-main')).toBeVisible()
    await page.goto(`/wbs/${plan.id}`)
    await page.getByRole('button', { name: '调试框图', exact: true }).click()
    const boxes = page.locator('.wd-task-box')
    await expect(boxes).toHaveCount(5)
    const geometry = async name => boxes.filter({ hasText: name }).locator('rect').evaluate(rect => ({
      x: +rect.getAttribute('x'), y: +rect.getAttribute('y'),
      w: +rect.getAttribute('width'), h: +rect.getAttribute('height'),
    }))
    const parent = await geometry('视觉标定')
    const child = await geometry('精度验证')
    const sibling = await geometry('环境验证')
    for (const box of [child, sibling]) {
      expect(box.x).toBeGreaterThan(parent.x)
      expect(box.x + box.w).toBeLessThan(parent.x + parent.w)
      expect(box.y).toBeGreaterThan(parent.y)
      expect(box.y + box.h).toBeLessThan(parent.y + parent.h)
    }
    expect(child.y + child.h).toBeLessThan(sibling.y)
    // title 是完整悬停文本，同名同责任人；SVG text 才是实际画出的内容。
    expect(await boxes.filter({ hasText: '精度验证' }).locator('text').allTextContents())
      .toEqual(['精度验证', ownerName])
    expect(await boxes.locator('text').allTextContents()).not.toContain('60%')
    await expect(page.locator('.wd-reference-axis')).toContainText('2026年10月')
    await expect(page.locator('.wd-reference-axis')).toContainText('2027年3月')
    await page.screenshot({ path: testInfo.outputPath('wbs-diagram-all-levels.png'), fullPage: true })
    const originalAxis = await page.locator('.wd-reference-axis').innerHTML()
    const secondStageX = await boxes.last().locator('rect').getAttribute('x')
    await page.locator('.el-select').filter({ has: page.getByRole('combobox', { name: '生成层级' }) }).click()
    await page.getByRole('option', { name: '生成到第 1 层', exact: true }).click()
    await expect(boxes).toHaveCount(2)
    expect(await page.locator('.wd-reference-axis').innerHTML()).toBe(originalAxis)
    expect(await boxes.last().locator('rect').getAttribute('x')).toBe(secondStageX)
    expect(await boxes.first().locator('rect').getAttribute('stroke')).toBe('#F56C6C')
    await expect(page.locator('.wd-note')).toContainText('另有 3 行')

    const monthInputs = page.locator('.wd-bar .el-date-editor input')
    await monthInputs.nth(0).fill('2027年01月')
    await monthInputs.nth(1).fill('2027年08月')
    await monthInputs.nth(1).press('Enter')
    await expect(page.locator('.wd-reference-axis')).toContainText('2027年8月')
    await expect(page.locator('.wd-reference-axis')).not.toContainText('2026年')
    await expect(boxes).toHaveCount(2)

    const depthSelect = page.locator('.el-select').filter({ has: page.getByRole('combobox', { name: '生成层级' }) })
    await depthSelect.click()
    await page.getByRole('option', { name: '生成全部层级', exact: true }).click()
    await expect(boxes).toHaveCount(5)
    for (const kind of ['SVG', 'PNG']) {
      const downloading = page.waitForEvent('download')
      await page.getByRole('button', { name: `导出 ${kind}`, exact: true }).click()
      const download = await downloading
      expect(await download.failure()).toBeNull()
      const file = testInfo.outputPath(`diagram.${kind.toLowerCase()}`)
      await download.saveAs(file)
      const bytes = await fs.readFile(file)
      if (kind === 'SVG') {
        expect(bytes.toString()).toContain('2027年8月')
        expect(bytes.toString()).toContain('精度验证')
        expect(bytes.toString()).toContain('环境验证')
        expect(bytes.toString()).not.toContain('60%')
        const exportedParent = await page.evaluate(svg => {
          const doc = new DOMParser().parseFromString(svg, 'image/svg+xml')
          const rect = doc.querySelector('.wd-task-box[data-code="1.1"] rect')
          return { x: +rect.getAttribute('x'), y: +rect.getAttribute('y'),
            w: +rect.getAttribute('width'), h: +rect.getAttribute('height') }
        }, bytes.toString())
        expect(exportedParent).toEqual(parent)
      } else {
        expect(bytes.subarray(0, 8)).toEqual(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
      }
    }
    await depthSelect.click()
    await page.getByRole('option', { name: '生成到第 1 层', exact: true }).click()
    await expect(boxes).toHaveCount(2)
    const request = page.waitForRequest(r => r.url().includes('/export.xlsx'))
    const downloading = page.waitForEvent('download')
    await page.getByRole('button', { name: '导出 Excel', exact: true }).click()
    const exportRequest = await request
    const query = new URL(exportRequest.url()).searchParams
    expect(query.get('max_depth')).toBe('1')
    expect(query.get('reference_start')).toBe('2027-01')
    expect(query.get('reference_end')).toBe('2027-08')
    expect(await (await downloading).failure()).toBeNull()
    await page.screenshot({ path: testInfo.outputPath('wbs-diagram.png'), fullPage: true })
  } finally {
    if (plan) await page.request.delete(`/api/wbs/plans/${plan.id}`, { headers })
    await page.request.delete(`/api/specials/${special.id}`, { headers })
  }
})
