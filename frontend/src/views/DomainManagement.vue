<template>
  <div class="domain-page">
    <el-tabs v-model="activeTab" class="domain-tabs">
      <!-- ===== 领域总览 ===== -->
      <el-tab-pane label="领域总览" name="overview">
        <!-- 需求口径分标签：按迭代（月）或按版本，**二选一**。版本是跨迭代的，
             两者叠加会得到一个既不是这个版本、也不是这个迭代的数（见后端 _ReqScope）。
             版本标签只列当前挂着需求的版本，条数就是挂着多少条。 -->
        <el-tabs v-model="scopeTab" type="card" class="scope-tabs" @tab-change="onScopeChange">
          <el-tab-pane name="iteration" label="按迭代" />
          <el-tab-pane
            v-for="v in data.versions"
            :key="v.id"
            :name="String(v.id)"
            :label="`${v.version_no || '未命名'} (${v.req_count})`"
          />
        </el-tabs>

        <div class="page-head">
          <div class="head-left">
            <span class="muted">需求口径：</span>
            <el-select
              v-if="scopeTab === 'iteration'"
              v-model="monthKey"
              size="small"
              style="width: 210px"
              @change="load"
            >
              <el-option label="进行中迭代（默认）" value="" />
              <el-option
                v-for="it in data.iterations"
                :key="it.year + '-' + it.month"
                :value="it.year + '-' + it.month"
                :label="it.label + statusSuffix(it)"
              />
            </el-select>
            <span v-else class="muted">按版本统计，不限迭代月份</span>
            <el-tag type="primary" effect="plain" style="margin-left: 8px">{{ data.iteration_label || '—' }}</el-tag>

            <span class="muted" style="margin-left: 16px">问题单项目：</span>
            <el-select v-model="project" size="small" style="width: 190px" placeholder="（无可选项目）"
              :disabled="!data.projects.length" @change="load">
              <el-option v-for="p in data.projects" :key="p.project" :value="p.project"
                :label="p.project + (p.latest_date ? ` · ${p.latest_date}` : '（未采集）')" />
            </el-select>
            <el-tag v-if="issueMeta.available" type="success" effect="plain" style="margin-left: 6px">
              {{ issueMeta.source === 'excel' ? '报表文件' : '快照' }} {{ issueMeta.file_mtime || '' }}
            </el-tag>
            <el-tooltip v-else :content="issueMeta.note || '未接入'" placement="top">
              <el-tag type="info" effect="plain" style="margin-left: 6px">未接入</el-tag>
            </el-tooltip>
          </div>
          <div class="head-right">
            <el-button v-if="auth.isAdmin.value" :icon="Aim" @click="openTargets">设定目标</el-button>
            <el-checkbox v-model="showHidden" @change="load">显示已隐藏</el-checkbox>
            <el-button :icon="Refresh" :loading="loading" @click="load">刷新</el-button>
          </div>
        </div>

        <el-table :data="data.rows" border stripe v-loading="loading" class="domain-table"
          :row-class-name="(o) => (o.row.hidden ? 'hidden-row' : '')">
          <el-table-column label="领域" min-width="180" fixed>
            <template #default="{ row }">
              <div class="domain-name">
                {{ row.name }}
                <el-tag v-if="row.hidden" size="small" type="info" effect="plain">已隐藏</el-tag>
              </div>
              <div class="domain-meta">
                <el-tag v-if="row.dept_name" size="small" effect="plain">{{ row.dept_name }}</el-tag>
                <span v-if="row.leader_name" class="muted">PL：{{ row.leader_name }}</span>
                <span class="muted">{{ row.member_count }} 人</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="需求情况" min-width="200">
            <template #default="{ row }">
              <!-- total 是「已剔除已变更之后」的条数：整组需求都变更掉时 total=0，
                   这时也要把格子渲染出来，否则看着像这个组一条需求都没有 -->
              <div
                v-if="row.req_summary.total || row.req_summary.changed"
                class="cell-clickable"
                @click="openReq(row)"
              >
                <div class="sum-line">
                  <b>{{ row.req_summary.total }}</b> 项
                  <el-tag size="small" type="success" effect="plain">完成 {{ row.req_summary.done }}</el-tag>
                  <el-tag size="small" type="warning" effect="plain">进行 {{ row.req_summary.in_progress }}</el-tag>
                  <el-tag size="small" type="info" effect="plain">未开始 {{ row.req_summary.not_started }}</el-tag>
                  <el-tag v-if="row.req_summary.delayed" size="small" type="danger">延期 {{ row.req_summary.delayed }}</el-tag>
                  <el-tag
                    v-if="row.req_summary.changed"
                    size="small"
                    type="info"
                    effect="plain"
                    title="标了「已变更」的需求整行不计入上面的数字"
                  >已变更 {{ row.req_summary.changed }}</el-tag>
                </div>
                <div class="prio-line">
                  <span v-for="(n, p) in row.req_summary.by_priority" :key="p" class="prio">{{ p }}:{{ n }}</span>
                </div>
              </div>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>

          <el-table-column label="问题单情况" min-width="190">
            <template #header>
              问题单情况
              <el-tooltip placement="top" content="数据来自问题单管理的最新一次采集快照；加权总分：致命 10 分 / 严重 3 分 / 一般 1 分 / 提示 0.1 分">
                <el-icon class="hdr-help"><QuestionFilled /></el-icon>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <template v-if="row.issue_summary.available">
                <div v-if="row.issue_summary.total" class="cell-clickable" @click="openIssues(row)">
                  <div class="sum-line">
                    <b :class="{ 'over-target': row.issue_summary.over_total }">{{ row.issue_summary.total }}</b> 个
                    <span class="score-sep">·</span>
                    <b class="issue-score" :class="{ 'over-target': row.issue_summary.over_score }">{{ row.issue_summary.score }}</b> 分
                  </div>
                  <div v-if="hasTarget(row.issue_summary)" class="target-line">
                    目标
                    <span v-if="row.issue_summary.target_total !== null">{{ row.issue_summary.target_total }} 个</span>
                    <span v-if="row.issue_summary.target_score !== null">/ {{ row.issue_summary.target_score }} 分</span>
                    <el-tag size="small" :type="overTarget(row.issue_summary) ? 'danger' : 'success'" effect="plain">
                      {{ overTarget(row.issue_summary) ? '超标' : '达成' }}
                    </el-tag>
                  </div>
                  <div class="sev-line">
                    <span v-for="(n, s) in row.issue_summary.by_severity" :key="s">
                      <el-tag size="small" :type="sevType(s)" :effect="s === '致命' ? 'dark' : 'plain'">{{ s }} {{ n }}</el-tag>
                    </span>
                  </div>
                </div>
                <div v-else>
                  <span class="muted">无</span>
                  <div v-if="hasTarget(row.issue_summary)" class="target-line">
                    目标 {{ row.issue_summary.target_total ?? '—' }} 个
                    <el-tag size="small" type="success" effect="plain">达成</el-tag>
                  </div>
                </div>
              </template>
              <span v-else class="muted">未接入</span>
            </template>
          </el-table-column>

          <el-table-column label="最近主要工作" min-width="260">
            <template #default="{ row }">
              <div v-if="row.recent_work" class="rich-cell" v-html="row.recent_work" />
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>

          <el-table-column label="风险与求助" min-width="240">
            <template #default="{ row }">
              <div v-if="row.risks && row.risks.length" class="risk-list">
                <div v-for="(r, i) in row.risks" :key="i" class="risk-item">
                  <el-tag size="small" :type="r.type === '求助' ? 'warning' : 'danger'" effect="plain">{{ r.type }}</el-tag>
                  <span class="risk-content">{{ r.content }}</span>
                  <span v-if="r.status" class="muted">（{{ r.status }}）</span>
                </div>
              </div>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>

          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
              <el-button v-if="!row.hidden" link type="danger" @click="hideDomain(row)">移除</el-button>
              <el-button v-else link type="success" @click="restoreDomain(row)">恢复</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ===== 事务与风险跟踪 ===== -->
      <el-tab-pane label="事务与风险跟踪" name="risks">
        <div class="page-head">
          <div class="head-left">
            <el-button type="primary" :icon="Plus" @click="openRisk()">新增</el-button>
            <el-checkbox v-model="showDoneRisks" style="margin-left: 12px" @change="loadRisks">显示已闭环 / 挂起</el-checkbox>
            <span class="muted" style="margin-left: 12px">共 {{ riskRows.length }} 条</span>
          </div>
          <el-button :icon="Refresh" :loading="riskLoading" @click="loadRisks">刷新</el-button>
        </div>

        <el-table :data="riskRows" border stripe size="small" v-loading="riskLoading"
          :row-class-name="(o) => riskRowClass(o.row)">
          <el-table-column prop="seq" label="序号" width="64" align="center" />
          <el-table-column prop="content" label="风险和事务" min-width="240" show-overflow-tooltip />
          <el-table-column label="优先级" width="80" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="prioType(row.priority)">{{ row.priority || '—' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="progress" label="当前进展" min-width="180" show-overflow-tooltip />
          <el-table-column label="责任领域" width="150">
            <template #default="{ row }">
              <el-tag v-if="row.domain_name" size="small" effect="plain">{{ row.domain_name }}</el-tag>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="计划闭环时间" width="130">
            <template #default="{ row }">{{ fmtDate(row.planned_close_date) || '—' }}</template>
          </el-table-column>
          <el-table-column label="当前状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="statusType(row.status)" effect="dark">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openRisk(row)">编辑</el-button>
              <el-button link type="danger" size="small" @click="delRisk(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ===== 遗留问题 ===== -->
      <el-tab-pane label="遗留问题" name="legacy">
        <div class="page-head">
          <div class="head-left">
            <el-button type="primary" :icon="Plus" @click="openLegacy()">新增</el-button>
            <el-checkbox v-model="showDoneLegacy" style="margin-left: 12px" @change="loadLegacy">显示已关闭</el-checkbox>
            <el-select v-model="legacyDomainId" size="small" clearable filterable placeholder="全部领域"
              style="width: 180px; margin-left: 12px" @change="loadLegacy">
              <el-option v-for="d in domainOptions" :key="d.id" :value="d.id" :label="d.name" />
            </el-select>
            <span class="muted" style="margin-left: 12px">共 {{ legacyRows.length }} 条</span>
          </div>
          <el-button :icon="Refresh" :loading="legacyLoading" @click="loadLegacy">刷新</el-button>
        </div>

        <el-table :data="legacyRows" border stripe size="small" v-loading="legacyLoading"
          :row-class-name="(o) => legacyRowClass(o.row)">
          <el-table-column prop="seq" label="编号" width="70" align="center" />
          <el-table-column prop="title" label="任务名称" min-width="220" show-overflow-tooltip />
          <el-table-column label="状态" width="94" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="legacyStatusType(row.status)" effect="dark">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="当前责任人" width="100">
            <template #default="{ row }">{{ row.owner_name || '—' }}</template>
          </el-table-column>
          <el-table-column label="提出人" width="90">
            <template #default="{ row }">{{ row.reporter_name || '—' }}</template>
          </el-table-column>
          <el-table-column label="确认人" width="90">
            <template #default="{ row }">{{ row.confirmer_name || '—' }}</template>
          </el-table-column>
          <el-table-column label="参与人" min-width="150">
            <template #default="{ row }">
              <span v-if="row.participant_names?.length">{{ row.participant_names.join('、') }}</span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="所属领域" width="140">
            <template #default="{ row }">
              <el-tag v-if="row.domain_name" size="small" effect="plain">{{ row.domain_name }}</el-tag>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="计划完成时间" width="126">
            <template #default="{ row }">{{ fmtDate(row.planned_date) || '—' }}</template>
          </el-table-column>
          <el-table-column label="优先级" width="80" align="center">
            <template #default="{ row }">
              <el-tag size="small" :type="prioType(row.priority)">{{ row.priority || '—' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openLegacy(row)">编辑</el-button>
              <el-button link type="danger" size="small" @click="delLegacy(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 遗留问题 编辑弹窗 -->
    <el-dialog v-model="legacyVisible" :title="legacyForm.id ? '编辑遗留问题' : '新增遗留问题'" width="640px" :close-on-click-modal="false">
      <el-form :model="legacyForm" label-width="110px">
        <el-form-item label="编号">
          <el-input-number v-model="legacyForm.seq" :min="0" :controls="false" style="width: 120px" />
          <span class="muted" style="margin-left: 8px">留 0 由系统顺延</span>
        </el-form-item>
        <el-form-item label="任务名称" required>
          <el-input v-model="legacyForm.title" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="legacyForm.status" style="width: 160px">
            <el-option v-for="s in LEGACY_STATUSES" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="当前责任人">
          <el-select v-model="legacyForm.owner_id" clearable filterable placeholder="选择人员" style="width: 100%">
            <el-option v-for="u in userOptions" :key="u.id" :value="u.id" :label="userLabel(u)" />
          </el-select>
        </el-form-item>
        <el-form-item label="提出人">
          <el-select v-model="legacyForm.reporter_id" clearable filterable placeholder="选择人员" style="width: 100%">
            <el-option v-for="u in userOptions" :key="u.id" :value="u.id" :label="userLabel(u)" />
          </el-select>
        </el-form-item>
        <el-form-item label="确认人">
          <el-select v-model="legacyForm.confirmer_id" clearable filterable placeholder="选择人员" style="width: 100%">
            <el-option v-for="u in userOptions" :key="u.id" :value="u.id" :label="userLabel(u)" />
          </el-select>
        </el-form-item>
        <el-form-item label="参与人">
          <el-select v-model="legacyForm.participants" multiple filterable clearable placeholder="可多选" style="width: 100%">
            <el-option v-for="u in userOptions" :key="u.id" :value="u.id" :label="userLabel(u)" />
          </el-select>
        </el-form-item>
        <el-form-item label="所属领域">
          <el-select v-model="legacyForm.domain_id" clearable filterable placeholder="选择领域（PL组）" style="width: 100%">
            <el-option v-for="d in domainOptions" :key="d.id" :value="d.id" :label="d.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="计划完成时间">
          <el-date-picker v-model="legacyForm.planned_date" type="date" value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="legacyForm.priority" style="width: 160px">
            <el-option v-for="p in PRIORITIES" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="legacyForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="legacyVisible = false">取消</el-button>
        <el-button type="primary" :loading="legacySaving" @click="saveLegacy">保存</el-button>
      </template>
    </el-dialog>

    <!-- 问题单目标（仅 admin） -->
    <el-dialog v-model="targetVisible" title="设定问题单目标" width="640px" :close-on-click-modal="false">
      <div class="muted" style="margin-bottom: 10px">
        项目：<b>{{ targetProject || '（通用）' }}</b>。
        两个目标都留空＝该领域不设目标；超标时总览页标红。
      </div>
      <el-table :data="targetRows" border size="small" max-height="52vh">
        <el-table-column prop="group_name" label="领域" min-width="150">
          <template #default="{ row }">
            {{ row.group_name }}
            <el-tag v-if="row.inherited" size="small" type="info" effect="plain">继承通用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="数量目标" width="150">
          <template #default="{ row }">
            <el-input-number v-model="row.target_total" :min="0" :controls="false" style="width: 110px" placeholder="不设" />
          </template>
        </el-table-column>
        <el-table-column label="加权分目标" width="150">
          <template #default="{ row }">
            <el-input-number v-model="row.target_score" :min="0" :precision="1" :controls="false" style="width: 110px" placeholder="不设" />
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="targetVisible = false">取消</el-button>
        <el-button type="primary" :loading="targetSaving" @click="saveTargets">保存</el-button>
      </template>
    </el-dialog>

    <!-- 编辑：最近主要工作 + 风险求助 -->
    <el-dialog v-model="editVisible" :title="`编辑 · ${editRow?.name || ''}`" width="760px" :close-on-click-modal="false">
      <div class="edit-section-title">最近主要工作</div>
      <RichTextEditor v-model="editForm.recent_work" min-height="140px" placeholder="本周期该领域的主要进展…" />

      <div class="edit-section-title" style="margin-top: 18px">
        风险与求助
        <el-button size="small" :icon="Plus" @click="addRisk">添加一条</el-button>
      </div>
      <div v-if="!editForm.risks.length" class="muted" style="padding: 8px 0">暂无，点击「添加一条」。</div>
      <div v-for="(r, i) in editForm.risks" :key="i" class="risk-edit-row">
        <el-select v-model="r.type" style="width: 90px">
          <el-option label="风险" value="风险" />
          <el-option label="求助" value="求助" />
        </el-select>
        <el-input v-model="r.content" placeholder="内容" />
        <el-input v-model="r.status" placeholder="状态/进展" style="width: 160px" />
        <el-button :icon="Delete" circle type="danger" plain @click="editForm.risks.splice(i, 1)" />
      </div>

      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 事务/风险 编辑弹窗 -->
    <el-dialog v-model="riskVisible" :title="riskForm.id ? '编辑事务/风险' : '新增事务/风险'" width="600px" :close-on-click-modal="false">
      <el-form :model="riskForm" label-width="100px">
        <el-form-item label="风险和事务" required>
          <el-input v-model="riskForm.content" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="riskForm.priority" style="width: 160px">
            <el-option v-for="p in PRIORITIES" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="责任领域">
          <el-select v-model="riskForm.domain_id" clearable filterable placeholder="选择领域（PL组）" style="width: 100%">
            <el-option v-for="d in domainOptions" :key="d.id" :value="d.id" :label="d.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="当前进展">
          <el-input v-model="riskForm.progress" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="计划闭环时间">
          <el-date-picker v-model="riskForm.planned_close_date" type="date" value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="当前状态">
          <el-select v-model="riskForm.status" style="width: 160px">
            <el-option v-for="s in STATUSES" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="riskVisible = false">取消</el-button>
        <el-button type="primary" :loading="riskSaving" @click="saveRisk">保存</el-button>
      </template>
    </el-dialog>

    <!-- 下钻：需求明细 -->
    <el-dialog v-model="reqVisible" :title="`需求明细 · ${drillName}`" width="900px">
      <el-table :data="reqRows" border stripe max-height="60vh" v-loading="reqLoading">
        <el-table-column label="编号" width="120">
          <template #default="{ row }">
            <a v-if="row.req_url" :href="row.req_url" target="_blank" class="link">{{ row.req_no || '查看' }}</a>
            <span v-else>{{ row.req_no || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column prop="owner" label="责任人" width="90" />
        <el-table-column prop="priority" label="优先级" width="80" />
        <el-table-column v-for="c in PROG_COLS" :key="c.key" :label="c.label" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="progType(row[c.key])" effect="plain">{{ row[c.key] || '—' }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 下钻：问题单 -->
    <el-dialog v-model="issueVisible" :title="`问题单 · ${drillName}`" width="900px">
      <el-table :data="issueRows" border stripe max-height="60vh" v-loading="issueLoading">
        <el-table-column prop="issue_id" label="编号" width="130" />
        <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
        <el-table-column prop="owner" label="责任人" width="90" />
        <el-table-column prop="severity" label="严重度" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="sevType(row.severity)" effect="plain">{{ row.severity || '—' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="progress" label="进展" min-width="160" show-overflow-tooltip />
        <el-table-column prop="version" label="版本" width="120" show-overflow-tooltip />
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Aim, Delete, Plus, QuestionFilled, Refresh } from '@element-plus/icons-vue'
import { domainApi, resourceGroupApi, userApi } from '../api'
import { auth } from '../store/auth'
import RichTextEditor from '../components/RichTextEditor.vue'

const PROG_COLS = [
  { key: 'progress_walkthrough', label: '需求串讲' },
  { key: 'progress_reverse', label: '反串讲' },
  { key: 'progress_stc', label: 'STC' },
  { key: 'progress_coding', label: '编码' },
  { key: 'progress_bbit', label: 'BBIT' },
  { key: 'progress_clarify', label: '转测澄清' },
]
const PRIORITIES = ['高', '中', '低']
const STATUSES = ['OPEN', 'CLOSED', '挂起']
// 与后端 enums.DOMAIN_LEGACY_STATUSES 一一对应；pending 是小写，别"顺手"统一成大写
const LEGACY_STATUSES = ['OPEN', 'CLOSED', 'pending']

const activeTab = ref('overview')
const data = reactive({ iteration_label: '', rows: [], iterations: [], versions: [], projects: [] })
const issueMeta = reactive({ available: false, file_mtime: null, note: '', source: '' })
const loading = ref(false)
const showHidden = ref(false)
// 需求口径：'' = 当前进行中迭代；'2026-6' = 指定年度迭代月份
const monthKey = ref('')
// 需求口径的另一档：'iteration' = 按上面的月份；其余是 release_versions.id（字符串，el-tabs 的 name 只认字符串）
const scopeTab = ref('iteration')

// 总览与下钻共用这一份口径参数——两边各拼一次的表现是「格子里写 8 条、点进去 5 条」。
function scopeParams() {
  if (scopeTab.value !== 'iteration') return { release_version_id: Number(scopeTab.value) }
  return parseKey(monthKey.value)
}

function onScopeChange() {
  load()
}
// 问题单口径：项目/版本；'' = 让后端挑第一个有快照的项目（首次进页面时）
const project = ref('')

function parseKey(k) {
  if (!k) return {}
  const [y, m] = k.split('-')
  return { year: Number(y), month: Number(m) }
}
function statusSuffix(it) {
  return { in_progress: '（进行中）', done: '（已完成）', planning: '（计划）' }[it.status] || ''
}
function fmtDate(d) {
  if (!d) return ''
  const dt = new Date(d)
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`
}

function sevType(s) {
  return { '致命': 'danger', '严重': 'danger', '一般': 'warning', '提示': 'info' }[s] || 'info'
}
function progType(v) {
  return {
    '已完成': 'success', '进行中': 'warning', '已延期': 'danger',
    '已变更': 'warning', '未开始': 'info', '不涉及': 'info',
  }[v] || 'info'
}
function prioType(p) {
  return { '高': 'danger', '中': 'warning', '低': 'info' }[p] || 'info'
}
function statusType(s) {
  // OPEN 橙、CLOSED 绿、挂起 灰
  return { 'OPEN': 'warning', 'CLOSED': 'success', '挂起': 'info' }[s] || 'info'
}
function legacyStatusType(s) {
  return { 'OPEN': 'warning', 'CLOSED': 'success', 'pending': 'info' }[s] || 'info'
}
function userLabel(u) {
  return u.full_name || u.username
}
function hasTarget(sum) {
  return sum && (sum.target_total !== null || sum.target_score !== null)
}
function overTarget(sum) {
  return !!(sum && (sum.over_total || sum.over_score))
}
function riskRowClass(row) {
  if (row.status === 'CLOSED') return 'risk-closed'
  if (row.status === '挂起') return 'risk-suspended'
  return ''
}

async function load() {
  loading.value = true
  try {
    const { data: d } = await domainApi.list({
      ...scopeParams(),
      include_hidden: showHidden.value,
      project: project.value || undefined,
    })
    data.iteration_label = d.iteration_label
    data.rows = d.rows
    data.iterations = d.iterations || []
    data.versions = d.versions || []
    data.projects = d.projects || []
    // 首次进页面没选项目，用后端挑中的那个回填选择器，免得下拉空着但表格有数
    project.value = d.selected_project || project.value || ''
    const first = d.rows.find((r) => r.issue_summary)?.issue_summary
    issueMeta.available = !!first?.available
    issueMeta.file_mtime = first?.file_mtime || null
    issueMeta.note = first?.note || ''
    issueMeta.source = first?.source || ''
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

async function hideDomain(row) {
  await ElMessageBox.confirm(`将「${row.name}」从领域管理移除？（不影响组织架构，可在"显示已隐藏"里恢复）`, '提示', { type: 'warning' })
  try {
    await domainApi.setVisibility(row.group_id, true)
    ElMessage.success('已移除')
    load()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '操作失败') }
}
async function restoreDomain(row) {
  try {
    await domainApi.setVisibility(row.group_id, false)
    ElMessage.success('已恢复')
    load()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '操作失败') }
}

// ── 领域内容编辑 ──────────────────────────────────────
const editVisible = ref(false)
const editRow = ref(null)
const saving = ref(false)
const editForm = reactive({ recent_work: '', risks: [], version: 0 })

function openEdit(row) {
  editRow.value = row
  editForm.recent_work = row.recent_work || ''
  editForm.risks = (row.risks || []).map((r) => ({ ...r }))
  editForm.version = row.version || 0
  editVisible.value = true
}
function addRisk() {
  editForm.risks.push({ content: '', type: '风险', status: '' })
}
async function saveEdit() {
  saving.value = true
  try {
    await domainApi.updateContent(editRow.value.group_id, {
      recent_work: editForm.recent_work,
      risks: editForm.risks,
      version: editForm.version,
    })
    ElMessage.success('已保存')
    editVisible.value = false
    load()
  } catch (e) {
    if (e.response?.status === 409) {
      load()
      editVisible.value = false
    } else {
      ElMessage.error(e.response?.data?.detail || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

// ── 事务与风险跟踪 ──────────────────────────────────────
const riskRows = ref([])
const riskLoading = ref(false)
const showDoneRisks = ref(true)
const domainOptions = ref([])
const riskVisible = ref(false)
const riskSaving = ref(false)
const riskForm = reactive(blankRisk())

function blankRisk() {
  return {
    id: null, version: 0, content: '', priority: '中', progress: '',
    domain_id: null, planned_close_date: null, status: 'OPEN',
  }
}
async function loadRisks() {
  riskLoading.value = true
  try {
    const { data: rows } = await domainApi.riskList({ include_done: showDoneRisks.value })
    riskRows.value = rows
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    riskLoading.value = false
  }
}
async function loadDomainOptions() {
  try {
    const { data } = await resourceGroupApi.list({ kind: 'pl' })
    domainOptions.value = data
  } catch { /* 下拉为空不阻塞 */ }
}
function openRisk(row) {
  Object.assign(riskForm, blankRisk(), row ? { ...row } : {})
  riskVisible.value = true
}
async function saveRisk() {
  if (!riskForm.content.trim()) { ElMessage.warning('内容不能为空'); return }
  riskSaving.value = true
  try {
    if (riskForm.id) await domainApi.riskUpdate(riskForm.id, riskForm)
    else await domainApi.riskCreate(riskForm)
    ElMessage.success('已保存')
    riskVisible.value = false
    loadRisks()
  } catch (e) {
    if (e.response?.status === 409) { riskVisible.value = false; loadRisks() }
    else ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    riskSaving.value = false
  }
}
async function delRisk(row) {
  await ElMessageBox.confirm('确认删除该条事务/风险吗？', '提示', { type: 'warning' })
  try {
    await domainApi.riskRemove(row.id)
    ElMessage.success('已删除')
    loadRisks()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '删除失败') }
}

// ── 遗留问题 ──────────────────────────────────────────
const legacyRows = ref([])
const legacyLoading = ref(false)
const showDoneLegacy = ref(true)
const legacyDomainId = ref(null)
const legacyVisible = ref(false)
const legacySaving = ref(false)
const legacyForm = reactive(blankLegacy())
const userOptions = ref([])

function blankLegacy() {
  return {
    id: null, version: 0, seq: 0, title: '', status: 'OPEN',
    owner_id: null, reporter_id: null, confirmer_id: null, participants: [],
    domain_id: null, planned_date: null, priority: '中', remark: '',
  }
}
function legacyRowClass(row) {
  if (row.status === 'CLOSED') return 'risk-closed'
  if (row.status === 'pending') return 'risk-suspended'
  return ''
}
async function loadLegacy() {
  legacyLoading.value = true
  try {
    const { data: rows } = await domainApi.legacyList({
      include_done: showDoneLegacy.value,
      domain_id: legacyDomainId.value || undefined,
    })
    legacyRows.value = rows
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    legacyLoading.value = false
  }
}
async function loadUserOptions() {
  try {
    const { data } = await userApi.options()
    userOptions.value = data
  } catch { /* 下拉为空不阻塞 */ }
}
function openLegacy(row) {
  Object.assign(legacyForm, blankLegacy(), row ? { ...row, participants: [...(row.participants || [])] } : {})
  legacyVisible.value = true
}
async function saveLegacy() {
  if (!legacyForm.title.trim()) { ElMessage.warning('任务名称不能为空'); return }
  legacySaving.value = true
  try {
    if (legacyForm.id) await domainApi.legacyUpdate(legacyForm.id, legacyForm)
    else await domainApi.legacyCreate(legacyForm)
    ElMessage.success('已保存')
    legacyVisible.value = false
    loadLegacy()
  } catch (e) {
    if (e.response?.status === 409) { legacyVisible.value = false; loadLegacy() }
    else ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    legacySaving.value = false
  }
}
async function delLegacy(row) {
  await ElMessageBox.confirm(`确认删除遗留问题「${row.title || row.seq}」吗？`, '提示', { type: 'warning' })
  try {
    await domainApi.legacyRemove(row.id)
    ElMessage.success('已删除')
    loadLegacy()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '删除失败') }
}

// ── 问题单目标（仅 admin）──────────────────────────────
const targetVisible = ref(false)
const targetSaving = ref(false)
const targetProject = ref('')
const targetRows = ref([])

async function openTargets() {
  targetProject.value = project.value || ''
  try {
    const { data: res } = await domainApi.issueTargets(targetProject.value)
    targetRows.value = (res.items || []).map((r) => ({ ...r }))
    targetVisible.value = true
  } catch (e) { ElMessage.error(e.response?.data?.detail || '加载失败') }
}
async function saveTargets() {
  targetSaving.value = true
  try {
    await domainApi.saveIssueTargets({
      project: targetProject.value,
      items: targetRows.value.map((r) => ({
        group_id: r.group_id,
        // el-input-number 清空后是 undefined，统一成 null＝清除该目标
        target_total: r.target_total ?? null,
        target_score: r.target_score ?? null,
        remark: r.remark || '',
      })),
    })
    ElMessage.success('已保存')
    targetVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    targetSaving.value = false
  }
}

// ── 下钻 ──────────────────────────────────────────────
const drillName = ref('')
const reqVisible = ref(false)
const reqLoading = ref(false)
const reqRows = ref([])
const issueVisible = ref(false)
const issueLoading = ref(false)
const issueRows = ref([])

async function openReq(row) {
  drillName.value = row.name
  reqVisible.value = true
  reqLoading.value = true
  reqRows.value = []
  try {
    const { data: rows } = await domainApi.requirements(row.group_id, scopeParams())
    reqRows.value = rows
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    reqLoading.value = false
  }
}
async function openIssues(row) {
  drillName.value = row.name
  issueVisible.value = true
  issueLoading.value = true
  issueRows.value = []
  try {
    const { data: res } = await domainApi.issues(row.group_id, { project: project.value || undefined })
    issueRows.value = res.rows || []
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    issueLoading.value = false
  }
}

onMounted(() => { load(); loadRisks(); loadDomainOptions(); loadLegacy(); loadUserOptions() })
</script>

<style scoped>
.domain-page { padding: 4px; }
/* 口径标签只当选择器用，内容区是空的——不压掉高度会白白多出一段留白 */
.scope-tabs :deep(.el-tabs__header) {
  margin-bottom: 10px;
}
.scope-tabs :deep(.el-tabs__content) {
  display: none;
}
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.head-left { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.head-right { display: flex; align-items: center; gap: 12px; }
.muted { color: #909399; font-size: 13px; }
.domain-name { font-weight: 600; display: flex; align-items: center; gap: 6px; }
.domain-meta { display: flex; align-items: center; gap: 6px; margin-top: 4px; flex-wrap: wrap; }
.cell-clickable { cursor: pointer; }
.cell-clickable:hover { color: #409EFF; }
.sum-line { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.sev-line { margin-top: 4px; display: flex; gap: 4px; flex-wrap: wrap; }
.score-sep { color: #c0c4cc; margin: 0 2px; }
.issue-score { color: #e6a23c; }
.hdr-help { font-size: 13px; color: #909399; vertical-align: -1px; cursor: help; }
.prio-line { margin-top: 4px; }
.prio { color: #909399; font-size: 12px; margin-right: 8px; }
.rich-cell {
  max-height: 96px;
  overflow: auto;
  font-size: 13px;
  line-height: 1.5;
}
.risk-list { display: flex; flex-direction: column; gap: 4px; }
.risk-item { display: flex; align-items: baseline; gap: 6px; font-size: 13px; }
.risk-content { flex: 1; }
.edit-section-title {
  font-weight: 600;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.risk-edit-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.target-line { margin-top: 4px; color: #909399; font-size: 12px; display: flex; align-items: center; gap: 4px; }
.over-target { color: #F56C6C; }
.link, a.link { color: #409EFF; text-decoration: none; }
/* 已隐藏领域行：淡化 */
.domain-table :deep(.hidden-row) { background: #fafafa; color: #909399; }
/* 事务风险：CLOSED 浅绿、挂起 浅灰 */
:deep(.risk-closed) td.el-table__cell { background: #f0f9eb !important; }
:deep(.risk-suspended) td.el-table__cell { background: #f4f4f5 !important; }
</style>
