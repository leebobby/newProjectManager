# 数据库迁移（Alembic）

本项目从「`create_all` 自动建表 + `migrate.py` 加列」过渡到 Alembic 管理结构变更。
Alembic 负责 `create_all` 做不到的事：**改名 / 删列 / 改类型 / 加约束 / 数据回填**。

> SQLite 不支持原生 ALTER，`env.py` 已开启 `render_as_batch=True`，
> Alembic 会用「建新表 → 拷数据 → 换名」自动完成这些变更。

所有命令都在 `backend/` 目录下执行（先激活 venv）。

## 一次性接入（现有库 app.db）

老库已有全部表，**不要重新建表**，只需把它标记到基线，再升级到最新：

```powershell
cd AIProjectManager\backend
alembic stamp 0001_baseline   # 告诉 Alembic：当前库就是基线状态
alembic upgrade head          # 应用 0001 之后的迁移（如 0002 优先级统一）
```

## 全新部署

`main.py` 启动时仍会 `create_all` 建好所有表（含全部约束/索引），因此新库开箱即用。
建好后把版本对齐到最新即可：

```powershell
alembic stamp head            # 表已由 create_all 建好，直接对齐版本
```

（也可以反过来：删掉自动建表、改用 `alembic upgrade head` 全量建库。当前为降风险保留 `create_all`。）

## 日常：新增一次结构变更

```powershell
# 1. 改 models.py（加表/改列…）
# 2. 自动生成迁移草稿（务必人工检查 SQLite batch 是否正确）
alembic revision --autogenerate -m "说明，如 customer_status 改名 machine_status"
# 3. 检查 versions/ 下新文件，必要时手改
# 4. 应用
alembic upgrade head
```

回滚一格：`alembic downgrade -1`；查看状态：`alembic current` / `alembic history`。

## 与旧机制的关系

- `migrate.py`（`ALTER TABLE ADD COLUMN`）已**冻结**，不要再往 `_ADDITIONS` 加新列；
  新的列/表/约束一律走 Alembic。保留它只为兼容尚未接入 Alembic 的旧库启动。
- `create_all` 仍在 `main.py` 启动时运行（幂等），保证新库/新表可用。
