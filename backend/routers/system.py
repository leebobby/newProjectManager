"""系统级查询接口：磁盘使用率等运维信息。"""
import pathlib
import shutil

from fastapi import APIRouter

router = APIRouter(prefix="/api/system", tags=["system"])

UPLOAD_ROOT = pathlib.Path(__file__).resolve().parent.parent / "uploads"


@router.get("/storage")
def get_storage():
    """返回上传目录所在分区的磁盘使用情况（字节）。

    路径若不存在，会回退到其父目录上去取（适用于首次部署 uploads/ 还没建的情况）。
    """
    probe = UPLOAD_ROOT
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    total, used, free = shutil.disk_usage(str(probe))
    return {
        "upload_root": str(UPLOAD_ROOT),
        "probe_path": str(probe),
        "total": total,
        "used": used,
        "free": free,
    }
