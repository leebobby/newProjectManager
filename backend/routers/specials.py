"""专项 / 攻关管理：
- 元数据（name/kind/owner/...）：admin 增删改
- 单条目的内容/事务/风险/全景图：任意登录用户可写
- 周报草稿：服务端生成草稿文本 + 美化 HTML，前端下载为 .eml（Outlook 可直接打开为草稿）
"""
import email.utils
import html
import json
import pathlib
import re
import uuid
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from html.parser import HTMLParser
from typing import List
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

import enums
import models
import schemas
import special_layout
from auth import get_current_user, require_admin
from database import get_db
from op_log import log_op
from notify import dispatch
from routers import _issue_source
from routers._lookups import fill_user_fk

router = APIRouter(prefix="/api/specials", tags=["specials"])

UPLOAD_ROOT = pathlib.Path(__file__).resolve().parent.parent / "uploads" / "specials"


def _kind_label(kind: str) -> str:
    return "攻关" if kind == "assault" else "专项"


def _ensure_dir(p: pathlib.Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _get_or_404(db: Session, sid: int) -> models.Special:
    item = db.query(models.Special).filter(models.Special.id == sid).first()
    if not item:
        raise HTTPException(404, "专项不存在")
    return item


def _notify_special_change(db: Session, special: models.Special, *, summary: str, actor) -> None:
    """给订阅了该专项/攻关的人发通知（订阅 source_type='special'）。"""
    dispatch(
        db, kind="status_change",
        title=f"{_kind_label(special.kind)}更新：{special.name or ''}",
        body=summary, link=f"/specials/{special.id}",
        source_type="special", source_id=special.id,
        actor=actor, recipient_ids=[], extra_subs=True,
    )


# 会被前端 v-html 直接渲染的富文本字段，写库前一律清洗
_RICH_FIELDS = ("goal", "progress_summary", "help_request", "content", "progress")


def _sanitize_rich_fields(data: dict) -> None:
    """就地清洗 data 里的富文本字段（只动传上来的键）。

    这些字段的 HTML 是前端 contenteditable 直接产出、页面又用 v-html 渲染的。
    以前只在导出周报时清洗——那只保护了收件人，页面本身仍是任何登录用户都能
    往别人的专项里存一段脚本。清洗放在**入口**，出口的清洗保持不变（老数据还没洗过）。
    """
    for k in _RICH_FIELDS:
        if isinstance(data.get(k), str):
            data[k] = _sanitize_rich(data[k])


def _sanitize_blocks_json(raw):
    """保存自定义分段前清洗文本框里的 HTML。

    文本框的 html 是前端 contenteditable 直接产出的，页面用 v-html 渲染——
    不在**服务端**过滤，等于让任何登录用户往别人的专项详情页里存一段脚本。
    只动 kind=text 的 html 字段，其余结构原样保留；解析不了的串原样退回，
    交给下游的容错解析（special_layout.loads）处理，不在这里 500。
    """
    if not raw:
        return raw
    try:
        blocks = json.loads(raw)
    except (ValueError, TypeError):
        return raw
    if not isinstance(blocks, list):
        return raw
    changed = False
    for b in blocks:
        if isinstance(b, dict) and b.get("kind") == "text" and b.get("html"):
            clean = _sanitize_rich(str(b["html"]))
            if clean != b["html"]:
                b["html"] = clean
                changed = True
    return json.dumps(blocks, ensure_ascii=False) if changed else raw


def _ensure_content(db: Session, special: models.Special) -> models.SpecialContent:
    if special.content:
        return special.content
    c = models.SpecialContent(special_id=special.id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# ─── 编辑锁 ────────────────────────────────────────────────────────
# 同一专项同一时刻只允许一人处于编辑模式：前端进入编辑时取锁，
# 每隔一段时间心跳续期；超过 TTL 未续期即视为失效（可被他人/管理员接管）。

LOCK_TTL_SECONDS = 180


def _is_admin(user: models.User) -> bool:
    return getattr(user, "role", "") == "admin"


def _user_display(user: models.User) -> str:
    return (getattr(user, "full_name", "") or user.username or "").strip()


def _active_lock(db: Session, sid: int):
    """返回未过期的锁；过期或不存在返回 None（过期的旧行保留，按时间判定）。"""
    lock = db.query(models.SpecialEditLock).filter(
        models.SpecialEditLock.special_id == sid
    ).first()
    if not lock:
        return None
    if (datetime.utcnow() - (lock.heartbeat_at or lock.acquired_at)) > timedelta(seconds=LOCK_TTL_SECONDS):
        return None
    return lock


def _lock_out(lock, current_user: models.User) -> schemas.SpecialLockOut:
    if not lock:
        return schemas.SpecialLockOut(locked=False, mine=False, ttl=LOCK_TTL_SECONDS)
    return schemas.SpecialLockOut(
        locked=True, mine=(lock.user_id == current_user.id),
        by=lock.user_name, by_user_id=lock.user_id,
        since=lock.acquired_at, ttl=LOCK_TTL_SECONDS,
    )


def _require_not_locked_by_other(db: Session, sid: int, user: models.User) -> None:
    """写操作前置校验：若有他人持新鲜锁，拒绝（423）。无锁则放行（向后兼容）。"""
    lock = _active_lock(db, sid)
    if lock and lock.user_id != user.id:
        raise HTTPException(423, f"{lock.user_name or '他人'}正在编辑该{_kind_label_by_sid(db, sid)}，暂时无法保存，请稍后再试")


def _kind_label_by_sid(db: Session, sid: int) -> str:
    s = db.query(models.Special.kind).filter(models.Special.id == sid).first()
    return _kind_label(s[0] if s else "special")


@router.get("/{sid}/lock", response_model=schemas.SpecialLockOut)
def get_lock(sid: int, db: Session = Depends(get_db),
             current_user: models.User = Depends(get_current_user)):
    _get_or_404(db, sid)
    return _lock_out(_active_lock(db, sid), current_user)


@router.post("/{sid}/lock", response_model=schemas.SpecialLockOut)
def acquire_lock(
    sid: int,
    request: Request,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """取锁 / 续期（心跳）。
    - 无锁或锁已过期：直接占有；
    - 自己持锁：刷新心跳；
    - 他人持新鲜锁：默认不授予（返回 mine=False 的当前持锁人）；管理员可 force=true 强制接管。
    """
    _get_or_404(db, sid)
    lock = db.query(models.SpecialEditLock).filter(
        models.SpecialEditLock.special_id == sid
    ).first()
    active = _active_lock(db, sid)
    now = datetime.utcnow()

    if active and active.user_id != current_user.id:
        if not (force and _is_admin(current_user)):
            return _lock_out(active, current_user)  # 未授予：返回当前持锁人
        # 管理员强制接管
        log_op(db, action="强制接管编辑锁", target=_kind_label_by_sid(db, sid), target_id=sid,
               detail=f"原持锁人={active.user_name}", user=current_user, request=request)

    name = _user_display(current_user)
    if lock is None:
        lock = models.SpecialEditLock(
            special_id=sid, user_id=current_user.id, user_name=name,
            acquired_at=now, heartbeat_at=now,
        )
        db.add(lock)
    else:
        if lock.user_id != current_user.id:
            lock.user_id = current_user.id
            lock.user_name = name
            lock.acquired_at = now
        lock.heartbeat_at = now
    db.commit()
    db.refresh(lock)
    return _lock_out(lock, current_user)


@router.delete("/{sid}/lock", response_model=schemas.SpecialLockOut)
def release_lock(sid: int, db: Session = Depends(get_db),
                 current_user: models.User = Depends(get_current_user)):
    """释放锁：仅持锁人本人或管理员可释放。"""
    _get_or_404(db, sid)
    lock = db.query(models.SpecialEditLock).filter(
        models.SpecialEditLock.special_id == sid
    ).first()
    if lock and (lock.user_id == current_user.id or _is_admin(current_user)):
        db.delete(lock)
        db.commit()
    return schemas.SpecialLockOut(locked=False, mine=False, ttl=LOCK_TTL_SECONDS)


# ─── Specials list ─────────────────────────────────────────────────

@router.get("", response_model=List[schemas.SpecialOut])
def list_specials(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(models.Special)
    if not include_inactive:
        q = q.filter(models.Special.is_active.is_(True))
    return q.order_by(models.Special.sort_order, models.Special.id).all()


# ─── 专项总览 ──────────────────────────────────────────────────────────────
# 一张跨专项的横表：一个专项一行，七列全部从各专项自己的字段推出来。
# **「自动提取」是这张表存在的理由**——总览不该是第八个要人填的地方，
# 填在详情页里的东西应该自己长到这儿来。所以除了点灯可以手工覆盖，
# 其余六列在总览上都是只读的，一处录入入口都没有。


def _auto_light(risks: List[models.SpecialRisk], today=None):
    """按「风险和问题」分段推这个专项的灯，返回 (light, reason, open_n, overdue_n)。

    只看一处数据源——risks 表里的行：

        gray    一条风险行都没登记 → **未评估**，不是绿（见 enums 里的说明）
        green   登记过，但全部已闭环
        yellow  有未闭环的，但都还没过计划闭环时间
        red     有未闭环的，且至少一条**已过**计划闭环时间

    「超过」才算，当天到期不算——记成超期会让人白紧张一天（与
    `_issue_source.is_overdue()` 同口径，日期解析直接共用 `parse_plan_date`，
    两处各写一份的表现是同一个日期在两个页面上一个算超期一个不算）。

    没填计划闭环时间的未闭环行**只顶到黄、不顶红**：那是「没排期」，
    不是「排了没做到」。混成一档会让一批从来不填日期的专项长期挂红，
    而红灯一多就没人看了，真红的那个反而淹掉。

    刻意**不掺里程碑延期**：延期的里程碑确实是风险信号，但掺进来这盏灯就
    再也说不清出处——页面写着红，风险表里一条超期都没有，没人查得动。
    真要让里程碑影响这盏灯，正确做法是去风险表里登一行。
    """
    today = today or date.today()
    if not risks:
        return enums.SPECIAL_OVERVIEW_LIGHT_AUTO, "还没登记过风险行，算不出来", 0, 0
    open_rows = [r for r in risks if (r.status or "open") == "open"]
    if not open_rows:
        return "green", f"{len(risks)} 条风险全部已闭环", 0, 0
    overdue = [r for r in open_rows
               if (d := _issue_source.parse_plan_date(r.planned_close_date))
               and d < today]
    if overdue:
        return ("red",
                f"{len(open_rows)} 条未闭环，其中 {len(overdue)} 条已过计划闭环时间",
                len(open_rows), len(overdue))
    return "yellow", f"{len(open_rows)} 条未闭环，均未到计划闭环时间", len(open_rows), 0


def _overview_risk(r: models.SpecialRisk, today) -> schemas.SpecialOverviewRisk:
    d = _issue_source.parse_plan_date(r.planned_close_date)
    return schemas.SpecialOverviewRisk(
        id=r.id,
        content=_strip_html(r.content or ""),
        progress=_strip_html(r.progress or ""),
        owner=r.owner or "",
        planned_close_date=r.planned_close_date or "",
        overdue=bool(d and d < today),
    )


def _overview_row(seq: int, sp: models.Special, today) -> schemas.SpecialOverviewRow:
    content = sp.content
    risks = list(sp.risks or [])
    auto, reason, open_n, overdue_n = _auto_light(risks, today)
    manual = enums.norm_special_light(getattr(content, "overview_light", "") or "")
    # 未闭环的排前面，其中超期的又排前面：一格里放不下几条，先露出来的
    # 得是最该看的那几条（同 pptx_utils 的 clip_cols——截断可以，但要截对头）
    open_rows = [r for r in risks if (r.status or "open") == "open"]
    cells = sorted((_overview_risk(r, today) for r in open_rows),
                   key=lambda x: (not x.overdue,))
    return schemas.SpecialOverviewRow(
        seq=seq, id=sp.id, name=sp.name, kind=sp.kind or "special",
        kind_label=_kind_label(sp.kind), owner=sp.owner or "",
        goal=_strip_html(getattr(content, "goal", "") or ""),
        progress=_strip_html(getattr(content, "progress_summary", "") or ""),
        risks=cells,
        light=manual or auto, light_auto=auto, light_manual=manual,
        light_reason=reason,
        risk_total=len(risks), risk_open=open_n, risk_overdue=overdue_n,
        version=int(getattr(content, "version", 0) or 0),
    )


# 必须排在 GET /{sid} **前面**：注册在后的话 "overview" 会被当成 sid 去解析，
# 表现是这个接口稳定返回 422（同 iteration_requirements 的 /duplicates）。
@router.get("/overview", response_model=List[schemas.SpecialOverviewRow])
def overview(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    """专项总览：各专项的目标 / 风险点灯 / 关键进展 / 关键风险和措施 / 责任人。

    顺序与侧栏一致（sort_order, id）——总览与菜单对不上，人就得在两边来回找。
    停用的专项默认不出现（同侧栏），要看得勾 include_inactive；
    页面上把这个开关摆出来，免得"少了一个专项"没人说得清是被谁滤掉的。
    """
    q = db.query(models.Special)
    if not include_inactive:
        q = q.filter(models.Special.is_active.is_(True))
    rows = q.order_by(models.Special.sort_order, models.Special.id).all()
    today = date.today()
    return [_overview_row(i, sp, today) for i, sp in enumerate(rows, 1)]


# 同 `/overview`：**必须排在 `GET /{sid}` 前面**，否则 "overview.pptx"
# 会被当成 sid 去解析，接口稳定 422。
@router.get("/overview.pptx")
def export_overview_pptx(
    request: Request,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """专项总览导出 PPT（登录用户可导，与页面同一档读权限）。

    **导出的行直接复用 `overview()` 的结果**，不在这儿另算一遍：
    点灯与风险筛选各写一份的表现是"页面是黄的、PPT 里是红的"，而两边看着都对。
    """
    from pptx_utils import build_special_overview_pptx

    rows = overview(include_inactive=include_inactive, db=db)
    stream = build_special_overview_pptx(rows)
    filename = f"special-overview-{datetime.now().strftime('%Y%m%d-%H%M%S')}.pptx"
    log_op(db, action="导出PPT", target="专项总览",
           detail=f"rows={len(rows)}", user=current_user, request=request)
    return StreamingResponse(
        stream,
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".presentationml.presentation"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("", response_model=schemas.SpecialOut)
def create_special(
    payload: schemas.SpecialCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    data = payload.model_dump()
    # template_id 不是 Special 的列，取出来单独用（建完后套版式）
    template_id = data.pop("template_id", None)
    if data.get("kind") not in ("special", "assault"):
        data["kind"] = "special"
    fill_user_fk(db, data, "owner", "owner_user_id")
    item = models.Special(**data)
    db.add(item)
    db.commit()
    db.refresh(item)
    # 创建对应的空 content
    content = models.SpecialContent(special_id=item.id)
    db.add(content)
    db.commit()
    tpl_note = ""
    if template_id:
        tpl = db.query(models.SpecialTemplate).filter(
            models.SpecialTemplate.id == template_id).first()
        if not tpl:
            raise HTTPException(400, "指定的模板不存在")
        special_layout.apply_template(content, tpl)
        content.version += 1
        db.commit()
        tpl_note = f" template={tpl.name}"
    log_op(db, action="新增", target=_kind_label(item.kind), target_id=item.id,
           detail=f"name={item.name}{tpl_note}",
           user=current_admin, request=request)
    return item


@router.put("/{sid}", response_model=schemas.SpecialOut)
def update_special(
    sid: int,
    payload: schemas.SpecialUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = _get_or_404(db, sid)
    data = payload.model_dump(exclude_unset=True)
    if "kind" in data and data["kind"] not in ("special", "assault"):
        raise HTTPException(400, "kind 仅支持 special / assault")
    fill_user_fk(db, data, "owner", "owner_user_id")
    for k, v in data.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target=_kind_label(item.kind), target_id=item.id,
           detail=f"name={item.name} fields={','.join(data.keys()) or '无'}",
           user=current_admin, request=request)
    if data:
        _notify_special_change(db, item, summary=f"变更字段：{'、'.join(data.keys())}", actor=current_admin)
    return item


@router.delete("/{sid}")
def delete_special(
    sid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    item = _get_or_404(db, sid)
    snapshot = f"name={item.name}"
    label = _kind_label(item.kind)
    # 清理全景图文件
    if item.content and item.content.panorama_image_path:
        try:
            p = (UPLOAD_ROOT.parent / item.content.panorama_image_path).resolve()
            if p.exists():
                p.unlink()
        except OSError:
            pass
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target=label, target_id=sid,
           detail=snapshot, user=current_admin, request=request)
    return {"ok": True}


# ─── 详情 ──────────────────────────────────────────────────────────


@router.get("/{sid}", response_model=schemas.SpecialDetailOut)
def get_one(sid: int, db: Session = Depends(get_db)):
    item = _get_or_404(db, sid)
    _ensure_content(db, item)
    return item


@router.put("/{sid}/content", response_model=schemas.SpecialContentOut)
def update_content(
    sid: int,
    payload: schemas.SpecialContentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    special = _get_or_404(db, sid)
    _require_not_locked_by_other(db, sid, current_user)
    content = _ensure_content(db, special)
    if content.version != payload.version:
        raise HTTPException(409, "数据已被他人修改，请刷新后重试")
    data = payload.model_dump(exclude_unset=True)
    data.pop("version", None)
    _sanitize_rich_fields(data)
    if "extra_grids_json" in data:
        data["extra_grids_json"] = _sanitize_blocks_json(data["extra_grids_json"])
    for k, v in data.items():
        setattr(content, k, v)
    content.version += 1
    db.commit()
    db.refresh(content)
    log_op(db, action="修改", target=f"{_kind_label(special.kind)}内容", target_id=sid,
           detail=f"name={special.name} fields={','.join(data.keys()) or '无'}",
           user=current_user, request=request)
    if data:
        _notify_special_change(db, special, summary=f"内容更新：{'、'.join(data.keys())}", actor=current_user)
    return content


@router.put("/{sid}/overview", response_model=schemas.SpecialOverviewRow)
def update_overview_light(
    sid: int,
    payload: schemas.SpecialOverviewLightUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """改某个专项的总览点灯（登录用户可写）。传空串＝清掉覆盖，回到自动。

    权限落「登录用户」而不是 admin：这是协作编辑域的日常填报——每周看总览的
    人就是该拨这盏灯的人，要 admin 代拨的话灯会一直停在上上周。
    并发同 `PUT /content`：共用 content.version 这一个乐观锁（本来就是同一行），
    他人正持编辑锁时返回 423。
    """
    special = _get_or_404(db, sid)
    _require_not_locked_by_other(db, sid, current_user)
    content = _ensure_content(db, special)
    if content.version != payload.version:
        raise HTTPException(409, "数据已被他人修改，请刷新后重试")
    try:
        light = enums.norm_special_light(payload.light)
    except ValueError as e:
        raise HTTPException(400, str(e))
    content.overview_light = light
    content.version += 1
    db.commit()
    db.refresh(special)
    log_op(db, action="修改", target=f"{_kind_label(special.kind)}总览点灯", target_id=sid,
           detail=f"name={special.name} light={light or '自动'}",
           user=current_user, request=request)
    return _overview_row(0, special, date.today())


@router.post("/{sid}/apply-template", response_model=schemas.SpecialContentOut)
def apply_template(
    sid: int,
    payload: schemas.SpecialApplyTemplate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    """给已存在的专项套一份版式模板（仅 admin）。

    权限落「仅 admin」：改的是整页版式，对所有看这个专项的人生效，
    与「分段改名/停用/排序」（登录用户可做，走 PUT /content）不是一档。
    套用是**只增不删**的——已填的分段与数据一律保留，详见 special_layout.apply_template。
    """
    special = _get_or_404(db, sid)
    _require_not_locked_by_other(db, sid, current_admin)
    content = _ensure_content(db, special)
    if content.version != payload.version:
        raise HTTPException(409, "数据已被他人修改，请刷新后重试")
    tpl = db.query(models.SpecialTemplate).filter(
        models.SpecialTemplate.id == payload.template_id).first()
    if not tpl:
        raise HTTPException(404, "模板不存在")

    stat = special_layout.apply_template(content, tpl)
    content.version += 1
    db.commit()
    db.refresh(content)
    log_op(db, action="修改", target=f"{_kind_label(special.kind)}版式", target_id=sid,
           detail=f"name={special.name} template={tpl.name} "
                  f"added={stat['added']} reused={stat['reused']}",
           user=current_admin, request=request)
    _notify_special_change(db, special, summary=f"版式已套用模板「{tpl.name}」",
                           actor=current_admin)
    return content


# ─── 全景图上传/下载 ────────────────────────────────────────────────

_PANORAMA_OK_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}


@router.post("/{sid}/panorama", response_model=schemas.SpecialContentOut)
def upload_panorama(
    sid: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ct = (file.content_type or "").lower()
    ext = pathlib.Path(file.filename or "").suffix.lower()
    is_image = ct.startswith("image/") or ct == "image/svg+xml"
    if not (is_image or ext in _PANORAMA_OK_EXT):
        raise HTTPException(400, "仅支持图片或 SVG 文件")
    special = _get_or_404(db, sid)
    _require_not_locked_by_other(db, sid, current_user)
    content = _ensure_content(db, special)

    # 写入新文件
    sub = UPLOAD_ROOT / str(sid)
    _ensure_dir(sub)
    orig_name = file.filename or "panorama.png"
    safe_ext = pathlib.Path(orig_name).suffix[:16] or ".png"
    stored = f"{uuid.uuid4().hex}{safe_ext}"
    full = sub / stored
    with open(full, "wb") as f:
        while True:
            chunk = file.file.read(64 * 1024)
            if not chunk:
                break
            f.write(chunk)

    # 删旧
    if content.panorama_image_path:
        try:
            old = (UPLOAD_ROOT.parent / content.panorama_image_path).resolve()
            if old.exists() and old != full.resolve():
                old.unlink()
        except OSError:
            pass

    content.panorama_image_path = f"specials/{sid}/{stored}"
    content.panorama_image_name = orig_name
    content.version += 1
    db.commit()
    db.refresh(content)
    log_op(db, action="修改", target=f"{_kind_label(special.kind)}全景图", target_id=sid,
           detail=f"name={special.name} file={orig_name}",
           user=current_user, request=request)
    return content


@router.get("/{sid}/panorama")
def get_panorama(sid: int, db: Session = Depends(get_db)):
    special = _get_or_404(db, sid)
    if not special.content or not special.content.panorama_image_path:
        raise HTTPException(404, "全景图未上传")
    p = (UPLOAD_ROOT.parent / special.content.panorama_image_path).resolve()
    if not p.exists():
        raise HTTPException(404, "全景图文件已丢失")
    return FileResponse(str(p))


# ─── 分段图片（图片分段可挂多张；文件在磁盘，引用存 extra_grids_json 里的 images 块）──
# 存储名 = uuid hex + 扩展名，服务端生成，正则校验后才拼路径，杜绝目录穿越。
_BLOCK_IMG_NAME_RE = re.compile(r"^[0-9a-f]{32}\.[A-Za-z0-9]{1,15}$")


@router.post("/{sid}/images")
def upload_block_image(
    sid: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """上传一张分段图片，返回 {file, name}；引用由前端随 extra_grids_json 一起保存。"""
    ct = (file.content_type or "").lower()
    ext = pathlib.Path(file.filename or "").suffix.lower()
    if not (ct.startswith("image/") or ext in _PANORAMA_OK_EXT):
        raise HTTPException(400, "仅支持图片文件")
    special = _get_or_404(db, sid)
    _require_not_locked_by_other(db, sid, current_user)

    sub = UPLOAD_ROOT / str(sid)
    _ensure_dir(sub)
    orig_name = file.filename or "image.png"
    safe_ext = (pathlib.Path(orig_name).suffix[:16] or ".png").lower()
    stored = f"{uuid.uuid4().hex}{safe_ext}"
    with open(sub / stored, "wb") as f:
        while True:
            chunk = file.file.read(64 * 1024)
            if not chunk:
                break
            f.write(chunk)

    log_op(db, action="上传", target=f"{_kind_label(special.kind)}分段图片", target_id=sid,
           detail=f"name={special.name} file={orig_name}",
           user=current_user, request=request)
    return {"file": stored, "name": orig_name}


@router.get("/{sid}/images/{stored}")
def get_block_image(sid: int, stored: str, db: Session = Depends(get_db)):
    _get_or_404(db, sid)
    if not _BLOCK_IMG_NAME_RE.match(stored):
        raise HTTPException(400, "非法文件名")
    p = (UPLOAD_ROOT / str(sid) / stored).resolve()
    if not p.exists():
        raise HTTPException(404, "图片不存在")
    return FileResponse(str(p))


@router.delete("/{sid}/images/{stored}")
def delete_block_image(
    sid: int,
    stored: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """删除磁盘文件（尽力而为）；JSON 引用由前端随保存移除。文件不存在也返回 ok。"""
    special = _get_or_404(db, sid)
    _require_not_locked_by_other(db, sid, current_user)
    if not _BLOCK_IMG_NAME_RE.match(stored):
        raise HTTPException(400, "非法文件名")
    # 全景图与分段图片同目录：别把当前全景图误删了
    if special.content and (special.content.panorama_image_path or "").endswith("/" + stored):
        raise HTTPException(400, "该文件是当前全景图，请在全景图分段中替换")
    p = (UPLOAD_ROOT / str(sid) / stored).resolve()
    try:
        if p.exists():
            p.unlink()
    except OSError:
        pass
    return {"ok": True}


# ─── 事务 / 风险 (合并实现) ─────────────────────────────────────────

def _item_model(kind: str):
    return models.SpecialTask if kind == "task" else models.SpecialRisk


def _action_target(kind: str) -> str:
    return "专项事务" if kind == "task" else "风险问题"


@router.get("/{sid}/tasks", response_model=List[schemas.SpecialItemOut])
def list_tasks(sid: int, db: Session = Depends(get_db)):
    _get_or_404(db, sid)
    return (
        db.query(models.SpecialTask)
        .filter(models.SpecialTask.special_id == sid)
        .order_by(models.SpecialTask.sort_order, models.SpecialTask.id)
        .all()
    )


@router.get("/{sid}/risks", response_model=List[schemas.SpecialItemOut])
def list_risks(sid: int, db: Session = Depends(get_db)):
    _get_or_404(db, sid)
    return (
        db.query(models.SpecialRisk)
        .filter(models.SpecialRisk.special_id == sid)
        .order_by(models.SpecialRisk.sort_order, models.SpecialRisk.id)
        .all()
    )


def _create_item(
    kind: str,
    sid: int,
    payload: schemas.SpecialItemBase,
    db: Session,
    user: models.User,
    request: Request,
):
    special = _get_or_404(db, sid)
    _require_not_locked_by_other(db, sid, user)
    Model = _item_model(kind)
    data = payload.model_dump(exclude_unset=True)
    _sanitize_rich_fields(data)
    if not data.get("seq"):
        cnt = db.query(Model).filter(Model.special_id == sid).count()
        data["seq"] = cnt + 1
    if not data.get("sort_order"):
        data["sort_order"] = data["seq"]
    fill_user_fk(db, data, "owner", "owner_user_id")
    item = Model(special_id=sid, **data)
    db.add(item)
    db.commit()
    db.refresh(item)
    log_op(db, action="新增", target=_action_target(kind), target_id=item.id,
           detail=f"special_id={sid} content={(item.content or '')[:60]}",
           user=user, request=request)
    _notify_special_change(
        db, special,
        summary=f"新增{_action_target(kind)}：{_strip_html(item.content or '')[:60]}",
        actor=user,
    )
    return item


def _update_item(
    kind: str,
    item_id: int,
    payload: schemas.SpecialItemUpdate,
    db: Session,
    user: models.User,
    request: Request,
):
    Model = _item_model(kind)
    item = db.query(Model).filter(Model.id == item_id).first()
    if not item:
        raise HTTPException(404, "条目不存在")
    _require_not_locked_by_other(db, item.special_id, user)
    data = payload.model_dump(exclude_unset=True)
    _sanitize_rich_fields(data)
    fill_user_fk(db, data, "owner", "owner_user_id")
    for k, v in data.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    log_op(db, action="修改", target=_action_target(kind), target_id=item.id,
           detail=f"special_id={item.special_id} fields={','.join(data.keys()) or '无'}",
           user=user, request=request)
    if data:
        special = db.query(models.Special).filter(models.Special.id == item.special_id).first()
        if special:
            _notify_special_change(
                db, special,
                summary=f"{_action_target(kind)}更新：{_strip_html(item.content or '')[:60]}",
                actor=user,
            )
    return item


def _delete_item(
    kind: str,
    item_id: int,
    db: Session,
    user: models.User,
    request: Request,
):
    Model = _item_model(kind)
    item = db.query(Model).filter(Model.id == item_id).first()
    if not item:
        raise HTTPException(404, "条目不存在")
    _require_not_locked_by_other(db, item.special_id, user)
    snapshot = f"special_id={item.special_id} content={(item.content or '')[:60]}"
    db.delete(item)
    db.commit()
    log_op(db, action="删除", target=_action_target(kind), target_id=item_id,
           detail=snapshot, user=user, request=request)
    return {"ok": True}


@router.post("/{sid}/tasks", response_model=schemas.SpecialItemOut)
def create_task(
    sid: int,
    payload: schemas.SpecialItemBase,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _create_item("task", sid, payload, db, current_user, request)


@router.put("/tasks/{item_id}", response_model=schemas.SpecialItemOut)
def update_task(
    item_id: int,
    payload: schemas.SpecialItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _update_item("task", item_id, payload, db, current_user, request)


@router.delete("/tasks/{item_id}")
def delete_task(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _delete_item("task", item_id, db, current_user, request)


@router.post("/{sid}/risks", response_model=schemas.SpecialItemOut)
def create_risk(
    sid: int,
    payload: schemas.SpecialItemBase,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _create_item("risk", sid, payload, db, current_user, request)


@router.put("/risks/{item_id}", response_model=schemas.SpecialItemOut)
def update_risk(
    item_id: int,
    payload: schemas.SpecialItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _update_item("risk", item_id, payload, db, current_user, request)


@router.delete("/risks/{item_id}")
def delete_risk(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _delete_item("risk", item_id, db, current_user, request)


# ─── 富文本辅助 ────────────────────────────────────────────────────
# 富文本字段（goal / progress_summary / task.content / task.progress / risk.*）
# 可能包含来自前端富文本编辑器的 HTML（b/strong/span style 等）。
# 为防 XSS，邮件 HTML 输出前用白名单过滤；纯文本输出前剥掉标签。

# ul/ol/li：富文本编辑器的列表按钮产出的结构。不在白名单里的后果不是报错，
# 而是周报 HTML 里项目符号被静默抹平成一段连排文字
_ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "s", "span", "br", "div", "p", "font",
                 "ul", "ol", "li"}
_VOID_TAGS = {"br"}
_ALLOWED_STYLE_PROPS = {
    "color", "background-color", "font-size", "font-weight",
    "font-style", "text-decoration", "font-family", "text-align",
}
_ALLOWED_FONT_ATTRS = {"color", "size"}


# 标签被丢掉时，**内容也要一起丢**的元素。其余标签只丢标签、留文字
# （<b>粗</b> → 粗），但 script/style 的"文字"是代码：转义后虽不会执行，
# 却会原样显示成一段 alert(1)，看着就像页面出了故障
_DROP_CONTENT_TAGS = {"script", "style"}


class _RichSanitizer(HTMLParser):
    """白名单 HTML 清洗，移除 script / on* / 不在白名单内的标签和样式。"""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out: List[str] = []
        self._drop_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _DROP_CONTENT_TAGS:
            self._drop_depth += 1
            return
        if tag not in _ALLOWED_TAGS:
            return
        kept = self._filter_attrs(tag, attrs)
        attr_str = "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in kept)
        self.out.append(f"<{tag}{attr_str}>")

    def handle_endtag(self, tag):
        if tag in _DROP_CONTENT_TAGS:
            self._drop_depth = max(0, self._drop_depth - 1)
            return
        if tag in _ALLOWED_TAGS and tag not in _VOID_TAGS:
            self.out.append(f"</{tag}>")

    def handle_startendtag(self, tag, attrs):
        if tag == "br":
            self.out.append("<br>")
        elif tag in _ALLOWED_TAGS:
            kept = self._filter_attrs(tag, attrs)
            attr_str = "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in kept)
            self.out.append(f"<{tag}{attr_str}/>")

    def handle_data(self, data):
        if self._drop_depth:
            return
        self.out.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        if self._drop_depth:
            return
        self.out.append(f"&{name};")

    def handle_charref(self, name):
        if self._drop_depth:
            return
        self.out.append(f"&#{name};")

    def _filter_attrs(self, tag, attrs):
        kept = []
        for k, v in attrs:
            v = v or ""
            kl = k.lower()
            if kl.startswith("on"):
                continue
            if kl == "style":
                clean = self._sanitize_style(v)
                if clean:
                    kept.append(("style", clean))
            elif tag == "font" and kl in _ALLOWED_FONT_ATTRS:
                if any(ch in v for ch in "<>\"'"):
                    continue
                kept.append((kl, v))
        return kept

    @staticmethod
    def _sanitize_style(style: str) -> str:
        parts = []
        for chunk in style.split(";"):
            if ":" not in chunk:
                continue
            prop, val = chunk.split(":", 1)
            prop = prop.strip().lower()
            val = val.strip()
            if prop not in _ALLOWED_STYLE_PROPS:
                continue
            low = val.lower()
            if "expression(" in low or "javascript:" in low or "url(" in low:
                continue
            if any(ch in val for ch in "<>\""):
                continue
            parts.append(f"{prop}: {val}")
        return "; ".join(parts)


def _sanitize_rich(s: str) -> str:
    if not s:
        return ""
    p = _RichSanitizer()
    p.feed(s)
    p.close()
    return "".join(p.out)


def _looks_like_html(s: str) -> bool:
    return bool(s) and bool(re.search(r"<[a-zA-Z!/][^>]*>", s))


def _rich_to_html(s: str) -> str:
    """供邮件 HTML 部分使用：富文本直接清洗；纯文本则转义并 \\n→<br>。"""
    if not s:
        return ""
    if _looks_like_html(s):
        return _sanitize_rich(s)
    return html.escape(s, quote=False).replace("\n", "<br>")


def _strip_html(s: str) -> str:
    """剥掉 HTML 转为纯文本，用于 .eml 的 text/plain 部分与服务端 draft body。"""
    if not s:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    text = re.sub(r"</\s*(p|div|h\d|li|tr)\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ─── 周报草稿 ──────────────────────────────────────────────────────

_MS_STATUS_LABEL = {
    "planning": "未开始", "in_progress": "进行中",
    "done": "已完成", "delayed": "已延期",
}


# ─── 周报 / 导出：一律按「版式」走 ─────────────────────────────────
# 章节标题、顺序、有没有这一段，全部来自 special_layout.resolve_sections()。
# 以前这里写死「一、目标 / 二、整体进展 / …」，自定义分段完全不进周报；
# 分段可改名可停用之后，写死的编号和标题必然和页面对不上。

_CN_DIGITS = "零一二三四五六七八九"


def _cn_index(n: int) -> str:
    """1→一、10→十、11→十一、21→二十一。分段数不会多到需要更复杂的规则。"""
    if n <= 0:
        return str(n)
    if n < 10:
        return _CN_DIGITS[n]
    if n < 20:
        return "十" + (_CN_DIGITS[n - 10] if n > 10 else "")
    tens, ones = divmod(n, 10)
    return _CN_DIGITS[tens] + "十" + (_CN_DIGITS[ones] if ones else "")


# 内置文本类分段 -> content 上的列
_TEXT_FIELD = {"goal": "goal", "progress": "progress_summary", "help": "help_request"}


def _cell_text(c) -> str:
    """RichGrid 单元格（{text,...} 或裸字符串）→ 纯文本。"""
    if isinstance(c, dict):
        return _strip_html(str(c.get("text") or ""))
    return _strip_html(str(c or ""))


def _grid_matrix(block: dict):
    """自定义表格分段 → (表头名, 文本化数据行)。

    colspan 展开成同名的多列——邮件/纯文本里没有合并单元格的表达力，
    与其丢掉表头层级不如让跨列表头在每列重复出现。
    模板预留的整行空白丢掉：空行进汇报只是噪音。
    """
    headers: List[str] = []
    for h in (block.get("headers") or []):
        if isinstance(h, dict):
            headers.extend([str(h.get("text") or "")] * max(1, int(h.get("colspan") or 1)))
        else:
            headers.append(str(h or ""))
    rows = [[_cell_text(c) for c in (r or [])] for r in (block.get("rows") or [])]
    return headers, [r for r in rows if any(x.strip() for x in r)]


def _milestones_of(content) -> list:
    return [m for m in special_layout.loads(getattr(content, "milestones_json", None), [])
            if isinstance(m, dict)]


def _block_milestones(block: dict) -> list:
    """自定义里程碑分段的节点列表。

    与内置「计划」分段读的是不同地方（块自带的 milestones 字段 vs
    content.milestones_json），但**往下的渲染必须共用**：一份专项里两种里程碑
    并存时，周报里长得不一样是没人能解释的。
    """
    return [m for m in (block.get("milestones") or []) if isinstance(m, dict)]


def _milestone_lines(milestones: list) -> List[str]:
    """里程碑 → 纯文本周报的正文行（内置计划与自定义里程碑分段共用）。"""
    out = []
    for m in milestones:
        st = _MS_STATUS_LABEL.get(m.get("status", "planning"), m.get("status", ""))
        day = special_layout.milestone_date_text(m.get("date"))
        out.append(f"  · {m.get('name', '')}  {day}  [{st}]")
    return out


def _formation_of(content):
    obj = special_layout.loads(getattr(content, "formation_json", None), {})
    headers = [str(h) for h in (obj.get("headers") or [])]
    rows = [[_cell_text(c) for c in (r or [])] for r in (obj.get("rows") or [])]
    return headers, [r for r in rows if any(x.strip() for x in r)]


def _section_text(special: models.Special, sec) -> List[str]:
    """一个分段在纯文本周报里的正文行。返回空 = 该段无内容，整段跳过。"""
    content = special.content
    if sec.is_custom:
        if sec.kind == "text":
            body = _strip_html(sec.block.get("html") or "")
            return [body] if body.strip() else []
        if sec.kind == "images":
            n = len([i for i in (sec.block.get("items") or []) if isinstance(i, dict)])
            return [f"  （{n} 张图片，见 HTML 版本）"] if n else []
        if sec.kind == "milestones":
            return _milestone_lines(_block_milestones(sec.block))
        headers, rows = _grid_matrix(sec.block)
        if not rows:
            return []
        out = ["  " + " | ".join(headers)] if any(headers) else []
        return out + ["  " + " | ".join(r) for r in rows]

    if sec.key in _TEXT_FIELD:
        val = getattr(content, _TEXT_FIELD[sec.key], "") if content else ""
        body = _strip_html(val or "")
        return [body] if body.strip() else []

    if sec.key == "plan":
        return _milestone_lines(_milestones_of(content))

    if sec.key == "panorama":
        name = getattr(content, "panorama_image_name", "") if content else ""
        return [f"  （见 HTML 版本：{name}）"] if name else []

    if sec.key == "risks":
        out = []
        for i, r in enumerate(special.risks or [], 1):
            out.append(f"  {i}. {_strip_html(r.content)}")
            if r.progress:
                out.append(f"     当前进展：{_strip_html(r.progress)}")
            meta = []
            if r.owner:
                meta.append(f"责任人：{r.owner}")
            if r.planned_close_date:
                meta.append(f"计划闭环：{r.planned_close_date}")
            if meta:
                out.append("     " + " / ".join(meta))
        return out

    if sec.key == "tasks":
        open_tasks = [t for t in (special.tasks or []) if (t.status or "open") == "open"]
        closed = [t for t in (special.tasks or []) if (t.status or "open") == "closed"]
        out = []
        if open_tasks:
            out.append(f"  ◇ 进行中（{len(open_tasks)} 项）")
            for i, t in enumerate(open_tasks, 1):
                out.append(f"    {i}. {_strip_html(t.content)}")
                if t.progress:
                    out.append(f"       进展：{_strip_html(t.progress)}")
                meta = []
                if t.owner:
                    meta.append(f"责任人：{t.owner}")
                if t.planned_close_date:
                    meta.append(f"计划闭环：{t.planned_close_date}")
                if meta:
                    out.append("       " + " / ".join(meta))
        if closed:
            out.append(f"  ◇ 本期已闭环（{len(closed)} 项）")
            for i, t in enumerate(closed, 1):
                out.append(f"    {i}. {_strip_html(t.content)}")
        return out

    if sec.key == "formation":
        headers, rows = _formation_of(content)
        if not rows:
            return []
        out = ["  " + " | ".join(headers)] if any(headers) else []
        return out + ["  " + " | ".join(r) for r in rows]

    return []


def _render_report_body(special: models.Special) -> str:
    label = _kind_label(special.kind)
    parts: List[str] = [
        f"[{label}名称] {special.name}",
        f"[责任人] {special.owner or '-'}",
        f"[报告日期] {datetime.now().strftime('%Y-%m-%d')}",
        "",
    ]
    n = 0
    for sec in special_layout.resolve_sections(special):
        lines = _section_text(special, sec)
        if not lines:
            continue  # 空段不占编号，避免周报里一串「三、（无）」
        n += 1
        parts.append(f"{_cn_index(n)}、{sec.title}")
        parts.extend(lines)
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def _render_subject(special: models.Special) -> str:
    label = _kind_label(special.kind)
    tpl = (special.email_subject_tpl or "").strip()
    today = datetime.now().strftime("%Y-%m-%d")
    if tpl:
        return (tpl
                .replace("{label}", label)
                .replace("{kind_label}", label)
                .replace("{name}", special.name)
                .replace("{owner}", special.owner or "")
                .replace("{date}", today))
    return f"【{label}周报】{special.name} - {today}"


# ─── HTML 美化版本 ─────────────────────────────────────────────────

_HTML_BASE_CSS = (
    "font-family: 'Microsoft YaHei','PingFang SC',Arial,sans-serif; "
    "font-size: 14px; line-height: 1.65; color: #303133;"
)

_HTML_TABLE_CSS = (
    "border-collapse: collapse; width: 100%; margin: 6px 0 10px 0; "
    "font-size: 13px;"
)
_HTML_TH_CSS = (
    "background: #4073BA; color: #fff; text-align: left; "
    "padding: 6px 10px; border: 1px solid #4073BA;"
)
_HTML_TD_CSS = "padding: 6px 10px; border: 1px solid #dcdfe6; vertical-align: top;"
_HTML_TD_ZEBRA = "padding: 6px 10px; border: 1px solid #dcdfe6; vertical-align: top; background: #f9fbfd;"


def _e(s) -> str:
    """HTML 转义 + 把换行变 <br>。"""
    return html.escape(str(s or ""), quote=False).replace("\n", "<br>")


def _row_td(cells, zebra: bool) -> str:
    css = _HTML_TD_ZEBRA if zebra else _HTML_TD_CSS
    return "<tr>" + "".join(f'<td style="{css}">{_e(c)}</td>' for c in cells) + "</tr>"


def _row_td_raw(cells_html, zebra: bool) -> str:
    """cells_html 中已是安全 HTML（调用方负责清洗）。"""
    css = _HTML_TD_ZEBRA if zebra else _HTML_TD_CSS
    return "<tr>" + "".join(f'<td style="{css}">{c}</td>' for c in cells_html) + "</tr>"


def _build_table(headers: list, rows: list) -> str:
    head = "<tr>" + "".join(f'<th style="{_HTML_TH_CSS}">{_e(h)}</th>' for h in headers) + "</tr>"
    body = "".join(_row_td(r, i % 2 == 1) for i, r in enumerate(rows))
    return f'<table style="{_HTML_TABLE_CSS}">{head}{body}</table>'


def _milestone_table(milestones: list) -> str:
    """里程碑 → HTML 表格（内置计划与自定义里程碑分段共用）。空清单返回空串＝整段跳过。"""
    if not milestones:
        return ""
    rows = [[m.get("name", ""), special_layout.milestone_date_text(m.get("date")),
             _MS_STATUS_LABEL.get(m.get("status", "planning"), m.get("status", ""))]
            for m in milestones]
    return _build_table(["里程碑", "日期", "状态"], rows)


def _build_table_rich(headers: list, rows_html: list) -> str:
    """rows_html 中每个单元格已是安全 HTML，由调用方对富文本字段做清洗。"""
    head = "<tr>" + "".join(f'<th style="{_HTML_TH_CSS}">{_e(h)}</th>' for h in headers) + "</tr>"
    body = "".join(_row_td_raw(r, i % 2 == 1) for i, r in enumerate(rows_html))
    return f'<table style="{_HTML_TABLE_CSS}">{head}{body}</table>'


def _h3(title: str, *, danger: bool = False) -> str:
    color = "#F56C6C" if danger else "#4073BA"
    return (f'<h3 style="color:{color};border-left:4px solid {color};'
            f'padding-left:8px;margin:18px 0 8px;">{_e(title)}</h3>')


# 点灯单元格底色：与前端 RichGrid 的 light 列、关键特性的着色思路一致
_LIGHT_CSS = {
    "red": "background:#FEF0F0;color:#F56C6C;font-weight:600;text-align:center;",
    "yellow": "background:#FDF6EC;color:#E6A23C;font-weight:600;text-align:center;",
    "green": "background:#F0F9EB;color:#67C23A;font-weight:600;text-align:center;",
}


# 单元格颜色只认 #RGB / #RRGGBB：这些值原样拼进 style="…"，
# 不校验就等于把样式属性开放给任意字符串（"red;background:url(...)" 之类）
_SAFE_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _fmt_css(cell: dict, *, default_align: str = "") -> str:
    """单元格自带格式（字体/字号/粗斜下划线/字色/底色/对齐）→ 内联 CSS。

    页面（RichGrid.cellStyle）、周报 HTML、Excel 三处必须同款，
    否则「页面上是宋体加粗，导出来是默认字体」这种问题没人查得动。
    白名单外的值一律丢弃而不是原样输出。
    """
    if not isinstance(cell, dict):
        return f"text-align:{default_align};" if default_align else ""
    parts = []
    align = cell.get("align") or default_align
    if align in ("left", "center", "right"):
        parts.append(f"text-align:{align};")
    color = str(cell.get("color") or "")
    if _SAFE_COLOR_RE.match(color):
        parts.append(f"color:{color};")
    bg = str(cell.get("bg") or "")
    if _SAFE_COLOR_RE.match(bg):
        parts.append(f"background:{bg};")
    if cell.get("bold"):
        parts.append("font-weight:700;")
    if cell.get("italic"):
        parts.append("font-style:italic;")
    if cell.get("underline"):
        parts.append("text-decoration:underline;")
    font = enums.GRID_FONTS.get(str(cell.get("font") or ""))
    if font:
        parts.append(f"font-family:{font['css']};")
    try:
        size = int(cell.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    if size in enums.GRID_FONT_SIZES:
        parts.append(f"font-size:{size}px;")
    return "".join(parts)


def _grid_rich_matrix(block: dict):
    """自定义表格 → (表头 dict 列表, 非空数据行的原始单元格)。

    与 _grid_matrix 的区别只在于**不把单元格压成字符串**：HTML 里要保留
    每格自己的字体与颜色。跨列表头照旧展开成同名多列。
    """
    headers = []
    for h in (block.get("headers") or []):
        if isinstance(h, dict):
            cell = {**h, "text": str(h.get("text") or "")}
            headers.extend([cell] * max(1, int(h.get("colspan") or 1)))
        else:
            headers.append({"text": str(h or "")})
    rows = []
    for r in (block.get("rows") or []):
        cells = [c if isinstance(c, dict) else {"text": str(c or "")} for c in (r or [])]
        if any(_strip_html(str(c.get("text") or "")).strip() for c in cells):
            rows.append(cells)
    return headers, rows


def _grid_html(block: dict) -> str:
    """自定义表格分段 → HTML 表格：单元格格式随行，点灯列按取值着色。"""
    headers, rows = _grid_rich_matrix(block)
    if not rows:
        return ""
    col_types = block.get("colTypes") or []
    head = ""
    if any(h["text"] for h in headers):
        head = "<tr>" + "".join(
            f'<th style="{_HTML_TH_CSS}{_fmt_css(h, default_align="center")}">'
            f'{_e(h["text"])}</th>' for h in headers) + "</tr>"
    body = []
    for i, r in enumerate(rows):
        tds = []
        for j, cell in enumerate(r):
            text = _strip_html(str(cell.get("text") or ""))
            css = (_HTML_TD_ZEBRA if i % 2 else _HTML_TD_CSS) + _fmt_css(cell)
            # 点灯列的着色压过单元格自己的字色/底色：整列口径一致才看得出灯
            if j < len(col_types) and col_types[j] == "light":
                light = enums.GRID_LIGHT_COLORS.get(text.strip())
                if light:
                    css += _LIGHT_CSS[light]
            tds.append(f'<td style="{css}">{_e(text)}</td>')
        body.append("<tr>" + "".join(tds) + "</tr>")
    return f'<table style="{_HTML_TABLE_CSS}">{head}{"".join(body)}</table>'


def _section_html(special: models.Special, sec, images: list) -> str:
    """一个分段的 HTML 正文；返回空串 = 该段无内容。

    images 是出参：需要内嵌的图片附加到这里，由 _build_eml 以 CID 关联，
    否则邮件里的 <img> 指向服务器内网地址，收件人一律看不到。
    """
    content = special.content
    if sec.is_custom:
        if sec.kind == "text":
            inner = _rich_to_html(sec.block.get("html") or "")
            return f"<div>{inner}</div>" if _strip_html(sec.block.get("html") or "").strip() else ""
        if sec.kind == "images":
            parts = []
            for im in (sec.block.get("items") or []):
                if not isinstance(im, dict) or not im.get("file"):
                    continue
                cid = _attach_image(special.id, im["file"], images)
                if cid:
                    width = im.get("width") or 50
                    parts.append(
                        f'<div style="display:inline-block;width:{width}%;'
                        f'vertical-align:top;padding:2px;">'
                        f'<img src="cid:{cid}" style="width:100%;border:1px solid #dcdfe6;" />'
                        f'</div>')
            return "".join(parts)
        if sec.kind == "milestones":
            return _milestone_table(_block_milestones(sec.block))
        return _grid_html(sec.block)

    if sec.key in _TEXT_FIELD:
        val = getattr(content, _TEXT_FIELD[sec.key], "") if content else ""
        if not _strip_html(val or "").strip():
            return ""
        return f"<div>{_rich_to_html(val)}</div>"

    if sec.key == "plan":
        return _milestone_table(_milestones_of(content))

    if sec.key == "panorama":
        path = getattr(content, "panorama_image_path", "") if content else ""
        if not path:
            return ""
        cid = _attach_image(special.id, pathlib.Path(path).name, images)
        if not cid:
            return ""
        return (f'<div><img src="cid:{cid}" '
                f'style="max-width:100%;border:1px solid #dcdfe6;" /></div>')

    if sec.key == "risks":
        risks = special.risks or []
        if not risks:
            return ""
        rows = [[_rich_to_html(r.content), _rich_to_html(r.progress),
                 _e(r.owner or ""), _e(r.planned_close_date or ""),
                 "Open" if (r.status or "open") == "open" else "Closed"]
                for r in risks]
        return _build_table_rich(
            ["问题内容", "当前进展", "责任人", "计划闭环时间", "状态"], rows)

    if sec.key == "tasks":
        open_tasks = [t for t in (special.tasks or []) if (t.status or "open") == "open"]
        closed = [t for t in (special.tasks or []) if (t.status or "open") == "closed"]
        if not (open_tasks or closed):
            return ""
        hdr = ["事务内容", "当前进展", "责任人", "计划闭环时间", "状态"]
        out = []
        for group, tone, note in ((open_tasks, "#E6A23C", "进行中"),
                                  (closed, "#67C23A", "本期已闭环")):
            if not group:
                continue
            rows = [[_rich_to_html(t.content), _rich_to_html(t.progress),
                     _e(t.owner or ""), _e(t.planned_close_date or ""),
                     "Open" if note == "进行中" else "Closed"] for t in group]
            out.append(f'<div style="font-weight:600;margin:6px 0;color:{tone};">'
                       f'◇ {note}（{len(group)} 项）</div>'
                       + _build_table_rich(hdr, rows))
        return "".join(out)

    if sec.key == "formation":
        headers, rows = _formation_of(content)
        if not rows:
            return ""
        return _build_table(headers or [""] * len(rows[0]), rows)

    return ""


def _attach_image(sid: int, stored: str, images: list):
    """把 uploads 里的图片读进内嵌附件清单，返回 cid；读不到返回 None。

    图片不进邮件正文只会让收件人看到裂图，属于「宁可少一段也别出错」的场景，
    所以任何异常都吞掉、当作这张图不存在。
    """
    if not _BLOCK_IMG_NAME_RE.match(stored or ""):
        return None
    path = (UPLOAD_ROOT / str(sid) / stored).resolve()
    try:
        if not path.exists() or UPLOAD_ROOT.resolve() not in path.parents:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) > 8 * 1024 * 1024:
        return None  # 单张过大就不塞进邮件，免得草稿打不开
    subtype = path.suffix.lower().lstrip(".") or "png"
    subtype = {"jpg": "jpeg", "svg": "svg+xml"}.get(subtype, subtype)
    cid = f"img{len(images)}@special"
    images.append({"cid": cid, "data": data, "subtype": subtype})
    return cid


def _render_report_html(special: models.Special):
    """返回 (html, inline_images)：图片以 cid: 引用，附件由调用方挂到邮件上。"""
    label = _kind_label(special.kind)
    today = datetime.now().strftime("%Y-%m-%d")

    images: List[dict] = []
    sections: List[str] = []
    n = 0
    for sec in special_layout.resolve_sections(special):
        inner = _section_html(special, sec, images)
        if not inner:
            continue  # 空段不占编号
        n += 1
        sections.append(_h3(f"{_cn_index(n)}、{sec.title}",
                            danger=(sec.key == "risks"))
                        + inner)

    body_inner = "".join(sections) or '<div style="color:#909399;">（该报告无内容）</div>'

    html_doc = (
        '<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
        f'<body style="{_HTML_BASE_CSS} margin:0;padding:0;background:#f5f7fa;">'
        '<div style="max-width:880px;margin:0 auto;background:#fff;'
        'box-shadow:0 1px 4px rgba(0,0,0,0.06);">'
        # 标题条
        f'<div style="background:linear-gradient(135deg,#4073BA 0%,#2D4A6B 100%);'
        f'color:#fff;padding:18px 24px;">'
        f'<div style="font-size:20px;font-weight:600;">【{_e(label)}周报】{_e(special.name)}</div>'
        f'<div style="margin-top:6px;font-size:13px;opacity:.9;">'
        f'责任人：{_e(special.owner or "-")} &nbsp;|&nbsp; '
        f'报告日期：{today}'
        f'</div></div>'
        # 内容
        f'<div style="padding:8px 24px 24px 24px;">{body_inner}</div>'
        '</div></body></html>'
    )
    return html_doc, images


def _build_eml(special: models.Special, subject: str, to: str, cc: str,
               text_body: str, html_body: str, images=None) -> bytes:
    msg = EmailMessage()
    msg["Subject"] = subject or _render_subject(special)
    if to:
        msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["MIME-Version"] = "1.0"
    # Outlook 识别此 header，会以"草稿"形式打开并允许发送
    msg["X-Unsent"] = "1"
    msg.set_content(text_body or "", charset="utf-8")
    msg.add_alternative(html_body or "", subtype="html", charset="utf-8")
    # 全景图与图片分段以 CID 内嵌：add_related 会把 html 部分升级为
    # multipart/related。失败不该让整封周报下载不下来，故整段兜底。
    if images:
        try:
            html_part = msg.get_payload()[-1]
            for im in images:
                html_part.add_related(im["data"], maintype="image",
                                      subtype=im["subtype"], cid=f"<{im['cid']}>")
        except Exception:
            pass
    return bytes(msg)


@router.get("/{sid}/export.xlsx")
def export_special_xlsx(
    sid: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """导出该专项/攻关为美观的 Excel（华为红风格，含目标/进展/里程碑/事务/风险）。"""
    from xlsx_utils import build_special_xlsx

    special = _get_or_404(db, sid)
    _ensure_content(db, special)
    db.refresh(special)
    stream = build_special_xlsx(special)

    fname_base = "".join(
        c for c in (special.name or "special") if c not in '\\/:*?"<>|'
    ).strip() or "special"
    fname = f"{fname_base}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    log_op(db, action="导出Excel", target=_kind_label(special.kind), target_id=sid,
           detail=f"name={special.name}", user=current_user, request=request)
    return Response(
        content=stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="special_{sid}.xlsx"; '
                f"filename*=UTF-8''{url_quote(fname)}"
            ),
        },
    )


@router.get("/{sid}/report-draft", response_model=schemas.SpecialReportDraft)
def get_report_draft(sid: int, db: Session = Depends(get_db)):
    special = _get_or_404(db, sid)
    _ensure_content(db, special)
    db.refresh(special)
    return schemas.SpecialReportDraft(
        subject=_render_subject(special),
        to=special.email_to or "",
        cc=special.email_cc or "",
        body=_render_report_body(special),
    )


@router.post("/{sid}/report.eml")
def export_report_eml(
    sid: int,
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """根据当前数据 + 前端编辑过的字段生成 .eml 文件供下载。

    payload 字段: subject / to / cc / body （body 是用户编辑过的纯文本）。
    HTML 部分用当前数据库内容现场渲染，保证格式美观；
    纯文本 fallback 用 body（用户编辑过的版本）。
    """
    special = _get_or_404(db, sid)
    _ensure_content(db, special)
    db.refresh(special)

    subject = str(payload.get("subject") or _render_subject(special))
    to = str(payload.get("to") or special.email_to or "")
    cc = str(payload.get("cc") or special.email_cc or "")
    text_body = str(payload.get("body") or _render_report_body(special))
    html_body, inline_images = _render_report_html(special)

    eml = _build_eml(special, subject, to, cc, text_body, html_body, inline_images)

    fname_base = "".join(
        c for c in (special.name or "report") if c not in '\\/:*?"<>|'
    ).strip() or "report"
    fname = f"{fname_base}_{datetime.now().strftime('%Y%m%d')}.eml"
    log_op(db, action="导出周报", target=_kind_label(special.kind), target_id=sid,
           detail=f"name={special.name}", user=current_user, request=request)
    return Response(
        content=eml,
        media_type="message/rfc822",
        headers={
            "Content-Disposition": (
                # ASCII fallback + RFC 5987 编码（处理中文文件名）
                f'attachment; filename="report_{sid}.eml"; '
                f"filename*=UTF-8''{url_quote(fname)}"
            ),
        },
    )
