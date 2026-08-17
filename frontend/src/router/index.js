import { createRouter, createWebHistory } from 'vue-router'
import { auth } from '../store/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { public: true, layout: 'blank' },
  },
  { path: '/', redirect: '/intro' },
  {
    path: '/intro',
    name: 'ProjectIntro',
    component: () => import('../views/ProjectIntro.vue'),
    meta: { title: '项目简介', icon: 'InfoFilled', group: '概览' },
  },
  {
    path: '/customer-status',
    name: 'CustomerStatus',
    component: () => import('../views/CustomerStatus.vue'),
    meta: { title: '客户面状态', icon: 'DataLine', customersParent: true, group: '客户面管理' },
  },
  {
    // 问题跟踪不再单独进侧边栏——它就是客户面状态的另一个视角，
    // 已收进 /customer-status 的「问题跟踪」tab。老链接重定向保持可用。
    path: '/customer-issues',
    redirect: (to) => ({ path: '/customer-status', query: { ...to.query, tab: 'issues' } }),
  },
  {
    path: '/customers',
    name: 'CustomerManagement',
    component: () => import('../views/CustomerManagement.vue'),
    meta: { title: '客户管理', icon: 'OfficeBuilding', hidden: true },
  },
  {
    path: '/customers/:id(\\d+)',
    name: 'CustomerDetail',
    component: () => import('../views/CustomerDetail.vue'),
    meta: { title: '客户详情', hidden: true },
  },
  {
    path: '/versions',
    name: 'VersionManagement',
    component: () => import('../views/VersionManagement.vue'),
    meta: { title: '版本管理', icon: 'Files', group: '进度管理' },
  },
  {
    path: '/iterations',
    name: 'IterationManagement',
    component: () => import('../views/IterationManagement.vue'),
    meta: { title: '迭代管理', icon: 'Calendar', group: '进度管理' },
  },
  {
    path: '/iterations/:id',
    name: 'IterationDetail',
    component: () => import('../views/IterationDetail.vue'),
    meta: { title: '迭代详情', hidden: true },
  },
  {
    path: '/issues',
    name: 'IssueManagement',
    component: () => import('../views/IssueManagement.vue'),
    meta: { title: '问题单管理', icon: 'Warning', group: '进度管理' },
  },
  {
    path: '/domains',
    name: 'DomainManagement',
    component: () => import('../views/DomainManagement.vue'),
    meta: { title: '领域管理', icon: 'Grid', group: '进度管理' },
  },
  {
    path: '/stakeholders',
    name: 'StakeholderManagement',
    component: () => import('../views/StakeholderManagement.vue'),
    meta: { title: '干系人管理', icon: 'Avatar', group: '组织管理' },
  },
  {
    path: '/business-trips',
    name: 'BusinessTripManagement',
    component: () => import('../views/BusinessTripManagement.vue'),
    meta: { title: '客户面支撑情况', icon: 'Suitcase', group: '客户面管理' },
  },
  {
    path: '/key-features',
    name: 'KeyFeatureManagement',
    component: () => import('../views/KeyFeatureManagement.vue'),
    meta: { title: '关键特性', icon: 'Opportunity', group: '进度管理' },
  },
  {
    path: '/roadmaps',
    name: 'RoadmapManage',
    component: () => import('../views/RoadmapManage.vue'),
    meta: { title: '里程碑管理', icon: 'Guide', requireAdmin: true, group: '概览' },
  },
  {
    path: '/handbook',
    name: 'ProjectHandbook',
    component: () => import('../views/ProjectHandbook.vue'),
    meta: { title: '项目一本通', icon: 'Notebook', group: '知识管理' },
  },
  {
    path: '/specials',
    name: 'SpecialList',
    // 路由本身不需要 requireAdmin（页面内自查），让左侧菜单的"专项管理"分组对普通用户也可见
    component: () => import('../views/SpecialList.vue'),
    meta: { title: '专项管理', icon: 'Briefcase', specialsParent: true, group: '进度管理' },
  },
  {
    path: '/specials/:id(\\d+)',
    name: 'SpecialDetail',
    component: () => import('../views/SpecialDetail.vue'),
    meta: { title: '专项详情', hidden: true },
  },
  {
    path: '/resource-groups',
    name: 'ResourceGroupManagement',
    component: () => import('../views/ResourceGroupManagement.vue'),
    meta: { title: '组织架构', icon: 'Connection', requireAdmin: true, group: '组织管理' },
  },
  {
    path: '/data-mapping',
    name: 'DataMapping',
    component: () => import('../views/DataMapping.vue'),
    meta: { title: '数据对账', icon: 'Link', requireAdmin: true, group: '系统管理' },
  },
  {
    path: '/metrics',
    name: 'MetricsDashboard',
    component: () => import('../views/MetricsDashboard.vue'),
    meta: { title: '度量看板', icon: 'TrendCharts', group: '质量管理' },
  },
  {
    path: '/users',
    name: 'UserManagement',
    component: () => import('../views/UserManagement.vue'),
    meta: { title: '用户管理', icon: 'User', requireAdmin: true, group: '系统管理' },
  },
  {
    path: '/op-logs',
    name: 'OperationLogs',
    component: () => import('../views/OperationLogs.vue'),
    meta: { title: '操作日志', icon: 'Document', requireAdmin: true, group: '系统管理' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.meta.public) return true
  if (!auth.isLoggedIn.value) return { path: '/login', query: { redirect: to.fullPath } }
  if (to.meta.requireAdmin && !auth.isAdmin.value) return { path: '/intro' }
  return true
})

export default router
