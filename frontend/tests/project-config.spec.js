import { expect, test } from '@playwright/test'

test('项目配置统一驱动登录、侧栏、首页和标签页，保存及重新读取后同步', async ({ page }) => {
  test.setTimeout(60000)
  let config = { about_content: '项目甲管理系统\n\n项目甲介绍\n\n维护团队', hero_badges: ['甲', '乙'] }
  let unavailable = false
  // 仅拦截本测试浏览器的配置请求，不改部署中的 config.json 或其他人的设置。
  await page.route('**/api/config', async route => {
    if (route.request().method() === 'PUT') config = { ...config, ...route.request().postDataJSON() }
    await route.fulfill({ status: unavailable ? 503 : 200, json: unavailable ? { detail: '暂不可用' } : config })
  })
  await page.goto('/login')
  await expect(page.locator('.brand h2')).toHaveText('项目甲管理系统')
  await expect(page).toHaveTitle('项目甲管理系统')
  await page.getByPlaceholder('用户名').fill('admin')
  await page.getByPlaceholder('密码').fill('admin123')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  const logo = page.locator('.app-logo')
  await expect(logo).toHaveText('项目甲管理系统')
  await expect(page.locator('.hero-title')).toHaveText('项目甲管理系统')
  await expect(page.locator('.hero-tag')).toContainText('项目甲管理系统')
  await expect(page.locator('.hero-sub')).toHaveText('项目甲介绍')
  await expect(page.locator('.hero-stack .badge')).toHaveCount(2)

  const about = page.locator('.about-card')
  await about.getByRole('button', { name: '编辑', exact: true }).click()
  await about.locator('textarea').fill('项目乙管理系统\n\n项目乙介绍')
  await about.getByRole('button', { name: '保存', exact: true }).click()
  await expect(logo).toHaveText('项目乙管理系统')
  await expect(page).toHaveTitle('项目乙管理系统')
  await expect(page.locator('.hero-title')).toHaveText('项目乙管理系统')
  await expect(page.locator('.hero-sub')).toHaveText('项目乙介绍')
  await expect(about.locator('.about-content')).toHaveText('项目乙管理系统\n\n项目乙介绍')

  await page.locator('.badge-edit-btn').click()
  const dialog = page.getByRole('dialog', { name: '编辑标签' })
  while (await dialog.locator('.badge-draft-row').count()) await dialog.locator('.badge-draft-row button').first().click()
  await dialog.getByRole('button', { name: '保存', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.locator('.hero-stack .badge')).toHaveCount(0)
  await page.reload()
  await expect(logo).toHaveText('项目乙管理系统')
  await expect(page.locator('.hero-stack .badge')).toHaveCount(0)

  config = { ...config, project_name: '云端管理系统', project_description: '云端项目目标' }
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await expect(logo).toHaveText('云端管理系统')
  await expect(page).toHaveTitle('云端管理系统')
  await expect(page.locator('.hero-title')).toHaveText('云端管理系统')
  await expect(page.locator('.hero-sub')).toHaveText('云端项目目标')
  await page.getByRole('button', { name: '收起侧栏' }).click()
  await expect(logo).toHaveText('云')
  await expect(logo).toHaveAttribute('title', '云端管理系统')
  await page.getByRole('button', { name: '展开侧栏' }).click()

  config = { ...config, issue_api_projects: ['新增项目'] }
  await page.goto('/issues')
  await expect(page.getByRole('tab', { name: '新增项目', exact: true })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'YLS3000', exact: true })).toHaveCount(0)
  config = { ...config, issue_api_projects: [] }
  await page.reload()
  await expect(page.getByRole('tab', { name: '历史数据', exact: true })).toBeVisible()
  await expect(page.getByRole('tab', { name: '新增项目', exact: true })).toHaveCount(0)
  await expect(page.getByRole('tab', { name: 'YLS3000', exact: true })).toHaveCount(0)
  await page.goto('/intro')
  await expect(logo).toHaveText('云端管理系统')

  unavailable = true
  const failedRead = page.waitForResponse(r => r.url().endsWith('/api/config') && r.status() === 503)
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await failedRead
  await expect(logo).toHaveText('云端管理系统')
  await expect(page).toHaveTitle('云端管理系统')

  unavailable = false
  config = { project_name: ' ', about_content: null, hero_badges: [] }
  await page.reload()
  await expect(logo).toHaveText('项目管理系统')
  await expect(page.locator('.hero-title')).toHaveText('项目管理系统')
  await expect(page).toHaveTitle('项目管理系统')
})
