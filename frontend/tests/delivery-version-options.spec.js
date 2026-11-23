import { expect, test } from '@playwright/test'

async function fixture(page) {
  page.setDefaultTimeout(10000)
  const login = await page.request.post('/api/auth/login', { data: { username: 'admin', password: 'admin123' } })
  expect(login.ok()).toBeTruthy()
  const headers = { Authorization: `Bearer ${(await login.json()).access_token}` }
  const created = []
  const post = async (path, data) => {
    const response = await page.request.post('/api' + path, { headers, data })
    expect(response.ok(), await response.text()).toBeTruthy()
    return response.json()
  }
  const key = String(Date.now())
  const past = new Date(Date.now() - 86400000).toISOString().slice(0, 10)
  const future = new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10)
  const project = await post('/roadmap/projects', { name: '交付版本-' + key })
  created.push(['/roadmap/projects', project.id])
  const major = await post('/major-versions', { project_id: project.id, version_no: 'OPT-' + key + '-100' })
  created.push(['/major-versions', major.id])
  const release = await post('/release-versions', { major_version_id: major.id,
    version_no: 'OPT-' + key + '-101', actual_release_date: past })
  created.push(['/release-versions', release.id])
  const builds = []
  for (const [suffix, actual] of [['001', null], ['002', future], ['003', past]]) {
    const build = await post('/iteration-versions', { release_version_id: release.id,
      version_no: release.version_no + 'B' + suffix, actual_release_date: actual, planned_date: future })
    builds.push(build)
    created.push(['/iteration-versions', build.id])
  }
  const iterations = await (await page.request.get('/api/annual-iterations?year=2092', { headers })).json()
  const iteration = iterations[0]
  const cleanup = async () => {
    for (const [path, id] of created.reverse()) await page.request.delete('/api' + path + '/' + id, { headers })
  }
  const signIn = async () => {
    await page.goto('/login')
    await page.getByPlaceholder('用户名').fill('admin')
    await page.getByPlaceholder('密码').fill('admin123')
    await page.getByRole('button', { name: '登录', exact: true }).click()
    await expect(page.locator('.el-main')).toBeVisible()
  }
  return { headers, post, key, project, major, release, builds, iteration, created, cleanup, signIn }
}

function versionSelect(page, dialog) {
  return dialog.locator('.el-form-item').filter({ has: page.getByText('计划交付版本', { exact: true }) }).locator('.el-select')
}
function option(page, build) {
  return page.getByRole('option', { name: new RegExp(build.version_no) })
}

test('父版本发布后仍能选择未发布构建，历史版本开关覆盖新增、行内和批量', async ({ page }) => {
  test.setTimeout(150000)
  const f = await fixture(page)
  const [open, future, shipped] = f.builds
  try {
    const historical = await f.post('/iteration-requirements', { iteration_id: f.iteration.id,
      title: '已有历史需求-' + f.key, planned_version: shipped.version_no })
    const editable = await f.post('/iteration-requirements', { iteration_id: f.iteration.id, title: '行内版本-' + f.key })
    f.created.push(['/iteration-requirements', historical.id], ['/iteration-requirements', editable.id])
    await f.signIn()
    await page.goto('/iterations/' + f.iteration.id)
    await page.getByRole('tab', { name: '领域需求', exact: true }).click()
    const historyToggle = page.getByRole('checkbox', { name: '显示已发布版本', exact: true })
    await expect(historyToggle).not.toBeChecked()
    const historyRow = page.getByRole('row').filter({ hasText: '已有历史需求-' + f.key })
    await expect(historyRow).toContainText(shipped.version_no)
    await page.getByRole('button', { name: '新增需求', exact: true }).click()
    let dialog = page.getByRole('dialog', { name: '新增需求', exact: true })
    await versionSelect(page, dialog).click()
    await expect(option(page, open)).toBeVisible()
    await expect(option(page, future)).toBeVisible()
    await expect(option(page, shipped)).toHaveCount(0)
    await option(page, future).click()
    await dialog.locator('.el-form-item').filter({ has: page.getByText('需求标题', { exact: true }) }).getByRole('textbox').fill('新构建需求-' + f.key)
    let saved = page.waitForResponse(r => r.url().endsWith('/api/iteration-requirements') && r.request().method() === 'POST')
    await dialog.getByRole('button', { name: '保存', exact: true }).click()
    let row = await (await saved).json()
    f.created.push(['/iteration-requirements', row.id])
    expect(row.target_version_id).toBe(future.id)
    await expect(dialog).not.toBeVisible()

    await page.locator('.version-controls .el-checkbox').click()
    await page.getByRole('button', { name: '新增需求', exact: true }).click()
    dialog = page.getByRole('dialog', { name: '新增需求', exact: true })
    await versionSelect(page, dialog).click()
    await expect(option(page, shipped)).toContainText('已发布')
    await option(page, shipped).click()
    await dialog.locator('.el-form-item').filter({ has: page.getByText('需求标题', { exact: true }) }).getByRole('textbox').fill('历史补录-' + f.key)
    saved = page.waitForResponse(r => r.url().endsWith('/api/iteration-requirements') && r.request().method() === 'POST')
    await dialog.getByRole('button', { name: '保存', exact: true }).click()
    row = await (await saved).json()
    f.created.push(['/iteration-requirements', row.id])
    expect(row.target_version_id).toBe(shipped.id)
    await expect(dialog).not.toBeVisible()

    await page.getByRole('tab', { name: '产品需求', exact: true }).click()
    await expect(historyToggle).toBeChecked()
    await page.getByRole('button', { name: '新增产品需求', exact: true }).click()
    dialog = page.getByRole('dialog', { name: '新增产品需求', exact: true })
    await versionSelect(page, dialog).click()
    await expect(option(page, shipped)).toContainText('已发布')
    await option(page, shipped).click()
    await dialog.getByRole('button', { name: '取消', exact: true }).click()
    await page.getByRole('tab', { name: '领域需求', exact: true }).click()

    const editableRow = page.getByRole('row').filter({ hasText: '行内版本-' + f.key })
    const headings = await page.getByRole('columnheader').allTextContents()
    const versionColumn = headings.findIndex(text => text.trim() === '计划交付版本')
    expect(versionColumn).toBeGreaterThan(0)
    await editableRow.locator('td').nth(versionColumn).locator('.edit-select-cell').click()
    await option(page, shipped).click()
    await expect(editableRow).toContainText(shipped.version_no)
    await editableRow.locator('.el-checkbox').click()
    const bulk = page.locator('.bulk-bar')
    await bulk.locator('.el-select').first().click()
    await page.getByRole('option', { name: `${f.project.name} · ${f.major.version_no} · ${f.release.version_no}`, exact: true }).click()
    await bulk.locator('.el-select').nth(1).click()
    await option(page, shipped).click()
    await page.locator('.version-controls .el-checkbox').click()
    await expect(bulk.getByRole('button', { name: '改计划交付版本', exact: true })).toBeDisabled()
    await expect(historyRow).toContainText(shipped.version_no)
    await expect(editableRow).toContainText(shipped.version_no)
    await bulk.locator('.el-select').nth(1).click()
    await option(page, future).click()
    await bulk.getByRole('button', { name: '改计划交付版本', exact: true }).click()
    await expect(editableRow).toContainText(future.version_no)
    const rows = await (await page.request.get('/api/iteration-requirements?iteration_id=' + f.iteration.id, { headers: f.headers })).json()
    expect(rows.find(item => item.id === editable.id).target_version_id).toBe(future.id)
  } finally { await f.cleanup() }
})

test('版本目录失败有提示，刷新可恢复并加载新建构建', async ({ page }) => {
  test.setTimeout(90000)
  const f = await fixture(page)
  try {
    await f.signIn()
    await page.route('**/api/iteration-versions/all', route => route.fulfill({ status: 500, json: { detail: '目录暂时不可用' } }), { times: 1 })
    await page.goto('/iterations/' + f.iteration.id)
    await expect(page.locator('.el-message')).toContainText('500')
    await page.getByRole('button', { name: '刷新版本', exact: true }).click()
    await expect(page.getByRole('button', { name: '刷新版本', exact: true })).not.toHaveClass(/is-loading/)
    const added = await f.post('/iteration-versions', { release_version_id: f.release.id, version_no: f.release.version_no + 'B004' })
    f.created.push(['/iteration-versions', added.id])
    await page.getByRole('button', { name: '刷新版本', exact: true }).click()
    await expect(page.getByRole('button', { name: '刷新版本', exact: true })).not.toHaveClass(/is-loading/)
    await page.getByRole('tab', { name: '领域需求', exact: true }).click()
    await page.getByRole('button', { name: '新增需求', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '新增需求', exact: true })
    await versionSelect(page, dialog).click()
    await expect(option(page, f.builds[0])).toBeVisible()
    await expect(option(page, added)).toBeVisible()
  } finally { await f.cleanup() }
})
