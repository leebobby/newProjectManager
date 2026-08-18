# 岳麓山项目管理系统

基于 **FastAPI + SQLite + Vue 3 + Element Plus** 搭建的前后端分离项目管理系统。

## 目录结构

```
.
├── backend/                     FastAPI 后端
│   ├── main.py                  入口：迁移链 → create_all → seed → 路由挂载 → 调度启动
│   ├── database.py              引擎 / Session；每条连接挂 PRAGMA（外键 / WAL / busy_timeout）
│   ├── models.py                ORM 模型（50+ 张表，注释含设计取舍）
│   ├── schemas.py               Pydantic v2 请求/响应模型
│   ├── enums.py                 状态 / 优先级枚举的单一来源 + norm_* 规范化校验器
│   ├── auth.py                  bcrypt 哈希 + JWT + get_current_user / require_admin
│   ├── op_log.py                操作日志写入（异常吞掉不影响主流程）
│   ├── notify.py                站内通知分发 dispatch / broadcast（与 op_log 是两条独立路径）
│   ├── scheduler.py             APScheduler：DDL 临期扫描 + 每日问题单快照采集
│   ├── migrate.py               ⚠ 已冻结的加列迁移（历史老库兼容，勿再追加）
│   ├── automigrate.py           启动时自动 alembic upgrade head（失败只记日志）
│   ├── alembic/                 结构变更的正式通道（改名/删列/改类型/加约束/数据回填）
│   │   ├── env.py               render_as_batch=True，SQLite 靠表重建完成 ALTER
│   │   └── versions/            0001_baseline … 0008_special_section_config
│   ├── special_layout.py        专项详情页「版式」解析（分段顺序/标题/启停 + 模板套用）
│   ├── xlsx_io.py               清单类 Excel 导出的统一外观（style_header + beautify）
│   ├── xlsx_utils.py            专项/攻关的单页图文混排 Excel 导出
│   ├── pptx_utils.py            PPT 导出工具
│   ├── config.json              运维可调项（阶段下拉 / 报表路径 / 采集配置 / 硬件清零选项…）
│   ├── requirements.txt
│   ├── scripts/
│   │   ├── fetch_issues_api.py  按项目从 DTS 拉问题单并清洗（问题单管理的采集脚本）
│   │   └── reset_password.py    忘记密码时的救急重置脚本
│   ├── tests/                   pytest 回归（conftest 起临时库，不碰开发库）
│   ├── data/issue_snapshots/    问题单快照明细 JSON（库里只存聚合数字）
│   ├── uploads/                 用户上传文件（已 gitignore，运行时创建）
│   │   ├── handbook/<yyyymm>/    一本通文件
│   │   ├── specials/<id>/        专项全景图 / 分段图片
│   │   ├── key_features/<id>/    关键特性附件
│   │   ├── licenses/             机台 license
│   │   ├── customer_extra/       机台自定义信息块附件
│   │   └── project_formation/    项目阵型图
│   └── routers/                 全部挂 /api 前缀；写操作记 op_log，协作编辑域带乐观锁
│       ├── auth.py                  /auth/login /logout /register(admin) /me /change-password
│       ├── users.py                 /users 用户与人员档案（仅 admin）
│       ├── resource_groups.py       /resource-groups 部门 / PL 组两级主数据
│       ├── op_logs.py               /op-logs 操作日志查询（仅 admin）
│       ├── config.py                /config（GET 公开读，PUT 仅 admin，改采集配置热更新调度）
│       ├── system.py                /system/storage 磁盘使用率等运维信息
│       ├── customers.py             /customers 客户主数据 + 别名（写仅 admin）
│       ├── customer_status.py       /customer-status 机台总览（字段级权限矩阵）
│       ├── customer_issues.py       /customer-issues 软件问题 / 现场事务 / 客户需求（一表三类）
│       ├── hardware_issues.py       /hardware-issues 硬件问题清零（尾部按机台展开）
│       ├── customer_extra.py        /customer-extra 机台自定义信息块（定义 + 值 + 附件）
│       ├── customer_custom_req.py   /customer-custom-reqs 客户定制化需求
│       ├── sow.py                   /sow SOW 列定义（全局）+ 每机台数据行
│       ├── licenses.py              /licenses 机台 license 上传 / 下载
│       ├── key_features.py          /key-features 关键特性目录 + 机台多对多 + 附件
│       ├── business_trips.py        /business-trips 出差记录 + 客户面支撑看板
│       ├── major_versions.py        /major-versions + /iteration-versions 两级版本
│       ├── debug_versions.py        /debug-versions + /debug-demands 现场调试版本 / 诉求 / 接收人
│       ├── annual_iterations.py     /annual-iterations 年度 12 月迭代
│       ├── iteration_requirements.py         /iteration-requirements 领域需求（6 进展子项）
│       ├── iteration_product_requirements.py /iteration-product-requirements 产品需求（7 进展子项）
│       ├── domains.py               /domains 按 PL 组聚合 + 事务与风险跟踪
│       ├── issues.py                /issues 问题单：本地报表 / 趋势 / 快照采集 / PPT
│       ├── metrics.py               /metrics 版本完成率 / 迭代质量 / 组级负载
│       ├── roadmap.py               /roadmap 项目 / 阶段 / 里程碑
│       ├── stakeholders.py          /stakeholders 沟通地图 / 战场矩阵
│       ├── project_formation.py     /project-formation 项目阵型图 + 工时名单
│       ├── specials.py              /specials 专项与攻关：内容 / 事务 / 风险 / 编辑锁 / 周报
│       ├── special_templates.py     /special-templates 专项版式模板（主数据，仅 admin 可写）
│       ├── handbook.py              /handbook 一本通分类 + 条目 + 文件
│       ├── notifications.py         /notifications 通知列表 / 已读 / 订阅 / 广播
│       ├── mapping.py               /mapping 数据对账：字符串字段批量绑主数据（仅 admin）
│       └── _lookups.py              跨 router 复用的「字符串 → 主数据 FK」反查工具
└── frontend/                    Vue 3 前端
    ├── package.json             vue-router / element-plus / echarts / axios
    ├── vite.config.js           /api 反向代理到 8000
    └── src/
        ├── main.js
        ├── App.vue              整体布局（可折叠侧栏 + 7 分组菜单 + 动态二级菜单 + 通知区）
        ├── router/index.js      路由 + 登录守卫；meta.group 决定侧栏分组
        ├── api/index.js         axios 封装（自动带 token + 401/409/423 拦截 + 跨 tab 同步登出）
        ├── store/
        │   ├── auth.js              全局 auth 状态 + 跨 tab 退出广播
        │   ├── idleWatcher.js       15 分钟闲置自动登出（多 tab 共享活动时间）
        │   ├── specials.js          启用中的专项列表（供侧栏二级菜单）
        │   ├── customerIssues.js    客户面问题条目的共享缓存
        │   └── storage.js           localStorage 读写封装
        ├── utils/
        │   ├── featureStatus.js     关键特性状态 → 点灯颜色
        │   ├── gridLight.js         自由表格「点灯」列的取值词表与红黄绿档位
        │   └── format.js            日期 / 文件大小格式化
        ├── components/
        │   ├── CustomerDetailPanel.vue  机台详情主面板（里程碑/SOW/license/自定义块/定制需求）
        │   ├── CustomerIssueCell.vue    表格内的问题条目清单单元格
        │   ├── DebugVersionPanel.vue    现场调试版本面板（版本管理的一个 Tab）
        │   ├── VersionTimeline.vue      版本时间线
        │   ├── VersionMergeDialog.vue   版本合入内容对话框
        │   ├── IssueApiPanel.vue        单项目问题单面板（采集 / 趋势 / 明细）
        │   ├── RichGrid.vue             可增删行列的自由表格（专项自定义分段；列格式含点灯）
        │   ├── RichTextEditor.vue       富文本编辑器
        │   ├── FormationGrid.vue        阵型格子表
        │   ├── MilestoneTimeline.vue    水平里程碑时间线
        │   ├── EditableText.vue         点击进入编辑的多行文本块
        │   ├── EditSelectCell.vue       表格内下拉即时保存单元格
        │   ├── SubscribeButton.vue      订阅 / 取消订阅按钮
        │   ├── NotificationBell.vue     顶栏通知铃
        │   ├── NotificationMarquee.vue  广播通知跑马灯
        │   └── iteration/
        │       ├── DomainRequirementTab.vue   迭代详情 · 领域需求页
        │       └── ProductRequirementTab.vue  迭代详情 · 产品需求页
        └── views/                （路径与权限见下方「页面与功能」）
            ├── Login.vue                    ProjectIntro.vue
            ├── CustomerStatus.vue           CustomerIssueTracking.vue *
            ├── HardwareClearance.vue *      CustomerManagement.vue
            ├── CustomerDetail.vue           BusinessTripManagement.vue
            ├── VersionManagement.vue        IterationManagement.vue
            ├── IterationDetail.vue          IssueManagement.vue
            ├── DomainManagement.vue         KeyFeatureManagement.vue
            ├── MetricsDashboard.vue         RoadmapManage.vue
            ├── RoadmapTimeline.vue *        StakeholderManagement.vue
            ├── ResourceGroupManagement.vue  ProjectHandbook.vue
            ├── SpecialList.vue              SpecialDetail.vue
            ├── SpecialTemplates.vue *
            ├── DataMapping.vue              UserManagement.vue
            └── OperationLogs.vue
                * 无独立路由，作为子组件嵌入：前两者是 CustomerStatus 的
                  「问题跟踪」/「硬件问题清零」Tab，RoadmapTimeline 供
                  ProjectIntro 与 RoadmapManage 复用渲染路线图。
```

## 启动

### 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

- 启动后访问 http://127.0.0.1:8000/docs 查看 Swagger 文档
- 首次启动自动创建 SQLite 数据库 `app.db`，并写入：
  - 默认管理员账号：**admin / admin123**（请尽快修改）
  - 少量业务示例数据

> 如果你在前一版本上跑过、表结构发生过变更（例如 `customer_status` 长度改变、加了 `users` 表），最简单的方式是删除 `backend/app.db` 后重启，让 SQLAlchemy 重新建表。

#### 生产部署环境变量

| 变量名 | 说明 |
| --- | --- |
| `APP_SECRET_KEY` | JWT 签名密钥，必须修改！默认值 `dev-secret-please-change-in-prod` |

### 前端

```powershell
cd frontend
npm install
npm run dev
```

打开 http://127.0.0.1:5173 进入登录页。

## 页面与功能

侧边栏按 `meta.group` 分 7 组渲染，下表按该顺序排列。「权限」列的 *登录用户* 指所有已登录
账号可读可写（协作编辑域，带乐观锁），*仅 admin* 指路由守卫或页面自查拦截非管理员。

| 分组 | 页面 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- | --- |
| — | 登录 | `/login` | 公开 | 仅登录（自助注册已下线，账号由管理员创建）；标题取自 `config.about_content` 首行 |
| 概览 | 项目简介 | `/intro` | 登录用户 | 品牌横幅 + 实时统计 + 模块导航卡片 + 路线图渲染 |
| 概览 | 里程碑管理 | `/roadmaps` | 仅 admin | 甘特式路线图，可管理项目 / 阶段 / 里程碑 |
| 客户面管理 | 客户面状态 | `/customer-status` | 登录用户 | 三个 Tab：**机台总览**（机台编号/客户/型号/阶段/现场版本/关注度/进展/关键特性点灯）、**问题跟踪**（全战场问题条目汇总，可按客户/责任领域/状态过滤，支持导入导出）、**硬件问题清零**（一行一问题，尾部按机台展开清零状态）。总览顶部「编辑」开关切换只读/编辑 |
| 客户面管理 | 客户管理 | `/customers` | 仅 admin | 客户主数据 + 别名维护；另含 SOW 字段配置、自定义信息块配置两个全局配置弹窗。侧栏入口在「客户面状态」二级菜单 |
| 客户面管理 | 客户详情 | `/customers/:id` | 登录用户 | 单客户档案 + 名下机台逐台展开（里程碑 / SOW / license / 自定义信息块 / 定制化需求 / 问题条目），可订阅变更 |
| 客户面管理 | 客户面支撑情况 | `/business-trips` | 登录用户 | 成员出差记录（谁 / 去哪个战场 / 起止时间 / 事由），状态按日期实时推导；含支撑看板视图 |
| 进度管理 | 版本管理 | `/versions` | 登录用户 | 按里程碑项目分 Tab，大版本含版本范围 / 实际发布时间，可展开迭代版本；另有「现场调试版本」Tab（T 版本 + 诉求收集 + 接收人清单） |
| 进度管理 | 迭代管理 | `/iterations` | 登录用户 | 年度视图，12 个月度迭代；点击进入需求清单详情页 |
| 进度管理 | 迭代详情 | `/iterations/:id` | 登录用户 | 两个 Tab：**产品需求**（7 个进展子项）/ **领域需求**（6 个进展子项）；均支持行内编辑、Excel 批量导入、导出 PPT |
| 进度管理 | 问题单管理 | `/issues` | 登录用户 | 按项目分 Tab（YLS3000/5000/8000，走 API 采集：每日快照 + 趋势 + 明细），另有「历史数据」Tab 读本地 Excel 报表（当天数据 / 趋势）；导出 PPT，统计明细可钻取到 19 列原始数据 |
| 进度管理 | 领域管理 | `/domains` | 登录用户 | 两个 Tab：**领域总览**（按 PL 组聚合需求情况 / 问题单情况 / 最近主要工作 / 风险与求助，可下钻明细、可移除不管理的组）、**事务与风险跟踪**（跨领域逐条，带责任领域列） |
| 进度管理 | 关键特性 | `/key-features` | 登录用户（删除 admin） | 全局特性目录：交付状态六档＝点灯、需求度量（总 SR/已验收/已转测）、责任人（FO/SE）、简介、附件与链接；机台按需勾选引用 |
| 进度管理 | 专项管理 | `/specials` | 仅 admin | 增删改专项 / 攻关（kind/name/owner/sort_order/is_active + 周报收件人默认值）。侧栏二级菜单按启用项动态展开 |
| 进度管理 | 专项详情 | `/specials/:id` | 登录用户 | 一专项一页：8 个内置分段（目标 / 里程碑时间线 / 整体进展 / 求助 / 全景图 / 风险问题表 / 事务表 / 阵型）+ 任意个自定义分段（自由表格、文本框、图片）。**分段可改标题、可整段停用、可调顺序，逐专项独立**；admin 可「套用模板」一次性换版式。带**编辑锁**（同一时刻仅一人可编辑，TTL 180s 心跳续期，admin 可强制接管）；导出 Excel 与周报 .eml 均按当前版式生成 |
| 进度管理 | 专项模板 | `/special-templates` | 仅 admin | 维护可复用的**版式预设**：内置分段改标题/停用、自定义表格定义列（文本/下拉/日期/**点灯**）。建专项时可直接套用；套用后与模板脱钩，改模板不影响已建专项 |
| 质量管理 | 度量看板 | `/metrics` | 登录用户 | 四个 Tab：版本完成率 / 迭代质量 / 组级负载 / 调试版本。完成率按进展子项加权（已完成 1.0、进行中 0.5、不涉及不计入） |
| 组织管理 | 干系人管理 | `/stakeholders` | 登录用户（写 admin） | 项目组沟通地图 + 战场沟通矩阵 + **项目阵型**（阵型图上传 / 工时名单，支持 Excel 导入导出） |
| 组织管理 | 组织架构 | `/resource-groups` | 仅 admin | 部门 / PL 组两级资源组主数据；组长挂 users，删除前拦截仍有成员或子组的组 |
| 知识管理 | 项目一本通 | `/handbook` | 登录用户（写 admin） | 自定义分类，条目支持外链或上传文件，普通用户只读 + 下载；顶部关键字搜索 |
| 系统管理 | 数据对账 | `/data-mapping` | 仅 admin | 把历史字符串字段批量绑定到主数据：客户对账（battlefield → customer_id）、人员对账（姓名/工号 → users），支持自动回填 / 手动指定 / 一键建档 |
| 系统管理 | 用户管理 | `/users` | 仅 admin | 增删用户、改角色、禁用、重置密码；也用于维护「纯人员档案」（`can_login=false`）与 PL 组归属 |
| 系统管理 | 操作日志 | `/op-logs` | 仅 admin | 登录与关键写操作审计；可按用户/动作/对象/时间范围/关键字分页查询 |

> 老链接 `/customer-issues` 已重定向到 `/customer-status?tab=issues`；`/specials/:slug` 改为
> `/specials/:id`（`specials.slug` 列保留但不再使用）。

### 客户面状态特性

「机台总览」Tab 的列结构：序号 / 机台编号 / 客户 / 型号 / 当前阶段 / 现场版本 /
近期关注度 / 当前进展 / 现场关键事务 / 软件类风险和问题 / 关键特性 / 硬件清零 / 操作。

- **编辑 / 完成 开关**：默认只读，各字段纯展示、不显示行操作；点「编辑」才进入可改状态
  （新增按钮还要求 admin）。**精简 / 详细** 另一组开关控制两个清单列的展开密度。
- **机台编号 / 客户 / 型号** 创建后锁定：编辑弹窗禁用，`CustomerStatusUpdate` schema
  也不接受，路由层再拒一次；新建时机台编号做唯一校验。
- **仅 admin 可改**（`_ADMIN_ONLY_FIELDS`，越权返回 403）：
  - **当前阶段** 下拉，候选项来自 [backend/config.json](backend/config.json) 的 `current_stages`，运维改文件即可调整，前端无需发版；
  - **现场版本** 记录机台当前部署的软件版本号，下拉源为「大版本 + 迭代版本」合并列表，可 allow-create 手填；
  - **近期关注度** 1-5 星，点击星星即时保存（0 = 未评估）。
- **所有登录用户可改**（`_USER_FIELDS`）：**当前进展** 双击单元格行内编辑，回车保存、ESC 取消。
- **现场关键事务 / 软件类风险和问题** 这两列已不再是 `customer_status.recent_focus` /
  `key_issues` 里的 JSON 清单——自 Alembic `0004_customer_issues` 起提升为实体表
  `customer_issues`，一行一条，靠 `kind` 区分（`task` = 现场关键事务，`issue` = 软件类问题，
  `demand` = 客户需求），额外承载责任人 / 责任领域 / 重要程度 / 提出与计划解决时间 /
  进展记录 / 状态。表格内由 `CustomerIssueCell` 渲染，跨战场汇总见同页「问题跟踪」Tab。
  两个旧文本列仅作回滚保险留在模型与白名单里，现有前端不再写入。
- **关键特性** 列按机台勾选的特性点灯，颜色取自 [featureStatus.js](frontend/src/utils/featureStatus.js)，
  取值与顺序须与后端 `enums.KEY_FEATURE_STATUSES` 六档一致。
- **硬件清零** 列显示 `已清零 / 需清零` 比值（数据源 `GET /api/hardware-issues/machine-summary`，
  状态为「不涉及」的不计入分母，判定集合可用 config 的 `hw_machine_cell_done_options` /
  `hw_machine_cell_na_options` 覆盖）；点数字跳到同页「硬件问题清零」Tab。
- 表头居中，机台编号 / 客户 / 型号 / 当前阶段 四列支持排序。整行更新走乐观锁，
  冲突返回 409。

### 配置文件示例 [backend/config.json](backend/config.json)

```json
{
  "current_stages": ["BFI", "岳麓山", "明场"],
  "issue_report_path": "报表目录路径",
  "about_content": "关于页面的文本内容（管理员可在页面内编辑）"
}
```

## 用户管理与认证

- **认证方式**：本地账号 + JWT（HS256，7 天有效），通过 `Authorization: Bearer <token>` 携带。
- **角色**：
  - `admin` — 可访问用户管理；其他业务接口同 normal。
  - `normal` — 可读写所有业务数据。
- **账号创建**：统一由管理员在 `/users` 页面创建并指定角色；自助注册已下线（`/api/auth/register` 仅管理员可调用）。
- **企业 SSO 预留**：`users` 表带 `auth_provider` 字段（local / company_sso），后续接公司账号体系时新增对应登录路径即可，不必改表结构。

## 后续可优化方向

- 接入公司 SSO（OIDC / LDAP）的实际实现
- 表格筛选、分页、导出 Excel
- 版本管理增加 changelog Markdown 渲染、附件上传
- 迭代管理增加甘特图视图
- 操作日志定期清理（cron + `DELETE WHERE created_at < ...`）
- Docker Compose 一键部署 + Nginx 反向代理

## 更新日志

> **两处已知空档，下面「补记」一节说明。** 日志缺 v0.14 – v0.24 的条目（v0.25.0 直接
> 接到 v0.13.0），且 v0.26.0 之后陆续合入的功能未登记。git 历史在导入本仓库时被压缩成
> 单个 `first upload` 提交，逐版本的日期与边界已无法还原，因此补记按**功能域**归并、
> **不编造版本号与日期**；证据来自 `migrate.py` 里带版本号的迁移注释、
> `alembic/versions/` 的 revision 说明与现有代码本身。后续发版请照常在此追加正式条目。

### 补记 · 尚未编入版本号的变更

**v0.14 – v0.24 空档**（依据 [migrate.py](backend/migrate.py) `_ADDITIONS` 中的版本注释重建）

| 版本 | 变更 |
| --- | --- |
| v0.14 | 专项/攻关拓展：`kind` 区分专项/攻关、周报默认收件人（`email_to`/`email_cc`/`email_subject_tpl`）、事务与风险加 `status`、专项内容加自定义分段 `extra_grids_json` |
| v0.15 | 迭代需求增加「责任人所属小组」`owner_group` |
| v0.16 | 引入**客户主数据** `customers` + `customer_aliases`（code 业务主键 + 多别名），并扩展 `industry` / `intro` / `key_focus` |
| v0.18 | `users` 表扩为人员档案：工号 `emp_no`、岗位 `job_title`、资源组归属 `group_id`、纯档案标记 `can_login`；引入两级**资源组** `resource_groups`（部门 → PL 组） |
| v0.19 | 客户主数据 FK 化：`customer_status` / `stakeholder_battlefields` 挂 `customer_id`；阵型成员挂 `user_id` |
| v0.20 | 业务表 owner / 版本 字符串 → FK（迭代、领域需求、产品需求、专项、事务、风险、一本通条目），反查逻辑收口到 [routers/_lookups.py](backend/routers/_lookups.py) |
| v0.21 | 领域需求增加版本质量统计：合入链接 / 代码量 / 自验证用例数 / 转测后问题单数 |
| v0.22 | 机台里程碑 `milestones_json`；机台自定义信息块（`customer_extra_fields` / `customer_extra_values`）；SOW（`sow_field_defs` / `sow_rows`）与机台 license |
| v0.23 | 专项「一句话进展&求助」拆分为「整体进展」+「求助」两个字段 |
| v0.24 | 专项/攻关详情页分段顺序可调（`section_order_json`，对齐 Alembic `0003`） |

**v0.26.0 之后**（依据 `alembic/versions/0004`–`0007` 与现有代码）

- **客户面问题条目实体化**（Alembic `0004` / `0005`）：`customer_status.recent_focus` /
  `key_issues` 的 JSON 清单提升为实体表 `customer_issues`，一表三类（`issue` / `task` /
  `demand`），补齐责任人 / 责任领域 / 重要程度 / 提出与计划解决时间 / 进展 / 分类专项；
  重要程度旧词表「紧急」迁移为「重要」。新增「问题跟踪」汇总视图与 Excel 导入导出。
- **关键特性重构**（Alembic `0006`）：从机台级单表改为全局特性目录 `key_features` +
  `machine_key_features` 多对多引用；交付状态六档＝点灯、需求度量三数、FO/SE、附件与链接。
- **硬件问题清零**（Alembic `0007`）：`hardware_issues` 一行一问题、尾部按机台展开清零状态
  （`machine_cells_json`，机台增删不改表结构），自定义列值走 `extra_fields_json`，
  列定义在 `config.hw_extra_columns`。
- **问题单 API 采集**：新增按项目（`config.issue_api_projects`）的每日快照体系——
  `issue_snapshots`（库存数字）+ `issue_snapshot_stats`（维度聚合，趋势数据源）+
  `issue_collect_logs`（采集执行日志，成功失败都记），明细 JSON 落
  `backend/data/issue_snapshots/`；采集脚本 [scripts/fetch_issues_api.py](backend/scripts/fetch_issues_api.py)，
  由 [scheduler.py](backend/scheduler.py) 按 `config.issue_snapshot_time` 定时执行（改配置热更新，不用重启）。
  本地 Excel 报表口径保留为「历史数据」Tab，并加 `issue_report_daily` 按天聚合缓存。
- **站内通知**：`notifications` / `notification_reads` / `subscriptions` 三表 +
  [notify.py](backend/notify.py) 分发器（定向 / 广播 / 按订阅），顶栏通知铃与广播跑马灯；
  调度器每天扫描临期与逾期项（专项事务、专项风险、客户面问题）通知责任人。
- **现场调试版本**：`debug_versions` + `debug_demands` + `debug_version_recipients`
  （接收人可从战场沟通矩阵自动带出并逐人勾选），作为版本管理的一个 Tab。
- **度量看板**：版本完成率 / 迭代质量 / 组级负载 / 调试版本四个视图；完成率按进展子项
  加权（已完成 1.0、进行中 0.5、未开始与已延期 0、不涉及不计入分母）。
- **领域管理增强**：事务与风险跟踪 `domain_risks`（跨领域、带责任领域列）、
  不管理的 PL 组软删除 `domain_hidden`。
- **客户面支撑情况**：`business_trips` 出差记录（人 / 战场 / 起止 / 事由），状态按日期
  实时推导不入库，另有支撑看板。
- **数据对账**：[routers/mapping.py](backend/routers/mapping.py) 把历史字符串字段批量绑定到
  主数据（客户 battlefield → `customer_id`；阵型成员姓名/工号 → `users`），支持自动回填 /
  手动指定 / 一键建档。
- **专项编辑锁**：`special_edit_locks` 保证同一专项同一时刻仅一人处于编辑态
  （TTL 180s 心跳续期，超时可接管，admin 可强制接管），写操作冲突返回 **423**；
  另加专项 Excel 导出与周报 `.eml` 生成。
- **专项版式模板**（Alembic `0008`）：不同专项需要不同分段，故分两层——
  运行层 `special_contents.section_config_json` 存每个分段的标题覆盖与启停
  （空对象＝默认标题、全部启用，存量专项行为不变）；授权层新增主数据表
  `special_templates` 存可复用的版式预设，建专项时可套、事后可
  `POST /specials/{id}/apply-template`。套用**只增不删**（按 `tkey` 认领分段，重复套用
  幂等，已填内容与模板外的分段一律保留），套完即与模板脱钩。
  顺序/标题/启停的解析收口到 [special_layout.py](backend/special_layout.py)，
  详情页、Excel 导出、周报三处共用；此前导出与周报写死「一、目标 二、整体进展…」，
  自定义分段进不了周报。自由表格新增**点灯**列格式（页面 / 周报 HTML / Excel 同一套红黄绿）。
- **并发与运维**：SQLite 连接挂 `journal_mode=WAL` / `busy_timeout=5000` /
  `synchronous=NORMAL`，连接池放宽到 15+25；启动路径接入
  [automigrate.py](backend/automigrate.py) 自动 `alembic upgrade head`；新增 pytest
  回归（`backend/tests/`）与 Excel 导出统一样式模块 [xlsx_io.py](backend/xlsx_io.py)。
- **修复 Alembic 升级链卡死**：`0003` 缺幂等守卫，而它要加的列 `migrate.py` 里也有一份，
  轮到 Alembic 时列已存在 → `duplicate column name` 被 `automigrate` 吞成一行 warning，
  结果**整条链停在 `0002`，`0004`~`0007` 从未在存量库上执行过**（新库因 `create_all`
  带全列而无症状）。补守卫后老库一次启动即可 `0002 → 0008` 追平。
- **部署指南重构**（[doc/部署指南.md](doc/部署指南.md)）：拆成「新环境部署」与「历史生产升级」
  两条互斥路径分别成章，每章按 **Linux / Windows** 给两套命令（systemd vs NSSM、cron vs
  任务计划、字体与子进程编码差异），并补上差异速查表；后端 worker 数由 2 更正为 1
  （APScheduler 与采集锁是进程内状态，多 worker 会重复执行）。
- **问题单统计拆分客户面与研发**：标题匹配不到任何客户的单子不再以「未标注」混进客户面
  统计，而是单独一张「研发问题 × 严重程度」表（按小组统计）；统计卡片增加「客户面问题 /
  研发问题」两个数字，钻取带 scope。页面与快照导出 Excel 的「统计分析」表同款口径。
- **问题单每日新增 / 解决**（新表 `issue_snapshot_flows`，`create_all` 自动建）：快照只存
  "当天还开着的单"，所以新增/解决靠相邻两次快照的编号集合求差，采集后增量算一次落库，
  看图只读数字。两套口径——**按采集日差分**（新增与解决同口径，净增＝存量差，从第二次
  采集算起）与**按编号创建日**（编号 SDTS+YYYYMMDD+序号 自带创建日，可回溯到开始采集
  之前）；新增「新增/解决」Tab，柱状＋存量折线，点数字钻取当天明细（解决的单当天已不在
  快照里，明细回上一次快照的文件取）。

---

### v0.26.0 — 2026-06-07

**数据库治理（数据模型重构第一步：先打地基）**
- **引入 Alembic**（[backend/alembic/](backend/alembic/)，用法见 [alembic/README.md](backend/alembic/README.md)）作为结构变更的系统：负责 `create_all` 做不到的改名 / 删列 / 改类型 / 加约束 / 数据回填；`env.py` 开 `render_as_batch=True` 让 SQLite 靠表重建完成 ALTER。基线 `0001_baseline`；现有库一次 `alembic stamp 0001_baseline` 接入，之后 `alembic upgrade head` 应用变更。
  - `migrate.py`（`ADD COLUMN`）就此**冻结**，新列/表/约束一律走 Alembic；`create_all` 仍保留在启动路径（新库/新表开箱即用，零风险）。
- **启用 SQLite 外键约束**：[database.py](backend/database.py) 给每条连接挂 `PRAGMA foreign_keys=ON`。此前 models 里所有 `ondelete=CASCADE/SET NULL` 只是写进 DDL 不生效——级联仅靠 ORM 兜底、裸 SQL 删除会留悬空外键；现已在数据库层强制（升级前已用 `PRAGMA foreign_key_check` 核验存量库零悬空外键）。
- **状态/优先级枚举收口** 到 [backend/enums.py](backend/enums.py) 单一来源：进展状态 6 值（含「已变更」）、优先级 P0–P3、事务/迭代状态。此前这些词表以自由字符串散落在各 router 与前端，导致口径漂移、错字静默漏算。
  - **统一两张需求表的优先级口径**：产品需求由「高/中/低」并入「P0–P3」（领域需求口径），存量数据由迁移 `0002` 按 高→P1/中→P2/低→P3 映射，Excel 导入自动转换，前端下拉同步。
  - Pydantic 校验只挂在 **Create/Update** schema（`norm_priority`/`norm_progress`），不碰 Base/Out——避免读取老库历史值时 `from_attributes` 抛错。

### v0.25.0 — 2026-06-06

**权限与安全收紧**
- 自助注册下线：`/api/auth/register` 改为仅管理员可调用，登录页移除「注册」Tab。账号统一由管理员在「用户管理」创建，消除「任何能访问接口的人都能自助建号」的风险。
- 遗留写接口下线：`versions`、`iterations` 两个旧路由改为**只读**（移除 POST/PUT/DELETE，仅项目简介页仍读 `versions`）；前端 `versionApi` 只保留 `list`，删除无人使用的 `iterationApi`。
- **侧边栏分组**

- 扁平长菜单改为 7 个分组：概览 / 客户面管理 / 进度管理 / 质量管理 / 组织管理 / 知识管理 / 系统管理；管理员专属项集中到「系统管理」。路由加 `meta.group`，[App.vue](frontend/src/App.vue) 用 `el-menu-item-group` 渲染，折叠态自动隐藏分组标题、整组无可见项时不显示。

**新增页面：领域管理**
- 路由 `/domains`（「进度管理」组），按组织架构中的 PL 资源组分类，每个 PL 组一行关联：
  - **需求情况** — 聚合迭代需求（口径＝当前进行中迭代），按完成 / 进行 / 未开始 / 延期 + 优先级统计，可下钻明细。
  - **问题单情况** — 实时读取问题单 Excel「原始数据」，按"责任人所属小组"匹配 PL 组名聚合（未配置/读不到则显示「未接入」），可下钻。
  - **最近主要工作** — 富文本，人工维护。
  - **风险与求助** — 结构化逐条（内容 / 类型「风险 / 求助」/ 状态），可增删。
- 新表 `domain_contents`（每 PL 组一行：最近主要工作 + 风险求助 JSON + 乐观锁），由 `create_all` 自动建。最近主要工作 / 风险求助属协作编辑域（登录可写，带 409 乐观锁）。
- 后端 [routers/domains.py](backend/routers/domains.py)：`GET /api/domains`、`GET /{id}/requirements`、`GET /{id}/issues`、`PUT /{id}/content`。

**客户面状态（总览）**
- 顶部新增「**编辑 / 完成**」开关，默认**只读**：只读态各字段纯展示、清单不可勾选/增删、不显示行操作；进入编辑态才可改并显示「编辑/删除」行操作与「新增」。
- 去掉「**问题单情况**」列及其分布抽屉（问题单分布改为只在客户详情页查看）。

**客户详情**
- 每台机台在「当前进展」之后新增「**现场关键事务**」清单块；编辑写的是 `recent_focus` 字段，与总览同一字段**双向同步**。登录用户可编辑，带 409 乐观锁。

**升级提示**
- 老库无需删 `app.db`，`domain_contents` 表启动时自动创建。

---

### v0.13.0 — 2026-05-20

**新增页面：项目一本通**
- 路由 `/handbook`，所有登录用户可访问，admin 维护内容。
- 分类自定义（`handbook_categories` 表），admin 增删改；条目（`handbook_items` 表）支持两种载体：**外链 URL** 或 **上传文件**。
- 文件存储到 `backend/uploads/handbook/<yyyymm>/<uuid>.<ext>`，下载走鉴权后的 blob 接口（`GET /api/handbook/items/{id}/download`）。
- 顶部关键字搜索：标题 / 说明 / 责任人 / URL / 文件名命中即过滤。

**新增页面：专项管理**
- 侧栏二级菜单：动态加载启用中的专项，admin 多一项 "专项配置"。
- 专项元数据（`specials` 表：slug / name / owner / sort_order / is_active）由 admin 维护；专项内容、事务、风险所有登录用户均可编辑（与客户面状态字段权限一致）。
- 单专项页面（`/specials/:slug`）按设计稿组装：
  - **专项目标**（文本，行内点击编辑）
  - **专项计划**（里程碑结构化数据：名称/日期/状态，水平时间线渲染，含未开始/进行中/已完成/已延期 4 种状态色）
  - **一句话进展&求助**（文本，行内点击编辑）
  - **专项全景图**（admin 上传图片，blob 鉴权流式下载）
  - **专项事务表**（序号/事务内容/当前进展/责任人/计划闭环时间，CRUD）
  - **风险和问题表**（同上结构）
  - **专项阵型**（动态可增删行/列的文本格子，统一保存）
- 内容字段加乐观锁（`version`），并发编辑返回 409。
- 新增组件 [EditableText.vue](frontend/src/components/EditableText.vue) / [MilestoneTimeline.vue](frontend/src/components/MilestoneTimeline.vue)。
- 关键写操作全部接入操作日志（一本通分类/条目，专项/专项内容/全景图/事务/风险）。

**数据库**
- 新建 6 张表：`handbook_categories` / `handbook_items` / `specials` / `special_contents` / `special_tasks` / `special_risks`，由 `create_all` 在启动时自动创建，无需手动迁移。
- 文件目录 `backend/uploads/` 已加入 `.gitignore`，部署时确保后端进程有写权限；备份脚本需追加该目录。

---

### v0.12.0 — 2026-05-20

**操作日志**
- 新增 `operation_logs` 表 + `op_log.log_op()` 工具（异常吞掉不影响主流程）。
- 记录范围：登录成功 / 失败 / 登出 / 注册 / 修改密码；以及所有关键写操作（新增 / 修改 / 删除 / 导入 / 导出 PPT / 运行脚本 / 修改配置）。
- 新增页面 [OperationLogs.vue](frontend/src/views/OperationLogs.vue) 路由 `/op-logs`（仅 admin）：可按用户 / 动作 / 对象 / 关键字 / 时间范围分页查询。
- 后端接口：`GET /api/op-logs`（分页+过滤）、`GET /api/op-logs/options`（下拉候选值）。

**闲置自动登出 + 多 tab 同步**
- 前端默认 15 分钟无操作（鼠标 / 键盘 / 滚动 / 触摸）自动登出并跳登录页，阈值在 [App.vue](frontend/src/App.vue) `IDLE_MS` 常量调整。
- 活动时间通过 `localStorage` 跨 tab 共享：任一 tab 在用其它 tab 都不会被判定为闲置。
- 一处登出（手动 / 401 / 修改密码 / 闲置触发）通过 `apm_logout_signal` 广播给所有 tab 同步退出。
- 「退出登录」会先调 `POST /api/auth/logout` 写一条登出日志（JWT 本身无服务端会话）。

**升级提示**
- 老库无需删 `app.db`，`operation_logs` 表自动创建。

---

### v0.11.0 — 2026-05-19

**客户面状态清单化**
- 「现场关键事务」（原"近期现场关键诉求"）与「软件类风险和问题」两列改为可勾选的清单：每行一个复选框 + 文本，勾选表示完成。
- 视图模式切换：**精简模式** 只显示第一个条目 + `+N` 计数；**详细模式** 全部展开 + 进度条。
- 数据存储用 JSON 数组：`[{"text":"...","done":true/false}, ...]`；旧的纯文本数据按换行符自动拆分兼容，无需迁移。
- PPT 导出同步：JSON 清单转换为 `✓ 已完成 / · 未完成` 可读文本。

**客户面状态多项修复**
- 表头改为居中对齐；机台编号 / 客户 / 型号 / 当前阶段 四列支持排序。
- 「问题单情况」改为"查看分布"链接，弹出 drawer 按客户分布展示，支持下钻到具体问题单（按 `group` + `category` 过滤匹配 19 列原始数据）。
- 「现场版本」下拉切到 `majorVersionApi`（合并大版本 + 迭代版本），与版本管理数据源对齐。
- 精简模式补「+」新增按钮；多列模板下用函数 ref 修复 focus 失效。

**问题单管理增强**
- 当天数据「统计明细」加 **表格 / 图表 / 同时显示** 切换按钮，避免数据多时压缩严重。
- 原始数据按 A-S 全部 19 列对齐（版本信息 / 缺陷业务编号 / 标题 / 当前责任人 / 当前责任人所属小组 / 进展 / 严重程度 / 严重程度DI值 / 根因 / 解决措施 / 进展记录 / 预计闭环时间 / 优先级 / 是否SDTS / 年份 / 月份 / 日期 / 年月 / 标题分类），修复钻取后明细为空的问题。
- "特性数据"暂时隐藏（`SHOW_FEATURE = false`，代码保留）。

**全局**
- 左侧导航栏改为可折叠（按钮在顶栏左侧），折叠状态写入 `localStorage`，刷新保留。
- 部署指南新增 5.4 节"特定版本升级说明"，记录 v0.10.x 清单字段格式变更的兼容方案。

---

### v0.10.0 — 2026-05-18

**登录页 & 首页**
- 登录页标题改为读 `config.about_content` 首行（之前是写死的"AI 项目管理系统"）；移除默认 admin 账号明文密码提示。
- 首页系统模块卡片调整间距，第一行和第二行之间不再挤压。

**问题单管理**
- 当天数据目录支持日期子目录结构：`<root>/YYYY-MM-DD/缺陷统计报表_*.xlsx`，新增日期选择器；如果根目录没有日期子目录则回退扁平扫描。
- 关闭"实时刷新"模式下的自动刷新。
- 原始数据表格列对齐到实际报表 A-G 7 列（注：后续 v0.11 又扩到全部 19 列以支持钻取）。

**接口**
- `GET /api/issues/dates` 列出可选日期；`GET /api/issues/data?date=` 与 `GET /api/issues/export.pptx?date=` 支持指定日期。

---

### v0.9.0 — 2026-05-17

**品牌重命名 & 配置调整**
- 系统名称全面改为「岳麓山项目管理系统」：浏览器标签页（`index.html`）、侧边栏 Logo（`App.vue`）、首页横幅（`ProjectIntro.vue`）同步更新。
- `config.json` 中 `current_stages` 调整为 `["BFI", "岳麓山", "明场"]`，与实际项目阶段对齐。

**首页「关于」卡片可编辑**
- 管理员在首页「关于」卡片右上角点击「编辑」，可直接在页面内修改内容（textarea），保存后通过 `PUT /api/config` 持久化到 `config.json`。
- 非管理员只读展示，内容支持换行（`white-space: pre-wrap`）。

**问题单管理优化**
- 删除「当天数据」模式下的「月度趋势」子 Tab（数据口径有误，移除避免误导）。
- 删除 mode-bar 中的独立「刷新」按钮（功能已被「实时刷新」模式覆盖，减少 UI 冗余）。

---

### v0.8.0 — 2026-05-17

**版本管理重构**
- 版本管理页面完全重写，支持按里程碑项目分 Tab 展示（从 `GET /api/roadmap/projects` 加载），另有「全局版本」Tab 存放不挂项目的版本。
- 引入二级版本结构：
  - **大版本**（`major_versions` 表）：版本号、标题、版本说明、版本范围（起止日期）、实际发布时间；约每 1.5 个月一个。
  - **迭代版本**（`iteration_versions` 表）：隶属于某个大版本，版本号、标题、预计发布日期；约每周一个；在大版本行展开后显示子表格。
- 新增后端路由 [routers/major_versions.py](backend/routers/major_versions.py)：
  - `GET /api/major-versions?project_id=...` — 按项目查询大版本列表（含嵌套迭代版本）
  - `POST/PUT/DELETE /api/major-versions/{id}` — 大版本 CRUD（admin 写，所有登录用户读）
  - `POST/PUT/DELETE /api/iteration-versions/{id}` — 迭代版本 CRUD（admin 写）
  - `GET /api/iteration-versions/all` — 返回所有迭代版本的扁平列表，含项目 / 大版本归属信息
- **迭代需求「计划交付版本」改为下拉选择**：从 `/api/iteration-versions/all` 加载候选项，按「项目 · 大版本」分组展示；保留 `allow-create` + `filterable`，仍可手动输入自定义版本号。
- 两张新表通过 `Base.metadata.create_all` 在启动时自动建，无需迁移脚本。

**升级提示**
- 老库（v0.7.0 → v0.8.0）无需删 `app.db`，新表自动建。

---

### v0.7.0 — 2026-05-17

**并发安全：乐观锁**
- 对三张高频多管理员编辑的表添加 `version` 乐观锁字段：`customer_status`、`iteration_requirements`、`roadmap_phases`。
- 每次 `PUT` 请求需携带当前 `version`；后端比对不一致时返回 `HTTP 409 Conflict`（提示「数据已被他人修改，请刷新后重试」）；成功则 `version += 1` 并返回新值给前端。
- axios 响应拦截器全局处理 409：自动弹 `ElMessage.warning`，无需各页面单独处理。
- [migrate.py](backend/migrate.py) 自动为老库三张表补 `version INTEGER NOT NULL DEFAULT 0` 列。
- 影响页面：CustomerStatus、IterationDetail、RoadmapManage。

**问题单管理（新页面）**
- 新页面 `/issues`（`IssueManagement.vue`），侧边栏菜单可见。
- **数据来源**：读取服务器指定目录下的 Excel 报表（格式 `缺陷统计报表_YYYYMMDD.xlsx`，6 个 sheet：原始数据 / 按组统计 / 按严重性统计 / 按模块统计 / 按负责人统计 / 月度趋势）；自动按文件名日期后缀选取最新文件。
- **三种浏览模式**（按钮切换）：
  - 「当天数据」：统计卡片（合计 / 严重 / 一般 / 提示，可点击展开明细抽屉）+ 3 张统计表各配对一个 ECharts 堆叠条形图 + 原始数据搜索表格。
  - 「查看趋势」：扫描目录下所有日期报表，绘制两条每日趋势折线图（按组 / 按严重性）+ 每日汇总表。
  - 「实时刷新」（admin）：触发后端执行配置的刷新脚本（`.py` / `.bat` / `.exe`），实时显示 stdout / stderr，成功后可一键切换至最新数据。
- **PPT 导出**：`GET /api/issues/export.pptx`，生成含彩色统计卡片 + 3 张统计明细表的演示文档。
- **管理员配置区**：报表目录路径 + 脚本路径，通过 `PUT /api/config` 持久化写入 `config.json`。
- 新增后端路由 [routers/issues.py](backend/routers/issues.py)：`GET /data`、`GET /trend`、`POST /run-script`、`GET /export.pptx`。

**配置接口**
- `GET /api/config` 已存在；本版新增 `PUT /api/config`（admin 限定），前端可保存任意配置键值到 [config.json](backend/config.json)。

**升级提示**
- 老库（v0.6.0 → v0.7.0）无需删 `app.db`，启动自动补三列。
- 需安装新依赖 `openpyxl`（若 v0.6.0 已安装则已满足）。

---

### v0.6.0 — 2026-05-16

**公共能力**
- 顶部用户下拉新增「修改密码」入口，调用 `POST /api/auth/change-password`，校验原密码并要求新密码 ≥ 6 位；修改成功后自动登出并跳登录页。
- 项目简介 / 首页重做：品牌色横幅 + 技术栈徽章 + 实时统计（版本 / 迭代 / 机台数）+ 可点击的模块卡片（含 hover 抬升与图标渐变），按角色显示用户管理入口。

**客户面状态页**
- 新增首列「序号」，直接显示行号，便于一眼看到行数。
- 「现场版本」改为下拉，候选项来自版本管理；同时保留 `allow-create`，可手动输入未登记的版本号。
- 新增最后一列「问题单情况」，存为 `issue_url`；管理员可双击/「设置」编辑，普通用户看到「查看」按钮新窗打开。
- PPT 导出全面改版：品牌色横幅标题 + 副标题（导出时间 / 数量）、斑马纹数据行、统一边框、问题单列同步加入。

**迭代管理页**
- 迭代详情页新增「批量导入」按钮：弹窗内一键下载 xlsx 模板（含表头 + 一行示例 + 提示），上传后调用 `POST /api/iteration-requirements/import?iteration_id=...` 批量入库，逐行报错提示。
- 新增「备注」列（`remark`）：记录该需求是否存在变更，双击编辑；表格内有内容时左侧出现「变更」橙色徽标。
- PPT 导出修复：表头增加「交付进展跟踪」父级标题（覆盖 6 个进展子列），新增「备注」列；表头使用品牌色 + 双层结构（父 / 子表头自动合并）。

**数据模型 & 路由**
- `CustomerStatus` 新增 `issue_url: VARCHAR(512)`；`IterationRequirement` 新增 `remark: TEXT`。
- [migrate.py](backend/migrate.py) 自动为老库补这两列。
- 新增路由：`POST /api/auth/change-password`、`GET /api/iteration-requirements/import-template.xlsx`、`POST /api/iteration-requirements/import`。
- 客户面状态字段权限矩阵：`issue_url` 归入「仅管理员可改」分组。

**依赖**
- requirements.txt 新增 `openpyxl==3.1.5`（用于 xlsx 模板下载与批量导入解析）。请在后端环境执行 `pip install -r requirements.txt`。

**升级提示**
- 老库（v0.5.0 → v0.6.0）无需删 `app.db`，启动会自动补列。

### v0.5.0 — 2026-05-16

**客户面状态页改造**
- 列结构调整：机台编号 / 客户（原战场，仅 UI 重命名）/ 型号（新字段 `model`） / 当前阶段 / 现场版本 / 近期关注度 / 当前进展 / 近期现场关键诉求 / 软件类风险和问题。
- 创建后锁定：机台编号、客户、型号（编辑弹窗禁用，后端 schema 也不接受）。
- 字段级权限：
  - **仅管理员可改**：当前阶段、现场版本、近期关注度（前端控件 disable，后端 PUT 校验返回 403）。
  - **所有登录用户可改**：当前进展、近期现场关键诉求、软件类风险和问题（行内双击编辑，立即保存）。
- 新增 / 编辑 / 删除按钮均收紧为管理员可见。
- 新增「导出 PPT」按钮（admin 限定），调用 `GET /api/customer-status/export.pptx`，单页 16:9 表格输出当前全量数据。

**迭代管理页面重构**
- 顶层视图改为年度规划：年份切换器 + 12 行月度迭代表格（不存在的月份自动占位）。
  - 列：月份 / 迭代名称 / 负责人 / 状态 / 迭代目标。
  - 迭代名称、负责人、目标、状态：仅管理员可改（双击或下拉切换）。
  - 点击「迭代名称」或「进入」跳转 `/iterations/:id` 子页面。
- 子页面 `IterationDetail`：需求清单表格。
  - 列：序号 / 需求编号（带超链接）/ 需求标题 / 责任人 / 优先级 / 计划交付版本 / 交付进展跟踪（含 6 个子状态列：需求串讲 / 反串讲 / STC设计 / 编码 / BBIT / 转测澄清）。
  - 子状态枚举：未开始 / 进行中 / 已完成 / 已延期 / 不涉及，直接下拉即时保存。
  - 普通字段支持双击行内编辑或「完整编辑」弹窗。
  - 「导出 PPT」按钮（admin 限定）：调用 `GET /api/annual-iterations/{id}/export.pptx`，输出该迭代全量需求的单页 16:9 表格。

**数据模型 & 路由**
- 新增 `AnnualIteration`（年/月唯一）、`IterationRequirement`（外键挂到年度迭代）两张表，旧的 `iterations` 表保留兼容。
- 新增 [routers/annual_iterations.py](backend/routers/annual_iterations.py)、[routers/iteration_requirements.py](backend/routers/iteration_requirements.py)、[pptx_utils.py](backend/pptx_utils.py)（PPT 生成）。
- [migrate.py](backend/migrate.py) 自动给老库补 `customer_status.model` 列；新增的两张表通过 `Base.metadata.create_all` 自动建。
- 启动种子：当前自然年自动生成 12 个迭代占位 + 当前月份示例需求一条。

**依赖**
- requirements.txt 新增 `python-pptx==1.0.2`，请在后端环境执行 `pip install -r requirements.txt`。

**升级提示**
- 老库（v0.4.0 → v0.5.0）无需删 `app.db`，启动会自动迁移并补齐种子。

### v0.4.0 — 2026-05-14

**客户面状态页：新增「现场版本」列**
- 数据模型：[models.py](backend/models.py) `CustomerStatus.field_version`（VARCHAR(128)，默认空串）；[schemas.py](backend/schemas.py) 同步加字段。
- 列位置在「当前阶段」与「近期关注度」之间。
- 支持表格内双击行内编辑（与「近期重点事务」「关键问题」一致），回车保存、ESC 回滚。
- 新增 / 编辑弹窗也加了「现场版本」输入框。
- 种子示例数据补 `field_version` 值。

**轻量迁移**
- [migrate.py](backend/migrate.py) `_ADDITIONS` 追加 `customer_status.field_version` 一项，老库（v0.3.0）启动时自动 `ALTER TABLE ADD COLUMN`，无需删 `app.db`。

### v0.3.0 — 2026-05-13

**客户面状态页增强**
- 「当前阶段」下拉候选改为固定的项目阶段：装机 / T0-T1 / T1-T2 / T2-T3 / T3 Release / 验收完成，写在 [backend/config.json](backend/config.json)，运维改文件即可调整。
- 新增「近期关注度」列，紧跟在「当前阶段」之后，使用 1-5 星表示（0 表示未评估）：
  - 数据模型：[models.py](backend/models.py) `CustomerStatus.attention_level` 整型字段，默认 0；schema 在 `CustomerStatusBase` / `CustomerStatusUpdate` 同步加字段。
  - 表格内点击星星即时保存（局部 `PUT { attention_level }`），无需打开编辑弹窗；失败自动回滚。
  - 新增 / 编辑弹窗中也加了 `el-rate` 控件。
- 种子示例数据带上 `attention_level`，启动后立刻能看到星级效果。

**轻量数据库迁移**
- 新增 [backend/migrate.py](backend/migrate.py)，启动时检查 `customer_status` 表是否缺少 `attention_level` 列，通过 `ALTER TABLE ADD COLUMN` 自动补齐。后续再有简单加列场景只需在 `_ADDITIONS` 列表追加一项。
- 老库 **无需删除** `app.db` 即可平滑升级到本版本（v0.2.0 → v0.3.0）。如果你是从 v0.1.0 直接升级，由于当时还没有 `users` 表 / `customer_status` 字段长度变更，仍建议删 db 重启。

### v0.2.0 — 2026-05-13

**客户面状态页改进**
- 机台编号、战场首次保存后锁定，编辑弹窗中两个字段 `disabled`；后端 `PUT /api/customer-status/{id}` 的 schema 收窄为仅接受 `current_stage / customer_status / recent_focus / key_issues` 四个字段（[backend/schemas.py](backend/schemas.py) 中 `CustomerStatusUpdate`），即使前端被绕过也无法改这两列。
- 新建时机台编号唯一性校验（[routers/customer_status.py](backend/routers/customer_status.py)）。
- "当前阶段" 改为下拉，候选项由 [backend/config.json](backend/config.json) 的 `current_stages` 提供，通过新接口 `GET /api/config` 暴露给前端；运维改文件即可调整，前端无需发版。
- 字段重命名：「客户面状态」→「客户面进展」（仅 UI 标签变更，数据库字段名保留 `customer_status` 以避免迁移）。
- 「近期重点事务」「关键问题」两列支持 **双击单元格行内编辑**，回车 / 失焦保存（局部 PUT，只发改动字段），ESC 取消并回滚。

**新增用户管理系统**
- 后端：新增 [auth.py](backend/auth.py)（bcrypt 哈希 + python-jose JWT + `get_current_user` / `require_admin` 依赖）、[routers/auth.py](backend/routers/auth.py)（`/login` `/register` `/me`）、[routers/users.py](backend/routers/users.py)（admin 专属 CRUD）。
- 业务路由全部挂载 `Depends(get_current_user)` 全局认证；用户管理路由内层挂 `require_admin`。
- 数据模型新增 `User` 表（[models.py](backend/models.py)），字段含 `role` (admin/normal)、`is_active`、`auth_provider` (local/company_sso，为公司 SSO 预留)。
- 首次启动自动注入 `admin / admin123` 账号（[main.py](backend/main.py) `seed_initial_data`）。
- 安全约束：管理员不能修改自己的角色、不能禁用自己、不能删除自己。
- 前端：新增 [store/auth.js](frontend/src/store/auth.js) 全局 auth 状态（token + user，持久化到 localStorage）、[Login.vue](frontend/src/views/Login.vue)（登录 / 注册 Tab）、[UserManagement.vue](frontend/src/views/UserManagement.vue)（admin 可见的用户表格）。
- axios 拦截器自动注入 `Authorization: Bearer ...`，收到 401 自动清 session 并跳登录页（[api/index.js](frontend/src/api/index.js)）。
- 路由守卫：未登录跳 `/login`、`requireAdmin` 路由对 normal 用户隐藏（[router/index.js](frontend/src/router/index.js)）；侧边菜单同步按角色过滤。
- [App.vue](frontend/src/App.vue) 头部加用户下拉（显示姓名 + admin 标签 + 退出）；登录页使用独立无侧栏布局（`meta.layout: 'blank'`）。

**部署相关**
- 新增环境变量 `APP_SECRET_KEY` 用于 JWT 签名，默认 `dev-secret-please-change-in-prod`，**生产必须覆盖**。
- requirements.txt 新增依赖：`python-jose[cryptography]`、`bcrypt`、`python-multipart`。

**迁移注意**
- 数据库表结构有变更（新增 `users` 表、`customer_status.customer_status` 字段长度由 128 增至 256）。SQLAlchemy 的 `create_all` 不会修改已有表，**升级时请删除 `backend/app.db` 后重启**让其重新建表。

### v0.1.0 — 2026-05-13

- 初版骨架：FastAPI + SQLite + Vue 3 + Element Plus
- 4 个页面：项目简介 / 客户面状态 / 版本管理 / 迭代管理
- 所有业务模块基础 CRUD
