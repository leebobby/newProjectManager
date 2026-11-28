import fs from 'node:fs/promises'
import { expect, test } from '@playwright/test'

async function setup(page) {
  const login = await page.request.post('/api/auth/login', { data: { username: 'admin', password: 'admin123' } })
  expect(login.ok()).toBeTruthy()
  const headers = { Authorization: `Bearer ${(await login.json()).access_token}` }
  const post = async (path, data) => {
    const response = await page.request.post('/api' + path, { headers, data })
    expect(response.ok(), await response.text()).toBeTruthy()
    return response.json()
  }
  await page.goto('/login')
  await page.getByPlaceholder('用户名').fill('admin')
  await page.getByPlaceholder('密码').fill('admin123')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.locator('.el-main')).toBeVisible()
  return { headers, post }
}

test('版本时间轴铺满窗口、独立收尾，标签紧贴箭头，选择范围后自适应', async ({ page }, testInfo) => {
  test.setTimeout(180000)
  const { headers, post } = await setup(page)
  const key = String(Date.now())
  const created = []
  const base = Date.now() - 90 * 86400000
  const date = days => new Date(base + days * 86400000).toISOString().slice(0, 10)
  try {
    const project = await post('/roadmap/projects', { name: '自适应时间轴-' + key })
    created.push(['/roadmap/projects', project.id])
    for (const [index, count, step] of [[0, 40, 15], [1, 5, 35], [2, 12, 35]]) {
      const major = await post('/major-versions', { project_id: project.id, version_no: `C${10 + index}SPC100`,
        range_start: date(0), range_end: date(700) })
      created.push(['/major-versions', major.id])
      if (!index) await post(`/major-versions/${major.id}/set-master`, {})
      for (let n = 0; n < count; n++) {
        const release = await post('/release-versions', { major_version_id: major.id,
          version_no: `C${10 + index}SPC${101 + n}`, planned_date: date((index ? 80 : 0) + n * step) })
        created.push(['/release-versions', release.id])
      }
    }
    await page.goto('/versions')
    await page.getByRole('tab', { name: project.name, exact: true }).click()
    const chart = page.locator('.vt-wrap')
    await expect(chart.locator('.vt-major-label')).toHaveCount(3)
    for (const width of [1366, 1920]) {
      await page.setViewportSize({ width, height: 1000 })
      for (const range of ['全部（自动收窄）', '近 3 月', '近 6 月', '近 1 年']) {
        await chart.locator('.el-select').first().click()
        await page.getByRole('option', { name: range, exact: true }).click()
        await expect.poll(() => chart.locator('.vt-svg').evaluate(svg =>
          Math.abs(svg.getBoundingClientRect().width - svg.viewBox.baseVal.width))).toBeLessThan(2)
        const result = await chart.locator('.vt-svg').evaluate(svg => {
          const frame = svg.getBoundingClientRect()
          const labels = [...svg.querySelectorAll('.vt-major-label')].map(group => {
            const box = group.querySelector('rect').getBoundingClientRect()
            const arrow = group.parentElement.querySelector('.vt-lane-arrow').getBoundingClientRect()
            return { name: group.querySelector('text').textContent, tip: arrow.right, gap: box.left - arrow.right,
              inside: box.left >= frame.left && box.right <= frame.right, box }
          })
          const intersects = (a, b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top
          const nodes = [...svg.querySelectorAll('circle')].filter(node => node.querySelector('title'))
          return { labels: labels.map(({ box, ...label }) => label),
            covered: nodes.filter(node => labels.some(label => intersects(node.getBoundingClientRect(), label.box))).length,
            valid: nodes.every(node => Number.isFinite(Number(node.getAttribute('cx')))), scale: svg.getScreenCTM().a }
        })
        expect(result.labels.every(label => label.inside && Math.abs(label.gap - 4) < 1)).toBeTruthy()
        expect(result.covered).toBe(0)
        expect(result.valid).toBeTruthy()
        expect(result.scale).toBe(1)
        if (range.startsWith('全部')) {
          const tip = name => result.labels.find(label => label.name.includes(name)).tip
          expect(tip('C11SPC100')).toBeLessThan(tip('C12SPC100'))
          expect(tip('C12SPC100')).toBeLessThan(tip('C10SPC100'))
        }
      }
    }
    await chart.locator('.el-select').first().click()
    await page.getByRole('option', { name: '按月份区间…', exact: true }).click()
    await chart.getByPlaceholder('起始月').fill(date(0).slice(0, 7))
    await chart.getByPlaceholder('结束月').fill(date(180).slice(0, 7))
    await chart.getByPlaceholder('结束月').press('Enter')
    await chart.getByPlaceholder('结束月').press('Tab')
    await expect(chart.locator('.vt-major-label')).toHaveCount(3)
    const downloading = page.waitForEvent('download')
    await chart.getByRole('button', { name: '导出图', exact: true }).click()
    await page.getByRole('menuitem', { name: 'SVG 矢量图（放大不糊）', exact: true }).click()
    const download = await downloading
    const file = testInfo.outputPath('responsive-versions.svg')
    await download.saveAs(file)
    const xml = await fs.readFile(file, 'utf8')
    const exportedWidth = Number(xml.match(/\bwidth="([\d.]+)"/)[1])
    expect(exportedWidth).toBe(await chart.locator('.vt-svg').evaluate(svg => svg.viewBox.baseVal.width))
    expect((xml.match(/class="vt-major-label"/g) || []).length).toBe(3)
    await chart.screenshot({ path: testInfo.outputPath('responsive-versions.png') })
  } finally {
    for (const [path, id] of created.reverse()) await page.request.delete(`/api${path}/${id}`, { headers })
  }
})

test('WBS 真接口适应宽度、固定日期轴，关闭预览后 Excel 保留布局选项', async ({ page }) => {
  test.setTimeout(120000)
  const { headers, post } = await setup(page)
  const special = await post('/specials', { name: '日期轴回归-' + Date.now() })
  let plan
  try {
    plan = await post('/wbs/plans', { kind: 'special', special_id: special.id, name: '长周期布局回归' })
    for (let n = 0; n < 24; n++) {
      const start = new Date(Date.UTC(2025, n, 1)).toISOString().slice(0, 10)
      await post(`/wbs/plans/${plan.id}/items`, { name: `验证任务 ${n + 1}`, planned_start: start, planned_end: start })
    }
    await page.goto(`/wbs/${plan.id}`)
    await page.getByRole('button', { name: '预览 A 图', exact: true }).click()
    const chart = page.locator('.wt-wrap')
    const viewport = chart.locator('.wt-scroll')
    await expect(chart.locator('.wt-task-box')).toHaveCount(24)
    await expect.poll(() => chart.locator('.wt-svg').evaluate(svg => +svg.getAttribute('width'))).toBeGreaterThan(3000)
    // 固定的是日期轴相对滚动容器的位置；弹窗入场动画会移动整个容器的页面坐标。
    const axisTop = () => viewport.evaluate(el =>
      el.querySelector('.wt-sticky-axis').getBoundingClientRect().top - el.getBoundingClientRect().top)
    const top = await axisTop()
    await viewport.evaluate(el => { el.scrollTop = 400; el.scrollLeft = 300 })
    await expect.poll(async () => Math.abs(await axisTop() - top)).toBeLessThan(2)
    await chart.getByRole('button', { name: '适应宽度', exact: true }).click()
    await expect.poll(() => viewport.evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1)
    await expect(chart.locator('.wt-count')).toContainText('缩放 100%')
    const available = await viewport.evaluate(el => el.clientWidth)
    const detail = await page.request.get(`/api/wbs/plans/${plan.id}/timeline`, { headers,
      params: { viewport_width: available, fit_width: true } })
    const spec = await detail.json()
    await expect(chart.locator('.wt-svg')).toHaveAttribute('width', String(spec.width))
    await page.locator('.el-dialog__headerbtn').click()
    await expect(chart).toHaveCount(0)
    const requestPromise = page.waitForRequest(request => request.url().includes(`/wbs/plans/${plan.id}/export.xlsx`))
    const downloading = page.waitForEvent('download')
    await page.getByRole('button', { name: '导出 Excel', exact: true }).click()
    const request = await requestPromise
    expect(new URL(request.url()).searchParams.get('fit_width')).toBe('true')
    expect(new URL(request.url()).searchParams.get('viewport_width')).toBe(String(available))
    expect(await (await downloading).failure()).toBeNull()
  } finally {
    if (plan) await page.request.delete(`/api/wbs/plans/${plan.id}`, { headers })
    await page.request.delete(`/api/specials/${special.id}`, { headers })
  }
})
