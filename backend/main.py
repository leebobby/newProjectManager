from datetime import datetime

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

import models
from auth import get_current_user, hash_password
from database import Base, SessionLocal, engine
from migrate import ensure_schema
from routers import annual_iterations, iteration_product_requirements, iteration_requirements
from routers import auth as auth_router
from routers import config as config_router
from routers import business_trips, customer_custom_req, customer_extra, customer_issues, customer_status, customers, debug_versions, domains, handbook, hardware_issues, issues, key_features, licenses, major_versions, mapping, metrics, notifications, op_logs, project_formation, resource_groups, roadmap, sow, specials, stakeholders, system as system_router, users

# 先做轻量迁移（给老库加列），再 create_all 补齐缺失的表，
# 最后自动把 Alembic 迁移追平 head（数据迁移/改列类，create_all 覆盖不到）。
ensure_schema()
Base.metadata.create_all(bind=engine)

from automigrate import upgrade_to_head  # noqa: E402
upgrade_to_head(engine)

app = FastAPI(title="AI Project Manager")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 公开路由（登录/注册、以及前端启动时需要读取的配置不需要 token）
app.include_router(auth_router.router)
app.include_router(config_router.router)   # GET 公开读，PUT 内部已限 require_admin

# 业务路由：全部需要登录
authed = [Depends(get_current_user)]
app.include_router(resource_groups.router, dependencies=authed)
app.include_router(customers.router, dependencies=authed)
app.include_router(mapping.router, dependencies=authed)
app.include_router(customer_status.router, dependencies=authed)
app.include_router(customer_issues.router, dependencies=authed)
app.include_router(hardware_issues.router, dependencies=authed)
app.include_router(key_features.router, dependencies=authed)
app.include_router(sow.router, dependencies=authed)
app.include_router(licenses.router, dependencies=authed)
app.include_router(customer_extra.router, dependencies=authed)
app.include_router(customer_custom_req.router, dependencies=authed)
app.include_router(annual_iterations.router, dependencies=authed)
app.include_router(iteration_requirements.router, dependencies=authed)
app.include_router(iteration_product_requirements.router, dependencies=authed)
app.include_router(roadmap.router, dependencies=authed)
app.include_router(issues.router, dependencies=authed)
app.include_router(major_versions.router, dependencies=authed)
app.include_router(debug_versions.router, dependencies=authed)
app.include_router(stakeholders.router, dependencies=authed)
app.include_router(metrics.router, dependencies=authed)
app.include_router(notifications.router, dependencies=authed)
app.include_router(handbook.router, dependencies=authed)
app.include_router(specials.router, dependencies=authed)
app.include_router(domains.router, dependencies=authed)
app.include_router(project_formation.router, dependencies=authed)
app.include_router(business_trips.router, dependencies=authed)
app.include_router(system_router.router, dependencies=authed)

# 用户管理 / 操作日志：路由内部已挂 require_admin
app.include_router(users.router)
app.include_router(op_logs.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


def seed_initial_data():
    """首次启动注入：默认 admin 账户 + 少量业务示例数据。"""
    db = SessionLocal()
    try:
        if db.query(models.User).count() == 0:
            db.add(models.User(
                username="admin",
                full_name="超级管理员",
                password_hash=hash_password("admin123"),
                role="admin",
                auth_provider="local",
                is_active=True,
            ))

        if db.query(models.CustomerStatus).count() == 0:
            db.add_all([
                models.CustomerStatus(
                    machine_id="M-001",
                    battlefield="华东客户A",
                    model="X-100",
                    current_stage="T3 Release",
                    field_version="v2.1.3",
                    attention_level=2,
                    customer_status="客户验收顺利,本周计划增订 5 台",
                    recent_focus="良率提升至 98%",
                    key_issues="",
                ),
                models.CustomerStatus(
                    machine_id="M-002",
                    battlefield="华南客户B",
                    model="X-200",
                    current_stage="T1-T2",
                    field_version="v2.0.5-rc2",
                    attention_level=5,
                    customer_status="客户反馈偶发停机,正在协调驻场",
                    recent_focus="解决偶发停机问题",
                    key_issues="主控板偶发复位,正在定位",
                ),
            ])

        # 注：legacy `versions` / `iterations` 两表已停止 seed 与路由（2026-07 清理），
        # 模型保留只为不动老库的存量表；新体系走 major_versions / annual_iterations。

        # 当前年度 12 个迭代占位 + 1 个示例需求
        current_year = datetime.now().year
        has_year = (
            db.query(models.AnnualIteration)
            .filter(models.AnnualIteration.year == current_year)
            .count()
        )
        if has_year == 0:
            for m in range(1, 13):
                db.add(models.AnnualIteration(
                    year=current_year,
                    month=m,
                    name=f"{current_year}年{m}月迭代",
                    status="planning",
                ))
            db.flush()
            current_month_it = (
                db.query(models.AnnualIteration)
                .filter(
                    models.AnnualIteration.year == current_year,
                    models.AnnualIteration.month == datetime.now().month,
                )
                .first()
            )
            if current_month_it:
                current_month_it.status = "in_progress"
                current_month_it.owner = "admin"
                db.add(models.IterationRequirement(
                    iteration_id=current_month_it.id,
                    seq=1,
                    req_no="REQ-2026-001",
                    req_url="https://example.com/req/2026-001",
                    title="客户面状态页增加型号字段",
                    owner="admin",
                    priority="P1",
                    planned_version="v0.5.0",
                    progress_walkthrough="已完成",
                    progress_reverse="已完成",
                    progress_stc="进行中",
                    progress_coding="进行中",
                    progress_bbit="未开始",
                    progress_clarify="未开始",
                ))
        # 首页项目里程碑示例数据
        if db.query(models.RoadmapProject).count() == 0:
            current_year = datetime.now().year
            demo = models.RoadmapProject(
                name="战略型产品路线图",
                description="示例项目：演示季度精度的路线图渲染。",
                year=current_year,
                granularity="quarter",
                sort_order=0,
                is_active=True,
            )
            db.add(demo)
            db.flush()
            db.add_all([
                models.RoadmapPhase(
                    project_id=demo.id,
                    name="启动阶段",
                    color="#67C23A",
                    start_year=current_year, start_month=1,
                    end_year=current_year, end_month=3,
                    goal="1. 公司战略级长线产品初始需求\n2. 团队练兵、熟悉业务",
                    core_products="AFKGoo",
                    scenarios="线上 + 线下互导流收割",
                    sort_order=0,
                ),
                models.RoadmapPhase(
                    project_id=demo.id,
                    name="持续交付阶段",
                    color="#409EFF",
                    start_year=current_year, start_month=4,
                    end_year=current_year, end_month=6,
                    goal="1. AFKGoo1.0 交付业务投产\n2. 验证超敏捷产品迭代交付节奏",
                    core_products="AFKGoo、Sharaly",
                    scenarios="微信生态群运营",
                    sort_order=1,
                ),
                models.RoadmapPhase(
                    project_id=demo.id,
                    name="聚焦效果阶段",
                    color="#F56C6C",
                    start_year=current_year, start_month=7,
                    end_year=current_year, end_month=9,
                    goal="1. 可量化、可视化的用户运营效果\n2. 内容 + 系统 + 服务体系建设\n3. 精准营销，提 LTV、复购率、降 CPC",
                    core_products="AFKGoo、Sharaly",
                    scenarios="C 端视角：参照 KualaLumpur\nB 端视角：参照 Gyllenhaal",
                    sort_order=2,
                ),
            ])
            db.add_all([
                models.RoadmapMilestone(project_id=demo.id, year=current_year, month=1, title="", description="产品 MRD、技术新底盘"),
                models.RoadmapMilestone(project_id=demo.id, year=current_year, month=2, title="", description="AFKGooPRD、原型\n云服务搭建"),
                models.RoadmapMilestone(project_id=demo.id, year=current_year, month=3, title="", description="需求分析、WBS\n进入研发 SOP"),
                models.RoadmapMilestone(project_id=demo.id, year=current_year, month=4, title="AFKGoo1.0", description=""),
                models.RoadmapMilestone(project_id=demo.id, year=current_year, month=5, title="AFKGoo 1.1", description="Q3 的产品 MRD\n6 月的产品 PRD、原型"),
                models.RoadmapMilestone(project_id=demo.id, year=current_year, month=6, title="Sharaly1.0", description="7 月的产品 PRD、原型"),
                models.RoadmapMilestone(project_id=demo.id, year=current_year, month=7, title="AFKGoo2.0", description="Q4 的产品 MRD\n8 月的产品 PRD、原型"),
                models.RoadmapMilestone(project_id=demo.id, year=current_year, month=8, title="Sharaly1.1", description="9 月的产品 PRD、原型"),
                models.RoadmapMilestone(project_id=demo.id, year=current_year, month=9, title="Sharaly2.0", description="10 月的产品 PRD、原型"),
            ])

        db.commit()
    finally:
        db.close()


seed_initial_data()

# 启动后台调度（DDL 临期扫描等）
try:
    import scheduler
    scheduler.start()
except Exception as exc:  # APScheduler 装载失败不应阻塞 API
    import logging
    logging.getLogger("main").warning("scheduler 启动失败：%s", exc)
