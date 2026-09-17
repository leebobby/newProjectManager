"""需求的**批量改版本 / 批量挪迭代**：领域需求与产品需求两张表共用一份实现。

两处各写一份的表现是「在领域需求那个 Tab 挪走会重排序号、在产品需求那个 Tab 挪走
不重排」，而两边单独看都正常。

三条口径写死在这里：

- **批量照样走乐观锁**。每一条都要带自己的 `version`，对不上就单独失败、不整批回滚
  ——整批失败的话，一条被别人动过就得从头再选一遍；而跳过不报的话，人以为 12 条
  全改了，其实只改了 9 条。所以是「能改的改掉，改不动的逐条报出来」。
- **挪迭代要重判重**：目标迭代里可能已经有同一条需求（上个月没做完、这个月已经
  手工补录过一条）。不判的话两条并存，度量里是实打实的分母，而每一行单独看都合法
  （同 `_req_dedup`）。
- **挪迭代要把 `seq` 重算成目标迭代的末位**。带着原序号过去会插进目标那一堆的中间，
  看着像随机落点（同版本三层改挂父级时的 `_tail_sort_order()`）。
"""
from typing import List, Optional

from sqlalchemy.orm import Session

import models
from routers._req_dedup import duplicate_message, find_duplicate


def _ensure_iteration(db: Session, year: int, month: int) -> models.AnnualIteration:
    """拿到 (year, month) 那条迭代；整年缺失时顺带补齐 12 条占位行。

    直接复用 annual_iterations._ensure_year，不在这儿另写一份——各写一份的表现是
    这里补出来的迭代没有名字，而迭代管理页上那一格就空着。
    """
    from routers.annual_iterations import _ensure_year
    _ensure_year(db, year)
    return (
        db.query(models.AnnualIteration)
        .filter(models.AnnualIteration.year == year, models.AnnualIteration.month == month)
        .first()
    )


def _tail_seq(db: Session, model, iteration_id: int) -> int:
    n = db.query(model).filter(model.iteration_id == iteration_id).count()
    return n + 1


def _shift(year: int, month: int, months: int):
    """(年, 月) 往后推 N 个月。12 月 +1 要跨年，就地取模会算出 13 月。"""
    idx = (year * 12 + (month - 1)) + months
    return idx // 12, idx % 12 + 1


def bulk_update(db: Session, model, items: List, *,
                planned_version: Optional[str] = None,
                target_version_id: Optional[int] = None,
                shift_months: Optional[int] = None,
                fill_version_fk=None) -> dict:
    """按 `items`（每条带 id + version）批量改。返回 {updated, conflicts}。

    `shift_months` 与版本字段互斥：一次只干一件事。两件混在一起时，一条需求既换了
    版本又换了迭代，出了问题没人说得清是哪一步干的。
    """
    updated = 0
    conflicts = []
    moved_labels = set()

    for it in items:
        row = db.query(model).filter(model.id == it.id).first()
        if row is None:
            conflicts.append({"id": it.id, "seq": None, "title": "",
                              "reason": "这一条已被他人删除"})
            continue
        if row.version != it.version:
            conflicts.append({"id": row.id, "seq": row.seq, "title": (row.title or "").strip(),
                              "reason": "已被他人修改，刷新后重试"})
            continue

        if shift_months is not None:
            src = db.query(models.AnnualIteration).filter(
                models.AnnualIteration.id == row.iteration_id).first()
            if src is None:
                conflicts.append({"id": row.id, "seq": row.seq, "title": (row.title or "").strip(),
                                  "reason": "所属迭代不存在，无法推算目标月份"})
                continue
            y, m = _shift(src.year, src.month, shift_months)
            target = _ensure_iteration(db, y, m)
            if target is None:
                conflicts.append({"id": row.id, "seq": row.seq, "title": (row.title or "").strip(),
                                  "reason": f"{y}-{m:02d} 的迭代建不出来"})
                continue
            if target.id == row.iteration_id:
                conflicts.append({"id": row.id, "seq": row.seq, "title": (row.title or "").strip(),
                                  "reason": "目标迭代就是当前迭代"})
                continue
            dup = find_duplicate(db, model, target.id, row.req_no, row.title)
            if dup is not None:
                conflicts.append({
                    "id": row.id, "seq": row.seq, "title": (row.title or "").strip(),
                    "reason": duplicate_message(dup, f"{y}-{m:02d} 里已经有这条需求"),
                })
                continue
            row.iteration_id = target.id
            row.seq = _tail_seq(db, model, target.id)
            moved_labels.add(f"{y}-{m:02d}")
        else:
            data = {}
            if planned_version is not None:
                data["planned_version"] = planned_version
            if target_version_id is not None:
                data["target_version_id"] = target_version_id
            # 只填了版本号没给 FK 时反查一把，口径与单行保存那条路一致
            if fill_version_fk and "planned_version" in data and "target_version_id" not in data:
                fill_version_fk(db, data, "planned_version", "target_version_id")
            for k, v in data.items():
                setattr(row, k, v)

        row.version += 1
        updated += 1

    if updated:
        db.commit()
    return {"updated": updated, "conflicts": conflicts,
            "moved_to": sorted(moved_labels)}
