import { computed, shallowRef } from 'vue'

// API 的读取和保存都更新这里，登录页、布局与首页使用同一份实例配置。
export const projectConfig = shallowRef({})
export function applyProjectConfig(data) {
  projectConfig.value = data && typeof data === 'object' && !Array.isArray(data) ? data : {}
}

const text = value => typeof value === 'string' ? value.trim() : ''
export const appName = computed(() => text(projectConfig.value.project_name)
  || text(text(projectConfig.value.about_content).split('\n')[0])
  || '项目管理系统')
export const appInitial = computed(() => Array.from(appName.value)[0] || '项')
export const projectDescription = computed(() => text(projectConfig.value.project_description)
  || text(text(projectConfig.value.about_content).split('\n').slice(1).join('\n')).split(/\n\s*\n/)[0]
  || '统一管理客户面状态、版本发布与迭代规划，让团队成员实时同步进度、关键问题与变更。')
