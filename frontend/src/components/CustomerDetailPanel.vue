<template>
  <div v-loading="loading" class="cd-panel">
    <template v-if="customer">
      <!-- 区块 1：基本信息（含别名）-->
      <section class="sec">
        <div class="sec-head">
          <span>基本信息</span>
          <div class="actions">
            <el-button v-if="canEdit" size="small" @click="openMetaDialog">编辑基本信息</el-button>
          </div>
        </div>
        <div class="sec-body">
          <div class="title-wrap">
            <span class="code">{{ customer.code }}</span>
            <span v-if="customer.display_name" class="display-name">{{ customer.display_name }}</span>
            <el-tag v-if="customer.region" size="small" effect="plain">{{ customer.region }}</el-tag>
            <el-tag v-if="customer.industry" size="small" effect="plain" type="info">{{ customer.industry }}</el-tag>
            <el-tag :type="customer.is_active ? 'success' : 'info'" size="small">
              {{ customer.is_active ? '启用' : '停用' }}
            </el-tag>
          </div>
          <div class="meta-grid">
            <div><label>客户编码 (Code)</label><span>{{ customer.code }}</span></div>
            <div><label>完整名称</label><span>{{ customer.display_name || '—' }}</span></div>
            <div><label>区域</label><span>{{ customer.region || '—' }}</span></div>
            <div><label>行业</label><span>{{ customer.industry || '—' }}</span></div>
            <div><label>状态</label><span>{{ customer.is_active ? '启用' : '停用' }}</span></div>
            <div><label>排序</label><span>{{ customer.sort_order }}</span></div>
          </div>

          <div class="alias-block">
            <label class="alias-label">别名</label>
            <div class="alias-tags">
              <el-tag
                v-for="a in customer.aliases"
                :key="a.id"
                :closable="canEdit"
                type="info"
                effect="plain"
                style="margin-right: 6px; margin-bottom: 6px"
                @close="removeAlias(a)"
              >{{ a.alias }}</el-tag>
              <span v-if="!customer.aliases?.length" class="muted">尚未添加别名</span>
              <span v-if="canEdit" class="alias-add">
                <el-input
                  v-if="addingAlias"
                  ref="aliasInputRef"
                  v-model="newAlias"
                  size="small"
                  style="width: 200px"
                  placeholder="输入别名按回车"
                  @keyup.enter="confirmAddAlias"
                  @blur="confirmAddAlias"
                  @keyup.esc="cancelAddAlias"
                />
                <el-button v-else size="small" :icon="Plus" @click="startAddAlias">添加别名</el-button>
              </span>
            </div>
            <div class="muted-hint">业务记录里凡是出现这些名字（如老的"战场"字符串），都视作同一客户</div>
          </div>
        </div>
      </section>

      <!-- 区块 2：客户面机台 tabs -->
      <section class="sec">
        <div class="sec-head">
          <span>客户面机台</span>
          <span class="muted-hint">机台来自「客户面状态」总览，按客户编码/别名匹配</span>
        </div>
        <div class="sec-body">
          <div v-if="!machines.length" class="empty">
            该客户在「客户面状态」总览中暂无关联机台。前往总览将机台的"客户"列设置为
            <b>{{ customer.code }}</b>
            或它的任一别名即可显示。
          </div>
          <el-tabs v-else v-model="activeMachine" type="card" class="machine-tabs">
            <el-tab-pane
              v-for="m in machines"
              :key="m.id"
              :label="m.machine_id"
              :name="String(m.id)"
            >
              <div class="machine-pane">
                <!-- 里程碑 -->
                <div class="block">
                  <div class="block-head">
                    <span>里程碑</span>
                    <span class="muted-hint">出厂 → Tier0 → Tier1 → Tier2 → Tier3 → 验收</span>
                    <div class="actions">
                      <el-button v-if="canEditStage" size="small" :icon="Edit" @click="openMilestoneDialog(m)">编辑里程碑</el-button>
                    </div>
                  </div>
                  <div class="block-body">
                    <MilestoneTimeline :milestones="machineState[m.id].milestones" :editable="false" />
                  </div>
                </div>

                <!-- 当前进展 -->
                <div class="block">
                  <div class="block-head">
                    <span>当前进展</span>
                    <span class="muted-hint">与「客户面状态」总览的"当前进展"字段同步</span>
                  </div>
                  <div class="block-body">
                    <el-input
                      v-model="machineState[m.id].current"
                      type="textarea"
                      autosize
                      placeholder="—"
                      :readonly="!canEditStage"
                    />
                    <div v-if="canEditStage" class="right">
                      <el-button
                        type="primary"
                        size="small"
                        :disabled="machineState[m.id].current === (m.customer_status || '')"
                        @click="saveCurrentStage(m)"
                      >保存当前进展</el-button>
                    </div>
                  </div>
                </div>

                <!-- 现场关键事务 / 软件类问题（与总览同一份 customer_issues 数据）-->
                <div class="block">
                  <div class="block-head">
                    <span>现场关键事务</span>
                    <span class="muted-hint">与「客户面状态」总览同步；勾选＝已闭环，点条目可到「问题跟踪」看详情</span>
                  </div>
                  <div class="block-body">
                    <CustomerIssueCell
                      kind="task"
                      :items="machineIssues[m.id]?.task || []"
                      :machine-status-id="m.id"
                      :edit-mode="canEditStage"
                      :show-completed="showCompletedIssues"
                      :is-admin="canEdit"
                      @refresh="loadMachineIssues"
                      @open="gotoTracking"
                    />
                  </div>
                </div>

                <div class="block">
                  <div class="block-head">
                    <span>软件类风险和问题</span>
                    <el-checkbox v-model="showCompletedIssues" size="small" label="显示已完成" />
                  </div>
                  <div class="block-body">
                    <CustomerIssueCell
                      kind="issue"
                      :items="machineIssues[m.id]?.issue || []"
                      :machine-status-id="m.id"
                      :edit-mode="canEditStage"
                      :show-completed="showCompletedIssues"
                      :is-admin="canEdit"
                      @refresh="loadMachineIssues"
                      @open="gotoTracking"
                    />
                  </div>
                </div>

                <!-- SOW 状态 -->
                <div class="block">
                  <div class="block-head">
                    <span>SOW 状态</span>
                    <span class="muted-hint">列由管理员在「客户管理 → SOW 字段配置」维护，所有客户共享</span>
                    <div class="actions">
                      <el-button v-if="canEdit" size="small" :icon="Plus" @click="addSowRow(m)">新增行</el-button>
                    </div>
                  </div>
                  <div class="block-body">
                    <el-table
                      :data="machineState[m.id].sowRows"
                      v-loading="machineState[m.id].sowLoading"
                      border
                      stripe
                      size="small"
                      empty-text="暂无 SOW 记录"
                      style="width: 100%"
                    >
                      <el-table-column
                        v-for="f in sowFields"
                        :key="f.id"
                        :label="f.label"
                        :min-width="f.field_type === 'date' ? 130 : 160"
                      >
                        <template #default="{ row }">
                          <el-date-picker
                            v-if="f.field_type === 'date'"
                            v-model="row.data[f.key]"
                            type="date"
                            value-format="YYYY-MM-DD"
                            size="small"
                            style="width: 100%"
                            :disabled="!canEdit"
                          />
                          <el-select
                            v-else-if="f.field_type === 'select'"
                            v-model="row.data[f.key]"
                            size="small"
                            clearable
                            style="width: 100%"
                            :disabled="!canEdit"
                          >
                            <el-option
                              v-for="opt in f.options"
                              :key="opt"
                              :label="opt"
                              :value="opt"
                            />
                          </el-select>
                          <el-input
                            v-else
                            v-model="row.data[f.key]"
                            size="small"
                            placeholder="—"
                            :disabled="!canEdit"
                          />
                        </template>
                      </el-table-column>
                      <el-table-column v-if="canEdit" label="操作" width="160" fixed="right">
                        <template #default="{ row, $index }">
                          <el-button
                            size="small"
                            type="primary"
                            :disabled="!isRowDirty(row, m.id, $index)"
                            @click="saveSowRow(m, row)"
                          >保存</el-button>
                          <el-button size="small" type="danger" @click="deleteSowRow(m, row)">删除</el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                    <div v-if="!sowFields.length" class="empty inline">
                      尚未配置 SOW 列。管理员可前往「客户管理 → SOW 字段配置」添加。
                    </div>
                  </div>
                </div>

                <!-- 自定义信息块（如 MPH状态）-->
                <div
                  v-for="f in extraFields"
                  :key="f.id"
                  class="block"
                >
                  <div class="block-head">
                    <span>{{ f.label }}</span>
                    <span class="muted-hint">自定义信息块，由管理员在「客户管理」维护</span>
                  </div>
                  <div class="block-body">
                    <el-input
                      v-model="getExtra(m.id, f.id).text"
                      type="textarea"
                      autosize
                      placeholder="—"
                      :readonly="!canEdit"
                    />
                    <div class="extra-foot">
                      <div class="extra-file">
                        <template v-if="getExtra(m.id, f.id).has_file">
                          <el-link type="primary" :icon="Paperclip" @click="downloadExtra(m.id, f.id)">
                            {{ getExtra(m.id, f.id).file_name }}
                          </el-link>
                          <el-button
                            v-if="canEdit"
                            size="small"
                            link
                            type="danger"
                            @click="removeExtraFile(m.id, f.id)"
                          >删除附件</el-button>
                        </template>
                        <span v-else class="muted">暂无附件</span>
                      </div>
                      <div v-if="canEdit" class="extra-actions">
                        <el-upload
                          :auto-upload="false"
                          :show-file-list="false"
                          :on-change="(file) => onExtraFileChange(m.id, f.id, file)"
                        >
                          <el-button size="small" :icon="Upload">上传附件/图片</el-button>
                        </el-upload>
                        <el-button
                          size="small"
                          type="primary"
                          :disabled="!isExtraDirty(m.id, f.id)"
                          @click="saveExtraText(m.id, f.id)"
                        >保存文本</el-button>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- License 管理 -->
                <div class="block">
                  <div class="block-head">
                    <span>License 管理</span>
                    <span class="muted-hint">每台机台可挂载多个 license 文件</span>
                    <div class="actions">
                      <el-button v-if="canEdit" size="small" :icon="Upload" @click="openLicenseUpload(m)">上传 License</el-button>
                    </div>
                  </div>
                  <div class="block-body">
                    <el-table
                      :data="machineState[m.id].licenses"
                      v-loading="machineState[m.id].licenseLoading"
                      border
                      stripe
                      size="small"
                      empty-text="暂无 License"
                      style="width: 100%"
                    >
                      <el-table-column prop="file_name" label="文件名" min-width="220" />
                      <el-table-column label="大小" width="100">
                        <template #default="{ row }">{{ formatBytes(row.file_size) }}</template>
                      </el-table-column>
                      <el-table-column label="备注" min-width="240">
                        <template #default="{ row }">
                          <el-input
                            v-model="row.remark"
                            size="small"
                            placeholder="—"
                            :disabled="!canEdit"
                            @change="saveLicenseRemark(m, row)"
                          />
                        </template>
                      </el-table-column>
                      <el-table-column prop="uploaded_by" label="上传人" width="120" />
                      <el-table-column label="上传时间" width="170">
                        <template #default="{ row }">{{ formatDateTime(row.uploaded_at) }}</template>
                      </el-table-column>
                      <el-table-column label="操作" width="160" fixed="right">
                        <template #default="{ row }">
                          <el-button size="small" @click="downloadLicense(row)">下载</el-button>
                          <el-button v-if="canEdit" size="small" type="danger" @click="deleteLicense(m, row)">删除</el-button>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </div>
              </div>
            </el-tab-pane>
          </el-tabs>
        </div>
      </section>

      <!-- 区块 3：客户定制化需求（整客户范围，tab 外）-->
      <section class="sec">
        <div class="sec-head">
          <span>客户定制化需求</span>
          <!-- 只滤不报的表现是"这个版本怎么选不到了"，而没人说得清少的是哪些 -->
          <span class="muted-hint">
            本客户的定制化需求清单<template v-if="versionReleasedHidden">；
            「预计合入版本」下拉已隐去 {{ versionReleasedHidden }} 个已发布的版本，
            确需填写时直接敲版本号</template>
          </span>
          <div class="actions">
            <el-button v-if="canEdit" size="small" :icon="Plus" @click="addCustomReq">新增需求</el-button>
            <el-button size="small" :icon="Refresh" @click="loadCustomReqs">刷新</el-button>
          </div>
        </div>
        <div class="sec-body">
          <el-table
            :data="customReqs"
            v-loading="customReqLoading"
            border
            stripe
            size="small"
            empty-text="暂无定制化需求"
            style="width: 100%"
          >
            <el-table-column prop="seq" label="序号" width="64" align="center">
              <template #default="{ row }">
                <el-input v-model.number="row.seq" size="small" :disabled="!canEdit" />
              </template>
            </el-table-column>
            <el-table-column label="需求描述" min-width="200">
              <template #default="{ row }">
                <el-input v-model="row.description" type="textarea" autosize size="small" :disabled="!canEdit" placeholder="—" />
              </template>
            </el-table-column>
            <el-table-column label="对客户价值" min-width="180">
              <template #default="{ row }">
                <el-input v-model="row.customer_value" type="textarea" autosize size="small" :disabled="!canEdit" placeholder="—" />
              </template>
            </el-table-column>
            <el-table-column label="领域" width="120">
              <template #default="{ row }">
                <el-input v-model="row.domain" size="small" :disabled="!canEdit" placeholder="—" />
              </template>
            </el-table-column>
            <el-table-column label="设计人员" width="120">
              <template #default="{ row }">
                <el-input v-model="row.designer" size="small" :disabled="!canEdit" placeholder="—" />
              </template>
            </el-table-column>
            <el-table-column label="是否涉及其他项目" width="140" align="center">
              <template #default="{ row }">
                <el-select v-model="row.involves_other" size="small" clearable :disabled="!canEdit" style="width: 100%">
                  <el-option label="是" value="是" />
                  <el-option label="否" value="否" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="预计合入版本" width="170">
              <template #default="{ row }">
                <!-- 存的是版本号字符串（不是 FK），所以 allow-create：老数据里什么写法都有，
                     强行只能选会逼着人把对不上的行改成一个错的版本。
                     :persistent="false" 是行内下拉的必需项，见 CLAUDE.md「前端约定」 -->
                <el-select
                  v-model="row.planned_version"
                  size="small"
                  clearable
                  filterable
                  allow-create
                  :persistent="false"
                  :disabled="!canEdit"
                  placeholder="—"
                  style="width: 100%"
                >
                  <el-option-group
                    v-for="group in versionGroups"
                    :key="group.label"
                    :label="group.label"
                  >
                    <el-option
                      v-for="v in group.options"
                      :key="v.id"
                      :label="v.version_no"
                      :value="v.version_no"
                    >
                      <span>{{ v.version_no }}</span>
                      <span v-if="v.title" style="color:#909399; margin-left:6px; font-size:12px">{{ v.title }}</span>
                    </el-option>
                  </el-option-group>
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="备注" min-width="160">
              <template #default="{ row }">
                <el-input v-model="row.remark" type="textarea" autosize size="small" :disabled="!canEdit" placeholder="—" />
              </template>
            </el-table-column>
            <el-table-column v-if="canEdit" label="操作" width="150" fixed="right">
              <template #default="{ row, $index }">
                <el-button size="small" type="primary" :disabled="!isCustomReqDirty(row, $index)" @click="saveCustomReq(row)">保存</el-button>
                <el-button size="small" type="danger" @click="deleteCustomReq(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </section>

      <!-- 区块 4：问题单情况（整客户范围，tab 外）-->
      <section class="sec">
        <div class="sec-head">
          <span>问题单情况</span>
          <span class="muted-hint">来自最新一期问题单报表，按本客户编码/别名过滤</span>
          <div class="actions">
            <el-button size="small" :icon="Refresh" @click="loadIssues">刷新</el-button>
          </div>
        </div>
        <div class="sec-body">
          <div v-if="issues.loading" v-loading="true" style="height: 60px" />
          <div v-else-if="!issues.configured" class="empty">
            问题单报表路径尚未配置，请联系管理员在系统设置中配置 <code>issue_report_path</code>。
          </div>
          <div v-else>
            <div class="issue-cards">
              <div class="issue-card total">
                <div class="num">{{ issues.filtered.length }}</div>
                <div class="lbl">合计</div>
              </div>
              <div class="issue-card sev-major">
                <div class="num">{{ issues.bySeverity['严重'] || 0 }}</div>
                <div class="lbl">严重</div>
              </div>
              <div class="issue-card sev-normal">
                <div class="num">{{ issues.bySeverity['一般'] || 0 }}</div>
                <div class="lbl">一般</div>
              </div>
              <div class="issue-card sev-info">
                <div class="num">{{ issues.bySeverity['提示'] || 0 }}</div>
                <div class="lbl">提示</div>
              </div>
            </div>
            <el-table
              :data="issues.filtered"
              border
              stripe
              size="small"
              empty-text="未匹配到本客户的问题单"
              style="width: 100%; margin-top: 12px"
              max-height="420"
            >
              <el-table-column prop="issue_id" label="编号" width="140" />
              <el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip />
              <el-table-column prop="severity" label="严重程度" width="100" />
              <el-table-column prop="owner" label="责任人" width="120" />
              <el-table-column prop="group" label="所属小组" width="120" />
              <el-table-column prop="progress" label="进展" min-width="180" show-overflow-tooltip />
              <el-table-column prop="estimated_close" label="预计闭环" width="120" />
            </el-table>
            <div v-if="issues.fileMtime" class="report-meta">
              数据快照时间：{{ issues.fileMtime }}
            </div>
          </div>
        </div>
      </section>
    </template>

    <!-- 编辑基本信息 -->
    <el-dialog v-model="metaDialog.visible" title="编辑基本信息" width="520px" append-to-body>
      <el-form :model="metaDialog.form" label-width="120px">
        <el-form-item label="客户编码"><el-input v-model="metaDialog.form.code" /></el-form-item>
        <el-form-item label="完整名称"><el-input v-model="metaDialog.form.display_name" /></el-form-item>
        <el-form-item label="区域"><el-input v-model="metaDialog.form.region" /></el-form-item>
        <el-form-item label="行业"><el-input v-model="metaDialog.form.industry" /></el-form-item>
        <el-form-item label="排序"><el-input-number v-model="metaDialog.form.sort_order" :min="0" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="metaDialog.form.is_active" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="metaDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="onSaveMeta">保存</el-button>
      </template>
    </el-dialog>

    <!-- 上传 License -->
    <el-dialog v-model="licenseDialog.visible" title="上传 License" width="480px" append-to-body>
      <el-form label-width="80px">
        <el-form-item label="文件">
          <el-upload
            :auto-upload="false"
            :show-file-list="true"
            :limit="1"
            :on-change="onLicenseFileChange"
            :on-remove="() => (licenseDialog.file = null)"
          >
            <el-button :icon="Upload">选择文件</el-button>
          </el-upload>
        </el-form-item>
        <el-form-item label="备注">
          <el-input
            v-model="licenseDialog.remark"
            type="textarea"
            :rows="3"
            placeholder="可填写有效期 / 授权范围 / 备注"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="licenseDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="licenseDialog.uploading" @click="submitLicenseUpload">上传</el-button>
      </template>
    </el-dialog>

    <!-- 编辑里程碑 -->
    <el-dialog v-model="milestoneDialog.visible" title="编辑里程碑" width="560px" append-to-body>
      <el-table :data="milestoneDialog.rows" border size="small">
        <el-table-column prop="name" label="节点" width="100" />
        <el-table-column label="状态" width="140">
          <template #default="{ row }">
            <el-select v-model="row.status" size="small" style="width: 100%">
              <el-option v-for="s in MS_STATUS" :key="s.value" :label="s.label" :value="s.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="日期">
          <template #default="{ row }">
            <el-date-picker
              v-model="row.date"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              placeholder="可选"
              style="width: 100%"
            />
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="milestoneDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="milestoneDialog.saving" @click="saveMilestones">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Edit, Paperclip, Plus, Refresh, Upload } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import {
  customerApi, customerCustomReqApi, customerExtraApi, customerIssueApi, customerStatusApi, downloadBlob, issueApi, licenseApi, majorVersionApi, sowApi,
} from '../api'
import { auth } from '../store/auth'
import CustomerIssueCell from './CustomerIssueCell.vue'
import MilestoneTimeline from './MilestoneTimeline.vue'

const router = useRouter()
const route = useRoute()

const MILESTONE_STAGES = ['出厂', 'Tier0', 'Tier1', 'Tier2', 'Tier3', '验收']
const MS_STATUS = [
  { value: 'planning', label: '未开始' },
  { value: 'in_progress', label: '进行中' },
  { value: 'done', label: '已完成' },
  { value: 'delayed', label: '已延期' },
]

function parseMilestones(raw) {
  let stored = []
  try { stored = raw ? JSON.parse(raw) : [] } catch { stored = [] }
  const byName = {}
  for (const s of stored) if (s && s.name) byName[s.name] = s
  return MILESTONE_STAGES.map((name) => ({
    name,
    date: byName[name]?.date || '',
    status: byName[name]?.status || 'planning',
  }))
}

const props = defineProps({
  customerId: { type: [Number, String], required: true },
})
const emit = defineEmits(['changed'])

const canEdit = computed(() => auth.isAdmin.value)
// "当前进展" 对应后端 customer_status.customer_status 字段，是用户字段（非 admin-only），所有登录用户可改
const canEditStage = computed(() => auth.isLoggedIn.value)

const loading = ref(false)
const customer = ref(null)

// 别名快捷添加
const addingAlias = ref(false)
const newAlias = ref('')
const aliasInputRef = ref(null)

const metaDialog = reactive({ visible: false, form: {} })

// 机台 tabs
const machines = ref([])
const activeMachine = ref('')
// machineState[machineId] = { current, sowLoading, sowRows, sowOriginals, licenseLoading, licenses }
const machineState = reactive({})
// machineIssues[machineId] = { task: [...], issue: [...] }，来自 customer_issues 表
const machineIssues = reactive({})
const showCompletedIssues = ref(false)

// SOW 字段定义（全局共享）
const sowFields = ref([])

// 自定义信息块定义（全局共享）
const extraFields = ref([])

// 里程碑编辑
const milestoneDialog = reactive({ visible: false, saving: false, machineId: null, rows: [] })

// 客户定制化需求
const customReqs = ref([])
const customReqLoading = ref(false)
// 「预计合入版本」下拉：**版本**这一层（C10SPC101），不是构建——客户面看的是对外发布的那一级。
// 已发布的不列出来：合入是往还没发的版本里合，已经发出去的版本合不进东西了。
const versionGroups = ref([])
const versionReleasedHidden = ref(0)
const customReqOrig = reactive({}) // id -> JSON 快照，用于 dirty 判断

// 问题单
const issues = reactive({
  loading: false,
  configured: true,
  raw: [],
  filtered: [],
  bySeverity: {},
  fileMtime: '',
})

// License 上传
const licenseDialog = reactive({
  visible: false,
  uploading: false,
  machine: null,
  file: null,
  remark: '',
})

// ─── 加载 ────────────────────────────────────────────────────────

async function loadCustomer() {
  if (!props.customerId) return
  loading.value = true
  try {
    const { data } = await customerApi.get(props.customerId)
    customer.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

async function loadSowFields() {
  try {
    const { data } = await sowApi.listFields(false)
    sowFields.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || 'SOW 字段加载失败')
  }
}

async function loadExtraFields() {
  try {
    const { data } = await customerExtraApi.listFields(false)
    extraFields.value = data
  } catch {
    /* 信息块加载失败不阻塞详情页 */
  }
}

async function loadExtraValues(mid) {
  const st = machineState[mid]
  if (!st) return
  try {
    const { data } = await customerExtraApi.listValues(mid)
    const map = {}
    const orig = {}
    for (const v of data) {
      map[v.field_id] = v
      orig[v.field_id] = v.text || ''
    }
    // 没有值记录的字段，给一个本地占位（保存时后端按需创建）
    for (const f of extraFields.value) {
      if (!map[f.id]) {
        map[f.id] = { id: null, field_id: f.id, text: '', file_name: '', file_size: 0, has_file: false, version: 0 }
        orig[f.id] = ''
      }
    }
    st.extra = map
    st.extraOrig = orig
    st.extraLoaded = true
  } catch {
    /* 静默 */
  }
}

async function loadMachines() {
  try {
    const { data } = await customerApi.machines(props.customerId)
    // 先填好 state 再赋值 machines，避免模板瞬间访问到尚未初始化的 machineState[m.id]
    for (const m of data) {
      if (!machineState[m.id]) {
        machineState[m.id] = {
          current: m.customer_status || '',
          milestones: parseMilestones(m.milestones_json),
          sowLoading: false,
          sowRows: [],
          sowOriginals: {}, // id -> JSON of original data, 用于判断 dirty
          licenseLoading: false,
          licenses: [],
          extra: {},        // field_id -> {id, text, file_name, file_size, has_file, version}
          extraOrig: {},    // field_id -> 原始 text，用于 dirty 判断
          extraLoaded: false,
        }
      } else {
        machineState[m.id].current = m.customer_status || ''
        machineState[m.id].milestones = parseMilestones(m.milestones_json)
      }
    }
    machines.value = data
    await loadMachineIssues()
    if (data.length) {
      // 支持 ?machine=<machine_status_id> 深链（问题跟踪的机台列跳转过来）：
      // 命中则定位到该机台 tab，否则默认第一台
      const wanted = String(route.query.machine || '')
      const target = data.find(m => String(m.id) === wanted) || data[0]
      activeMachine.value = String(target.id)
      // 先把目标 tab 的子数据加载出来
      await Promise.all([loadSowRows(target.id), loadLicenses(target.id), loadExtraValues(target.id)])
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '机台加载失败')
  }
}

// 问题/事务条目：一次拉全量再按机台分组，避免每个机台一个请求
async function loadMachineIssues() {
  try {
    const { data } = await customerIssueApi.list()
    const ids = new Set(machines.value.map((m) => m.id))
    const grouped = {}
    for (const it of data) {
      if (!ids.has(it.machine_status_id)) continue
      const g = (grouped[it.machine_status_id] ||= { task: [], issue: [] })
      ;(it.kind === 'task' ? g.task : g.issue).push(it)
    }
    Object.keys(machineIssues).forEach((k) => delete machineIssues[k])
    Object.assign(machineIssues, grouped)
  } catch {
    /* 静默：条目加载失败不该拖垮整个客户详情 */
  }
}

function gotoTracking(item) {
  // 问题跟踪是客户面状态页的一个 tab，用查询串深链过去（focus=条目 id 时自动高亮）
  const query = { tab: 'issues', ...(item?.id ? { focus: item.id } : {}) }
  router.push({ path: '/customer-status', query })
}

async function loadSowRows(mid) {
  const st = machineState[mid]
  if (!st) return
  st.sowLoading = true
  try {
    const { data } = await sowApi.listRows(mid)
    st.sowRows = data.map((r) => ({
      id: r.id,
      version: r.version,
      sort_order: r.sort_order,
      // 确保所有列 key 都在 data 中（即使是空字符串），以便双向绑定可用
      data: fillRowData(r.data),
    }))
    st.sowOriginals = Object.fromEntries(
      st.sowRows.map((r) => [r.id, JSON.stringify(r.data)])
    )
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || 'SOW 行加载失败')
  } finally {
    st.sowLoading = false
  }
}

function fillRowData(src) {
  const out = {}
  for (const f of sowFields.value) out[f.key] = src?.[f.key] ?? ''
  // 保留 src 中可能存在但已被删除的字段（仅展示用，不再渲染）
  for (const k of Object.keys(src || {})) {
    if (!(k in out)) out[k] = src[k]
  }
  return out
}

async function loadLicenses(mid) {
  const st = machineState[mid]
  if (!st) return
  st.licenseLoading = true
  try {
    const { data } = await licenseApi.list(mid)
    st.licenses = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || 'License 加载失败')
  } finally {
    st.licenseLoading = false
  }
}

// ─── 客户定制化需求 ───────────────────────────────────────────
const CUSTOM_REQ_KEYS = ['seq', 'description', 'customer_value', 'domain', 'designer', 'involves_other', 'planned_version', 'remark']
// 这几列是自由文本，且其中两列挂着 clearable 的 el-select
const CUSTOM_REQ_TEXT_KEYS = new Set(
  ['description', 'customer_value', 'domain', 'designer', 'involves_other', 'planned_version', 'remark'],
)

// el-select 的清除按钮把值置成 **undefined**（Element Plus 的 valueOnClear 默认值），
// 而 undefined 会被 JSON.stringify 从请求体里整个丢掉，后端按「没传＝不修改」处理——
// 表现是"清空保存，一刷新又回来了"，页面还提示保存成功。所以文本列一律折成空串。
function customReqValue(row, k) {
  const v = row[k]
  return CUSTOM_REQ_TEXT_KEYS.has(k) ? (v ?? '') : v
}

function customReqSnapshot(row) {
  const o = {}
  for (const k of CUSTOM_REQ_KEYS) o[k] = customReqValue(row, k)
  return JSON.stringify(o)
}

async function loadVersionOptions() {
  try {
    const { data } = await majorVersionApi.allReleaseVersions()
    // `released` 由服务端判（填了实际发布日期且那天已过），前端不重算日期——
    // 各页面自己比 new Date() 的话跨零点会给出不同答案，而两边看着都对。
    const usable = data.filter((v) => !v.released)
    versionReleasedHidden.value = data.length - usable.length
    const map = new Map()
    for (const v of usable) {
      const label = v.project_name ? `${v.project_name} · ${v.major_version_no}` : v.major_version_no
      if (!map.has(label)) map.set(label, [])
      map.get(label).push(v)
    }
    versionGroups.value = Array.from(map.entries()).map(([label, options]) => ({ label, options }))
  } catch (e) {
    /* 下拉为空不阻塞：这一列仍可自由输入 */
  }
}

async function loadCustomReqs() {
  if (!props.customerId) return
  customReqLoading.value = true
  try {
    const { data } = await customerCustomReqApi.list(props.customerId)
    customReqs.value = data
    for (const r of data) customReqOrig[r.id] = customReqSnapshot(r)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '定制化需求加载失败')
  } finally {
    customReqLoading.value = false
  }
}

function isCustomReqDirty(row) {
  if (!row.id) return true
  return customReqOrig[row.id] !== customReqSnapshot(row)
}

async function addCustomReq() {
  try {
    const { data } = await customerCustomReqApi.create({ customer_id: Number(props.customerId) })
    customReqs.value.push(data)
    customReqOrig[data.id] = customReqSnapshot(data)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '新增失败')
  }
}

async function saveCustomReq(row) {
  try {
    const payload = { version: row.version }
    for (const k of CUSTOM_REQ_KEYS) payload[k] = customReqValue(row, k)
    const { data } = await customerCustomReqApi.update(row.id, payload)
    Object.assign(row, data)
    customReqOrig[row.id] = customReqSnapshot(row)
    ElMessage.success('已保存')
  } catch (e) {
    if (e.response?.status === 409) {
      await loadCustomReqs()
    } else {
      ElMessage.error(e.response?.data?.detail || '保存失败')
    }
  }
}

async function deleteCustomReq(row) {
  try {
    await ElMessageBox.confirm('确认删除该定制化需求？', '提示', { type: 'warning' })
  } catch { return }
  try {
    await customerCustomReqApi.remove(row.id)
    customReqs.value = customReqs.value.filter((r) => r.id !== row.id)
    delete customReqOrig[row.id]
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

async function loadIssues() {
  if (!customer.value) return
  issues.loading = true
  try {
    const { data } = await issueApi.getData()
    if (data.configured === false) {
      issues.configured = false
      issues.raw = []
      issues.filtered = []
      issues.bySeverity = {}
      return
    }
    issues.configured = true
    const names = [customer.value.code, ...(customer.value.aliases || []).map((a) => a.alias)]
      .map((s) => (s || '').trim().toLowerCase())
      .filter(Boolean)
    issues.raw = data.raw || []
    issues.filtered = issues.raw.filter((r) => {
      const cat = (r.category || '').toLowerCase()
      return names.some((n) => cat && cat.includes(n))
    })
    const sev = {}
    for (const r of issues.filtered) {
      const k = r.severity || '其它'
      sev[k] = (sev[k] || 0) + 1
    }
    issues.bySeverity = sev
    issues.fileMtime = data.file_mtime || ''
  } catch (e) {
    // 报表配置或解析问题，不阻塞详情页
    issues.configured = false
    issues.raw = []
    issues.filtered = []
    issues.bySeverity = {}
  } finally {
    issues.loading = false
  }
}

watch(() => props.customerId, async () => {
  if (!props.customerId) return
  await Promise.all([loadCustomer(), loadSowFields(), loadExtraFields()])
  await loadMachines()
  await Promise.all([loadIssues(), loadCustomReqs(), loadVersionOptions()])
}, { immediate: true })

watch(activeMachine, async (mid) => {
  if (!mid) return
  const id = Number(mid)
  const st = machineState[id]
  if (!st) return
  // 切 tab 时按需加载（如果之前没加载过）
  await Promise.all([
    st.sowRows.length === 0 && !st.sowLoading ? loadSowRows(id) : Promise.resolve(),
    st.licenses.length === 0 && !st.licenseLoading ? loadLicenses(id) : Promise.resolve(),
    !st.extraLoaded ? loadExtraValues(id) : Promise.resolve(),
  ])
})

// ─── 基本信息 / 别名 ───────────────────────────────────────────

function startAddAlias() {
  addingAlias.value = true
  newAlias.value = ''
  nextTick(() => aliasInputRef.value?.focus?.())
}
function cancelAddAlias() {
  addingAlias.value = false
  newAlias.value = ''
}
async function confirmAddAlias() {
  const s = newAlias.value.trim()
  addingAlias.value = false
  if (!s) return
  if ((customer.value.aliases || []).some((a) => a.alias === s)) {
    newAlias.value = ''
    return
  }
  const next = [...(customer.value.aliases || []).map((a) => a.alias), s]
  await updateAliases(next)
  newAlias.value = ''
}
async function removeAlias(a) {
  const next = (customer.value.aliases || []).filter((x) => x.id !== a.id).map((x) => x.alias)
  await updateAliases(next)
}
async function updateAliases(aliasList) {
  try {
    const { data } = await customerApi.update(customer.value.id, {
      version: customer.value.version,
      aliases: aliasList,
    })
    customer.value = data
    emit('changed', data)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

function openMetaDialog() {
  metaDialog.form = {
    code: customer.value.code,
    display_name: customer.value.display_name || '',
    region: customer.value.region || '',
    industry: customer.value.industry || '',
    sort_order: customer.value.sort_order || 0,
    is_active: !!customer.value.is_active,
  }
  metaDialog.visible = true
}
async function onSaveMeta() {
  try {
    const { data } = await customerApi.update(customer.value.id, {
      version: customer.value.version,
      ...metaDialog.form,
    })
    customer.value = data
    emit('changed', data)
    metaDialog.visible = false
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

// ─── 当前进展 ─────────────────────────────────────────────────

async function saveCurrentStage(m) {
  const st = machineState[m.id]
  try {
    const { data } = await customerStatusApi.update(m.id, {
      version: m.version,
      customer_status: st.current,
    })
    // 同步本地状态
    const idx = machines.value.findIndex((x) => x.id === m.id)
    if (idx >= 0) {
      machines.value[idx] = {
        ...machines.value[idx],
        customer_status: data.customer_status,
        version: data.version,
      }
    }
    st.current = data.customer_status || ''
    ElMessage.success('已同步到总览')
  } catch (e) {
    if (e.response?.status === 409) {
      // 409 已由 axios 拦截器弹 warning；这里重新拉一遍机台状态
      await loadMachines()
    } else {
      ElMessage.error(e.response?.data?.detail || '保存失败')
    }
  }
}

// ─── 里程碑 ───────────────────────────────────────────────────

function openMilestoneDialog(m) {
  const st = machineState[m.id]
  milestoneDialog.machineId = m.id
  // 深拷贝当前里程碑供编辑
  milestoneDialog.rows = (st.milestones || parseMilestones('')).map((x) => ({ ...x }))
  milestoneDialog.visible = true
}

async function saveMilestones() {
  const mid = milestoneDialog.machineId
  const m = machines.value.find((x) => x.id === mid)
  if (!m) return
  milestoneDialog.saving = true
  try {
    const json = JSON.stringify(milestoneDialog.rows)
    const { data } = await customerStatusApi.update(mid, {
      version: m.version,
      milestones_json: json,
    })
    // 同步本地
    const idx = machines.value.findIndex((x) => x.id === mid)
    if (idx >= 0) machines.value[idx] = { ...machines.value[idx], version: data.version, milestones_json: json }
    machineState[mid].milestones = parseMilestones(json)
    milestoneDialog.visible = false
    ElMessage.success('里程碑已保存')
  } catch (e) {
    if (e.response?.status === 409) {
      await loadMachines()
    } else {
      ElMessage.error(e.response?.data?.detail || '保存失败')
    }
  } finally {
    milestoneDialog.saving = false
  }
}

// ─── 自定义信息块 ─────────────────────────────────────────────

function getExtra(mid, fid) {
  const st = machineState[mid]
  if (!st || !st.extra[fid]) {
    return { id: null, field_id: fid, text: '', file_name: '', file_size: 0, has_file: false, version: 0 }
  }
  return st.extra[fid]
}

function isExtraDirty(mid, fid) {
  const st = machineState[mid]
  if (!st) return false
  return (st.extra[fid]?.text || '') !== (st.extraOrig[fid] || '')
}

async function saveExtraText(mid, fid) {
  try {
    const { data } = await customerExtraApi.saveText(mid, fid, getExtra(mid, fid).text || '')
    machineState[mid].extra[fid] = data
    machineState[mid].extraOrig[fid] = data.text || ''
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function onExtraFileChange(mid, fid, file) {
  const raw = file?.raw || file
  if (!raw) return
  try {
    const { data } = await customerExtraApi.uploadAttachment({ machine_status_id: mid, field_id: fid, file: raw })
    machineState[mid].extra[fid] = data
    machineState[mid].extraOrig[fid] = data.text || ''
    ElMessage.success('附件已上传')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
  }
}

async function downloadExtra(mid, fid) {
  const v = getExtra(mid, fid)
  if (!v.id) return
  try {
    const resp = await customerExtraApi.downloadAttachment(v.id)
    downloadBlob(resp.data, v.file_name || 'attachment')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '下载失败')
  }
}

async function removeExtraFile(mid, fid) {
  const v = getExtra(mid, fid)
  if (!v.id) return
  try {
    await ElMessageBox.confirm('确认删除该附件？', '提示', { type: 'warning' })
  } catch { return }
  try {
    const { data } = await customerExtraApi.removeAttachment(v.id)
    machineState[mid].extra[fid] = data
    machineState[mid].extraOrig[fid] = data.text || ''
    ElMessage.success('附件已删除')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// ─── SOW 行 ───────────────────────────────────────────────────

function isRowDirty(row, mid, idx) {
  if (!row.id) return true // 新行
  const st = machineState[mid]
  if (!st) return false
  return st.sowOriginals[row.id] !== JSON.stringify(row.data)
}

async function addSowRow(m) {
  try {
    const blank = {}
    for (const f of sowFields.value) blank[f.key] = ''
    const { data } = await sowApi.createRow(m.id, { data: blank })
    const st = machineState[m.id]
    st.sowRows.push({
      id: data.id,
      version: data.version,
      sort_order: data.sort_order,
      data: fillRowData(data.data),
    })
    st.sowOriginals[data.id] = JSON.stringify(st.sowRows[st.sowRows.length - 1].data)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '新增失败')
  }
}

async function saveSowRow(m, row) {
  try {
    const { data } = await sowApi.updateRow(row.id, {
      version: row.version,
      data: row.data,
    })
    row.version = data.version
    machineState[m.id].sowOriginals[row.id] = JSON.stringify(fillRowData(data.data))
    ElMessage.success('已保存')
  } catch (e) {
    if (e.response?.status === 409) {
      await loadSowRows(m.id)
    } else {
      ElMessage.error(e.response?.data?.detail || '保存失败')
    }
  }
}

async function deleteSowRow(m, row) {
  try {
    await ElMessageBox.confirm('确认删除该 SOW 行？', '提示', { type: 'warning' })
  } catch { return }
  try {
    await sowApi.removeRow(row.id)
    const st = machineState[m.id]
    st.sowRows = st.sowRows.filter((r) => r.id !== row.id)
    delete st.sowOriginals[row.id]
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// ─── License ──────────────────────────────────────────────────

function openLicenseUpload(m) {
  licenseDialog.machine = m
  licenseDialog.file = null
  licenseDialog.remark = ''
  licenseDialog.visible = true
}
function onLicenseFileChange(file) {
  licenseDialog.file = file?.raw || null
}
async function submitLicenseUpload() {
  if (!licenseDialog.file) {
    ElMessage.warning('请选择文件')
    return
  }
  licenseDialog.uploading = true
  try {
    await licenseApi.upload({
      machine_status_id: licenseDialog.machine.id,
      file: licenseDialog.file,
      remark: licenseDialog.remark || '',
    })
    licenseDialog.visible = false
    await loadLicenses(licenseDialog.machine.id)
    ElMessage.success('已上传')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
  } finally {
    licenseDialog.uploading = false
  }
}
async function saveLicenseRemark(m, row) {
  try {
    await licenseApi.updateRemark(row.id, row.remark || '')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存备注失败')
    await loadLicenses(m.id)
  }
}
async function downloadLicense(row) {
  try {
    const resp = await licenseApi.download(row.id)
    downloadBlob(resp.data, row.file_name)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '下载失败')
  }
}
async function deleteLicense(m, row) {
  try {
    await ElMessageBox.confirm(`确认删除 license「${row.file_name}」？`, '提示', { type: 'warning' })
  } catch { return }
  try {
    await licenseApi.remove(row.id)
    const st = machineState[m.id]
    st.licenses = st.licenses.filter((x) => x.id !== row.id)
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// ─── 工具 ────────────────────────────────────────────────────

function formatBytes(n) {
  if (!n) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
function formatDateTime(s) {
  if (!s) return '—'
  try {
    const d = new Date(s)
    if (Number.isNaN(d.getTime())) return s
    const pad = (x) => String(x).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch { return s }
}

defineExpose({ reload: loadCustomer })
</script>

<style scoped>
.cd-panel {
  padding: 4px 4px 8px;
}
.sec {
  margin-bottom: 16px;
}
.sec-head {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  font-size: 15px;
  color: #303133;
  border-left: 3px solid #409eff;
  padding-left: 8px;
  margin-bottom: 10px;
}
.sec-head .actions {
  margin-left: auto;
}
.muted-hint { font-size: 12px; color: #909399; font-weight: normal; }
.muted { color: #c0c4cc; }

.title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding-bottom: 10px;
  border-bottom: 1px dashed #ebeef5;
  margin-bottom: 12px;
}
.title-wrap .code {
  font-size: 20px;
  font-weight: 700;
  color: #303133;
}
.title-wrap .display-name {
  color: #606266;
  font-size: 15px;
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px 24px;
  margin-bottom: 12px;
}
.meta-grid > div { display: flex; flex-direction: column; }
.meta-grid label { color: #909399; font-size: 12px; margin-bottom: 2px; }

.alias-block {
  border-top: 1px dashed #ebeef5;
  padding-top: 10px;
}
.alias-label {
  color: #909399;
  font-size: 12px;
  display: block;
  margin-bottom: 6px;
}
.alias-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 0;
}
.alias-add { margin-left: 6px; display: inline-flex; align-items: center; }

.empty {
  color: #909399;
  text-align: center;
  padding: 24px;
  background: #fafbfc;
  border-radius: 4px;
}
.empty.inline { padding: 12px; }

.machine-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}
.machine-pane {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.block {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #fff;
}
.block-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-bottom: 1px solid #ebeef5;
  font-weight: 600;
  color: #303133;
  font-size: 14px;
}
.block-head .actions { margin-left: auto; }
.block-body {
  padding: 12px;
}
.block-body .right { text-align: right; margin-top: 8px; }

/* 现场关键事务清单 */
.rf-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.rf-box {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  border: 1.5px solid #c0c4cc;
  border-radius: 3px;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all .15s;
}
.rf-box.checked { background: #67c23a; border-color: #67c23a; }
.rf-box svg { width: 9px; height: 9px; display: block; }
.rf-done :deep(.el-input__inner) { color: #b0b3b8; text-decoration: line-through; }

.extra-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 8px;
  flex-wrap: wrap;
}
.extra-file { display: flex; align-items: center; gap: 10px; }
.extra-actions { display: flex; align-items: center; gap: 8px; }

.issue-cards {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.issue-card {
  flex: 1 1 120px;
  min-width: 120px;
  padding: 12px 16px;
  border-radius: 6px;
  background: #f5f7fa;
  color: #303133;
}
.issue-card .num { font-size: 22px; font-weight: 700; }
.issue-card .lbl { font-size: 12px; color: #606266; margin-top: 2px; }
.issue-card.total { background: #ecf5ff; color: #409eff; }
.issue-card.sev-major { background: #fef0f0; color: #f56c6c; }
.issue-card.sev-normal { background: #fdf6ec; color: #e6a23c; }
.issue-card.sev-info { background: #f4f4f5; color: #909399; }
.report-meta {
  margin-top: 8px;
  color: #909399;
  font-size: 12px;
}
</style>
