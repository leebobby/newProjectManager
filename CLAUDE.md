# 开发约定

本文件是 **岳麓山项目管理系统** 的工程约定索引，供在本仓库上开发的人（和 AI 助手）在动手前
对齐口径。业务功能说明见 [README.md](README.md)，部署与运维见 [doc/部署指南.md](doc/部署指南.md)。

> 本文件是若干 router 注释里「见 CLAUDE.md『Write-permission principle』」的落点。

---

## 速览

```
后端  backend/   FastAPI + SQLAlchemy + SQLite      入口 main.py，端口 8000
前端  frontend/  Vue 3 + Vite + Element Plus        端口 5173，/api 代理到 8000
```

```bash
# 后端
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload --port 8000      # 默认账号 admin / admin123
.venv/bin/python -m pytest tests -q                  # 回归测试（用临时库，不碰 app.db）
# 前端
cd frontend && npm ci && npm run dev
npm run lint                                         # eslint，主要就为了 no-undef
npm run test:e2e                                     # 冒烟：真开浏览器把每页点一遍
```

**提交前跑一遍 `pytest` + `npm run lint` + `npm run build` + `npm run test:e2e`**，
这四条就是 [.github/workflows/ci.yml](.github/workflows/ci.yml) 里跑的全部内容。
冒烟用例（[frontend/tests/smoke.spec.js](frontend/tests/smoke.spec.js)）不验业务口径，
只回答「打出来的包点得开吗」——前三条全绿而页面白屏是真发生过的。
它从**真实 DOM 里取侧栏菜单项**，新加的页面自动被覆盖，不必回来改测试；
`playwright.config.js` 的 `webServer` 会自己把前后端拉起来（后端用全新的 `app.db`）。
装依赖用 `npm ci` 不用 `npm install`：前者严格按 `package-lock.json` 装，
后者会在锁文件与 `package.json` 不一致时顺手改锁文件，于是各人装出各人的依赖。

**测试文件里不要在模块顶层 import 应用模块**（`routers.*` / `models` / `database`）。
`conftest.py` 的 `client` 夹具靠 `os.chdir` 把 `sqlite:///./app.db` 指到临时目录，
收集阶段的顶层 import 会赶在 chdir 之前把引擎连上仓库里的 `backend/app.db`，
之后整个会话都跑在那个老库上。表现是**别的测试文件成片报「no such column」**，
而单跑这个文件一切正常——看着完全不像是新加的文件干的。要用就在夹具里 import
（夹具依赖 `client`，顺序才有保证）。

`main.py` 的启动顺序是有意为之，改动前先读懂：
`ensure_schema()`（老库补列）→ `Base.metadata.create_all()`（补缺失的表）→
`automigrate.upgrade_to_head()`（追平 Alembic）→ `seed_initial_data()` → `scheduler.start()`。

---

## Write-permission principle

写权限只有三档，**新增接口必须落在其中一档**，不要发明第四种：

| 档位 | 依赖 | 适用 |
| --- | --- | --- |
| **登录用户**（协作编辑域） | `Depends(get_current_user)` | 日常填报与记录：进展、事务、风险、问题条目、出差、调试版本、领域内容、领域遗留问题、关键特性…… |
| **仅 admin** | `Depends(require_admin)` | 主数据与配置：用户、资源组、客户、里程碑项目、版本三层、专项元数据、专项版式模板、一本通、干系人、阵型、领域问题单目标、`config.json`、数据对账 |
| **字段级白名单** | 路由内按角色逐字段判 | 同一行里不同字段权限不同，见 [routers/customer_status.py](backend/routers/customer_status.py) |

配套硬规则：

- **删除权限按「删掉的是什么」定，不跟随该表的写权限**。现状（逐个端点核对得来）：
  - **仅 admin**：主数据与配置类，以及客户面数据——客户面问题条目、硬件清零、
    SOW 字段与数据行、机台 license、机台自定义信息块、客户定制化需求、专项本体。
  - **登录用户**：专项/攻关的事务行与风险行、专项分段图片、现场调试版本与诉求与接收人、
    出差记录、领域风险、领域遗留问题。
  - 判断依据是「误删的代价」：别人长期跟踪的客户面记录和主数据要拦，
    自己录的日常条目不拦。新增删除接口时对照上面两组归类，**不要凭该表的写权限推断**。
- **创建后锁定的字段**要在三处都拦住：前端禁用、`*Update` schema 不声明该字段、路由再拒一次。
  只靠前端等于没拦。
- 字段级权限用集合常量表达（`_ADMIN_ONLY_FIELDS` / `_USER_FIELDS`），越权返回 **403**，
  白名单外的字段返回 **400**；不要用 if-else 长链。
- 读权限默认对所有登录用户开放（owner / group 选择器到处要用）。少数页面自查 admin
  （如专项配置），注意那属于 UI 约束，**服务端仍要独立校验**。

## 并发：乐观锁（409）与编辑锁（423）

- 协作编辑表都带 `version` 整型列。`PUT` 请求体必须携带客户端当前 `version`；
  服务端比对不一致返回 **409**，一致则 `version += 1` 并把新值回给前端。
- 前端不需要在每个页面处理 409/423——[api/index.js](frontend/src/api/index.js) 的响应
  拦截器已统一弹提示。新增可编辑实体请照抄这个模式，不要自己 try/catch 弹窗。
- 专项详情页额外有**编辑锁**（`special_edit_locks`）：同一专项同一时刻仅一人可进入编辑态，
  前端心跳续期，TTL 180s 过期可被接管，admin 可强制接管；他人持锁时写操作返回 **423**。
  只有「整页多字段联动编辑」的场景才值得上编辑锁，普通表格用乐观锁就够。

## 专项详情页：版式（分段）与模板

专项详情页不是固定表单，是**若干「分段」按配置拼起来的**。改这块前先读
[special_layout.py](backend/special_layout.py) 顶部说明。三份 JSON 决定一个专项长什么样：

| 列（`special_contents`） | 内容 |
| --- | --- |
| `section_order_json` | 分段顺序 `["goal", "grid:<gid>", "risks", …]` |
| `section_config_json` | 分段标题覆盖与启停 + 套过的模板名 |
| `extra_grids_json` | 自定义分段本体（`kind` = grid / text / images / milestones） |

- 8 个内置分段的 key 与默认顺序在 [enums.py](backend/enums.py) `SPECIAL_SECTIONS`，
  须与前端 `SpecialDetail.vue` 的 `FIXED_KEYS` 一致。内置分段各有专属交互
  （里程碑时间轴、事务/风险表、阵型网格），所以**只能改标题或整段停用，不能动态增删**；
  要新表格就加自定义分段。自定义分段有四种形态（`enums.SPECIAL_BLOCK_KINDS`）：
  表格 / 文本框 / 图片 / 里程碑。**新增一种形态要同时接四处**：`_instantiate_block()`、
  前端 `normBlock()` + 详情页 `v-if` 链、`_section_text()` / `_section_html()`、
  `build_special_xlsx()` 的分段分派——漏一处就是「页面上有、周报里没有」。
  自定义里程碑与内置「计划」是**同形态不同数据源**（块自带 `milestones` vs
  `content.milestones_json`），但渲染函数必须共用，否则一个专项里两种里程碑长得不一样。
- **顺序与标题的解析只有一份实现**：`special_layout.resolve_sections()`。详情页、Excel 导出、
  周报三处都走它。前端 `reconcileOrder()` 的规则必须与 `resolve_order()` 保持一致——
  两边分叉的表现是「页面顺序和周报顺序不一样」，很难被测出来。
- 新增内置分段时：`SPECIAL_SECTIONS` 加一条 + 详情页 `v-if` 链加一段 +
  `_section_text()` / `_section_html()` / `build_special_xlsx()` 各加一个分支。
  **缺任何一处的后果是那段在页面上有、在周报/导出里没有。**
- 空分段不占章节编号：导出与周报里「启用但没内容」的段整段跳过，避免一串「三、—」。
  Excel 侧靠 `build_special_xlsx` 的 `section()` / `_flush_section()` 实现——标题先挂起，
  等第一笔内容落笔才写。**别改回「先写标题、空了再补一行—」**：那样模板里多一个
  空分段，Excel 的章节号就会和周报错位，而这种错没人会当成 bug 去查。
- **模板（`special_templates`）只是录入期的便利，不是运行期依赖**：套用时把版式写进上面三列，
  之后与模板脱钩。改模板、删模板都不影响已建专项——不要反过来做成「详情页读模板渲染」。
- 套用语义是**只增不删**（`apply_template()`）：按 `tkey` 认领已挂上的分段，重复套用幂等；
  模板外的分段与已填的行一律保留。版式是配置，填进去的内容不是。
- 权限分档：改模板、套模板＝**仅 admin**（配置类主数据 / 改的是整页版式）；
  某专项内部的分段改名、停用、排序＝**登录用户**（协作编辑，走 `PUT /content` 的乐观锁）。

## 版本：三层与主干/分支

```
major_versions        大版本    C10SPC100        号段，自己不发布
  └ release_versions  版本      C10SPC101/102    真正对外发布的一级
      └ iteration_versions  迭代版本  C10SPC101B001  构建
```

**哪一层给谁用**（改口径前先看这张表，改错了各页面对不上，而且看着都正常）：

| 场景 | 用哪层 |
| --- | --- |
| 客户面：现场版本、客户定制化需求的预计合入版本 | **版本** |
| 迭代管理：领域/产品需求的计划交付版本；问题单的「版本信息」 | **迭代版本** |
| 版本达成率 `GET /api/metrics/version/{id}` | **版本**（id 是 release_version_id） |
| 时间轴 `VersionTimeline`：泳道 / 节点 | 大版本 / **版本** |

- `iteration_versions.major_version_id` 是**冗余列**，只由服务端从父版本推导
  （`_sync_major_id`），客户端传的一律忽略；改挂父版本时要把子行一起搬走，
  否则达成率会按旧大版本聚合。
- **「已发布」的判定只有一份实现**：`major_versions._is_released()`＝填了
  `actual_release_date` **并且那天已经过了**。两个 `/all` 接口各带一个 `released` 字段，
  前端不重算——各页面自己比 `new Date()` 的话，跨零点时两个页面会给出不同答案，
  而两边看着都对。取「日子过了」而不是「填了就算」：发版计划一定就会先把日期填上，
  那之前版本还在收需求，不该从「计划交付版本」下拉里消失。
  构建的 `released` 还要**或上父版本的**——版本一发，名下的构建就都是历史了。
- **两个 `/all` 接口只标不滤，过滤是调用页的事**。客户面的「现场版本」多半就是已发布
  的那些、度量看板要的更是发布完的版本、问题单管理要按构建号查历史数据；
  服务端一刀切掉的话那几个页面的下拉会莫名其妙变空。目前滤掉已发布项的只有两处
  ——迭代管理的「计划交付版本」（`IterationDetail.loadVersionGroups`，用**迭代版本**）
  与客户详情页定制化需求的「预计合入版本」（`CustomerDetailPanel.loadVersionOptions`，
  用**版本**）：合入是往还没发的版本里合，已经发出去的合不进东西了。
  两处都把隐去的条数如实显示出来——只滤不报的表现是"这个版本怎么选不到了"，
  而没人说得清少的是哪些。已填的值**不会因此显示不出来**：这两列存的都是版本号字符串、
  下拉又是 `allow-create`，选项里没有也照常显示原值、也仍然可以手敲
  （老数据里什么写法都有，强行只能选会逼着人把对不上的行改成一个错的版本）。
- 字符串反查 `resolve_iteration_version_id()` 由细到粗试三层，落到该层下**序号最小**的构建；
  粗匹配落空返回 None 留给数据对账，不要瞎猜一个。
- **大版本这一层按「开始时间」（`range_start`）倒序**，最新的在最上面；没填开始时间的
  整批排到最后、内部仍按 `sort_order`。收口在 `list_major_versions()` 的 `order_by`——
  `range_start.is_(None)` 那一段是**显式**写的，别当成冗余删掉：NULL 排最后只是 SQLite
  的默认行为，换个库就变成"没填的全顶到最上面"，而页面上看着只是顺序有点怪。
  因此**大版本没有 ↑↓ 手排**（另两层有）：顺序由日期这条数据决定，改顺序＝改开始时间。
  留一个按了不动的按钮比没有更糟。别改成按版本号推：号段是人定的，`C10SPC100` 之后
  完全可能再拉一个 `C09SPC200` 的老线分支。
- **版本与迭代版本这两层的页面顺序＝`sort_order`，不按版本号推**。三层各有一个 `POST /{tier}/reorder`
  （`{parent_id, ids}`）整体重写顺序：逐个 PUT `sort_order` 在中途失败就留下「排到一半」
  的顺序，而顺序错了不报错、只是看着不对。ids 里混进别的父级的行返回 **400**（静默忽略
  会让人以为排序时灵时不灵）；列表里没提到的兄弟排到后面，别人刚新增的行不会被挤乱。
  前端对应的表**不要再挂列排序**（`sortable` / `default-sort`），否则手排的顺序会被
  每次渲染时的列排序盖掉，看起来就像「排了没保存」。
- **改挂父级时 `sort_order` 要重算成新父级的末位**（`_tail_sort_order()`），
  并且前端编辑时**不要把旧 `sort_order` 传回来**——带着旧序号过去会插进目标那一堆的
  中间，看着像随机落点。版本改挂大版本时，名下构建的冗余列 `major_version_id` 一起搬。

**主干/分支是大版本的属性**，不变量是「同一项目同一时刻只有一个主干」：

- 只能走 `POST /api/major-versions/{id}/set-master`——它在同一事务里把原主干降为分支、
  盖上 `branched_at`、补上 `branch_name`。`line` 刻意不在 `MajorVersionUpdate` 里：
  做成普通字段就会出现两个主干或零个主干，页面上看着完全正常，没人会当 bug 报。
- 新建的大版本默认 `branch`，接管主干要显式点一次。
- **不要改成自动推断**（「出现已发布的版本就自动接管主干」）：拉分支是研发流程动作，
  不必然和发版同一天；推断错了，页面上的分支状态和 Git 实际状态对不上，比漏点一次更难查。

**老库迁移**（`alembic/versions/0010_version_three_tier.py`）：两层时代的 `iteration_versions`
里混着两级——`C10SPC101` 其实是「版本」，`C10SPC101B001` 才是构建。迁移按 `B\d+` 后缀劈开；
被提升成「版本」的原行**只有在没被 `*_requirements.target_version_id` 引用时才删**，
被引用的留着让人工处理（SET NULL 掉别人填了半年的计划交付版本更糟）。
`major_versions.actual_release_date` 是遗留列，值已下沉到同号的版本，新代码不读写它。

**迁移只跑了一半会长什么样**：`0010` 的回填带了一道「`release_versions` 非空就整段跳过」
的守卫，本意是重跑幂等，但在上一次跑到一半的库上会反咬——列已加、部分版本已生成，
重跑时直接跳过，剩下的 `iteration_versions` 永远停在 `release_version_id IS NULL`。
这些行在页面上**完全不可见**（版本页是三层嵌套渲染的），现象是「迁移完版本全丢了、
只剩第一层」，但数据一直在库里。`0012` 是它的自愈补丁：只挂接不删除，天然幂等；
要看报告或顺手清理冗余行用 [scripts/repair_version_tiers.py](backend/scripts/repair_version_tiers.py)
（默认只读预演，`--apply` 才写库）。**新写幂等守卫时别按「结果表非空」判，
要按「这一行还没处理」判**——前者在半成品上会把剩下的活全跳过。

## 迭代需求：项目维度与按项目度量

**迭代不属于任何项目**——它是按年月排的，同一个月的迭代里同时排着多个项目的需求。
所以项目维度挂在**需求行**上：`iteration_requirements.project_id` /
`iteration_product_requirements.project_id`（FK → `roadmap_projects`，可空）。
不要反过来往 `annual_iterations` 上加 `project_id`：那样一个月就要开 N 条迭代，
迭代号从「2026-03」变成「2026-03-甲」，问题单、版本、周报里所有按年月找迭代的地方都要跟着改。

**「已变更」＝这条需求本轮不做了，整行不进任何统计**。判定收口在
`enums.is_changed_row()`：任一进展子项标了「已变更」就算整行已变更（取"任一"而不是"全部"，
改口径只动那一行）。度量看板四个接口与领域总览的 `_req_summary()` 都走它——
**两处各写一份迟早分叉**，一个看板算进去、另一个不算，都不报错却对不上。

- `metrics._WEIGHT` 里**故意没有「已变更」这一档**：带它的行在 `_split_changed()` 就整行
  被剔掉，到不了加权那一步。别再给它补个 0.5——那等于把一条已经不做的需求
  重新算进平均完成度，把团队的数字白白拖低。
- **先剔已变更、再按项目切**（各接口里的调用顺序）。反过来的话，没填项目的已变更行
  会混进 `unassigned`，页面提示「还有 N 条没填项目」，人去补完发现数字纹丝不动。
- 排除多少条要**如实报出来**：四个接口都回一个 `changed`，领域总览回
  `DomainReqSummary.changed`。只剔不报的表现是「升级完看板数字小了一截」，没人说得清为什么。
- **服务端不过滤这些行**，列表接口照常返回；置灰与「隐藏已变更」都是前端的事。
  服务端藏起来的话，误标成已变更的行会连同「改回来」的入口一起消失。
- 前端 `isChangedRow()` 的判定必须与后端同款，分叉的表现是「页面上灰着的行还在看板的数里」。
  Excel / PPT 导出**不剔**：那是交付记录，变更过的需求本就该留在里面（带着「已变更」的着色）。

度量口径收口在 `metrics._split_by_project()`，四个接口（版本完成率 / 迭代 / 年度迭代质量 /
组级负载）都吃可选的 `project_id`：

- **没填项目的行不计入任何一个项目**。把它们摊进当前项目、或按「库里只有一个项目就算它的」
  兜底，数字看着都合理，偏了没人看得出来。
- 作为补偿，响应里带一个 `unassigned`＝同口径下因没填项目而被排除的条数，
  前端拿它渲染一条黄条提示去补录。**加新的按项目度量接口时要一并返回它**——
  只筛不报的表现是「按项目一看数字小了一截」，而没人知道少的是哪些。
- 不传 `project_id` ＝ 全量口径，此时 `unassigned` 恒为 0（没有「被排除」这回事）。
- 密度类指标（用例密度 / 问题单密度）要**分子分母一起筛**。只筛分子会得到一个
  分母含别的项目的密度，量纲对、数值错。

前端：项目下拉在 `IterationDetail.vue` 里加载一次、传给两个需求 Tab，别各拉一遍。
需求列表按项目**分标签**（不是筛选下拉）：标签在 `DomainRequirementTab` /
`ProductRequirementTab` 里渲染，选中值由 `IterationDetail` 持有（`v-model:project-scope`）——
两个 Tab 共用一个选择，来回切时筛选跟着走，各记一份的表现是「切回来筛选自己变了」。

- 标签名只能是**字符串**（el-tabs 的 `name`），比较前要 `Number()`；两个特殊页签
  `all` / `none` 用常量表达。「未指定项目」必须是一个**显式页签**：没填项目的行
  正是最该被找出来补录的那批，混在「全部」里就永远没人去补。
- 标签上的条数按 `baseList`（除项目外其它筛选都已生效）算，**不是按整表算**。
  否则会出现「标签写 12、点进去 3 条」，而没人说得清哪个数是对的。
- 停在某个项目标签上时，新增的需求默认归它（`currentProjectId()`）。
- 切标签**不重新请求**：数据一次拉全，标签只是前端切片。别改成按项目请求——
  一次请求就能拿到的东西分成 N 次，还得处理"切太快回来的是上一个项目的数据"。

Excel 导入的「项目」列按项目名**完全匹配**（`_lookups.resolve_project_id`），
不做模糊匹配：`YLS3000` 很容易被认到 `YLS3000-PLUS` 上，错挂的需求在度量时只是数字偏一点。
反查不中留空、不报错，交给页面事后补选。

**判重口径只有一份**：[routers/_req_dedup.py](backend/routers/_req_dedup.py)，领域需求与
产品需求两张表、手工新增 / 编辑 / Excel 导入三条写路径共用。分叉的表现是「页面拦住了、
导入照样进」，或者两个 Tab 松紧不一样。

- 范围是**一个迭代**，不是全表：同一条需求本轮没做完、下个月接着排是正常的，
  跨迭代拦住会逼着人改标题绕过去，那比重复更糟。
- **有需求编号按编号判，没编号按标题判**。编号是业务主键，但它是选填的——只按编号判
  等于「不填编号就能重复录」，而漏填编号的行恰恰是手工补录的那批。
- 比较前把空白全去掉再转小写：Excel 里粘出来的编号常带首尾空格或全角空格，
  肉眼看不出差别，按原样比较则判不出重。
- **导入撞上重复是跳过、不是报错**（一次导入里混着几条已录过的很正常），但要如实
  报出来：响应里带 `skipped`，每一条进 `errors` 指明撞的是哪一行。只跳不报的表现是
  「导入 80 条只进了 60 条」，而没人说得清少的是哪些。
- 编辑也能造出重复（把编号改成另一行的），所以 `PUT` 同样判，并把自己排除掉。
- **跨迭代重复不拦、只报**：本轮没做完下个月接着排，和"上个月录过这个月又录一条"，
  从数据上分不出来，只有人分得出。`scan_duplicates()` 把「它还出现在哪几个迭代」摆到
  页面顶部（`RequirementDuplicateAlert.vue`，两个 Tab 共用），导入时也在 `errors` 里
  提一句并计入 `cross_iteration`（**这些行是导进来了的**，与 `skipped` 分开报，
  合在一起说会被当成也没进）。同一迭代内的重复照样扫——判重是后加的，
  **存量重复不会自己消失**，不摆出来就永远没人去合并。
- 重复的需求在度量里是**实打实的分母**（加权完成度被摊薄、按项目/领域的条数偏大），
  而每一行单独看都合法。存量重复用
  [scripts/find_duplicate_requirements.py](backend/scripts/find_duplicate_requirements.py)
  查（默认只读，`--apply` 只删「六个进展全未开始、数字与备注全空」的空壳行，每组至少留一条）；
  **被人填过内容的重复行不自动删**——那上面可能有别人跟了半年的进展。

## 度量看板：质量的两个维度

**版本质量看整个版本，领域质量看一个迭代**——这两个口径不一样，而且必须不一样：

| 维度 | 口径 | 接口 |
| --- | --- | --- |
| 版本质量 | **整个版本**（C10SPC101 这一层，跨迭代） | `GET /api/metrics/version/{release_version_id}` |
| 领域质量 | **一个迭代**（按月排活） | `GET /api/metrics/domain-quality/{iteration_id}` |

领域是按月排活的，问「这个月各领域干得怎么样」才有意义；版本是跨月的，按月截一刀
会得到一个既不是这个版本、也不是这个月的数（同 `domains._ReqScope` 的取舍）。

- **按领域分行的形状只有一份**：`metrics.DomainQualityRow`，两个接口共用，前端也共用
  [DomainQualityTable.vue](frontend/src/components/metrics/DomainQualityTable.vue)。
  各定义一份的话，同一批字段会长出两套列名，口径也会慢慢分叉。
- **质量字段（代码量 / 自验证用例 / 转测后问题单）只有领域需求有**。所以版本口径的
  `total` 把产品需求也算进来（进度要看全），但 `by_domain` 各行只数领域需求，
  两个数对不上是正常的——**表头要写明白**，否则会被当成丢数据。
- **只列当前口径下确实挂着需求的领域**，没填 PL 组的归到「未指定领域」一行并排最后。
  把所有 PL 组都铺出来，一屏全是 0，真正在干活的那几行反而找不到；而没填组的行
  正是最该被捞出来补录的那批，藏起来就永远没人去补。
- 合计由**服务端**给出（`DomainQualityOut` 的那几个字段）。前端再加一遍的话，
  两端各加一次迟早对不上。表格里的合计行是例外：**密度不能逐行相加**，
  必须用「合计用例数 ÷ 合计代码量」重算，把各行密度加起来会得到一个大得离谱、
  却还挺像个数的值。

**采集问题单只进版本口径，且必须报匹配率**：

- 快照行的「版本信息」是 DTS 那边的自由串（多数是 pbiName），和三层版本号不保证对得上。
  所以只做**精确匹配**（版本号本身 + 名下所有构建号，`_req_scope.build_no_set()`），
  命中多少如实报（`VersionIssueStat.match_rate`），没命中的取值也报出来
  （`unmatched_top`）——匹配率低时一眼能看出是命名没对上，而不是「这个版本怎么
  一个问题单都没有」。**不要改成模糊匹配**：C10SPC101 很容易被认到 C10SPC1011 上，
  错挂的单在质量表里只是数字偏一点，没人会去核。
- **迭代口径下没有这两列**：快照是"当天还开着的单"，没有迭代维度，按月摊给某个迭代
  是编的。领域质量表里的「转测后问题单」是需求行上人填的那一列。
- 「未指定领域」那行的采集问题单**留空而不是记 0**：0 会被读成"这个领域没问题单"，
  留空才是"这一格算不出来"。
- 数据源的选取（快照优先、无快照回退老 Excel、指定项目没快照时如实报不可用）收口在
  [routers/_issue_source.py](backend/routers/_issue_source.py)，领域总览与度量看板共用。
  两处各写一份的表现是同一个领域在两个页面上问题单数不一样，而两边看着都像对的。

**问题单超期是看板里唯一按「采集项目」切的一页**（`GET /api/metrics/issue-overdue`）：

- 它的 `project` 是**问题单的采集项目**（字符串，如 `YLS3000`），与看板顶部的
  「度量项目」（需求行上的 `roadmap_projects` FK）**不是一个维度**。混用的表现是
  选了顶部那个却什么都没变，看着像页面坏了——所以这一页自带一个「问题单项目」选择器，
  旁边写明两者的区别。
- 数据源与口径都与领域总览**共用一份**（`_issue_source.resolve_issue_source` +
  `overdue_stats`）：两处各写一份的表现是同一个组在两个页面上超期数不一样，
  而两边看着都像对的。
- **超期占比的分母是「填了预计闭环时间的条数」，不是总条数**。按总条数算的话，
  一个 DTS 里压根没填日期的组会显示成 0%，看着比谁都干净。分母为 0 时页面显示
  「没有可比的基数」而不是 0%。
- 「未归组」那一行由服务端标 `ungrouped`，前端据此提示**去补名单**——它和
  「组名对不上主数据」（`group_id` 为空）是两回事，混在一起会提示管理员去建一个
  根本不该存在的组。标志位由服务端给，免得前端再写一份 `UNGROUPED_GROUP` 字面量。
- 还给一列「最久超了多少天」：2 条超 200 天比 5 条超 2 天更该先看，只排条数看不出来。

**调试版本看板不在度量看板里**：它按客户 × 月统计，和版本 / 领域 / 组三个维度不是一回事，
挂在「版本管理 → 现场调试版本」的录入页上（`DebugVersionPanel.vue`）。

## 问题单采集：三道过滤，只有一道该丢行

采集到的原始行在 [routers/issues.py](backend/routers/issues.py) 的 `_enrich_rows()` 里过三道，
**改这里之前先想清楚「丢一行」的代价**：

| 过滤 | 问的是 | 丢行？ |
| --- | --- | --- |
| ① 状态剔除（`issue_exclude_statuses`，默认 关闭/撤销） | 这单还开着吗 | **丢** |
| ② 部门过滤（`issue_stat_departments`） | 这单归不归我们管 | **丢** |
| ③ 责任人归组（`issue_groups`） | 归我们哪个组 | **不丢**，归 `UNGROUPED_GROUP` |

代价不对称的原因在差分那一头：**「解决」＝这一单从快照里消失**
（`_ensure_flows()`：`resolved = 上次的 id 集合 − 今天的`），**它从不读状态**。
所以任何"因为过滤规则掉出快照"的行都会变成一笔**假解决**——数字自洽、图也自洽，
没人会当 bug 报。③ 尤其致命：问题单从「定位」转到「实施修改」正是换责任人的时刻，
新人/借调/换部门的人不在名单里很常见，丢掉的话每次转手都记一笔解决。

- ③ 归不到组的人由 `_ungrouped_owners()` 汇总（按人聚合、带部门、按条数降序），
  两个出口：采集完成的提示、`GET /api/issues/ungrouped`（配置页「未归组责任人」）。
  **名单不全是配置问题，不该表现成数据问题**——所以是"留下 + 提醒"，不是"丢掉"。
- ③ 的匹配是**双向包含**（名单可能比 DTS 短——DTS 常写成「张伟 00123456」；
  也可能更长——名单里写「张伟(SE)」），但两个方向都要过 `_contains_person_name()`
  的边界检查：**紧邻的字符要么是分隔符、要么属于另一个字符类**。汉字接汉字
  （张伟|明）＝把一个更长的名字切开了，拒绝；汉字接西文（张伟|00123456）是姓名与
  工号的交界，接受。少了这道边界，「张伟」会认走「张伟明」的单——名单里根本没有
  张伟明，他的单却被安安静静记进了张伟所在的组，组级负载和交叉表都偏一点，
  而两边看着都对。**这条规则比客户面的 `_contains_name()` 严，两者不能互相套用**：
  客户名是从**标题**（自然语句）里认的，两侧本来就没有分隔符；责任人是一个**名字
  字段**，两端本就该是边界。
- 这份清单**从明细文件现算，不入库**：名单一改它就该跟着变，存一份下来会一直
  显示已经补过的人，比没有更糟。
- `UNGROUPED_GROUP`（"未归组"）**只有一个字面量**，Excel 交叉表、维度聚合、前端提示共用。
  两处各写一个的表现是同一批人在两张表里分成两档，加起来还对，看着都像对的。
- ① 是**子串**匹配 `progress`（DTS 的「进展」列），所以"待关闭""申请关闭"一并被剔掉。
  这是已知的粗口径，改成精确匹配前要先确认 DTS 那边的取值全集。
- **客户面是从标题里认出来的，认的时候不许把一串数字从中间切开**。客户名大量是
  「N号机」这种带编号的写法，而 `"1号机" in "11号机"` 是真的（从第二个字符起就是）。
  两道防线缺一不可：`_load_customer_matchers()` 按长度降序试（更具体的先命中），
  `_contains_name()` 再要求「以数字开头的名字前面一位不能还是数字、以数字结尾的后面
  一位不能还是数字」。只有前者的话，**只要「11号机」没登记进客户主数据，它的单就会被
  「1号机」整批吃掉**——两台机器的单混进一行、同一台机器的单散在两行，数字加起来还对，
  没人会当 bug 报。边界**只拒绝数字被切开这一种**：客户名混在标题里本来就没有分隔符，
  要求两侧都是分隔符会把「西安1号机异常」这类正常标题一并拒掉。
  改了匹配规则之后，**已经落盘的快照不会自己重算**（趋势图读的是 `issue_snapshot_stats`
  里的数字），用 [scripts/repair_issue_dimensions.py](backend/scripts/repair_issue_dimensions.py)
  重算历史——客户面与所属小组这两列都是匹配推导出来的，同一个脚本一起管（默认只读预演，
  `--apply` 才写）。它**不碰 `issue_snapshot_flows`**：差分按缺陷编号算，与这两列无关，
  重算反而会造出一批假新增/假解决。
- `scripts/fetch_issues_api.py` 的翻页**每页都要校验，最后再对一次总数**：
  任一页 `data` 不是 dict（DTS 会话中途失效返回的是 HTTP 200 + `data: null`，
  `raise_for_status()` 拦不住）、任一中间页 0 条、或 `len(rows) < data.total`
  ——一律抛错让整次采集失败。**不要改回 `or []`**：少拉一页（200 条）的快照
  看着完全合法，第二天差分给出 200 条假解决，而 `_snapshot_ids()` 只防住了
  "文件整个丢了"，防不住"少了一半"。快照落盘后差分还会缓存进
  `issue_snapshot_flows`，事后修数据源也不自动重算，所以宁可这次失败。
  反过来 `len(rows) > total` **只警告不失败**：那是翻页期间有单增删导致的行位移，
  多出来的是重复行，去重会处理，不会变成假解决。

## 问题单跟踪：进展与合入计划

问题单本身**不入库**——每天采集回来的明细落文件、只有维度数字入库，快照是"当天还开着
的单"的一份存档。所以跟踪记录（进展 + 合入计划）单独一张表
[models.IssueTrack](backend/models.py)，按 **项目 + 缺陷编号** 认领，与快照彻底解耦。

- **这就是它存在的理由**：挂在某一天的快照行上，第二天重新采集就等于全丢了，
  而页面上只表现成「昨天填的怎么没了」。现在只要这单还在 DTS 里开着（没被关闭/撤销、
  没从快照里消失），今天填的进展与合入计划每天都看得到。回归见
  [tests/test_issue_track.py](backend/tests/test_issue_track.py) 的
  `test_track_survives_the_next_days_snapshot`。
- **合入计划两层都记，两层答的不是同一个问题**：`plan_version_id` → **版本**
  （release_versions，C10SPC101 这一层）＝排期时说得出来的粒度；`merged_build_id` →
  **迭代版本/构建**（C10SPC101B001）＝合完之后才填得出来的事实。填反了的表现是
  下拉里选的和存的不是一回事，而页面上看着都对。
- **计划那一栏滤掉已发布的版本、实际那一栏不滤**：合入是往还没发的版本里合，
  已经发出去的合不进东西了；而"实际合到哪个构建"记的是已经发生的事，已发布的构建
  正是要选的那些。滤掉的条数要如实显示（同 `CustomerDetailPanel.loadVersionOptions`），
  两栏都是 `allow-create`，老数据里什么写法都有。
- 字符串 → FK 的反查走 [_lookups.py](backend/routers/_lookups.py)：计划栏用
  `resolve_release_version_id()`（认版本号，也认构建号并挂到它所属的版本上——那不是猜，
  构建挂在哪个版本是库里的事实；再粗就不认了，大版本下面可能有好几个版本）。
- 写权限＝**登录用户**（协作编辑域，日常填报）。**没有删除接口**：清空就等于没填，
  而误删的是别人跟了几周的进展。并发用乐观锁（`version`），第一次填时库里还没有行，
  所以 `version` 可以不传（None ＝ 新建）。
- 前端在问题单明细表里用**分组表头**「跟踪（本系统记录）」把这几列圈起来、排在
  「所属小组」后面：一是它们不来自 DTS，混在采集列里分不清谁是事实谁是我们的判断；
  二是排到表尾的话十几列宽的表要横着拉到底才看得见，而这正是天天要填的那几格。
  **编辑走弹窗不做行内**：一份快照几百上千条单，每行挂三个下拉会把页面拖垮。

## 领域管理：需求口径（迭代 / 版本）与问题单口径

领域总览的「需求情况」有**两种口径，二选一**，收口在 `domains._resolve_req_scope()`：

| 口径 | 参数 | 范围 |
| --- | --- | --- |
| 按迭代（默认） | `year` + `month`，都不给＝进行中迭代 | 该月排的需求 |
| 按版本 | `release_version_id` | 该**版本**（C10SPC101 这一层）上的需求，**跨迭代** |

- **两者不叠加**：给了 `release_version_id` 就忽略 `year/month`。版本是跨月的，
  叠上「当前迭代」会得到一个既不是这个版本、也不是这个迭代的数，页面上看着像
  「这个版本怎么只有 3 条」，而没人会想到是被月份截了一刀。响应里
  `selected_release_version_id` 非空＝当前是版本口径，`iteration_label` 明写生效的是哪一档。
- **版本匹配规则只有一份实现**：[routers/_req_scope.py](backend/routers/_req_scope.py)
  的 `version_clause()`——该版本名下所有构建的 id，外加字符串回退（不少老需求直接把
  版本号写进了 `planned_version`，FK 还没反查上）。度量看板的版本达成率走的是同一份；
  两处各写一份的表现是同一个版本在两个页面上条数不一样，而两边看着都像对的。
- **可选版本只列当前挂着需求的那些**（`_version_options()`，一趟扫描算完条数）。
  三层版本里光构建就上百个，全列出来点进去大半是空的。别改成每个版本各查一次。
- 页面上**只有「按迭代 / 按版本」两个标签**，具体哪个月、哪个版本由旁边的下拉选。
  版本不铺成标签：挂着需求的版本也可能十几个，一排标签比下拉更难找，而且标签栏一换行
  整个页头就散了。切到「按版本」还没选过版本时落到列表最后一个（`sort_order` 末位，
  通常就是最新那个）；**一个可选版本都没有时不发请求**——退回迭代口径会让页头写着
  「按版本」、底下显示的却是本月的数字。
- **下钻与总览必须同口径**（都走 `_resolve_req_scope` + `_req_query`）。
  分叉的表现是「格子里写 8 条、点进去 5 条」，看着像丢数据。
- 明细接口**不藏「已变更」的行**，但总览的 `total` 已剔除它——所以下钻的行数
  正常就比 `total` 多 `changed` 条，这不是 bug。

## 领域管理：问题单口径与目标

领域总览的「问题单情况」有**两个可能的数据源**，判断逻辑收口在
`domains._resolve_issue_source()`，改口径前先读它：

1. **优先**：`issue_snapshots` 里选定项目的**最新一次快照**（问题单管理采集的结果）。
   只看最新一份——趋势属于问题单管理，别在领域页再造一套。
2. **回退**：一份快照都没有时读老的问题单 Excel（`config.issue_report_path`）。
   保留它只是为了不让还没接 API 采集的部署丢掉这一列。

两条硬规则：

- **指定的项目没有快照时，如实返回 `available=False` + 原因，绝不静默换成别的项目的数字**。
  数字看着都合理，换掉了没人看得出来。
- 快照元数据在库、明细在文件，两者可能不同步（目录被清理、迁移漏拷）。
  `_snapshot_rows()` 读不到文件时返回空列表而不是抛错——整页 500 比显示 0 条更糟。
**「超期未处理」= 超过 DTS「预计闭环时间」且仍在快照里**（`_issue_source.overdue_stats()`）：

- **不读状态**判断"没处理"：快照里本来就只有当天还开着的单（关闭/撤销在采集时就剔掉了），
  在快照里 ＝ 还没处理。这与「解决＝从快照里消失」是同一套口径，两处必须一致，
  否则会出现"已闭环的单还挂在超期数里"。
- 「**超过**」才算，当天到期不算——记成超期会让人白紧张一天。
- 日期解析（`parse_plan_date()`）认多种写法（`2026-09-15` / `2026/9/15` / 带时分秒 /
  毫秒时间戳 / `2026年9月15日`），但**认不出来的一律算「没填」而不是算「没超期」**：
  后者会把一批读不懂的日期悄悄记成达标，数字看着还挺好。
- **没填预计闭环时间的条数要一起报**（`overdue_unknown`）。DTS 那一列是选填的，
  没接上时全库都是空，此时「超期 0」会被读成"一条都没超期"——所以整组都没填时
  页面显示的是「超期未知」而不是「无超期」。这与 `unassigned` / `match_rate`
  是同一条规矩：**只筛不报的数字比没有更糟**。
- 数字点得进去（`GET /{group_id}/issues?overdue=true`）：只给个「超期 8」的话，
  没人说得清是哪 8 条。
- 字段本身由 `fetch_issues_api.py` 的 `FIELD_MAPPING` 里 `planCloseTime` → 「预计闭环时间」
  接进来，落到快照行的 `estimated_close`。**历史快照里没有这一列**，改完要重采才有数。

- 目标值（`domain_issue_targets`）是**管理口径不是采集事实**，因此按主数据一档＝**仅 admin 可写**，
  读对所有登录用户开放（页面要显示达成情况）。`project=""` 是通用兜底目标，
  项目专属目标优先；继承来的值要在设定界面标出来，否则管理员会以为自己在改本项目的值。

## 客户面支撑：工作量（人天）口径

`business_trips` 一行＝一次支撑（谁、哪个战场、哪个项目、现场还是线上、哪段时间）。
工作量口径**只有一份实现**：[routers/business_trips.py](backend/routers/business_trips.py)
的 `_calc_man_days()` / `_man_days_in()`，看板与明细都走它。

- `man_days` **填了就以它为准，留空才按日历天数推**（含头含尾）。不做成必填也不做成
  纯推导：现场支撑一去就是整段连续投入，按天数推是对的；线上支撑常常是五天里各花
  两小时，按天数推会把 5 人天算给一个实际 1 人天的事，而看板上没人能看出这个数是虚的。
- 区间统计**按重叠天数占整段的比例分摊**，不是「有重叠就整段计入」。后者的表现是
  跨月的支撑在每个月各算一遍，各月看着都对，加起来比全年总量还大，没人会去核。
- 明细表底部的合计走**整段** `calc_man_days`，与看板的区间分摊值口径不同——
  表里一行就是一整条记录，按区间截一刀反而和那一行自己显示的数对不上。两个数
  差得出来是正常的，别把其中一个改成另一个。
- `support_mode` 的两档在 [enums.py](backend/enums.py) `SUPPORT_MODES`，前端
  `BusinessTripManagement.vue` 里有一份同名常量，**两边必须同步**。
  老数据由 `0011` 全部回填成「现场支撑」——改造前这张表登记的就是出差。
- 看板的项目 / 支撑方式筛选**同时作用于 now 快照与区间统计**。只筛区间的话，
  上面的「当前支撑中」和下面的分项对不上，看着像统计错了。

## 枚举：单一来源

所有状态 / 优先级词表收口在 [backend/enums.py](backend/enums.py)，**不要在 router 或前端
另写字面量**。历史上这些词表以自由字符串散落各处，导致口径漂移、错字静默漏算。

- 校验用 `norm_*` 系列函数（`norm_priority` / `norm_progress` / `norm_issue_status` …）。
- **`norm_*` 只挂在 `Create` / `Update` schema 上，绝不挂 `Base` / `Out`**：`Out` 继承 `Base`
  并走 `from_attributes` 读库，老库里的历史脏值会让读取直接 422。
- **同词表不等于同一列**：领域事务/风险的「优先级」与「风险等级」都是高/中/低，
  但答的是两个问题——先处理哪个 vs 爆了有多疼。合成一列就再也表达不出"低优先级的
  高风险"（短期不动、但爆了很惨），而合并之后没人能从数据里看出丢了什么。
  风险等级（`DOMAIN_RISK_LEVELS`）**没有默认值、空是合法取值**：那张表里事务行和
  风险行混着，事务本来就没有等级，默认成「中」会让半屏事务挂上一个凭空捏的等级。
  所以它的 `norm_domain_risk_level()` 不走 `_norm_choice`——后者把空当作"不修改"
  或"落默认值"，这里空既不是不修改也不该有默认，一律归一成空串，
  「清掉等级」与「没填过」在库里是同一个值，统计时不用分两种情况判。
- 状态词表里**大小写不统一的字面量要在入口归一**：领域遗留问题的三档是
  `OPEN / CLOSED / pending`（业务方指定的写法，别顺手统一成大写），
  `norm_domain_legacy_status()` 把任意大小写折回这三个字面量——否则
  "Pending" 与 "pending" 在按字面量分组的统计里会各占一档，且没人会当 bug 去查。
- 前端下拉值必须与 `enums.py` 一致；关键特性的颜色映射在
  [utils/featureStatus.js](frontend/src/utils/featureStatus.js)，顺序须与后端六档一致。
- 自由表格的列格式白名单 `GRID_COL_TYPES`（text / select / date / **light**）在两端各有一份：
  后端 `enums.py`、前端 [utils/gridLight.js](frontend/src/utils/gridLight.js)。
  **前端漏加一项的后果是该格式的列每次加载被静默重置成 text**（`normGrid()` 按白名单过滤）。
  点灯的取值词表与红黄绿档位同理两端各一份，页面 / 周报 HTML / Excel 三处着色必须同款。
- 单元格与富文本的**字体 / 字号 / 底色**同样是两端各一份：后端 `GRID_FONTS` /
  `GRID_FONT_SIZES` / `GRID_CELL_BG`，前端 [utils/gridFormat.js](frontend/src/utils/gridFormat.js)。
  单元格里**存 key 不存 CSS 串**（`font: "simsun"`），因为三个出口要的东西不一样：
  页面与周报要 CSS、Excel 要字体名 + 磅值（px×0.75）。存 CSS 串会逼着 Excel 端去
  反解析 font-family 列表。三处映射分别在 `formatStyle()` / `_fmt_css()` / `_cell_font_spec()`。

## 富文本：入口清洗，出口也清洗

多处用 `v-html` 渲染用户填的 HTML（专项的目标 / 整体进展 / 求助 / 事务 / 风险 / 文本框分段，
领域的最近主要工作 / 事务风险当前进展 / 遗留问题当前进展）。
**写库前必须过 `_sanitize_rich()`**（`routers/specials.py` 的 `_sanitize_rich_fields()` /
`_sanitize_blocks_json()`），只在导出周报时清洗等于只保护了收件人，页面本身仍是任何
登录用户都能往别人的专项里存一段脚本。出口的清洗保留着——老数据还没洗过。
**领域侧没有 `_sanitize_rich_fields()` 这种批量入口**，是逐个字段调 `_sanitize_rich()`
（`domains.py` 的 `update_domain_content` / `create_legacy_issue` / `update_legacy_issue`）：
**新加一个 `v-html` 字段就得在自己那条写路径上补一次调用**，漏了不会报错，
只是那一列从此可以存脚本。

- **把一个存量纯文本列改成富文本时，出口要过 `_rich_to_html()` 而不是直接丢给 `v-html`**
  （`domains._task_out()` 对 `domain_risks.progress` 就是这么做的）。老值里的 `<`
  会被浏览器当成标签吃掉、换行会被压平，改造后那些行看着像"内容丢了"；
  `_rich_to_html()` 看着像 HTML 的走清洗、纯文本的转义并把 `\n` 换成 `<br>`，
  两种都落到正确的显示。顺带也挡住老数据里可能存着的标记——入口清洗是加字段那天才有的，
  之前存进来的没洗过。

- 白名单 `_ALLOWED_TAGS` / `_ALLOWED_STYLE_PROPS` 决定编辑器能提供什么格式：
  **加了工具条按钮就要同步加白名单**，否则那个格式每次保存被静默抹掉
  （列表按钮对应 `ul`/`ol`/`li`，对齐对应 `text-align`，高亮对应 `background-color`）。
- `script` / `style` 走 `_DROP_CONTENT_TAGS`：连内容一起丢。其余非白名单标签只丢标签留文字。

## 数据库结构变更

三条通道并存，**用错会导致老库缺列而新库正常，问题只在生产暴露**：

| 通道 | 用途 | 状态 |
| --- | --- | --- |
| `Base.metadata.create_all()` | 新增**整张表** | 在用。幂等，启动时跑 |
| [migrate.py](backend/migrate.py) `_ADDITIONS` | `ALTER TABLE ADD COLUMN` | **已冻结，不要再加** |
| [alembic/](backend/alembic/) | 改名 / 删列 / 改类型 / 加约束 / 数据回填 | 在用，唯一正式通道 |

- 给**已有表加列**也走 Alembic（不要碰 `migrate.py`）。
- SQLite 不支持原生 ALTER，`env.py` 已开 `render_as_batch=True`，靠建新表→拷数据→改名完成。
- **迁移必须带 inspector 幂等守卫**，因为 `ensure_schema()` 与 `create_all()` 都跑在 Alembic 之前，
  列/表往往已经存在。漏守卫的后果不是报错退出，而是 `automigrate` 把异常吞成一行 warning、
  **整条升级链停在那一版，后续迁移全部静默不执行**——新库正常、老库缺列，只在生产暴露。
  （`0003` 就踩过这个坑：它加的列 `migrate.py` 里也有，导致 `0004`~`0007` 长期没跑过。）
- 自动生成的迁移**务必人工检查** batch 段落：`alembic revision --autogenerate -m "..."`。
- `alembic/env.py` 的 `fileConfig(..., **disable_existing_loggers=False**)` 不能去掉：
  默认值会把此刻已存在、但没写进 `alembic.ini` 的 logger 全部禁用，而 `automigrate`
  跑在 uvicorn 装好 logger 之后——等于每次启动都顺手关掉 `uvicorn.error` / `uvicorn.access`，
  **进程从此不打访问日志、500 也不打 traceback**。回归见
  [tests/test_startup_logging.py](backend/tests/test_startup_logging.py)。
- 详细用法见 [alembic/README.md](backend/alembic/README.md)。

## 日志与通知是两条独立路径

- [op_log.py](backend/op_log.py) `log_op()` —— **审计**。登录与关键写操作都要记，
  `detail` 只放语义摘要（`machine_id=... fields=...`），不写敏感字段。
- [notify.py](backend/notify.py) `dispatch()` / `broadcast()` —— **通知人**。按显式收件人
  + `Subscription` 订阅表投递。
- 两者目的不同，**不要相互替代或合并**；两者的异常都被吞掉，绝不阻塞主业务。

## 时间：库里存 UTC，出接口转北京时间

DateTime 列有两类，**口径不同，别混**：

| 类别 | 例子 | 存的是 | 出接口 |
| --- | --- | --- | --- |
| 服务端盖章 | `created_at` / `updated_at` / `uploaded_at` / `started_at` / `acquired_at` | 朴素 UTC（`datetime.utcnow`） | 转 `+08:00` |
| 用户填写 | `planned_date` / `range_start` / `release_date` / `planned_close_date` / `start_date` | 前端传的本地时间，原样存 | **不转** |

- 转换收口在 [timeutil.py](backend/timeutil.py)：Pydantic 出口字段标 `LocalDT`，
  手写 dict 的接口用 `fmt_local()` / `iso_local()`，**查询条件**用 `local_to_utc()`。
- 新增服务端时间戳字段：`Out` schema 里写 `LocalDT`，不要写 `datetime`。
  写成 `datetime` 会输出**不带时区后缀**的串，前端 `new Date()` 按本地时间解析，页面早 8 小时。
- 反过来，把用户填的日期标成 `LocalDT` 会凭空加 8 小时。判断依据是**这个值是谁写进去的**。
- 用 `date`/`datetime.now()` 生成的**日期字符串**（`snapshot_date`、导出文件名、报告日期）
  本来就是本地时间，不要动。

## 主数据与 FK 反查

`customers` / `users` / `resource_groups` / `iteration_versions` / `roadmap_projects` 是主数据，
业务表逐步从「存字符串」迁到「存 FK + 字符串快照」。

- 字符串 → FK 的反查统一走 [routers/_lookups.py](backend/routers/_lookups.py)
  （`resolve_*` / `fill_*_fk`），不要在各 router 里重写匹配规则。
- 反查失败**不要报错**，留空让「数据对账」页（`/data-mapping`）事后补全。
- 快照字段（`owner` / `owner_group` / `planned_version` …）保留用于展示与导入兜底，
  FK 为空时前端回退到它。
- **项目是个例外：只存 FK，不留字符串快照**（`project_id` 无 `project_name` 列）。
  项目表只有个位数行且会改名，存快照就得到处同步；出接口时用
  `_lookups.project_name_map()` 一次性回填 `project_name`（响应字段，非模型列），
  逐行 join 会变成 N+1。

## 导出与上传

- **配色只有一份：[brand.py](backend/brand.py)**，PPT 与 Excel 共用。
  **不要在 `pptx_utils` / `xlsx_io` / `xlsx_utils` / router 里另写颜色字面量**——
  历史上清单 Excel 走品牌蓝 `#4073BA`、专项 Excel 走华为红、PPT 又是另一套红，
  同一批数据导出的三个文件是三个配色，而每一份单独看都挺正常，
  没人会把「两份文件不像一套材料」当成 bug 报上来。
  回归见 [tests/test_xlsx_style.py](backend/tests/test_xlsx_style.py) 的
  `test_ppt_and_excel_share_one_palette`。
- **Excel 清单类导出**：用 [xlsx_io.py](backend/xlsx_io.py) 的 `style_header()` + `beautify()`
  （浅蓝灰表头、细边框、斑马纹、状态点灯、冻结表头、列宽自适应）。调用顺序是
  写表头 → 写数据行 → `beautify()` → 再追加提示行。
  状态点灯是**精确匹配**（`brand.status_style()`）：包含匹配会把「已完成三个模块联调」
  整格染绿，而那一行其实还在进行中。状态词只是普通文本的表传 `light_status=False`。
- **专项图文混排导出**用 [xlsx_utils.py](backend/xlsx_utils.py)。周报的层次是
  红字标题 + 细红线 → 中灰章节行 → 浅蓝灰表头 → 白底正文，**红不参与分层**。
  状态底色**只上在状态那一格**，不整行铺：整行绿看着像「这一行整体没问题」，
  而它表达的其实只是某一列填了「已完成」。
- **PPT 表格一律走 [pptx_utils.py](backend/pptx_utils.py) 的 `add_table_slides()`**
  （宽矩阵用 `add_matrix_slides()`），不要自己 `add_table` 排版：
  - **一张 slide 装不下就分页**，页数由**估算行高**决定而不是固定条数——
    客户面一行可能是 6 行文字、也可能是 1 行，按条数切的结果是有的页空半张、
    有的页照样溢出。行高估算按 CJK 全角 1.0 em / 西文 0.52 em 算，**宁可估宽**：
    估窄了会算出"装得下"，导出的表照样长到幻灯片外面去。
  - **列宽传比例不传英寸**（`col_ratios`），内部归一化到正好铺满页宽。
    手写英寸数的话，加一列、改个标题就再也对不上，表格要么越过右边界、
    要么右边空一条——这是历史上四张表里三张都对不上的原因。
  - **长文本列必须给 `clip_cols`**（{列下标: 最多行数}）。一格能吃掉一整页，
    不截断的话分页也救不回来；截断后要写明"另 N 条"，别悄悄少几行。
  - 行高**显式写入**每一行（`table.rows[i].height`）：不写的话 `add_table` 把总高
    均分给每行，短行被撑得老高、长行还是溢出。PowerPoint 只会把行撑得更高、
    不会压缩，所以显式高度是下界，测试就断言这个下界不越过页底。
  - 合计行按首格文字（`_TOTAL_LABELS`）自动加粗加底色；URL 列用 `link_cols`
    渲染成可点的「查看」，别把整条链接摊在格子里。
  版面回归见 [tests/test_pptx_layout.py](backend/tests/test_pptx_layout.py)——
  溢出是**看不出报错**的那类 bug：文件能生成、能打开，只是一半内容在页面外。
- **导出配色对齐部门述职模板**（PPT 与 Excel 同款），取色逻辑是
  「红定位、蓝分层、饱和色点灯」，三者各管一件事，**不要互相借用**：
  - **红（`_BRAND` #C7000B）一页只出现两处**：标题文字 + 标题下那条通栏细线。
    表头、横幅、卡片都不用红。以前是深红横幅压顶 + 红底白字表头 + 浅红斑马，
    红铺满半页，最抢眼的成了那块红，而看的人要找的是表里的数。
    测试断言「整页只有一个红色填充块、且高度 ≤ 0.05"」——粗了就退化回横幅。
  - **表头浅蓝灰底 + 黑字**（`_HEADER_BG` / `_HEADER_TEXT`），分栏线用白色。
    浅底上白线是"分栏"，灰线会糊成一片。
  - **状态是给格子上底色，不是给字上色**（`_STATUS_FILLS`：绿/黄/红/灰）。
    六档里「未开始 / 不涉及」故意不点灯——它们表达的是"这里没有进展"，
    上了底色会和真有状态的格子一样抢眼。这是整页唯一的饱和色，所以一眼扫得到；
    改回染字色的话，6 个进展列全是同字号小字，得逐格读才分得出来。
  - 斑马纹（`_ZEBRA`）**压到几乎看不见**且跟着表头走蓝灰一系。模板里的表都在
    6 列以内，白底就够认行；产品需求表有 13~14 列，全白时眼睛横扫会串行。
  - 专项/自由表格的**点灯列**（`GRID_LIGHT_COLORS` 那套红黄绿）是**另一回事**，
    它是用户在页面上配的格式，必须与前端 `gridLight.js` 和周报 HTML 三处同款
    ——不要顺手把它并到 `brand.STATUS_FILLS` 里。
  - 页脚三件套（口号 / 密级 / 页码）**每页都有，封面也有**：导出的表经常被截图
    贴进别的材料，落单的一张没有页码就找不回出处。不想要就把 `_FOOTER_BRAND` /
    `_FOOTER_SLOGAN` / `_FOOTER_MARK` 置空，页脚只剩分隔线与页码。
- **上传文件**落 `backend/uploads/<模块>/`，**不放静态目录**；下载走鉴权 blob 端点
  （`FileResponse` / `StreamingResponse`），存储名用 `uuid4().hex + 后缀`，
  取用前用正则校验防路径穿越（见 `key_features.py` 的 `_STORED_RE`）。

## 运行时数据不入库

`backend/app.db`、`backend/uploads/`、`backend/config.json`、`__pycache__/`
已在 [.gitignore](.gitignore) 中。`config.json` 里是本机绝对路径与本部署要采集的项目，
而且页面「配置」会改写它；跟着代码走的后果是每次 `git pull` 把线上配好的路径盖回
某台开发机的 `D:\...`，页面上看不出来，只是问题单采集从此指向一个不存在的目录。
模板是 `backend/config.example.json`，读不到 `config.json` 时回落到它
（回落到 `{}` 会让 `hw_machine_cell_options` 这类**词表**默认值一起空掉，
新装实例里那几个下拉是空的，看着像功能坏了）。
数据库属于部署实例的状态而非源码——新库由 `create_all` + `seed_initial_data` 自动生成，
备份按 [部署指南](doc/部署指南.md) 第 6 章的定时 `.backup` 走。

## 前端约定

- **新增页面**＝在 [router/index.js](frontend/src/router/index.js) 加一条，`meta` 填
  `title` / `icon` / `group`（决定侧栏 7 分组归属）/ 按需 `requireAdmin` / `hidden`。
  路由守卫只拦 `requireAdmin`，页面内的 admin 自查是额外一层，**不能替代服务端校验**。
- **组件里抛出的异常会静默白屏**，所以 [main.js](frontend/src/main.js) 挂了
  `app.config.errorHandler`：控制台留完整堆栈 + 页面弹一条提示。别把它摘掉——
  setup/render 抛异常时 Vue 只在控制台写一行，页面一片空白，而且之后点别的菜单
  也不再渲染，现象是「进了某个页面之后整个系统就没反应了，刷新一下又好」，
  看着完全不像是那个页面的错。**少写一个 `import` 就够触发**（`VersionManagement.vue`
  用了 `computed` 却没 import，正是这么坏的），而构建不会报错：Vite 不做 no-undef 检查。
  现在 `npm run lint` 的 `no-undef` 会在提交前拦住这一类，但 errorHandler 是兜底，
  两者都要留着：lint 拦的是漏 import，运行时还有别的抛法。
  [eslint.config.js](frontend/eslint.config.js) **只开能抓真 bug 的规则**，
  刻意不加风格类规则——23k 行存量代码一次冒出几百条 warning，之后就没人看 lint 输出了。
- **加载失败的提示要带上 HTTP 状态**，用 `api/index.js` 导出的 `apiError(e, '加载XX失败')`。
  统一写成一句「加载失败」的话，500（去翻服务端 traceback）、超时（后端还活着但卡住了）、
  连不上（后端没起来）三种完全不同的故障在页面上长得一模一样，来回问一轮才知道看哪儿。
- **API 调用**统一加到 [api/index.js](frontend/src/api/index.js) 的对应 `*Api` 对象，
  不要在组件里直接 `axios`——token 注入与 401/409/423 拦截都在那一层。
- 详情页组件用 `:key="route.fullPath"`（见 App.vue）：参数变化时重建实例，
  避免迟到的异步响应写错对象（专项内容串台）。
- 状态管理没用 Pinia，是 `store/` 下手写的 `reactive` 单例，跟随现有写法即可。
- **大表格里别每行放 `el-date-picker`**。它给内部 tooltip 传的 `persistent` 写死为真，
  面板**立即渲染**且没有关掉的入口——一行两个日期列＝两个完整月历（各 40+ 格），
  几百行就是几万个节点，页面卡在这里。做法是退化成文本、点开才挂控件、面板关掉就卸载
  （见 [CustomerIssueTracking.vue](frontend/src/views/CustomerIssueTracking.vue) 的 `DateCell`）。
  `el-select` 有 `:persistent="false"` 这个入口，行内下拉加上它即可，不必改成点开才挂。
- **`clearable` 的 `el-select` 清除后值是 `undefined`**（Element Plus 的 `valueOnClear`
  默认值），而 `undefined` 会被 `JSON.stringify` 从请求体里整个丢掉，后端按
  「没传＝不修改」处理。表现是"清空保存，一刷新又回来了"，而页面还提示保存成功。
  **拼整行 payload 的表格要在出口把文本列折成空串**（见 `CustomerDetailPanel` 的
  `customReqValue()`）；`exclude_unset` 那一侧不要改——"没传"和"传了空"本来就该是两件事。
  行数本身也要兜住：这类逐格可编辑的表一律分页，别整表铺开。

## 已知待处理

- `GET /api/system/storage` 无前端消费方。
- `POST /api/major-versions/reorder` 无前端消费方：大版本改成按开始时间倒序后页面撤了
  ↑↓ 入口。接口留着（对没填开始时间的那批仍有效），删掉会让三层的重排不再对称。
- `models.Version` / `models.Iteration` 是为兼容老库存量表保留的死模型，新代码勿用。
- `major_versions.actual_release_date` 是两层版本体系的遗留列，0010 迁移后无人读写。
- 单进程假设：APScheduler 与问题单采集锁都是进程内内存态，上多 worker 会重复执行。
