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
from datetime import datetime, timedelta
from email.message import EmailMessage
from html.parser import HTMLParser
from typing import List
from urllib.parse import quote as url_quote

from fastapi import APIRouter, Body, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

import models
import schemas
from auth import get_current_user, require_admin
from database import get_db
from op_log import log_op
from notify import dispatch
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


@router.post("", response_model=schemas.SpecialOut)
def create_special(
    payload: schemas.SpecialCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    data = payload.model_dump()
    if data.get("kind") not in ("special", "assault"):
        data["kind"] = "special"
    fill_user_fk(db, data, "owner", "owner_user_id")
    item = models.Special(**data)
    db.add(item)
    db.commit()
    db.refresh(item)
    # 创建对应的空 content
    db.add(models.SpecialContent(special_id=item.id))
    db.commit()
    log_op(db, action="新增", target=_kind_label(item.kind), target_id=item.id,
           detail=f"name={item.name}",
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

_ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "s", "span", "br", "div", "p", "font"}
_VOID_TAGS = {"br"}
_ALLOWED_STYLE_PROPS = {
    "color", "background-color", "font-size", "font-weight",
    "font-style", "text-decoration", "font-family", "text-align",
}
_ALLOWED_FONT_ATTRS = {"color", "size"}


class _RichSanitizer(HTMLParser):
    """白名单 HTML 清洗，移除 script / on* / 不在白名单内的标签和样式。"""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in _ALLOWED_TAGS:
            return
        kept = self._filter_attrs(tag, attrs)
        attr_str = "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in kept)
        self.out.append(f"<{tag}{attr_str}>")

    def handle_endtag(self, tag):
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
        self.out.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        self.out.append(f"&{name};")

    def handle_charref(self, name):
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


def _render_report_body(special: models.Special) -> str:
    label = _kind_label(special.kind)
    content = special.content
    parts: List[str] = []

    parts.append(f"[{label}名称] {special.name}")
    parts.append(f"[责任人] {special.owner or '-'}")
    parts.append(f"[报告日期] {datetime.now().strftime('%Y-%m-%d')}")
    parts.append("")

    if content and content.goal:
        parts.append(f"一、{label}目标")
        parts.append(_strip_html(content.goal))
        parts.append("")

    if content and content.progress_summary:
        parts.append("二、整体进展")
        parts.append(_strip_html(content.progress_summary))
        parts.append("")

    if content and content.help_request:
        parts.append("三、求助")
        parts.append(_strip_html(content.help_request))
        parts.append("")

    # 里程碑
    milestones = []
    if content and content.milestones_json:
        try:
            milestones = json.loads(content.milestones_json) or []
        except (ValueError, TypeError):
            milestones = []
    if milestones:
        parts.append(f"四、{label}计划（里程碑）")
        for m in milestones:
            st = _MS_STATUS_LABEL.get(m.get("status", "planning"), m.get("status", ""))
            parts.append(f"  · {m.get('name','')}  {m.get('date','')}  [{st}]")
        parts.append("")

    # 风险（调整到事务之前）
    risks = special.risks or []
    if risks:
        parts.append("五、风险和问题")
        for i, r in enumerate(risks, 1):
            parts.append(f"  {i}. {_strip_html(r.content)}")
            if r.progress: parts.append(f"     当前进展：{_strip_html(r.progress)}")
            meta = []
            if r.owner: meta.append(f"责任人：{r.owner}")
            if r.planned_close_date: meta.append(f"计划闭环：{r.planned_close_date}")
            if meta: parts.append(f"     " + " / ".join(meta))
        parts.append("")

    # 事务
    open_tasks = [t for t in (special.tasks or []) if (t.status or "open") == "open"]
    closed_tasks = [t for t in (special.tasks or []) if (t.status or "open") == "closed"]
    if open_tasks or closed_tasks:
        parts.append(f"六、{label}事务")
        if open_tasks:
            parts.append(f"  ◇ 进行中（{len(open_tasks)} 项）")
            for i, t in enumerate(open_tasks, 1):
                parts.append(f"    {i}. {_strip_html(t.content)}")
                if t.progress: parts.append(f"       进展：{_strip_html(t.progress)}")
                meta = []
                if t.owner: meta.append(f"责任人：{t.owner}")
                if t.planned_close_date: meta.append(f"计划闭环：{t.planned_close_date}")
                if meta: parts.append(f"       " + " / ".join(meta))
        if closed_tasks:
            parts.append(f"  ◇ 本期已闭环（{len(closed_tasks)} 项）")
            for i, t in enumerate(closed_tasks, 1):
                parts.append(f"    {i}. {_strip_html(t.content)}")
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


def _build_table_rich(headers: list, rows_html: list) -> str:
    """rows_html 中每个单元格已是安全 HTML，由调用方对富文本字段做清洗。"""
    head = "<tr>" + "".join(f'<th style="{_HTML_TH_CSS}">{_e(h)}</th>' for h in headers) + "</tr>"
    body = "".join(_row_td_raw(r, i % 2 == 1) for i, r in enumerate(rows_html))
    return f'<table style="{_HTML_TABLE_CSS}">{head}{body}</table>'


def _render_report_html(special: models.Special) -> str:
    label = _kind_label(special.kind)
    content = special.content
    today = datetime.now().strftime("%Y-%m-%d")

    sections: List[str] = []

    if content and content.goal:
        sections.append(
            f'<h3 style="color:#4073BA;border-left:4px solid #4073BA;padding-left:8px;margin:18px 0 8px;">'
            f'一、{label}目标</h3>'
            f'<div>{_rich_to_html(content.goal)}</div>'
        )

    if content and content.progress_summary:
        sections.append(
            f'<h3 style="color:#4073BA;border-left:4px solid #4073BA;padding-left:8px;margin:18px 0 8px;">'
            f'二、整体进展</h3>'
            f'<div>{_rich_to_html(content.progress_summary)}</div>'
        )

    if content and content.help_request:
        sections.append(
            f'<h3 style="color:#4073BA;border-left:4px solid #4073BA;padding-left:8px;margin:18px 0 8px;">'
            f'三、求助</h3>'
            f'<div>{_rich_to_html(content.help_request)}</div>'
        )

    # 里程碑
    milestones = []
    if content and content.milestones_json:
        try:
            milestones = json.loads(content.milestones_json) or []
        except (ValueError, TypeError):
            milestones = []
    if milestones:
        rows = [
            [m.get("name", ""), m.get("date", ""),
             _MS_STATUS_LABEL.get(m.get("status", "planning"), m.get("status", ""))]
            for m in milestones
        ]
        sections.append(
            f'<h3 style="color:#4073BA;border-left:4px solid #4073BA;padding-left:8px;margin:18px 0 8px;">'
            f'四、{label}计划（里程碑）</h3>'
            + _build_table(["里程碑", "日期", "状态"], rows)
        )

    # 风险（调整到事务之前）
    risks = special.risks or []
    if risks:
        rows = [
            [_rich_to_html(r.content), _rich_to_html(r.progress),
             _e(r.owner or ""), _e(r.planned_close_date or ""),
             "Open" if (r.status or "open") == "open" else "Closed"]
            for r in risks
        ]
        sections.append(
            f'<h3 style="color:#F56C6C;border-left:4px solid #F56C6C;padding-left:8px;margin:18px 0 8px;">'
            f'五、风险和问题</h3>'
            + _build_table_rich(["问题内容", "当前进展", "责任人", "计划闭环时间", "状态"], rows)
        )

    # 事务
    open_tasks = [t for t in (special.tasks or []) if (t.status or "open") == "open"]
    closed_tasks = [t for t in (special.tasks or []) if (t.status or "open") == "closed"]
    if open_tasks or closed_tasks:
        block = [
            f'<h3 style="color:#4073BA;border-left:4px solid #4073BA;padding-left:8px;margin:18px 0 8px;">'
            f'六、{label}事务</h3>'
        ]
        if open_tasks:
            rows = [
                [_rich_to_html(t.content), _rich_to_html(t.progress),
                 _e(t.owner or ""), _e(t.planned_close_date or ""), "Open"]
                for t in open_tasks
            ]
            block.append(
                f'<div style="font-weight:600;margin:6px 0;color:#E6A23C;">'
                f'◇ 进行中（{len(open_tasks)} 项）</div>'
                + _build_table_rich(["事务内容", "当前进展", "责任人", "计划闭环时间", "状态"], rows)
            )
        if closed_tasks:
            rows = [
                [_rich_to_html(t.content), _rich_to_html(t.progress),
                 _e(t.owner or ""), _e(t.planned_close_date or ""), "Closed"]
                for t in closed_tasks
            ]
            block.append(
                f'<div style="font-weight:600;margin:6px 0;color:#67C23A;">'
                f'◇ 本期已闭环（{len(closed_tasks)} 项）</div>'
                + _build_table_rich(["事务内容", "当前进展", "责任人", "计划闭环时间", "状态"], rows)
            )
        sections.append("".join(block))

    body_inner = "".join(sections) or '<div style="color:#909399;">（该报告无内容）</div>'

    return (
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


def _build_eml(special: models.Special, subject: str, to: str, cc: str,
               text_body: str, html_body: str) -> bytes:
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
    html_body = _render_report_html(special)

    eml = _build_eml(special, subject, to, cc, text_body, html_body)

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
