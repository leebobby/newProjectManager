/**
 * RichGrid 的「点灯」列：单一来源，表格编辑器与模板编辑页共用。
 * 取值词表与颜色档位须与后端 enums.GRID_LIGHT_COLORS / GRID_LIGHT_DEFAULT_OPTIONS
 * 一致——后端在周报 HTML 与 Excel 里按同一套映射着色，两边分叉就会出现
 * 「页面是绿的、导出没颜色」。
 */
export const LIGHT_DEFAULT_OPTIONS = ['绿', '黄', '红']

/** RichGrid 支持的列格式白名单，须与后端 enums.GRID_COL_TYPES 一致。 */
export const GRID_COL_TYPES = ['text', 'select', 'date', 'light']

// 单元格文本（去空白后精确匹配）→ 颜色档位
const LIGHT_OF = {
  红: 'red', 黄: 'yellow', 绿: 'green',
  红灯: 'red', 黄灯: 'yellow', 绿灯: 'green',
  R: 'red', Y: 'yellow', G: 'green',
}

const LIGHT_STYLE = {
  red: { background: '#fef0f0', color: '#f56c6c' },
  yellow: { background: '#fdf6ec', color: '#e6a23c' },
  green: { background: '#f0f9eb', color: '#67c23a' },
}

export function lightOf(text) {
  return LIGHT_OF[String(text || '').trim()] || ''
}

/** 点灯单元格的样式；未命中词表返回 null（不着色，按普通单元格渲染）。 */
export function lightStyle(text) {
  const l = lightOf(text)
  if (!l) return null
  return { ...LIGHT_STYLE[l], fontWeight: 700, textAlign: 'center' }
}
