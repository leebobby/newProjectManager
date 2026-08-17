// 通用格式化 / 比较工具。
// 之前 fmtDate 在 VersionManagement / DebugVersionPanel / VersionTimeline 各写了一份，
// naturalCompare 在 VersionManagement / CustomerStatus 各写了一份——收口到这里，新页面直接 import。

/** 日期 → YYYY-MM-DD。接受 Date / 时间戳 / 可被 new Date 解析的字符串；空值返回 ''。 */
export function fmtDate(d) {
  if (d == null || d === '') return ''
  const dt = new Date(d)
  if (Number.isNaN(dt.getTime())) return ''
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
}

/** 自然排序比较：数字段按数值比（M2 < M10、V2.2 < V2.10），供 el-table sort-method 用。 */
export function naturalCompare(a, b) {
  return String(a ?? '').localeCompare(String(b ?? ''), 'zh-Hans-CN', { numeric: true, sensitivity: 'base' })
}
