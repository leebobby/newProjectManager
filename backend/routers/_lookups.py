"""跨 router 复用的"字符串 → 主数据 FK"反查工具。

Owner / 资源组 / 版本 / 项目 是散布在多张表上的字符串字段，这里集中处理：
- 用户：优先按 emp_no 精确匹配，其次按 full_name 完全匹配
- 资源组（PL 组）：按 code 或 name 完全匹配
- 迭代版本：按 version_no 完全匹配
- 项目：按 name 完全匹配（roadmap_projects）

所有 resolve 函数返回 Optional[int]；不要在调用方报错，让 UI 在导入后能通过对账页补全。
"""
from typing import Optional

from sqlalchemy.orm import Session

import models


def resolve_user_id(db: Session, value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    # emp_no 命中优先
    u = db.query(models.User).filter(models.User.emp_no == s).first()
    if u:
        return u.id
    # full_name 命中（重名会返回首个；不可靠时建议 UI 用 user_id 显式选）
    u = db.query(models.User).filter(models.User.full_name == s).first()
    if u:
        return u.id
    # 兜底：登录名
    u = db.query(models.User).filter(models.User.username == s).first()
    return u.id if u else None


def resolve_group_id(db: Session, value: Optional[str], kind: str = "pl") -> Optional[int]:
    """按 code 或 name 反查资源组；默认只看 PL 组（kind=pl）。"""
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    q = db.query(models.ResourceGroup)
    if kind:
        q = q.filter(models.ResourceGroup.kind == kind)
    g = q.filter(models.ResourceGroup.code == s).first()
    if g:
        return g.id
    g = q.filter(models.ResourceGroup.name == s).first()
    return g.id if g else None


def _first_iteration_of(db: Session, **filters) -> Optional[int]:
    iv = (
        db.query(models.IterationVersion)
        .filter_by(**filters)
        .order_by(models.IterationVersion.sort_order, models.IterationVersion.id)
        .first()
    )
    return iv.id if iv else None


def resolve_iteration_version_id(db: Session, value: Optional[str]) -> Optional[int]:
    """字符串版本号 → 迭代版本 id。三层都试，由细到粗。

    命中顺序是 迭代版本（C10SPC101B001）→ 版本（C10SPC101）→ 大版本（C10SPC100），
    后两档落到该层下**序号最小的**那个构建。粗匹配落空返回 None 而不是报错，
    留给「数据对账」页事后补（见 CLAUDE.md「主数据与 FK 反查」）。
    """
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    v = db.query(models.IterationVersion).filter(models.IterationVersion.version_no == s).first()
    if v:
        return v.id
    rv = db.query(models.ReleaseVersion).filter(models.ReleaseVersion.version_no == s).first()
    if rv:
        return _first_iteration_of(db, release_version_id=rv.id)
    mv = db.query(models.MajorVersion).filter(models.MajorVersion.version_no == s).first()
    if mv:
        return _first_iteration_of(db, major_version_id=mv.id)
    return None


def resolve_project_id(db: Session, value: Optional[str]) -> Optional[int]:
    """项目名 → roadmap_projects.id。只做完全匹配。

    项目名是人手填的短名（"YLS3000"），模糊匹配很容易把 "YLS3000" 认到
    "YLS3000-PLUS" 上去，而错挂的需求在按项目度量时只是数字偏一点，没人查得出来。
    """
    if not value:
        return None
    # 导入路径可能递进来数字（项目名恰好是纯数字时 openpyxl 会给 int），先转字符串
    s = str(value).strip()
    if not s:
        return None
    p = db.query(models.RoadmapProject).filter(models.RoadmapProject.name == s).first()
    return p.id if p else None


def fill_user_fk(db: Session, data: dict, str_field: str, fk_field: str) -> None:
    """便利函数：在 model_dump 后的字典上原位填 FK。

    - 如果 fk_field 已显式提供，尊重它（即使是 None 也尊重）
    - 否则按 str_field 自动反查
    """
    if fk_field in data:
        return
    if str_field in data and data.get(str_field):
        data[fk_field] = resolve_user_id(db, data[str_field])


def fill_group_fk(db: Session, data: dict, str_field: str, fk_field: str) -> None:
    if fk_field in data:
        return
    if str_field in data and data.get(str_field):
        data[fk_field] = resolve_group_id(db, data[str_field])


def fill_version_fk(db: Session, data: dict, str_field: str, fk_field: str) -> None:
    if fk_field in data:
        return
    if str_field in data and data.get(str_field):
        data[fk_field] = resolve_iteration_version_id(db, data[str_field])


def fill_project_fk(db: Session, data: dict, str_field: str, fk_field: str) -> None:
    if fk_field in data:
        return
    if str_field in data and data.get(str_field):
        data[fk_field] = resolve_project_id(db, data[str_field])


def project_name_map(db: Session) -> dict:
    """{roadmap_projects.id: name}。列表接口回填 project_name 用。

    项目表只有个位数行，一次全量取出比逐行 join 便宜，也避免 N+1。
    """
    return {p.id: p.name for p in db.query(models.RoadmapProject).all()}
