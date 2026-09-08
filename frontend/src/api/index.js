import axios from 'axios'
import { ElMessage } from 'element-plus'
import { auth } from '../store/auth'

const http = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

http.interceptors.request.use((config) => {
  if (auth.state.token) {
    config.headers.Authorization = `Bearer ${auth.state.token}`
  }
  return config
})

http.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error.response?.status === 401) {
      // 让其它 tab 一起退出
      auth.signalLogout('401')
      if (location.pathname !== '/login') {
        location.replace('/login')
      }
    } else if (error.response?.status === 409) {
      ElMessage.warning(error.response.data?.detail || '数据已被他人修改，请刷新后重试')
    } else if (error.response?.status === 423) {
      ElMessage.warning(error.response.data?.detail || '该内容正被他人编辑，暂时无法保存')
    }
    return Promise.reject(error)
  }
)

/**
 * 把 axios 的异常折成一句「能照着查」的话。
 *
 * 页面上常见的写法是 `e.response?.data?.detail || '加载失败'`，问题是三种完全不同的
 * 故障会写成同一句：后端 500（要去看服务端 traceback）、请求超时（后端还活着，只是这
 * 一下慢了或卡住了）、以及压根没连上（后端没起来 / 代理挂了）。三种原因、三种处理，
 * 用户报上来的却只有「加载失败」四个字，来回问一轮才知道要看哪儿。
 *
 * 所以这里一定把**状态码**带出来：500/502 与超时的处理完全不同，而这是唯一能一眼
 * 分开它们的东西。FastAPI 未捕获异常返回的 detail 是 "Internal Server Error"，
 * 本身没信息量，但配上 HTTP 500 就足以指向"去翻后端控制台"。
 */
export function apiError(e, fallback = '请求失败') {
  if (e?.code === 'ECONNABORTED') {
    return `${fallback}：请求超时（${(e.config?.timeout || 0) / 1000 || 10} 秒内没有响应），后端可能正卡在别的活上`
  }
  const status = e?.response?.status
  if (!status) return `${fallback}：连不上后端（${e?.message || '网络错误'}）`
  const detail = e?.response?.data?.detail
  const tail = status >= 500 ? '，请看后端控制台的报错' : ''
  return typeof detail === 'string' && detail
    ? `${fallback}：${detail}（HTTP ${status}）${tail}`
    : `${fallback}：HTTP ${status}${tail}`
}

export const authApi = {
  login: (data) => http.post('/auth/login', data),
  me: () => http.get('/auth/me'),
  logout: () => http.post('/auth/logout'),
  changePassword: (data) => http.post('/auth/change-password', data),
}

export const opLogApi = {
  list: (params) => http.get('/op-logs', { params }),
  options: () => http.get('/op-logs/options'),
}

export const systemApi = {
  storage: () => http.get('/system/storage'),
}

export const formationApi = {
  imageInfo: () => http.get('/project-formation/image-info'),
  uploadImage: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post('/project-formation/image', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  // 真正图片 blob 通过 http.get('/project-formation/image', {responseType:'blob'}) 自取
  listMembers: () => http.get('/project-formation/members'),
  createMember: (data) => http.post('/project-formation/members', data),
  updateMember: (id, data) => http.put(`/project-formation/members/${id}`, data),
  removeMember: (id) => http.delete(`/project-formation/members/${id}`),
  importTemplate: () => http.get('/project-formation/import-template.xlsx', { responseType: 'blob' }),
  importMembers: (file, replace = false) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post('/project-formation/import', fd, {
      params: { replace },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  exportXlsx: () => http.get('/project-formation/export.xlsx', { responseType: 'blob' }),
}

export const handbookApi = {
  listCategories: () => http.get('/handbook/categories'),
  createCategory: (data) => http.post('/handbook/categories', data),
  updateCategory: (id, data) => http.put(`/handbook/categories/${id}`, data),
  removeCategory: (id) => http.delete(`/handbook/categories/${id}`),
  createItem: (formData) => http.post('/handbook/items', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  updateItem: (id, formData) => http.put(`/handbook/items/${id}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  removeItem: (id) => http.delete(`/handbook/items/${id}`),
  download: (id) => http.get(`/handbook/items/${id}/download`, { responseType: 'blob' }),
}

export const specialApi = {
  list: (include_inactive = false) => http.get('/specials', { params: { include_inactive } }),
  create: (data) => http.post('/specials', data),
  update: (id, data) => http.put(`/specials/${id}`, data),
  remove: (id) => http.delete(`/specials/${id}`),
  detail: (id) => http.get(`/specials/${id}`),
  // 总览：七列全部由服务端从各专项自己的字段推出来，只有点灯能改
  overview: (include_inactive = false) => http.get('/specials/overview', { params: { include_inactive } }),
  setOverviewLight: (id, light, version) => http.put(`/specials/${id}/overview`, { light, version }),
  exportOverviewPptx: (include_inactive = false) =>
    http.get('/specials/overview.pptx', { responseType: 'blob', params: { include_inactive } }),
  updateContent: (id, data) => http.put(`/specials/${id}/content`, data),
  uploadPanorama: (id, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post(`/specials/${id}/panorama`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  // 分段图片（图片分段可多张；引用随 extra_grids_json 保存）
  uploadBlockImage: (id, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post(`/specials/${id}/images`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  deleteBlockImage: (id, stored) => http.delete(`/specials/${id}/images/${stored}`),
  panoramaUrl: (id) => `/api/specials/${id}/panorama`,
  listTasks: (id) => http.get(`/specials/${id}/tasks`),
  createTask: (id, data) => http.post(`/specials/${id}/tasks`, data),
  updateTask: (item_id, data) => http.put(`/specials/tasks/${item_id}`, data),
  removeTask: (item_id) => http.delete(`/specials/tasks/${item_id}`),
  listRisks: (id) => http.get(`/specials/${id}/risks`),
  createRisk: (id, data) => http.post(`/specials/${id}/risks`, data),
  updateRisk: (item_id, data) => http.put(`/specials/risks/${item_id}`, data),
  removeRisk: (item_id) => http.delete(`/specials/risks/${item_id}`),
  // 编辑锁：getLock 查询状态；acquireLock 取锁/心跳（force=管理员强制接管）；releaseLock 释放
  getLock: (id) => http.get(`/specials/${id}/lock`),
  acquireLock: (id, force = false) => http.post(`/specials/${id}/lock`, null, { params: { force } }),
  releaseLock: (id) => http.delete(`/specials/${id}/lock`),
  reportDraft: (id) => http.get(`/specials/${id}/report-draft`),
  reportEml: (id, payload) => http.post(`/specials/${id}/report.eml`, payload, { responseType: 'blob' }),
  exportXlsx: (id) => http.get(`/specials/${id}/export.xlsx`, { responseType: 'blob' }),
  // 套用版式模板（仅 admin）：只增不删，version 走乐观锁
  applyTemplate: (id, template_id, version) =>
    http.post(`/specials/${id}/apply-template`, { template_id, version }),
}

// 专项版式模板（主数据）：读开放给登录用户，增删改仅 admin
export const specialTemplateApi = {
  list: (params = {}) => http.get('/special-templates', { params }),
  get: (id) => http.get(`/special-templates/${id}`),
  create: (data) => http.post('/special-templates', data),
  update: (id, data) => http.put(`/special-templates/${id}`, data),
  remove: (id) => http.delete(`/special-templates/${id}`),
  // 内置分段清单（key / 默认标题 / 可选列格式），模板编辑页列选项用
  sections: () => http.get('/special-templates/sections'),
}

export const userApi = {
  list: () => http.get('/users'),
  options: (params = {}) => http.get('/users/options', { params }),
  create: (data) => http.post('/users', data),
  update: (id, data) => http.put(`/users/${id}`, data),
  remove: (id) => http.delete(`/users/${id}`),
}

export const resourceGroupApi = {
  list: (params = {}) => http.get('/resource-groups', { params }),
  get: (id) => http.get(`/resource-groups/${id}`),
  create: (data) => http.post('/resource-groups', data),
  update: (id, data) => http.put(`/resource-groups/${id}`, data),
  remove: (id) => http.delete(`/resource-groups/${id}`),
}

export const mappingApi = {
  customerUnmapped: () => http.get('/mapping/customers/unmapped'),
  customerAutoFill: () => http.post('/mapping/customers/auto-fill'),
  customerAssign: (data) => http.put('/mapping/customers/assign', data),
  personUnmapped: () => http.get('/mapping/persons/formation-unmapped'),
  personAutoFill: () => http.post('/mapping/persons/auto-fill'),
  personAssign: (data) => http.put('/mapping/persons/assign', data),
  personCreateFromMember: (data) => http.post('/mapping/persons/create-from-member', data),
}

export const metricsApi = {
  // params 里可带 project_id：项目挂在需求行上，传了就只统计该项目的需求，
  // 未填项目的老数据不计入任何项目（后端回一个 unassigned 让页面提示去补）。
  version: (release_version_id, params = {}) =>
    http.get(`/metrics/version/${release_version_id}`, { params }),
  iteration: (iteration_id, params = {}) =>
    http.get(`/metrics/iteration/${iteration_id}`, { params }),
  iterationQuality: (year, params = {}) =>
    http.get(`/metrics/iteration-quality/${year}`, { params }),
  // 领域质量按**迭代**切、版本质量按**整个版本**切：领域是按月排活的，
  // 版本是跨月的，按月截一刀会得到一个既不是这个版本也不是这个月的数。
  domainQuality: (iteration_id, params = {}) =>
    http.get(`/metrics/domain-quality/${iteration_id}`, { params }),
  // 注意这里的 project 是**问题单的采集项目**（字符串，如 YLS3000），
  // 与看板顶部的「度量项目」（需求上的 roadmap_projects FK）不是一回事。
  issueOverdue: (project) =>
    http.get('/metrics/issue-overdue', { params: { project: project || undefined } }),
  group: (group_id, params = {}) => http.get(`/metrics/group/${group_id}`, { params }),
}

export const notificationApi = {
  list: (params = {}) => http.get('/notifications', { params }),
  unreadCount: () => http.get('/notifications/unread-count'),
  markRead: (id) => http.post(`/notifications/${id}/read`),
  markAllRead: () => http.post('/notifications/read-all'),
  listSubs: () => http.get('/notifications/subscriptions'),
  addSub: (data) => http.post('/notifications/subscriptions', data),
  removeSub: (params) => http.delete('/notifications/subscriptions', { params }),
  broadcast: (data) => http.post('/notifications/broadcast', data),
}

export const configApi = {
  get: () => http.get('/config'),
  save: (data) => http.put('/config', data),
}

export const issueApi = {
  listDates:    ()     => http.get('/issues/dates'),
  getData:      (date) => http.get('/issues/data', date ? { params: { date } } : {}),
  getTrend:     ()     => http.get('/issues/trend'),
  scriptStatus: ()     => http.get('/issues/run-script/status'),
  runScript:    ()     => http.post('/issues/run-script'),
  exportPptx:   (date) => http.get('/issues/export.pptx', { responseType: 'blob', ...(date ? { params: { date } } : {}) }),
  // 每日快照：库存数字（趋势）+ 文件存明细（某次统计）
  snapshotList:    (project)            => http.get('/issues/snapshots', { params: { project } }),
  snapshotDetail:  (project, date)      => http.get('/issues/snapshot-detail', { params: date ? { project, date } : { project } }),
  snapshotTrend:   (project, dimension) => http.get('/issues/snapshot-trend', { params: { project, dimension } }),
  // 每日新增/解决：相邻快照差分（后端算好落库，这里只取数字）
  snapshotFlow:    (project)            => http.get('/issues/snapshot-flow', { params: { project } }),
  flowDetail:      (project, date, kind) => http.get('/issues/flow-detail', { params: { project, date, kind } }),
  // 归不到小组的责任人：小组名单的待办清单，从最新快照现算（名单一改就跟着变）
  ungrouped:       (project, date)      => http.get('/issues/ungrouped', { params: date ? { project, date } : { project } }),
  // 采集是长任务（几分钟），后端起线程立即返回，前端轮询 collectStatus 拿结果
  snapshotCollect: (project)            => http.post('/issues/snapshot-collect', null, { params: project ? { project } : {} }),
  collectStatus:   ()                   => http.get('/issues/collect-status'),
  collectLogs:     (project, limit = 50) => http.get('/issues/collect-logs', { params: project ? { project, limit } : { limit } }),
  // 定时采集运行态：排查"采集日志里只有手动记录"用，见 scheduler.snapshot_job_status()
  collectSchedule: ()                   => http.get('/issues/collect-schedule'),
  snapshotExport:  (project, date)      => http.get('/issues/snapshot-export', { responseType: 'blob', params: date ? { project, date } : { project } }),
}

// 客户面「软件类问题 / 现场关键事务」条目：单机台清单与全战场汇总共用 list
export const customerIssueApi = {
  list:    (params = {}) => http.get('/customer-issues', { params }),
  summary: ()            => http.get('/customer-issues/summary'),
  create:  (data)        => http.post('/customer-issues', data),
  update:  (id, data)    => http.put(`/customer-issues/${id}`, data),
  remove:  (id)          => http.delete(`/customer-issues/${id}`),
  exportXlsx: (include_closed = true) =>
    http.get('/customer-issues/export.xlsx', { responseType: 'blob', params: { include_closed } }),
  importTemplate: () => http.get('/customer-issues/import-template.xlsx', { responseType: 'blob' }),
  importXlsx: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post('/customer-issues/import', fd)
  },
}

export const keyFeatureApi = {
  list:      ()         => http.get('/key-features'),
  byMachine: ()         => http.get('/key-features/by-machine'),
  create:    (data)     => http.post('/key-features', data),
  update:    (id, data) => http.put(`/key-features/${id}`, data),
  remove:    (id)       => http.delete(`/key-features/${id}`),
  setMachine: (machineId, feature_ids) => http.put(`/key-features/machine/${machineId}`, { feature_ids }),
  uploadAttachment: (id, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post(`/key-features/${id}/attachments`, fd)
  },
  addLink: (id, name, url) => {
    const fd = new FormData()
    fd.append('name', name)
    fd.append('url', url)
    return http.post(`/key-features/${id}/links`, fd)
  },
  removeAttachment: (id, attId) => http.delete(`/key-features/${id}/attachments/${attId}`),
  downloadAttachment: (id, stored) => http.get(`/key-features/${id}/attachments/${stored}`, { responseType: 'blob' }),
}

export const hardwareIssueApi = {
  list:    ()         => http.get('/hardware-issues'),
  machineSummary: ()  => http.get('/hardware-issues/machine-summary'),
  create:  (data)     => http.post('/hardware-issues', data),
  update:  (id, data) => http.put(`/hardware-issues/${id}`, data),
  remove:  (id)       => http.delete(`/hardware-issues/${id}`),
  exportXlsx:     () => http.get('/hardware-issues/export.xlsx', { responseType: 'blob' }),
  importTemplate: () => http.get('/hardware-issues/import-template.xlsx', { responseType: 'blob' }),
  importXlsx: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post('/hardware-issues/import', fd)
  },
}

export const customerApi = {
  list: (include_inactive = false) => http.get('/customers', { params: { include_inactive } }),
  get: (id) => http.get(`/customers/${id}`),
  create: (data) => http.post('/customers', data),
  update: (id, data) => http.put(`/customers/${id}`, data),
  remove: (id) => http.delete(`/customers/${id}`),
  resolve: (name) => http.get('/customers/resolve', { params: { name } }),
  machines: (id) => http.get(`/customers/${id}/machines`),
}

export const sowApi = {
  // 字段定义（全局共享）
  listFields: (include_inactive = false) => http.get('/sow/fields', { params: { include_inactive } }),
  createField: (data) => http.post('/sow/fields', data),
  updateField: (id, data) => http.put(`/sow/fields/${id}`, data),
  removeField: (id) => http.delete(`/sow/fields/${id}`),
  // 每台机台的行
  listRows: (machine_status_id) => http.get('/sow/rows', { params: { machine_status_id } }),
  createRow: (machine_status_id, data) => http.post('/sow/rows', data, { params: { machine_status_id } }),
  updateRow: (id, data) => http.put(`/sow/rows/${id}`, data),
  removeRow: (id) => http.delete(`/sow/rows/${id}`),
}

export const licenseApi = {
  list: (machine_status_id) => http.get('/licenses', { params: { machine_status_id } }),
  upload: ({ machine_status_id, file, remark = '' }) => {
    const fd = new FormData()
    fd.append('machine_status_id', String(machine_status_id))
    fd.append('remark', remark)
    fd.append('file', file)
    return http.post('/licenses', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  updateRemark: (id, remark) => {
    const fd = new FormData()
    fd.append('remark', remark)
    return http.put(`/licenses/${id}`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  remove: (id) => http.delete(`/licenses/${id}`),
  download: (id) => http.get(`/licenses/${id}/download`, { responseType: 'blob' }),
}

export const customerStatusApi = {
  list: () => http.get('/customer-status'),
  create: (data) => http.post('/customer-status', data),
  update: (id, data) => http.put(`/customer-status/${id}`, data),
  remove: (id) => http.delete(`/customer-status/${id}`),
  exportPptx: () => http.get('/customer-status/export.pptx', { responseType: 'blob' }),
}

export const customerExtraApi = {
  // 信息块定义（全局共享）
  listFields: (include_inactive = false) => http.get('/customer-extra/fields', { params: { include_inactive } }),
  createField: (data) => http.post('/customer-extra/fields', data),
  updateField: (id, data) => http.put(`/customer-extra/fields/${id}`, data),
  removeField: (id) => http.delete(`/customer-extra/fields/${id}`),
  // 每台机台的值
  listValues: (machine_status_id) => http.get('/customer-extra/values', { params: { machine_status_id } }),
  saveText: (machine_status_id, field_id, text) =>
    http.put('/customer-extra/values', { machine_status_id, field_id, text }),
  uploadAttachment: ({ machine_status_id, field_id, file }) => {
    const fd = new FormData()
    fd.append('machine_status_id', String(machine_status_id))
    fd.append('field_id', String(field_id))
    fd.append('file', file)
    return http.post('/customer-extra/values/attachment', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  downloadAttachment: (value_id) => http.get(`/customer-extra/values/${value_id}/attachment`, { responseType: 'blob' }),
  removeAttachment: (value_id) => http.delete(`/customer-extra/values/${value_id}/attachment`),
}

export const customerCustomReqApi = {
  list: (customer_id) => http.get('/customer-custom-reqs', { params: { customer_id } }),
  create: (data) => http.post('/customer-custom-reqs', data),
  update: (id, data) => http.put(`/customer-custom-reqs/${id}`, data),
  remove: (id) => http.delete(`/customer-custom-reqs/${id}`),
}

// 版本三层：大版本（C10SPC100）→ 版本（C10SPC101）→ 迭代版本（C10SPC101B001）。
// 哪一层给谁用见 backend/routers/major_versions.py 顶部：
// 客户面用「版本」，迭代管理与问题单用「迭代版本」，达成率看「版本」。
// 问题单跟踪（进展 + 合入计划）。按「项目 + 缺陷编号」认领，与每天的快照解耦——
// 挂在快照上的话第二天重采就全丢了，页面上只表现成"昨天填的怎么没了"。
export const issueTrackApi = {
  list: (project) => http.get('/issue-tracks', { params: { project } }),
  // upsert：问题单不是我们建的，第一次填时"这条记录存不存在"是实现细节，
  // 不该让页面先查一次再决定调哪个接口
  save: (data) => http.put('/issue-tracks', data),
}

export const majorVersionApi = {
  list: (project_id) => http.get('/major-versions', { params: project_id != null ? { project_id } : {} }),
  create: (data) => http.post('/major-versions', data),
  update: (id, data) => http.put(`/major-versions/${id}`, data),
  remove: (id) => http.delete(`/major-versions/${id}`),
  // 主干只能整体切换：后端会把同项目的原主干一并降为分支，别做成普通字段
  setMaster: (id) => http.post(`/major-versions/${id}/set-master`),
  // 排序整体提交：{ parent_id, ids }。逐个 PUT sort_order 会留下「排到一半」的顺序，
  // 而顺序错了不报错，只是看着不对
  reorderReleases: (parent_id, ids) => http.post('/release-versions/reorder', { parent_id, ids }),
  reorderIterVersions: (parent_id, ids) =>
    http.post('/iteration-versions/reorder', { parent_id, ids }),
  allReleaseVersions: () => http.get('/release-versions/all'),
  createRelease: (data) => http.post('/release-versions', data),
  updateRelease: (id, data) => http.put(`/release-versions/${id}`, data),
  removeRelease: (id) => http.delete(`/release-versions/${id}`),
  allIterationVersions: () => http.get('/iteration-versions/all'),
  createIterVersion: (data) => http.post('/iteration-versions', data),
  updateIterVersion: (id, data) => http.put(`/iteration-versions/${id}`, data),
  removeIterVersion: (id) => http.delete(`/iteration-versions/${id}`),
}

export const annualIterationApi = {
  years: () => http.get('/annual-iterations/years'),
  list: (year) => http.get('/annual-iterations', { params: { year } }),
  get: (id) => http.get(`/annual-iterations/${id}`),
  update: (id, data) => http.put(`/annual-iterations/${id}`, data),
  exportPptx: (id) => http.get(`/annual-iterations/${id}/export.pptx`, { responseType: 'blob' }),
}

export const iterationRequirementApi = {
  list: (iteration_id, params = {}) =>
    http.get('/iteration-requirements', { params: { iteration_id, ...params } }),
  byVersion: (version_id) => http.get('/iteration-requirements/by-version', { params: { version_id } }),
  duplicates: (iteration_id) => http.get('/iteration-requirements/duplicates', { params: { iteration_id } }),
  create: (data) => http.post('/iteration-requirements', data),
  update: (id, data) => http.put(`/iteration-requirements/${id}`, data),
  remove: (id) => http.delete(`/iteration-requirements/${id}`),
  importTemplate: () => http.get('/iteration-requirements/import-template.xlsx', { responseType: 'blob' }),
  importExcel: (iteration_id, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post('/iteration-requirements/import', fd, {
      params: { iteration_id },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}

export const domainApi = {
  // params: { year, month, release_version_id, include_hidden, project }
  //（不传＝进行中迭代 + 第一个有快照的项目；给了 release_version_id 就按版本、忽略 year/month）
  list: (params) => http.get('/domains', { params }),
  requirements: (groupId, params) => http.get(`/domains/${groupId}/requirements`, { params }),
  issues: (groupId, params) => http.get(`/domains/${groupId}/issues`, { params }),
  updateContent: (groupId, data) => http.put(`/domains/${groupId}/content`, data),
  setVisibility: (groupId, hidden) => http.put(`/domains/${groupId}/visibility`, { hidden }),
  // 事务与风险跟踪
  riskList: (params) => http.get('/domains/risks', { params }),
  riskCreate: (data) => http.post('/domains/risks', data),
  riskUpdate: (id, data) => http.put(`/domains/risks/${id}`, data),
  riskRemove: (id) => http.delete(`/domains/risks/${id}`),
  // 遗留问题
  legacyList: (params) => http.get('/domains/legacy-issues', { params }),
  legacyCreate: (data) => http.post('/domains/legacy-issues', data),
  legacyUpdate: (id, data) => http.put(`/domains/legacy-issues/${id}`, data),
  legacyRemove: (id) => http.delete(`/domains/legacy-issues/${id}`),
  // 问题单目标（读开放，写仅 admin）
  issueTargets: (project) => http.get('/domains/issue-targets', { params: { project } }),
  saveIssueTargets: (data) => http.put('/domains/issue-targets', data),
}

export const debugVersionApi = {
  list: () => http.get('/debug-versions'),
  create: (data) => http.post('/debug-versions', data),
  update: (id, data) => http.put(`/debug-versions/${id}`, data),
  remove: (id) => http.delete(`/debug-versions/${id}`),
  dashboard: () => http.get('/debug-versions/dashboard'),
  // 接受版本姓名列表
  recipients: (vid) => http.get(`/debug-versions/${vid}/recipients`),
  autoMatchRecipients: (vid) => http.post(`/debug-versions/${vid}/recipients/auto-match`),
  addRecipient: (vid, data) => http.post(`/debug-versions/${vid}/recipients`, data),
  updateRecipient: (rid, data) => http.put(`/debug-versions/recipients/${rid}`, data),
  removeRecipient: (rid) => http.delete(`/debug-versions/recipients/${rid}`),
}

export const debugDemandApi = {
  list: () => http.get('/debug-demands'),
  create: (data) => http.post('/debug-demands', data),
  update: (id, data) => http.put(`/debug-demands/${id}`, data),
  remove: (id) => http.delete(`/debug-demands/${id}`),
}

export const businessTripApi = {
  // params: { user_id?, customer_id?, project_id?, support_mode? }
  list: (params) => http.get('/business-trips', { params }),
  // params: { start?, end?, project_id?, support_mode? }
  // 看板返回人次与工作量（人天）两套数字，人天口径见后端 _man_days_in
  dashboard: (params) => http.get('/business-trips/dashboard', { params }),
  create: (data) => http.post('/business-trips', data),
  update: (id, data) => http.put(`/business-trips/${id}`, data),
  remove: (id) => http.delete(`/business-trips/${id}`),
}

export const productRequirementApi = {
  list: (iteration_id, params = {}) =>
    http.get('/iteration-product-requirements', { params: { iteration_id, ...params } }),
  byVersion: (version_id) => http.get('/iteration-product-requirements/by-version', { params: { version_id } }),
  duplicates: (iteration_id) => http.get('/iteration-product-requirements/duplicates', { params: { iteration_id } }),
  create: (data) => http.post('/iteration-product-requirements', data),
  update: (id, data) => http.put(`/iteration-product-requirements/${id}`, data),
  remove: (id) => http.delete(`/iteration-product-requirements/${id}`),
  importTemplate: () => http.get('/iteration-product-requirements/import-template.xlsx', { responseType: 'blob' }),
  importExcel: (iteration_id, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post('/iteration-product-requirements/import', fd, {
      params: { iteration_id },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}

export const stakeholderApi = {
  listProjectContacts: () => http.get('/stakeholders/project-contacts'),
  createProjectContact: (data) => http.post('/stakeholders/project-contacts', data),
  updateProjectContact: (id, data) => http.put(`/stakeholders/project-contacts/${id}`, data),
  removeProjectContact: (id) => http.delete(`/stakeholders/project-contacts/${id}`),

  listBattlefields: () => http.get('/stakeholders/battlefields'),
  createBattlefield: (data) => http.post('/stakeholders/battlefields', data),
  updateBattlefield: (id, data) => http.put(`/stakeholders/battlefields/${id}`, data),
  removeBattlefield: (id) => http.delete(`/stakeholders/battlefields/${id}`),
}

export const roadmapApi = {
  listProjects: (include_inactive = false) =>
    http.get('/roadmap/projects', { params: { include_inactive } }),
  getProject: (id) => http.get(`/roadmap/projects/${id}`),
  createProject: (data) => http.post('/roadmap/projects', data),
  updateProject: (id, data) => http.put(`/roadmap/projects/${id}`, data),
  removeProject: (id) => http.delete(`/roadmap/projects/${id}`),

  createPhase: (data) => http.post('/roadmap/phases', data),
  updatePhase: (id, data) => http.put(`/roadmap/phases/${id}`, data),
  removePhase: (id) => http.delete(`/roadmap/phases/${id}`),

  createMilestone: (data) => http.post('/roadmap/milestones', data),
  updateMilestone: (id, data) => http.put(`/roadmap/milestones/${id}`, data),
  removeMilestone: (id) => http.delete(`/roadmap/milestones/${id}`),
}

// 修订历史（只读——能改的历史就不是历史了，服务端也没有写接口）
export const historyApi = {
  // scope 形如 special:12 / domain:3 / customer:7 / hardware:0；
  // 也可按行查（entity + entity_id）。至少要给一个，否则服务端 400。
  list: (params) => http.get('/history', { params }),
  // 某一行在某个时刻的样子。at 传**本地时间**，服务端自己换算成 UTC 去比。
  at: (entity, entity_id, at) => http.get('/history/at', { params: { entity, entity_id, at } }),
  // 实体 / 列名对照由服务端给，前端不要再存一份（加一列时总有一处会漏）
  entities: () => http.get('/history/entities'),
}

// 整页存档（每周自动 + 手工）
export const archiveApi = {
  kinds: () => http.get('/archives/kinds'),
  targets: (kind) => http.get('/archives/targets', { params: { kind } }),
  list: (params) => http.get('/archives', { params }),
  get: (id) => http.get(`/archives/${id}`),
  // 回看用的 HTML 由服务端渲染：专项走的就是周报那一份，另写一套必然分叉。
  // 走 axios 而不是把 URL 塞进 iframe 的 src——接口要带 token，iframe 发不出请求头，
  // 表现是存档页一片空白而控制台里是 401。拿到 HTML 后用 srcdoc 挂进去。
  view: (id) => http.get(`/archives/${id}/view`, { responseType: 'text' }),
  create: (kind, ref_id) => http.post('/archives', { kind, ref_id }),
  remove: (id) => http.delete(`/archives/${id}`),
}

export function downloadBlob(blob, filename) {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.URL.revokeObjectURL(url)
}

export default http
