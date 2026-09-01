/**
 * 冒烟：把系统真跑起来，把侧栏每一页都点一遍，断言页面确实渲染出了东西。
 *
 * 这里不验证业务口径（那是后端 pytest 的活），只回答一个问题：**打出来的包点得开吗**。
 * 起因是 VersionManagement.vue 漏 import 的那次——`vite build` 绿、后端测试全绿，
 * 而线上那一页白屏，并且进过它之后整个前端都不再渲染，只有整页刷新能恢复。
 * 那种故障，只有真开一个浏览器点一遍才看得见。
 */
import { expect, test } from '@playwright/test'

/**
 * 分两档收错，**这个区分是这份用例能不能长期留着的关键**：
 *
 * - fatal：页面自己崩了——未捕获异常，或 main.js 全局 errorHandler 打的 `[Vue]` 那条。
 *   组件在 setup/render 里抛异常时页面只是白掉，不一定有 pageerror 冒到这里，
 *   所以两样都要盯。这一档判红。
 * - noisy：请求失败但页面接住了（`Failed to load resource`、api 层的 `加载XX失败`）。
 *   只打印不判红——一个没配报表路径的干净环境里，问题单那几页本来就会 404，
 *   把它算成失败，CI 会因为"数据没配"红给你看，红几次之后这道闸门就没人信了。
 *   接口本身对不对是后端 pytest 的活。
 */
function watchErrors(page) {
  const fatal = []
  const noisy = []
  page.on('pageerror', (e) => fatal.push(`未捕获异常：${e.message}`))
  page.on('console', (m) => {
    if (m.type() !== 'error') return
    const text = m.text().slice(0, 200)
    ;(text.includes('[Vue]') ? fatal : noisy).push(`控制台：${text}`)
  })
  return { fatal, noisy }
}

async function login(page) {
  await page.goto('/login')
  await page.getByPlaceholder('用户名').fill('admin')
  await page.getByPlaceholder('密码').fill('admin123')
  await page.getByRole('button', { name: '登 录' }).or(page.getByRole('button')).first().click()
  await expect(page.locator('.el-main')).toBeVisible({ timeout: 15_000 })
}

/** 页面"有内容"的判据：主区域渲染出了肉眼可见的文字，而不是一个空壳。 */
async function expectRendered(page, where) {
  const main = page.locator('.el-main')
  await expect(main, `${where}：主区域没渲染出来`).toBeVisible({ timeout: 15_000 })
  await expect
    .poll(async () => (await main.innerText()).trim().length, {
      message: `${where}：主区域是空的（组件多半在 setup 里就抛了）`,
      timeout: 15_000,
    })
    .toBeGreaterThan(0)
}

test('登录进得去，首页渲染得出来', async ({ page }) => {
  const { fatal } = watchErrors(page)
  await login(page)
  await expectRendered(page, '登录后的首页')
  expect(fatal, `首页有报错：\n${fatal.join('\n')}`).toEqual([])
})

test('侧栏每一页都点得开', async ({ page }) => {
  await login(page)

  // 从真实 DOM 里取菜单项，而不是维护一份路由清单：
  // 新加的页面自动被这条用例覆盖，不必记得回来改测试
  const items = page.getByRole('menuitem')
  const names = (await items.allInnerTexts())
    .map((t) => t.replace(/\s+/g, ' ').trim())
    .filter(Boolean)
  expect(names.length, '侧栏一个菜单项都没有，登录态多半没建立起来').toBeGreaterThan(5)

  const broken = []
  const noticed = []
  for (const name of names) {
    // 每一页单独收错：一页坏了要能说出是哪一页，而不是丢一堆栈让人自己猜
    const { fatal, noisy } = watchErrors(page)
    const item = page.getByRole('menuitem', { name, exact: true }).first()
    if (!(await item.isVisible().catch(() => false))) continue
    await item.click()
    try {
      await expectRendered(page, name)
    } catch (e) {
      broken.push(`【${name}】${e.message.split('\n')[0]}`)
    }
    // 歇一下再摘监听：异常常常比"页面渲染完"晚半拍到，摘早了这条错会被记到
    // 下一页头上，看报告的人就跑去翻一个没问题的文件
    await page.waitForTimeout(200)
    if (fatal.length) broken.push(`【${name}】${fatal.join(' | ')}`)
    if (noisy.length) noticed.push(`【${name}】${noisy.join(' | ')}`)
    page.removeAllListeners('pageerror')
    page.removeAllListeners('console')
  }

  // 请求失败不判红，但要打出来：多半是这个环境没配数据，偶尔是真坏了
  if (noticed.length) console.log(`\n以下页面有失败的请求（不判红）：\n${noticed.join('\n')}`)
  expect(broken, `以下页面点开有问题：\n${broken.join('\n')}`).toEqual([])
})

test('进过版本管理之后，别的页面还渲染得出来', async ({ page }) => {
  // 这条单独立一个用例，因为它测的不是"版本管理坏没坏"，而是**一个页面出错会不会
  // 把整个前端带走**：Vue 在 setup 里抛异常后 router-view 就不再渲染任何页面，
  // 现象是「进了某个页面之后点别的菜单都没反应，刷新一下又好」，
  // 看着完全不像是那个页面的错。
  const { fatal } = watchErrors(page)
  await login(page)

  await page.getByRole('menuitem', { name: '迭代管理', exact: true }).first().click()
  await expectRendered(page, '迭代管理（进版本管理之前）')

  await page.getByRole('menuitem', { name: '版本管理', exact: true }).first().click()
  await expectRendered(page, '版本管理')

  await page.getByRole('menuitem', { name: '迭代管理', exact: true }).first().click()
  await expect(page).toHaveURL(/\/iterations/)
  await expectRendered(page, '迭代管理（从版本管理切回来）')

  expect(fatal, `切换过程中有报错：\n${fatal.join('\n')}`).toEqual([])
})
