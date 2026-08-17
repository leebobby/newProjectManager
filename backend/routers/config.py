import json
import pathlib

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

import models
from auth import require_admin
from database import get_db
from op_log import log_op

router = APIRouter(prefix="/api/config", tags=["config"])

CONFIG_PATH = pathlib.Path(__file__).resolve().parent.parent / "config.json"


def _load() -> dict:
    if not CONFIG_PATH.exists():
        return {"current_stages": []}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


@router.get("")
def get_config():
    """读取项目级配置，前端启动时拉取一次即可。"""
    try:
        return _load()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"配置文件解析失败: {exc}")


@router.put("")
def save_config(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin),
):
    """保存项目级配置（仅管理员）。只更新 payload 中携带的键，不影响其余字段。"""
    try:
        cfg = _load()
        cfg.update(payload)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        log_op(db, action="修改", target="配置",
               detail=f"keys={','.join(payload.keys())}",
               user=current_admin, request=request)
        # 改了定时采集配置就热更新调度，省得改完还要重启后端才生效
        if {"issue_snapshot_time", "issue_snapshot_enabled"} & set(payload.keys()):
            try:
                import scheduler
                scheduler.apply_issue_snapshot_schedule()
            except Exception:  # 调度未启动 / 装载失败不该让保存失败
                pass
        return cfg
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存配置失败: {exc}")
