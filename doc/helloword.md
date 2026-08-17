## Layout

The actual app lives in `ProjectManager/` — a two-folder split:

- `ProjectManager/backend/` — FastAPI + SQLAlchemy + SQLite (`app.db`)
- `ProjectManager/frontend/` — Vue 3 + Vite + Element Plus

Always `cd ProjectManager/...` first; the repo root only holds this file and the `ProjectManager/` directory.

## Commands

Backend (PowerShell on Windows is the assumed shell):
```powershell
cd ProjectManager\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
- Swagger at http://127.0.0.1:8000/docs
- First start auto-seeds `admin / admin123` and example rows.
- `APP_SECRET_KEY` env var overrides the JWT signing key (default is `dev-secret-please-change-in-prod`).
- **Tests**: `cd backend && python -m pytest tests -q`. The session fixture in `tests/conftest.py` chdirs into a tmp dir and imports `main` — a fresh seeded SQLite DB per run, never touches dev `app.db`. Add a test file per feature; monkeypatch a router's `load_config` for config-driven behavior (see `test_hardware_issues.py`). No linter configured.

Frontend:
```powershell
cd ProjectManager\frontend
npm install
npm run dev        # http://127.0.0.1:5173, /api proxied to :8000
npm run build      # production build
```

## Database & migrations

- Single SQLite file `ProjectManager/backend/app.db`.
- **Alembic is now the system of record for schema changes** (`backend/alembic/`, see `backend/alembic/README.md`). It handles what `create_all` can't: rename / drop / type-change / add-constraint / data-backfill. `env.py` sets `render_as_batch=True` so SQLite ALTERs work via table-rebuild. Baseline is `0001_baseline` (existing DBs: `alembic stamp 0001_baseline`); apply changes with `alembic upgrade head`.
- `main.py` still runs `ensure_schema()` then `Base.metadata.create_all()` at import time (kept for zero-risk startup: fresh DBs and brand-new tables still appear automatically). **After that, `automigrate.upgrade_to_head()` auto-runs Alembic to head at startup** (stamps `0001_baseline` first for never-tracked DBs; failures log a warning without blocking startup) — manual `alembic upgrade head` is no longer part of deploys, but migrations must stay inspector-guarded/idempotent since create_all builds new tables before they run.
- `migrate.py` (`ALTER TABLE ... ADD COLUMN` via `_ADDITIONS`) is **frozen** — don't add new entries. Any new column/table/constraint goes through Alembic. It remains only to boot legacy DBs that predate Alembic.
- **SQLite foreign keys are enforced**: `database.py` sets `PRAGMA foreign_keys=ON` per connection (an `event.listens_for(engine, "connect")` listener). Without it the `ondelete=` rules are dead DDL. New raw deletes now cascade/SET NULL at the DB level — keep that in mind. (Alembic uses its own engine, so batch migrations are unaffected.)
- **Status/priority vocabularies live in `backend/enums.py`** (single source): `PROGRESS_STATUSES` (6 values incl. 已变更), `PRIORITIES` (P0–P3, unified across both requirement tables — product reqs no longer use 高/中/低), `TASK_STATUSES`, `ITERATION_STATUSES`. Validate inputs with `enums.norm_priority` / `enums.norm_progress` on the **Create/Update** schemas only (never on Base/Out — `from_attributes` would raise on legacy DB values during reads). Frontend dropdown values must match this file.
- A handful of tables use optimistic locking via a `version` Integer column (currently `customer_status`, `iteration_requirements`, `roadmap_phases`, `special_contents`, `customers`). PUT handlers compare `payload.version` to `row.version` and return 409 on mismatch; axios's response interceptor (`api/index.js`) already shows the warning toast.
- Pydantic v2 quirk: `CustomerStatus.model` is a real column, so schemas set `protected_namespaces=()` to silence the `model_` warning. Carry that forward for any model that adds a column starting with `model_`.

## Backend wiring rules

To add a feature, you almost always touch four files:

1. `models.py` — new tables/columns. Stick at the existing place (file is currently single-flat, no per-domain split).
2. `schemas.py` — Pydantic Base/Create/Update/Out. Update schemas carry `version: int` when the table uses optimistic locking.
3. `routers/<name>.py` — `APIRouter(prefix="/api/...", tags=[...])`. Reads are open to all logged-in users (`Depends(get_current_user)`); pick the write guard per the **write-permission principle** below.
4. `main.py` — import the new module and `app.include_router(<mod>.router, dependencies=authed)`. Auth-public routes (`auth_router`, `config_router`) are registered separately; `users.router` and `op_logs.router` mount their own admin guard internally.

### Write-permission principle

Every endpoint that mutates data falls into exactly one of two domains. Decide which **before** writing the handler; don't default by habit.

- **管理员维护域 (admin-maintained)** — master data, structure, and configuration: customers, resource groups, roadmaps/milestones, handbook, SOW, stakeholders, licenses, customer extra-fields, custom requirements, annual-iteration shells, major/iteration versions, mapping, special **definitions** (create/update/delete a special, not its content), user management, op-log, `config.json`. Writes guard with `Depends(require_admin)`.
- **协作编辑域 (collaborative)** — day-to-day filling that the whole team owns: special **content/tasks/risks** (protected by the pessimistic edit lock), iteration requirements & product requirements, and the user-facing fields of customer-面状态. Writes guard with `Depends(get_current_user)`; enforce any per-field admin carve-outs inside the handler (`customer_status.py` is the reference: `_ADMIN_ONLY_FIELDS` vs `_USER_FIELDS`).

Rules of thumb: a new domain defaults to **管理员维护域** unless it is explicitly a shared filling surface. Never leave a write on bare `get_current_user` "for now" — that is how the legacy `versions`/`iterations` write endpoints became an over-permissive, unused attack surface (now removed; both routers are read-only). Self-registration is **not** a thing: account creation is admin-only (`/api/auth/register` requires admin; day-to-day use `/api/users`).

Audit logging: every write should call `op_log.log_op(db, action=..., target=..., target_id=..., detail=..., user=current_user, request=request)`. It swallows its own exceptions, so a logging failure never breaks the request.

Excel exports/templates share `backend/xlsx_io.py` (`style_header` + `beautify`: brand-blue header, zebra, borders, auto column widths, frozen header). Call `beautify()` after data rows and **before** appending tip rows. Chinese download filenames must use the RFC5987 pattern (ASCII `filename=` fallback + `filename*=UTF-8''...`) — raw Chinese in a Content-Disposition header breaks (headers are latin-1). PPT exports share `pptx_utils.py` primitives (`_apply_run_font` sets the East-Asian font — without it Chinese renders in fallback serif).

Uploads land under `backend/uploads/` (`handbook/<yyyymm>/`, `specials/<id>/`) and are served via authenticated blob endpoints — do not expose them through static file mounts.

`config.json` is the runtime knob for dropdown choices (e.g. `current_stages`) and the issue-report directory path. Reading is public; writing requires admin.

## Frontend wiring rules

- All HTTP goes through `src/api/index.js`. The axios instance auto-attaches the Bearer token, redirects to `/login` on 401, and toasts on 409. Per-module APIs are exported as `<domain>Api` objects.
- Routes in `src/router/index.js`. A route with `meta.title` and `meta.icon` (any Element Plus icon name) automatically appears in the sidebar — all icons are globally registered in `main.js`. Use `meta.hidden: true` for detail pages and `meta.requireAdmin: true` for admin-only sections.
- Auth state and the cross-tab logout broadcast live in `src/store/auth.js`. The 15-minute idle auto-logout is wired in `App.vue` (`IDLE_MS` constant) and shares activity across tabs via localStorage.
- The "专项管理" sidebar entry is special: it renders as a submenu populated from `store/specials.js` (loaded on login, refreshed via `reloadSpecials()`). Other routes go through the default flat-menu branch.
- Reusable components in `src/components/`: `EditableText.vue` (click-to-edit text, supports rich/plain modes — pair with `RichTextEditor.vue` for rich), `MilestoneTimeline.vue` (horizontal milestone strip). Prefer these over hand-rolled inline editors.
- Heavy tab-embedded pages (CustomerStatus 的问题跟踪/硬件清零) wrap the child in `<KeepAlive>` + `v-if` and refresh silently via `onActivated` (guarded so the first activation doesn't double-fetch after `onMounted`). Don't revert to bare `v-if` — remounting refetches everything and made tab switches visibly laggy.

## Domain notes worth knowing up-front

- **客户面问题/事务** (`customer_issues`, `routers/customer_issues.py`, UI＝「客户面状态」页的「问题跟踪」tab；`/customer-issues` 仅作重定向) — 原本是 `customer_status.key_issues` / `recent_focus` 两个 Text 列里的 JSON 清单 `[{text,done}]`；已提升为一行一条的实体表（Alembic `0004_customer_issues` 建表 + 回填，旧 Text 列**保留但不再读写**，留回滚余地）。一表三类靠 `kind` 区分：`issue` 软件类问题与 `demand` 需求用全套字段（描述/关联问题单/紧急程度 重要紧急·紧急·一般/责任人 user FK + 自由文本兜底/提出·预计·闭环时间/状态 OPEN·CLOSED·挂起；demand 在问题栏以「需求:」前缀录入、同栏展示带蓝色角标），`task` 现场关键事务只用 描述 + `due_date` + 状态。跟踪表已闭环行用专项管理同款浅绿（#f0f9eb）。`customer_id` 随机台冗余，汇总页按战场过滤靠它。状态置 CLOSED 自动补 `closed_at`、撤回自动清空。逾期＝`due_date` 已过且未 CLOSED，`scheduler.daily_ddl_scan` 会扫它发临期/逾期通知。协作编辑域，**删除仅 admin**。单机台清单与全战场汇总共用同一个 `GET`（传不传 `machine_status_id`）。前端单元格统一走 `components/CustomerIssueCell.vue`（总览 + 客户详情共用），已完成条目默认折叠。
- **Customer master data** (`customers` + `customer_aliases`) was introduced as the single source of truth for customer identity. Existing tables like `customer_status.battlefield` and `stakeholder_battlefields.battlefield` are still plain strings — there is no FK yet. A planned phase will add `customer_id` columns and backfill from the alias table; until then the new module is an island.
- Legacy `iterations` and `versions` tables are **fully retired at the code level** (2026-07 cleanup): routers deleted, seeds removed, no frontend callers (ProjectIntro counts `major_versions` now). The two model classes stay in `models.py` only so existing DB tables are left untouched; a future Alembic revision may drop them. New work goes through `annual_iterations`/`iteration_requirements` and `major_versions`+`iteration_versions` (`majorVersionApi`).
- Shared frontend helpers live in `src/utils/format.js` (`fmtDate`, `naturalCompare`) — import these instead of redefining per-component.
- `specials` covers both 专项 and 攻关 (distinguished by `kind`). Same model for both; the UI label switches based on `kind`. 详情页自定义分段统一存 `special_contents.extra_grids_json`，数组元素靠 `kind` 区分：`grid`（RichGrid 表格，正文单元格支持 bold/align/color，导出 xlsx 独立工作表）/ `text`（富文本框）/ `images`（多图，`items:[{file,name,width%}]`，文件走 `POST/GET/DELETE /specials/{sid}/images[/{stored}]`，与全景图同目录）。新增入口是页面末尾的「新增分段」下拉；分段 key 一律 `grid:<gid>` 参与 `section_order_json` 排序（历史命名，非 grid 块也用它）。
- **领域管理** (`routers/domains.py`, page `/domains`) is a per-PL-group overview. Only the manual fields (最近主要工作 rich text, 风险与求助 itemized) are persisted (`domain_contents`, one row per PL group, optimistic-locked). The other two columns are **derived live, not stored**: 需求情况 aggregates `iteration_requirements` by `group_id`, scoped by default to the **in-progress** annual iteration(s) (`status == "in_progress"`) but overridable via `?year=&month=` (the page has a month selector); 问题单情况 reads the latest issue **Excel** (`issue_report_path`) raw rows, matches `group` (责任人所属小组) against the PL group's `name`/`code`, and reports both a count and a **weighted score** (致命10/严重3/一般1/提示0.1, weights in `domains._SEVERITY_WEIGHTS`). If the Excel is unconfigured/unreadable the issue cell degrades to "未接入" rather than erroring. It's a 协作编辑域. The page is **two tabs**: 「领域总览」(the above) and 「事务与风险跟踪」(`domain_risks` table: 序号/风险和事务/优先级 高中低/当前进展/责任领域=PL组 FK/计划闭环/状态 OPEN·CLOSED·挂起, color-coded, optimistic-locked, `GET/POST/PUT/DELETE /api/domains/risks`; `?include_done=false` returns only OPEN). Domains can be **soft-hidden** from 领域总览 (`domain_hidden` table, one row per hidden PL group; `PUT /api/domains/{id}/visibility {hidden}`; `list_domains?include_hidden=true` to see/restore) — this does **not** touch the org-structure PL group. Both new tables via `create_all` (no column added to existing `domain_contents`, on purpose — old-DB `create_all` won't add columns).
- **客户面支撑情况** (`routers/business_trips.py`, table `business_trips`, page `/business-trips`, sidebar 客户面管理) — renamed from 出差管理 (table/route names kept). 支撑人(user FK)/支撑战场(customer FK)/起止/事由, status derived from dates (计划中/进行中/已完成) + cancelled. Dashboard `GET /business-trips/dashboard?start=&end=` (default＝当月) returns now-snapshot (on_trip_now/planned) + range breakdowns **by 战场 / by 人 / by 领域** (领域＝支撑人所属 PL 组 group_name). Month-Gantt timeline (人×天). 协作编辑域.
- **现场调试版本 (T 版本)** (`routers/debug_versions.py`) lives **inside the 版本管理 page** as the "现场调试版本" tab (renamed from 客户面调试版本 / the old empty 全局版本; `activeTab === 'debug'` swaps the major-version table/timeline for `DebugVersionPanel.vue`). Tables: `debug_versions` (版本号/基线/目标客户=`customers` FK/计划·实际发布/合入内容 3 列/自验证归档), `debug_demands` (诉求收集; 涉及战场 = customer-id JSON list), and `debug_version_recipients` (**接受版本姓名列表**: 姓名/role/received, FK→debug_versions CASCADE). Recipients are **auto-matched from the 战场沟通矩阵** (`StakeholderBattlefield` rows where `customer_id == target_customer_id`, taking `contact1`/`contact2` split by line → name, role=服务/APPS) via `POST /debug-versions/{vid}/recipients/auto-match` (additive, dedup by name); the panel auto-runs it on first open of an empty list. Recipients have **no optimistic lock** (simple toggles). All 协作编辑域, new tables via `create_all`. The quality dashboard tab (`MetricsDashboard.vue` → `/debug-versions/dashboard`) pivots debug versions per month (bucket = release_date, else planned_release_date, else 未排期) × 目标客户.
- **Notification granularity (大颗粒)**: iteration-requirement progress field changes **no longer dispatch** `status_change` (was a flood when filling 70-80 rows). Only `assignment` (becoming a requirement owner) fires. `customer_status` / `specials` notifications are subscription-based (opt-in, already coarse); scheduler `due_soon`/`overdue` are daily. Keep version-class notifications fine-grained if added later. Marquee (`NotificationMarquee.vue`) only auto-scrolls at ≥5 items (else static), ~8s/item.
- **版本计划图** (`VersionTimeline.vue`, top of each project tab in 版本管理) is an SVG git-graph: newest major version = main trunk (full-width, bold over its real range), older majors branch off the trunk at their start date down to parallel lanes; iteration versions are nodes by `planned_date`. Has a 时间范围 selector (全部/近3/6/12月) and staggered+collision-skipped node labels. Needs ≥1 major version with a date to render; otherwise shows a hint.

## Things that quietly break

- Adding a kwarg to a Pydantic schema without the matching SQLAlchemy column. `_create_item` uses `Model(**data)` and SQLAlchemy's declarative `__init__` raises `TypeError`, which surfaces as a 500 with no `detail`, which the frontend shows as a generic "保存失败". Always keep schema and model fields in sync. (Updates use `setattr` and don't raise, so the bug only fires on create — easy to miss.)
- Forgetting to add a new column to `migrate.py`'s `_ADDITIONS`. Fresh databases work via `create_all`; existing user databases silently miss the column until first write fails.
- Element Plus icon names are case-sensitive and must be valid (e.g. `OfficeBuilding`, `DataLine`). A typo just renders nothing in the sidebar.
