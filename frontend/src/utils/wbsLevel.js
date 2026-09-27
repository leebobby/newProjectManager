// WBS 各级任务的**字号阶梯**：第 1 层最大、越往下越小，一眼就能看出层级。
//
// 这是后端 `enums.WBS_LEVEL_FONTS` 的前端那一份，**两端必须同步**（同
// `SUPPORT_MODES`、`GRID_COL_TYPES`、`LIGHT_LABELS` 那几处）。分叉的表现是
// 「页面上分组比子任务大一号、导出的 Excel 里一样大」，而两边单独看都正常，
// 没人会当 bug 报上来。
//
// 这里只要 px（页面画的是像素），pt 那一列是 Excel 用的，留在后端。
// 深于最后一档的层级**一律用最后一档**——层数是不限的，按公式一路缩下去
// 第 8 层会是负数，而页面上只表现成"那几行怎么看不见了"。
const LEVELS = [
  { px: 15, bold: 700, color: '#1F242E' },   // 第 1 层：分组 / 调试阶段
  { px: 13.5, bold: 600, color: '#262626' }, // 第 2 层：工作包
  { px: 12.5, bold: 400, color: '#3A3F4B' }, // 第 3 层：子任务
  { px: 11.5, bold: 400, color: '#606266' }, // 第 4 层及以下
]

export function levelFont(depth) {
  return LEVELS[Math.min(Math.max(1, Number(depth) || 1) - 1, LEVELS.length - 1)]
}

/** 直接挂到元素 :style 上的写法。 */
export function levelStyle(depth) {
  const f = levelFont(depth)
  return { fontSize: `${f.px}px`, fontWeight: f.bold, color: f.color }
}

export default LEVELS
