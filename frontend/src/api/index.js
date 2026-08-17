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
  version: (major_version_id) => http.get(`/metrics/version/${major_version_id}`),
  iteration: (iteration_id) => http.get(`/metrics/iteration/${iteration_id}`),
  iterationQuality: (year) => http.get(`/metrics/iteration-quality/${year}`),
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
  // 采集是长任务（几分钟），后端起线程立即返回，前端轮询 collectStatus 拿结果
  snapshotCollect: (project)            => http.post('/issues/snapshot-collect', null, { params: project ? { project } : {} }),
  collectStatus:   ()                   => http.get('/issues/collect-status'),
  collectLogs:     (project, limit = 50) => http.get('/issues/collect-logs', { params: project ? { project, limit } : { limit } }),
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

// 遗留版本表：只读，仅项目简介页消费旧数据；写接口已在后端下线
export const majorVersionApi = {
  list: (project_id) => http.get('/major-versions', { params: project_id != null ? { project_id } : {} }),
  create: (data) => http.post('/major-versions', data),
  update: (id, data) => http.put(`/major-versions/${id}`, data),
  remove: (id) => http.delete(`/major-versions/${id}`),
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
  list: (iteration_id) => http.get('/iteration-requirements', { params: { iteration_id } }),
  byVersion: (version_id) => http.get('/iteration-requirements/by-version', { params: { version_id } }),
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
  // params: { year, month, include_hidden }（不传＝当前进行中迭代口径）
  list: (params) => http.get('/domains', { params }),
  requirements: (groupId, params) => http.get(`/domains/${groupId}/requirements`, { params }),
  issues: (groupId) => http.get(`/domains/${groupId}/issues`),
  updateContent: (groupId, data) => http.put(`/domains/${groupId}/content`, data),
  setVisibility: (groupId, hidden) => http.put(`/domains/${groupId}/visibility`, { hidden }),
  // 事务与风险跟踪
  riskList: (params) => http.get('/domains/risks', { params }),
  riskCreate: (data) => http.post('/domains/risks', data),
  riskUpdate: (id, data) => http.put(`/domains/risks/${id}`, data),
  riskRemove: (id) => http.delete(`/domains/risks/${id}`),
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
  // params: { user_id?, customer_id? }
  list: (params) => http.get('/business-trips', { params }),
  dashboard: (params) => http.get('/business-trips/dashboard', { params }),
  create: (data) => http.post('/business-trips', data),
  update: (id, data) => http.put(`/business-trips/${id}`, data),
  remove: (id) => http.delete(`/business-trips/${id}`),
}

export const productRequirementApi = {
  list: (iteration_id) => http.get('/iteration-product-requirements', { params: { iteration_id } }),
  byVersion: (version_id) => http.get('/iteration-product-requirements/by-version', { params: { version_id } }),
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
