"""迭代需求查重：把同一迭代里录重了的行找出来（可选清掉其中没人动过的那些）。

判重口径直接用 `routers/_req_dedup.py`（有编号按编号、没编号按标题、同一迭代内），
与页面上的新增/导入拦截**共用一份实现**——两处分叉的表现是「页面说重复，脚本查不出来」。

采集侧现在已经拦住新的重复了，但**已经录进去的不会自己消失**。重复的需求在度量里是
实打实的分母：加权完成度被摊薄、按项目/领域的条数偏大，而每一行单独看都合法。

`--apply` 只删**没人动过的空壳行**：六个进展列全是「未开始」、代码量/用例数/问题单数
都空、备注与合入链接也空。每一组至少保留一行（留内容最全的那条，一样全就留最早的）。
被人填过内容的重复行**不会自动删**，只列出来让人自己合并——那上面可能有别人跟了半年
的进展，误删的代价远大于多一行。

    python scripts/find_duplicate_requirements.py                 # 只读体检
    python scripts/find_duplicate_requirements.py --apply         # 删掉空壳重复行
    python scripts/find_duplicate_requirements.py --db /path/app.db

改库前请先备份：cp app.db app.db.bak
"""
import argparse
import pathlib
import sys
from collections import defaultdict

BACKEND = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

_PROGRESS_PREFIX = "progress_"
_EMPTY_NUMS = ("code_volume", "self_test_case_count", "post_test_issue_count")
_EMPTY_TEXTS = ("remark", "merge_links", "code_areas")


def _session(db_path: pathlib.Path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(f"sqlite:///{db_path}")
    return sessionmaker(bind=engine, autoflush=False)()


def _filled_fields(row) -> int:
    """这一行被人填过多少东西——用来决定一组重复里留哪条。"""
    n = 0
    for col in row.__table__.columns:
        name = col.name
        v = getattr(row, name, None)
        if name.startswith(_PROGRESS_PREFIX):
            n += 1 if (v or "") not in ("", "未开始") else 0
        elif name in _EMPTY_NUMS:
            n += 1 if v not in (None, "", 0) else 0
        elif name in _EMPTY_TEXTS:
            n += 1 if (v or "").strip() else 0
    return n


def _is_untouched(row) -> bool:
    """空壳：没有任何人在这一行上记过进展或数据。"""
    return _filled_fields(row) == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="迭代需求查重")
    ap.add_argument("--db", default=str(BACKEND / "app.db"), help="app.db 路径")
    ap.add_argument("--apply", action="store_true",
                    help="删掉重复组里没人动过的空壳行；默认只读体检")
    args = ap.parse_args()

    db_path = pathlib.Path(args.db)
    if not db_path.exists():
        print(f"找不到数据库：{db_path}")
        return 1

    import models
    from routers._req_dedup import dedup_key

    db = _session(db_path)
    iter_label = {i.id: f"{i.year}-{i.month:02d}"
                  for i in db.query(models.AnnualIteration).all()}

    tables = [("领域需求", models.IterationRequirement),
              ("产品需求", models.IterationProductRequirement)]
    to_delete, total_groups, total_rows = [], 0, 0

    for label, model in tables:
        groups = defaultdict(list)
        for row in db.query(model).order_by(model.id).all():
            k = dedup_key(row.req_no, row.title)
            if k is not None:
                groups[(row.iteration_id, k)].append(row)
        dups = {k: v for k, v in groups.items() if len(v) > 1}
        if not dups:
            print(f"{label}：没有重复。 ✔")
            continue

        print(f"\n{label}：{len(dups)} 组重复、共 {sum(len(v) for v in dups.values())} 行")
        for (iteration_id, key), rows in sorted(dups.items(), key=lambda x: str(x[0])):
            total_groups += 1
            total_rows += len(rows)
            # 留内容最全的那条；一样全就留最早录的（id 最小）
            rows_sorted = sorted(rows, key=lambda r: (-_filled_fields(r), r.id))
            keep, extras = rows_sorted[0], rows_sorted[1:]
            kind = "编号" if key[0] == "no" else "标题"
            print(f"\n  [{iter_label.get(iteration_id, iteration_id)}] 按{kind}重复："
                  f"{(keep.title or '').strip() or '无标题'}")
            print(f"    保留 id={keep.id} 序号={keep.seq} 编号={(keep.req_no or '').strip() or '-'}"
                  f"（已填 {_filled_fields(keep)} 项）")
            for r in extras:
                shell = _is_untouched(r)
                mark = "空壳，可自动删" if shell else "**有人填过，请人工合并**"
                print(f"    重复 id={r.id} 序号={r.seq} 编号={(r.req_no or '').strip() or '-'}"
                      f"（已填 {_filled_fields(r)} 项）→ {mark}")
                if shell:
                    to_delete.append((model, r.id))

    if not total_groups:
        return 0

    print(f"\n合计 {total_groups} 组、{total_rows} 行；其中可自动删除的空壳行 {len(to_delete)} 条，"
          f"需人工合并 {total_rows - total_groups - len(to_delete)} 条。")
    if not args.apply:
        print("以上仅为体检，未删除任何数据。确认无误后加 --apply 执行。")
        return 0

    for model, rid in to_delete:
        db.query(model).filter(model.id == rid).delete(synchronize_session=False)
    db.commit()
    print(f"已删除 {len(to_delete)} 条空壳重复行；有人填过内容的重复行一条没动，请按上面的清单人工合并。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
