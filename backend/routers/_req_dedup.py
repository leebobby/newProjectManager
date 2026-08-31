"""需求判重：同一迭代内「同一条需求」只该录一次。

判重口径**只有一份实现**，领域需求与产品需求两张表共用——两处各写一份的表现是
「手工新增拦住了、Excel 导入照样进」，或者两个 Tab 的判重松紧不一样。

口径：
- **范围是一个迭代**，不是全表。同一条需求本轮没做完、下个月接着排是正常的，
  跨迭代拦住会逼着人改标题绕过去，那比重复更糟。
- **有需求编号按编号判，没编号按标题判**。编号是业务主键；但编号是选填的，
  只按编号判等于「不填编号就能重复录」，而漏填编号的行恰恰是手工补录的那批。
- 比较前把空白全部去掉再转小写：Excel 里粘出来的编号常带首尾空格或全角空格，
  肉眼看不出差别，按原样比较则判不出重。
- 编号与标题都是空的行不参与判重（没有可比的东西），照旧放行。
"""
import re
from typing import Optional, Tuple

from sqlalchemy.orm import Session

#: 判重键：("no", 编号) 或 ("title", 标题)
DedupKey = Tuple[str, str]


def _squash(s) -> str:
    """去掉所有空白（含全角空格）再转小写。"""
    return re.sub(r"[\s　]+", "", str(s or "")).lower()


def dedup_key(req_no, title) -> Optional[DedupKey]:
    """一行需求的判重键；编号与标题都空时返回 None（不参与判重）。"""
    no = _squash(req_no)
    if no:
        return ("no", no)
    t = _squash(title)
    return ("title", t) if t else None


def find_duplicate(db: Session, model, iteration_id: int, req_no, title,
                   exclude_id: Optional[int] = None):
    """本迭代里是否已有同一条需求；有则返回那一行，没有返回 None。

    `exclude_id` 用于编辑场景——一行跟自己重复不算重复。
    """
    key = dedup_key(req_no, title)
    if key is None or not iteration_id:
        return None
    q = db.query(model).filter(model.iteration_id == iteration_id)
    if exclude_id:
        q = q.filter(model.id != exclude_id)
    for row in q.all():
        if dedup_key(row.req_no, row.title) == key:
            return row
    return None


def duplicate_message(row, prefix: str = "本迭代里已经有这条需求") -> str:
    """给使用者看的重复提示：指到具体是哪一行，好让人去改那一行而不是重录一条。"""
    no = (row.req_no or "").strip()
    tail = f"（需求编号 {no}）" if no else ""
    return (f"{prefix}：序号 {row.seq or '-'}、{(row.title or '').strip() or '无标题'}{tail}。"
            "要改内容请直接编辑那一行。")


def scan_duplicates(db: Session, model, iteration_id: int) -> dict:
    """本迭代的需求里，哪些在**别的迭代**（或本迭代内）还录过一遍。

    与 `find_duplicate()` 的区别是它**不拦，只报**：

    - 同一迭代内重复是硬错误，新增/导入那一刻就已经 409 挡住了；这里仍然要扫，
      因为判重是后加的，**存量数据里的重复不会自己消失**，得让人看见去合并。
    - 跨迭代重复**不能拦**——同一条需求本轮没做完、下个月接着排是正常的。但它也
      可能是"上个月已经录过，这个月又录了一条"，两者从数据上分不出来，只有人分得出。
      所以做成提示：把"它还出现在哪几个迭代"摆出来，让人自己判断要不要改。

    返回 {"groups": [...], "same_iteration": n, "cross_iteration": m}，
    groups 按本迭代的序号排，每组带上本迭代里的行与别处的出现位置。
    """
    import models

    rows = db.query(model).filter(model.iteration_id == iteration_id).all()
    here: dict = {}
    for r in rows:
        k = dedup_key(r.req_no, r.title)
        if k is not None:
            here.setdefault(k, []).append(r)
    if not here:
        return {"groups": [], "same_iteration": 0, "cross_iteration": 0}

    elsewhere: dict = {}
    for r in db.query(model).filter(model.iteration_id != iteration_id).all():
        k = dedup_key(r.req_no, r.title)
        if k in here:
            elsewhere.setdefault(k, []).append(r)

    labels = {i.id: f"{i.year}-{i.month:02d}"
              for i in db.query(models.AnnualIteration).all()}

    def _brief(r, with_iteration=False):
        d = {"id": r.id, "seq": r.seq, "req_no": (r.req_no or "").strip(),
             "title": (r.title or "").strip()}
        if with_iteration:
            d["iteration_id"] = r.iteration_id
            d["iteration_label"] = labels.get(r.iteration_id, str(r.iteration_id))
        return d

    groups, same_n, cross_n = [], 0, 0
    for key, mine in here.items():
        others = elsewhere.get(key, [])
        if len(mine) < 2 and not others:
            continue
        if len(mine) > 1:
            same_n += 1
        if others:
            cross_n += 1
        groups.append({
            "kind": key[0],                       # no ＝按编号撞的，title ＝按标题撞的
            "rows": [_brief(r) for r in sorted(mine, key=lambda x: (x.seq or 0, x.id))],
            "others": [_brief(r, True) for r in
                       sorted(others, key=lambda x: (x.iteration_id, x.seq or 0))],
        })
    groups.sort(key=lambda g: (g["rows"][0]["seq"] or 0, g["rows"][0]["id"]))
    return {"groups": groups, "same_iteration": same_n, "cross_iteration": cross_n}
