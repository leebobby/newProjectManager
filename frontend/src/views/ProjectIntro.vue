<template>
  <div class="intro-page">
    <div class="hero">
      <div class="hero-inner">
        <div class="hero-tag">岳麓山 · 项目管理</div>
        <h1 class="hero-title">岳麓山项目管理系统</h1>
        <p class="hero-sub">
          统一管理客户面状态、版本发布与迭代规划，让团队成员实时同步进度、关键问题与变更。
        </p>
        <div class="hero-stack">
          <span v-for="(b, i) in heroBadges" :key="i" class="badge" :class="`badge-c${i % 4}`">{{ b }}</span>
          <button v-if="isAdmin" class="badge-edit-btn" title="编辑标签" @click="startEditBadges">
            <el-icon><Edit /></el-icon>
          </button>
        </div>
        <div class="hero-stats">
          <div class="stat-item">
            <div class="stat-num">{{ stats.versions }}</div>
            <div class="stat-label">版本</div>
          </div>
          <div class="stat-divider" />
          <div class="stat-item">
            <div class="stat-num">{{ stats.iterations }}</div>
            <div class="stat-label">迭代</div>
          </div>
          <div class="stat-divider" />
          <div class="stat-item">
            <div class="stat-num">{{ stats.machines }}</div>
            <div class="stat-label">机台</div>
          </div>
        </div>
      </div>
    </div>

    <el-card v-if="roadmaps.length || roadmapsLoading" shadow="never" class="roadmap-section">
      <template #header>
        <span class="card-title"><el-icon><Guide /></el-icon> 项目里程碑</span>
        <span v-if="isAdmin" class="card-hint">
          <el-link type="primary" :underline="false" @click="$router.push('/roadmaps')">
            管理里程碑 <el-icon><Right /></el-icon>
          </el-link>
        </span>
      </template>
      <div v-if="roadmapsLoading" class="loading-hint">加载中…</div>
      <div v-else class="roadmap-stack">
        <RoadmapTimeline v-for="p in roadmaps" :key="p.id" :project="p" />
      </div>
    </el-card>

    <el-card shadow="never" class="modules-card">
      <template #header>
        <span class="card-title"><el-icon><Grid /></el-icon> 系统模块</span>
        <span class="card-hint">点击卡片快速进入对应模块</span>
      </template>
      <el-row :gutter="20">
        <el-col :xs="24" :sm="12" :md="8" v-for="m in modules" :key="m.path">
          <div class="module-card" :class="m.theme" @click="$router.push(m.path)" tabindex="0" @keyup.enter="$router.push(m.path)">
            <div class="module-icon"><el-icon><component :is="m.icon" /></el-icon></div>
            <div class="module-meta">
              <h3>{{ m.title }}</h3>
              <p>{{ m.desc }}</p>
              <span class="module-link">进入 <el-icon><Right /></el-icon></span>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 标签编辑 Dialog -->
    <el-dialog v-model="badgesDialogVisible" title="编辑标签" width="400px" @close="cancelEditBadges">
      <div v-for="(b, i) in badgesDraft" :key="i" class="badge-draft-row">
        <el-input v-model="badgesDraft[i]" placeholder="标签文字" size="small" />
        <el-button :icon="Delete" circle size="small" type="danger" plain @click="badgesDraft.splice(i, 1)" />
      </div>
      <el-button
        v-if="badgesDraft.length < 8"
        :icon="Plus"
        size="small"
        style="margin-top: 8px"
        @click="badgesDraft.push('')"
      >添加标签</el-button>
      <template #footer>
        <el-button @click="cancelEditBadges">取消</el-button>
        <el-button type="primary" :loading="badgesSaving" @click="saveBadges">保存</el-button>
      </template>
    </el-dialog>

    <el-card shadow="never" class="about-card">
      <template #header>
        <span class="card-title"><el-icon><InfoFilled /></el-icon> 关于</span>
        <el-button v-if="isAdmin && !aboutEditing" size="small" :icon="Edit" @click="startEditAbout">编辑</el-button>
        <div v-if="isAdmin && aboutEditing" style="display:inline-flex;gap:8px">
          <el-button size="small" type="primary" :loading="aboutSaving" @click="saveAbout">保存</el-button>
          <el-button size="small" @click="cancelEditAbout">取消</el-button>
        </div>
      </template>
      <el-input
        v-if="aboutEditing"
        v-model="aboutDraft"
        type="textarea"
        :rows="6"
        placeholder="输入关于内容（支持换行）"
      />
      <div v-else class="about-content">{{ aboutContent }}</div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Delete, Edit, Plus } from '@element-plus/icons-vue'
import { auth } from '../store/auth'
import {
  annualIterationApi,
  configApi,
  customerStatusApi,
  majorVersionApi,
  roadmapApi,
} from '../api'
import RoadmapTimeline from './RoadmapTimeline.vue'

const isAdmin = auth.isAdmin

const modules = [
  {
    title: '客户面状态',
    desc: '机台分阶段进展、关注度、关键诉求、风险问题与问题单。',
    icon: 'DataLine',
    path: '/customer-status',
    theme: 't-blue',
  },
  {
    title: '版本管理',
    desc: '大版本/迭代版本两级规划、版本计划图与现场调试版本（T版本）。',
    icon: 'Files',
    path: '/versions',
    theme: 't-green',
  },
  {
    title: '迭代管理',
    desc: '年度 12 月迭代规划、需求清单、6 段交付进展跟踪与导出。',
    icon: 'Calendar',
    path: '/iterations',
    theme: 't-orange',
  },
  ...(isAdmin.value
    ? [{
        title: '用户管理',
        desc: '账号、角色、启停与重置密码（仅管理员）。',
        icon: 'User',
        path: '/users',
        theme: 't-purple',
      }]
    : []),
]

const stats = reactive({ versions: '-', iterations: '-', machines: '-' })

const roadmaps = ref([])
const roadmapsLoading = ref(true)

// ── 标签（hero badges）──────────────────────────────
const DEFAULT_BADGES = ['Python · FastAPI', 'Vue 3 · Element Plus', 'SQLite · SQLAlchemy', 'JWT · bcrypt']
const heroBadges          = ref([...DEFAULT_BADGES])
const badgesDialogVisible = ref(false)
const badgesDraft         = ref([])
const badgesSaving        = ref(false)

function startEditBadges() {
  badgesDraft.value = [...heroBadges.value]
  badgesDialogVisible.value = true
}

function cancelEditBadges() {
  badgesDialogVisible.value = false
}

async function saveBadges() {
  badgesSaving.value = true
  try {
    const filtered = badgesDraft.value.map(b => b.trim()).filter(Boolean)
    await configApi.save({ hero_badges: filtered })
    heroBadges.value = filtered.length ? filtered : [...DEFAULT_BADGES]
    badgesDialogVisible.value = false
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    badgesSaving.value = false
  }
}

// ── 关于内容 ──────────────────────────────────────────
const aboutContent  = ref('')
const aboutEditing  = ref(false)
const aboutDraft    = ref('')
const aboutSaving   = ref(false)

async function loadAbout() {
  try {
    const { data } = await configApi.get()
    aboutContent.value = data.about_content || ''
    if (Array.isArray(data.hero_badges) && data.hero_badges.length) {
      heroBadges.value = data.hero_badges
    }
  } catch { /* 非阻塞 */ }
}

function startEditAbout() {
  aboutDraft.value  = aboutContent.value
  aboutEditing.value = true
}

function cancelEditAbout() {
  aboutEditing.value = false
}

async function saveAbout() {
  aboutSaving.value = true
  try {
    await configApi.save({ about_content: aboutDraft.value })
    aboutContent.value = aboutDraft.value
    aboutEditing.value = false
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    aboutSaving.value = false
  }
}

async function loadRoadmaps() {
  roadmapsLoading.value = true
  try {
    const { data } = await roadmapApi.listProjects(false)
    roadmaps.value = data
  } catch (e) {
    /* 不阻塞 */
  } finally {
    roadmapsLoading.value = false
  }
}

async function loadStats() {
  try {
    const [v, m] = await Promise.all([
      majorVersionApi.list(),   // 两级版本体系：首页统计数的是大版本
      customerStatusApi.list(),
    ])
    stats.versions = v.data.length
    stats.machines = m.data.length
  } catch (e) { /* 不阻塞 */ }
  try {
    const year = new Date().getFullYear()
    const { data } = await annualIterationApi.list(year)
    stats.iterations = data.filter(it => it.name).length || data.length
  } catch (e) { /* 不阻塞 */ }
}

onMounted(() => {
  loadStats()
  loadRoadmaps()
  loadAbout()
})
</script>

<style scoped>
.intro-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.hero {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  background: linear-gradient(135deg, #1b3a6b 0%, #2c558c 35%, #4073ba 100%);
  color: #fff;
  padding: 32px 36px;
  box-shadow: 0 8px 24px -12px rgba(31, 45, 61, 0.45);
}
.hero::before, .hero::after {
  content: '';
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.05);
  pointer-events: none;
}
.hero::before { width: 240px; height: 240px; right: -60px; top: -80px; }
.hero::after  { width: 160px; height: 160px; right: 140px; bottom: -80px; background: rgba(255, 255, 255, 0.07); }

.hero-inner { position: relative; z-index: 1; }
.hero-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  background: rgba(255,255,255,0.16);
  font-size: 12px;
  letter-spacing: 1.5px;
  margin-bottom: 12px;
}
.hero-title {
  font-size: 30px;
  margin: 0 0 8px 0;
  letter-spacing: 1px;
}
.hero-sub {
  margin: 0 0 18px 0;
  color: rgba(255,255,255,0.85);
  max-width: 720px;
  line-height: 1.65;
}
.hero-stack {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 18px;
}
.badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  background: rgba(255,255,255,0.15);
  border: 1px solid rgba(255,255,255,0.2);
}
.badge-c0 { background: rgba(255, 209, 102, 0.18); border-color: rgba(255, 209, 102, 0.5); }
.badge-c1 { background: rgba(102, 217, 171, 0.18); border-color: rgba(102, 217, 171, 0.5); }
.badge-c2 { background: rgba(110, 172, 255, 0.20); border-color: rgba(110, 172, 255, 0.55); }
.badge-c3 { background: rgba(245, 130, 130, 0.18); border-color: rgba(245, 130, 130, 0.5); }

.badge-edit-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.25);
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
  padding: 0;
}
.badge-edit-btn:hover {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
}

.badge-draft-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.hero-stats {
  display: flex;
  align-items: center;
  gap: 24px;
  margin-top: 4px;
}
.stat-item { display: flex; flex-direction: column; }
.stat-num { font-size: 26px; font-weight: 700; line-height: 1.1; }
.stat-label { font-size: 12px; color: rgba(255,255,255,0.7); }
.stat-divider { width: 1px; height: 28px; background: rgba(255,255,255,0.2); }

.modules-card :deep(.el-row) {
  row-gap: 16px;
}

.modules-card :deep(.el-card__header),
.about-card   :deep(.el-card__header),
.roadmap-section :deep(.el-card__header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.roadmap-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.loading-hint {
  text-align: center;
  color: #909399;
  padding: 24px 0;
  font-size: 13px;
}
.card-title { font-size: 16px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px; }
.card-hint  { color: #909399; font-size: 12px; }

.module-card {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  padding: 16px;
  border-radius: 8px;
  border: 1px solid #eaecef;
  cursor: pointer;
  transition: all 0.2s ease;
  background: #fff;
  height: 100%;
}
.module-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 24px -16px rgba(31, 45, 61, 0.3);
  border-color: transparent;
}
.module-card:focus-visible {
  outline: 2px solid #409EFF;
  outline-offset: 2px;
}
.module-icon {
  width: 44px; height: 44px;
  display: flex; align-items: center; justify-content: center;
  font-size: 22px;
  border-radius: 8px;
  color: #fff;
  flex-shrink: 0;
}
.t-blue   .module-icon { background: linear-gradient(135deg, #4073ba, #2c558c); }
.t-green  .module-icon { background: linear-gradient(135deg, #67c23a, #449728); }
.t-orange .module-icon { background: linear-gradient(135deg, #e6a23c, #b87f1e); }
.t-purple .module-icon { background: linear-gradient(135deg, #8e7ad8, #6b5ab8); }

.module-meta { flex: 1; min-width: 0; }
.module-meta h3 { margin: 0 0 4px 0; font-size: 16px; color: #303133; }
.module-meta p  { margin: 0 0 8px 0; color: #606266; font-size: 13px; line-height: 1.55; }
.module-link {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12px; color: #409EFF; font-weight: 500;
}

.about-content {
  color: #606266;
  line-height: 1.9;
  white-space: pre-wrap;
  font-size: 14px;
}
</style>
