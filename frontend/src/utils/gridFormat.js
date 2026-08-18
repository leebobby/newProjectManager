/**
 * 单元格 / 富文本的字体与格式：单一来源，RichGrid 与 RichTextEditor 共用。
 *
 * 与后端 enums.GRID_FONTS / GRID_FONT_SIZES / GRID_CELL_BG **必须同步**。
 * 存进单元格的是 key（'simsun'）不是 CSS 串——页面要 CSS、周报 HTML 要 CSS、
 * Excel 要一个字体名，三处出口不同；存 CSS 串会逼着 Excel 端去反解析
 * font-family 列表。漏加一项的后果与列格式白名单一样：该字体每次加载被静默清掉。
 */
export const FONTS = [
  { value: '', label: '默认', css: '' },
  { value: 'yahei', label: '微软雅黑', css: "'Microsoft YaHei', 微软雅黑, sans-serif" },
  { value: 'simsun', label: '宋体', css: 'SimSun, 宋体, serif' },
  { value: 'simhei', label: '黑体', css: 'SimHei, 黑体, sans-serif' },
  { value: 'kaiti', label: '楷体', css: 'KaiTi, 楷体, serif' },
  { value: 'fangsong', label: '仿宋', css: 'FangSong, 仿宋, serif' },
  { value: 'arial', label: 'Arial', css: 'Arial, Helvetica, sans-serif' },
  { value: 'times', label: 'Times New Roman', css: "'Times New Roman', Times, serif" },
]

const FONT_CSS = Object.fromEntries(FONTS.map((f) => [f.value, f.css]))

export const FONT_SIZES = [
  { value: '', label: '默认' },
  { value: 12, label: '小 12' },
  { value: 13, label: '13' },
  { value: 14, label: '正常 14' },
  { value: 16, label: '中 16' },
  { value: 18, label: '大 18' },
  { value: 22, label: '超大 22' },
]
const SIZE_SET = new Set(FONT_SIZES.map((s) => s.value).filter(Boolean))

/** 字色候选（与富文本编辑器的取色盘同一套）。 */
export const TEXT_COLORS = [
  { value: '', label: '默认', hex: '#303133' },
  { value: '#C7000B', label: '红', hex: '#C7000B' },
  { value: '#1565C0', label: '蓝', hex: '#1565C0' },
  { value: '#67C23A', label: '绿', hex: '#67C23A' },
  { value: '#E6A23C', label: '橙', hex: '#E6A23C' },
  { value: '#909399', label: '灰', hex: '#909399' },
]

/** 单元格底色候选，须与后端 enums.GRID_CELL_BG 一致。 */
export const CELL_BGS = [
  { value: '', label: '无底色' },
  { value: '#FFF7E6', label: '浅橙' },
  { value: '#FEF0F0', label: '浅红' },
  { value: '#F0F9EB', label: '浅绿' },
  { value: '#ECF5FF', label: '浅蓝' },
  { value: '#F4F4F5', label: '浅灰' },
]

export function fontCss(key) {
  return FONT_CSS[String(key || '')] || ''
}

/** 白名单过滤：非法字体/字号一律清空，与后端 _fmt_css 的丢弃口径一致。 */
export function normFont(key) {
  return FONT_CSS[String(key || '')] !== undefined && key ? String(key) : ''
}
export function normSize(v) {
  const n = Number(v)
  return SIZE_SET.has(n) ? n : ''
}

/**
 * 单元格格式 → 内联 style 对象。
 * 供 RichGrid 的显示与编辑态共用，保证「编辑时看到的」就是「保存后看到的」。
 */
export function formatStyle(cell) {
  if (!cell || typeof cell !== 'object') return {}
  const st = {}
  if (cell.align) st.textAlign = cell.align
  if (cell.color) st.color = cell.color
  if (cell.bg) st.background = cell.bg
  if (cell.bold) st.fontWeight = 700
  if (cell.italic) st.fontStyle = 'italic'
  if (cell.underline) st.textDecoration = 'underline'
  const css = fontCss(cell.font)
  if (css) st.fontFamily = css
  if (cell.size) st.fontSize = `${cell.size}px`
  return st
}
