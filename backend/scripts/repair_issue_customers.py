"""历史快照的「客户面」重算：把被短名字吃掉的带编号客户改回来。

背景：客户面是采集时由标题匹配客户主数据得到的（`routers/issues.py::_match_customer`），
匹配过去是朴素的子串包含。而 `"1号机" in "11号机"` 是真的（从第二个字符起就是），
于是标题里的「11号机」会落到「1号机」那一档——两台机器的单混进一行、同一台机器的单
散在两行，数字都还对得上，没人会当 bug 报。采集侧已经加了数字边界，但**已经落盘的
快照不会自己重算**，趋势图里那段历史仍然是错的。

本脚本按当前的匹配规则（直接 import `routers.issues`，规则只有一份）重算每份快照
明细里的 `customer` 字段，并重建 `issue_snapshot_stats` 里 dimension='customer' 的数字。

三件事**不动**：
- `issue_snapshot_flows`（新增/解决差分）按缺陷编号算，与客户面无关，重算它反而会
  凭空造出一批假新增/假解决；
- 明细里的其它字段（小组、部门、严重程度）；
- `data/issue_excel/` 下的历史 Excel 备份——那是当天的存档，重写等于篡改历史存档。
  重算后重新导出即可。

    python scripts/repair_issue_customers.py                    # 只读预演，不动任何文件
    python scripts/repair_issue_customers.py --project YLS3000  # 只看某个项目
    python scripts/repair_issue_customers.py --apply            # 真的写回

改动前请先备份：cp app.db app.db.bak，快照目录也一并复制一份。
"""
import argparse
import json
import pathlib
import sys
from collections import Counter

BACKEND = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


def _session(db_path: pathlib.Path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(f"sqlite:///{db_path}")
    return sessionmaker(bind=engine, autoflush=False)()


def main() -> int:
    ap = argparse.ArgumentParser(description="重算历史快照的客户面分类")
    ap.add_argument("--db", default=str(BACKEND / "app.db"), help="app.db 路径")
    ap.add_argument("--project", default="", help="只处理这个项目（默认全部）")
    ap.add_argument("--apply", action="store_true", help="真的写回；默认只读预演")
    args = ap.parse_args()

    db_path = pathlib.Path(args.db)
    if not db_path.exists():
        print(f"找不到数据库：{db_path}")
        return 1

    import models
    import routers.issues as ri

    db = _session(db_path)
    matchers = ri._load_customer_matchers(db)
    if not matchers:
        print("客户主数据是空的（customers/customer_aliases 没有可匹配的名字），"
              "重算只会把所有客户面清空——先去「客户面管理」把客户和别名补齐。")
        return 1
    print(f"客户主数据：{len(matchers)} 条可匹配名字（code / 全称 / 别名）")

    root = ri._snapshot_root()
    q = db.query(models.IssueSnapshot)
    if args.project:
        q = q.filter(models.IssueSnapshot.project == args.project)
    snaps = q.order_by(models.IssueSnapshot.project,
                       models.IssueSnapshot.snapshot_date).all()
    if not snaps:
        print("没有快照可处理。")
        return 0

    moves: Counter = Counter()     # (旧, 新) → 条数
    touched, missing, rows_changed = [], [], 0

    for snap in snaps:
        fp = root / (snap.data_file or "")
        if not snap.data_file or not fp.exists():
            # 元数据在库、明细在文件，两者可能不同步（目录被清理、迁移漏拷）
            missing.append(f"{snap.project} {snap.snapshot_date}")
            continue
        try:
            raw = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            missing.append(f"{snap.project} {snap.snapshot_date}（读不动：{e}）")
            continue

        changed = 0
        for r in raw:
            # 客户面在源数据里本来就没有，一律是标题匹配出来的，所以无条件重算
            old = (r.get("customer") or "").strip()
            new = ri._match_customer(r.get("title", ""), matchers)
            if new != old:
                moves[(old or "（未匹配）", new or "（未匹配）")] += 1
                r["customer"] = new
                changed += 1
        if not changed:
            continue
        rows_changed += changed
        touched.append((snap, fp, raw, changed))

    print(f"\n扫描快照 {len(snaps)} 份，需要改动 {len(touched)} 份、共 {rows_changed} 行。")
    if missing:
        print(f"明细文件缺失/读不动 {len(missing)} 份（跳过）：{', '.join(missing[:5])}"
              + (" …" if len(missing) > 5 else ""))
    if moves:
        print("\n客户面改动汇总（旧 → 新 ： 条数）：")
        for (old, new), cnt in moves.most_common():
            print(f"  {old:<16} → {new:<16} {cnt}")
    if not touched:
        print("\n历史快照的客户面已经是对的，无需修复。 ✔")
        return 0

    if not args.apply:
        print("\n以上仅为预演，未写入任何文件。确认无误后加 --apply 执行。")
        return 0

    for snap, fp, raw, _cnt in touched:
        fp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        # 只重建 customer 这一维，group / severity 没变
        db.query(models.IssueSnapshotStat).filter(
            models.IssueSnapshotStat.snapshot_id == snap.id,
            models.IssueSnapshotStat.dimension == "customer",
        ).delete(synchronize_session=False)
        for key, cnt in ri._count_by(raw, "customer").items():
            db.add(models.IssueSnapshotStat(
                snapshot_id=snap.id, dimension="customer", dim_key=key, count=cnt,
            ))
    db.commit()
    print(f"\n已写回：{len(touched)} 份快照明细 + 对应的客户面趋势数字。")
    print("新增/解决差分（issue_snapshot_flows）按缺陷编号算，与客户面无关，未改动。")
    print("data/issue_excel/ 下的历史 Excel 备份是当天存档，未改写；需要的话在页面上重新导出。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
