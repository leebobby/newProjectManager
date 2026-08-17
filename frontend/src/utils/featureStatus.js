/**
 * 关键特性交付状态：单一来源，管理页与客户总览点灯共用（避免颜色/取值漂移）。
 * 顺序从"最成熟"到"最早期"，须与后端 enums.KEY_FEATURE_STATUSES 一致。
 */
export const FEATURE_STATUSES = ['可商用', 'beta验证', '测试', '开发', '设计', '分析']

export const FEATURE_STATUS_COLOR = {
  可商用: '#67c23a',   // 绿
  beta验证: '#409eff', // 蓝
  测试: '#26c9c3',     // 青
  开发: '#e6a23c',     // 橙
  设计: '#8e7ad8',     // 紫
  分析: '#909399',     // 灰
}

export function featureColor(status) {
  return FEATURE_STATUS_COLOR[status] || '#c0c4cc'
}
