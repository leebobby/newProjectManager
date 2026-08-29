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
EXAMPLE_PATH = CONFIG_PATH.with_name("config.example.json")


def _load() -> dict:
    """读运行时配置；`config.json` 不存在时回落到仓库里的 `config.example.json`。

    `config.json` **不入版本库**：里面是这台机器上的绝对路径、这个部署要采集的项目，
    属于部署实例的状态而不是源码（同 `app.db` / `uploads/`）。它曾经是跟着代码走的，
    后果是每次 `git pull` 都把线上配好的路径盖回某台开发机的 `D:\\...`，
    而页面上一切正常——只是问题单采集从此指向一个不存在的目录。

    回落到模板而不是回落到 `{}`：`hw_machine_cell_options` 这类**词表**默认值
    也在这份配置里，空掉的话新装的实例里那几个下拉是空的，看着像功能坏了。
    """
    for path in (CONFIG_PATH, EXAMPLE_PATH):
        if path.exists():
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
            # 模板里的说明键不该出现在接口响应里
            return {k: v for k, v in cfg.items() if not k.startswith("_")}
    return {"current_stages": []}


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
                # 把排期结论回给前端：以前这里的返回值被丢掉，调度器没起来时
                # 页面照样提示"已保存：每天 07:30 自动采集"，而实际一次都不会跑
                cfg = dict(cfg, _schedule_message=scheduler.apply_issue_snapshot_schedule())
            except Exception as exc:  # 调度未启动 / 装载失败不该让保存失败
                cfg = dict(cfg, _schedule_message=f"配置已存，但调度热更新失败：{exc}")
        return cfg
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存配置失败: {exc}")
