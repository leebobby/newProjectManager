/**
 * 需求列表的「计划交付版本」筛选：产品需求与领域需求两个 Tab 共用一份实现。
 * 两处各写一份的表现是同一个版本在两个 Tab 里筛出来的条数不一样，而两边看着都对。
 *
 * **选项从数据里取，不从编辑用的 `versionGroups` 取**，两个原因：
 * - 那份下拉刻意滤掉了已发布的版本（合入是往还没发的版本里合），而已经填在行上的
 *   版本里有大量是已发布的——拿它当筛选选项，那些行就永远筛不出来，
 *   而页面上只表现成「这个版本怎么筛不到」。
 * - 三层版本里光构建就上百个，全列出来点进去大半是空的（同 `domains._version_options()`：
 *   只列当前确实挂着需求的那些）。
 *
 * 比较前把空白全去掉再转小写，与后端判重的 `_req_dedup._squash()` 同款：Excel 里粘出来的
 * 版本号常带首尾空格或全角空格，肉眼看不出差别，按原样比较会把同一个版本劈成两个选项，
 * 两个选项长得一模一样、条数还各占一半。
 */

/** 「未指定版本」这一档的选项值。用哨兵值而不是空串：空串会被 el-select 当成"没选"。 */
export const UNSET_VERSION = '__unset__'

/** 归一化版本号：去掉所有空白（含全角空格）再转小写。 */
export function normVersionNo(s) {
  return String(s ?? '').replace(/[\s　]+/g, '').toLowerCase()
}

/**
 * 一行需求是否命中当前选中的版本。`picked` 为空＝没筛，全放行。
 *
 * 选中值存的是**显示用的版本号原样**、比较时才两边归一：存归一化后的键的话，
 * 一个在本 Tab 里一条都没匹配的选中值（切了 Tab / 切了项目标签之后很常见）
 * 会被 el-select 原样摊在框里，显示成一串小写，看着像另一个版本。
 */
export function matchPlannedVersion(row, picked) {
  if (!picked) return true
  const v = normVersionNo(row.planned_version)
  return picked === UNSET_VERSION ? !v : v === normVersionNo(picked)
}

/**
 * 按当前这批行算出版本下拉的选项，每项带条数。
 *
 * `rows` 要传「除版本外其它筛选都已生效」的结果——传已经按版本筛过的列表的话，
 * 选中一个版本之后其它选项的条数全变成 0（自己把自己滤掉了）。
 * 顺序跟 `versionGroups` 走（那是服务端的 `sort_order`，别按版本号推），
 * 不在其中的（已发布的、以及老数据里手敲进去的写法）排在后面。
 */
export function buildVersionOptions(rows, versionGroups = [], picked = '') {
  const order = new Map()
  let i = 0
  for (const g of versionGroups || []) {
    for (const v of g.options || []) {
      const k = normVersionNo(v.version_no)
      if (k && !order.has(k)) order.set(k, i++)
    }
  }

  const seen = new Map()
  let unset = 0
  for (const r of rows) {
    const raw = String(r.planned_version ?? '').trim()
    const k = normVersionNo(raw)
    if (!k) {
      unset += 1
      continue
    }
    const hit = seen.get(k)
    if (hit) hit.count += 1
    else seen.set(k, { key: k, value: raw, label: raw, count: 1 })
  }

  // 当前选中的值即使一条都不匹配也要留在选项里：切了项目标签、或切到另一个 Tab 之后
  // 常常一条都没有，选项里没有它的话 el-select 会退化成把原始值摊在框里，看着像坏了。
  const pickedKey = normVersionNo(picked)
  if (pickedKey && picked !== UNSET_VERSION && !seen.has(pickedKey)) {
    seen.set(pickedKey, { key: pickedKey, value: picked, label: picked, count: 0 })
  }

  const out = Array.from(seen.values()).sort((a, b) => {
    const ai = order.has(a.key) ? order.get(a.key) : Number.MAX_SAFE_INTEGER
    const bi = order.has(b.key) ? order.get(b.key) : Number.MAX_SAFE_INTEGER
    return ai !== bi ? ai - bi : a.label.localeCompare(b.label)
  })

  // 「未指定版本」是一个**显式**选项并排最后，同项目标签的「未指定项目」：
  // 没填版本的行正是最该被捞出来补录的那批，混在「全部」里就永远没人去补。
  if (unset || picked === UNSET_VERSION) {
    out.push({ key: UNSET_VERSION, value: UNSET_VERSION, label: '未指定版本', count: unset })
  }
  return out
}
