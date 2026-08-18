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
cd frontend && npm install && npm run dev
```

`main.py` 的启动顺序是有意为之，改动前先读懂：
`ensure_schema()`（老库补列）→ `Base.metadata.create_all()`（补缺失的表）→
`automigrate.upgrade_to_head()`（追平 Alembic）→ `seed_initial_data()` → `scheduler.start()`。

---

## Write-permission principle

写权限只有三档，**新增接口必须落在其中一档**，不要发明第四种：

| 档位 | 依赖 | 适用 |
| --- | --- | --- |
| **登录用户**（协作编辑域） | `Depends(get_current_user)` | 日常填报与记录：进展、事务、风险、问题条目、出差、调试版本、领域内容、关键特性…… |
| **仅 admin** | `Depends(require_admin)` | 主数据与配置：用户、资源组、客户、里程碑项目、专项元数据、专项版式模板、一本通、干系人、阵型、`config.json`、数据对账 |
| **字段级白名单** | 路由内按角色逐字段判 | 同一行里不同字段权限不同，见 [routers/customer_status.py](backend/routers/customer_status.py) |

配套硬规则：

- **删除权限按「删掉的是什么」定，不跟随该表的写权限**。现状（逐个端点核对得来）：
  - **仅 admin**：主数据与配置类，以及客户面数据——客户面问题条目、硬件清零、
    SOW 字段与数据行、机台 license、机台自定义信息块、客户定制化需求、专项本体。
  - **登录用户**：专项/攻关的事务行与风险行、专项分段图片、现场调试版本与诉求与接收人、
    出差记录、领域风险。
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
| `extra_grids_json` | 自定义分段本体（`kind` = grid / text / images） |

- 8 个内置分段的 key 与默认顺序在 [enums.py](backend/enums.py) `SPECIAL_SECTIONS`，
  须与前端 `SpecialDetail.vue` 的 `FIXED_KEYS` 一致。内置分段各有专属交互
  （里程碑时间轴、事务/风险表、阵型网格），所以**只能改标题或整段停用，不能动态增删**；
  要新表格就加自定义分段。
- **顺序与标题的解析只有一份实现**：`special_layout.resolve_sections()`。详情页、Excel 导出、
  周报三处都走它。前端 `reconcileOrder()` 的规则必须与 `resolve_order()` 保持一致——
  两边分叉的表现是「页面顺序和周报顺序不一样」，很难被测出来。
- 新增内置分段时：`SPECIAL_SECTIONS` 加一条 + 详情页 `v-if` 链加一段 +
  `_section_text()` / `_section_html()` / `build_special_xlsx()` 各加一个分支。
  **缺任何一处的后果是那段在页面上有、在周报/导出里没有。**
- 空分段不占章节编号：导出与周报里「启用但没内容」的段整段跳过，避免一串「三、—」。
- **模板（`special_templates`）只是录入期的便利，不是运行期依赖**：套用时把版式写进上面三列，
  之后与模板脱钩。改模板、删模板都不影响已建专项——不要反过来做成「详情页读模板渲染」。
- 套用语义是**只增不删**（`apply_template()`）：按 `tkey` 认领已挂上的分段，重复套用幂等；
  模板外的分段与已填的行一律保留。版式是配置，填进去的内容不是。
- 权限分档：改模板、套模板＝**仅 admin**（配置类主数据 / 改的是整页版式）；
  某专项内部的分段改名、停用、排序＝**登录用户**（协作编辑，走 `PUT /content` 的乐观锁）。

## 枚举：单一来源

所有状态 / 优先级词表收口在 [backend/enums.py](backend/enums.py)，**不要在 router 或前端
另写字面量**。历史上这些词表以自由字符串散落各处，导致口径漂移、错字静默漏算。

- 校验用 `norm_*` 系列函数（`norm_priority` / `norm_progress` / `norm_issue_status` …）。
- **`norm_*` 只挂在 `Create` / `Update` schema 上，绝不挂 `Base` / `Out`**：`Out` 继承 `Base`
  并走 `from_attributes` 读库，老库里的历史脏值会让读取直接 422。
- 前端下拉值必须与 `enums.py` 一致；关键特性的颜色映射在
  [utils/featureStatus.js](frontend/src/utils/featureStatus.js)，顺序须与后端六档一致。
- 自由表格的列格式白名单 `GRID_COL_TYPES`（text / select / date / **light**）在两端各有一份：
  后端 `enums.py`、前端 [utils/gridLight.js](frontend/src/utils/gridLight.js)。
  **前端漏加一项的后果是该格式的列每次加载被静默重置成 text**（`normGrid()` 按白名单过滤）。
  点灯的取值词表与红黄绿档位同理两端各一份，页面 / 周报 HTML / Excel 三处着色必须同款。

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

`customers` / `users` / `resource_groups` / `iteration_versions` 是主数据，业务表逐步从
「存字符串」迁到「存 FK + 字符串快照」。

- 字符串 → FK 的反查统一走 [routers/_lookups.py](backend/routers/_lookups.py)
  （`resolve_*` / `fill_*_fk`），不要在各 router 里重写匹配规则。
- 反查失败**不要报错**，留空让「数据对账」页（`/data-mapping`）事后补全。
- 快照字段（`owner` / `owner_group` / `planned_version` …）保留用于展示与导入兜底，
  FK 为空时前端回退到它。

## 导出与上传

- **Excel 清单类导出**：用 [xlsx_io.py](backend/xlsx_io.py) 的 `style_header()` + `beautify()`
  （品牌蓝 `#4073BA`、细边框、斑马纹、冻结表头、列宽自适应）。调用顺序是
  写表头 → 写数据行 → `beautify()` → 再追加提示行。
- **专项图文混排导出**用 [xlsx_utils.py](backend/xlsx_utils.py)；**PPT** 用
  [pptx_utils.py](backend/pptx_utils.py)。不要新起一套样式。
- **上传文件**落 `backend/uploads/<模块>/`，**不放静态目录**；下载走鉴权 blob 端点
  （`FileResponse` / `StreamingResponse`），存储名用 `uuid4().hex + 后缀`，
  取用前用正则校验防路径穿越（见 `key_features.py` 的 `_STORED_RE`）。

## 运行时数据不入库

`backend/app.db`、`backend/uploads/`、`__pycache__/` 已在 [.gitignore](.gitignore) 中。
数据库属于部署实例的状态而非源码——新库由 `create_all` + `seed_initial_data` 自动生成，
备份按 [部署指南](doc/部署指南.md) 第 6 章的定时 `.backup` 走。

## 前端约定

- **新增页面**＝在 [router/index.js](frontend/src/router/index.js) 加一条，`meta` 填
  `title` / `icon` / `group`（决定侧栏 7 分组归属）/ 按需 `requireAdmin` / `hidden`。
  路由守卫只拦 `requireAdmin`，页面内的 admin 自查是额外一层，**不能替代服务端校验**。
- **API 调用**统一加到 [api/index.js](frontend/src/api/index.js) 的对应 `*Api` 对象，
  不要在组件里直接 `axios`——token 注入与 401/409/423 拦截都在那一层。
- 详情页组件用 `:key="route.fullPath"`（见 App.vue）：参数变化时重建实例，
  避免迟到的异步响应写错对象（专项内容串台）。
- 状态管理没用 Pinia，是 `store/` 下手写的 `reactive` 单例，跟随现有写法即可。

## 已知待处理

- `GET /api/system/storage` 无前端消费方。
- `models.Version` / `models.Iteration` 是为兼容老库存量表保留的死模型，新代码勿用。
- 单进程假设：APScheduler 与问题单采集锁都是进程内内存态，上多 worker 会重复执行。
