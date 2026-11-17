from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

import models
from requirement_identity import ar_key


def find_ar_duplicate(db, value, exclude_id=None):
    key = ar_key(value)
    if key is None:
        return None
    query = db.query(models.IterationRequirement).filter(models.IterationRequirement.ar_key == key)
    if exclude_id is not None:
        query = query.filter(models.IterationRequirement.id != exclude_id)
    return query.first()


def ar_duplicate_message(row):
    return f'需求编号 AR「{row.ar_no}」已存在（序号 {row.seq or "-"}，{row.title or "无标题"}），AR 不允许重复'


def commit_ar(db):
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        if 'ar_key' in str(error.orig):
            raise HTTPException(409, '需求编号 AR 已存在，请刷新后检查重复编号') from error
        raise
