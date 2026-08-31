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
