"""历史快照的 DI 加权分回算。

`issue_snapshot_stats.score`（DI：致命10 严重3 一般1 提示0.1）是后加的列，
在那之前采集的快照只存了条数。那些行的 score 是 NULL——**NULL 不是 0 分，
是"这份快照压根没算过"**，接口会把这些日期列进 `di_missing_dates`，
页面上明说还没回算，趋势图那一段断开而不是贴着零轴画一条直线。

明细 JSON 还在的话 DI 完全补得回来：严重程度是采集时就落在明细里的字段，
不像客户面/所属小组那样要靠匹配推导，所以这个脚本**不改明细文件一个字**，
只把库里的 score 补上。

    python scripts/backfill_issue_di.py                     # 只读预演，不写库
    python scripts/backfill_issue_di.py --project YLS3000    # 只看某个项目
    python scripts/backfill_issue_di.py --force              # 连已有 DI 的也重算
    python scripts/backfill_issue_di.py --apply              # 真的写回

默认**只补 NULL 的**：已经算过的那些是采集当天按当时明细算的，重算等于用今天的
明细去覆盖当天的结论。只有在改过权重表之后才该加 --force。

改动前请先备份：cp app.db app.db.bak
"""
import argparse
import json
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


def _session(db_path: pathlib.Path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(f"sqlite:///{db_path}")
    return sessionmaker(bind=engine, autoflush=False)()


def main() -> int:
    ap = argparse.ArgumentParser(description="回算历史快照的 DI 加权分")
    ap.add_argument("--project", default="", help="只处理这个采集项目")
    ap.add_argument("--force", action="store_true", help="连已经有 DI 的快照也重算")
    ap.add_argument("--apply", action="store_true", help="真的写回（默认只读预演）")
    args = ap.parse_args()

    db_path = BACKEND / "app.db"
    if not db_path.exists():
        print(f"找不到数据库：{db_path}")
        return 1

    import models  # noqa: F401  建立映射
    import routers.issues as ri
    db = _session(db_path)

    q = db.query(models.IssueSnapshot).order_by(
        models.IssueSnapshot.project.asc(), models.IssueSnapshot.snapshot_date.asc())
    if args.project:
        q = q.filter(models.IssueSnapshot.project == args.project)
    snaps = q.all()
    if not snaps:
        print("没有快照可处理。")
        return 0

    root = ri._snapshot_root()
    todo, skipped, missing = [], 0, []
    for snap in snaps:
        stats = (db.query(models.IssueSnapshotStat)
                 .filter(models.IssueSnapshotStat.snapshot_id == snap.id).all())
        if not stats:
            # 空快照没有维度行，DI 天然就是 0，没什么可补的
            continue
        if not args.force and any(st.score is not None for st in stats):
            skipped += 1
            continue
        fp = root / snap.data_file
        if not snap.data_file or not fp.exists():
            # 明细文件不在了（目录被清理 / 迁移漏拷）就补不回来。如实列出来，
            # 别拿 0 填上——那等于把"读不到"记成"没缺陷"。
            missing.append(f"{snap.project} {snap.snapshot_date}")
            continue
        try:
            raw = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            missing.append(f"{snap.project} {snap.snapshot_date}（明细读不出来：{exc}）")
            continue
        di_by_dim = {d: ri.score_by(raw, d) for d in ("group", "customer", "severity")}
        todo.append((snap, stats, di_by_dim, ri.weighted_score(raw)))

    print(f"待回算 {len(todo)} 份快照" + (f"，跳过 {skipped} 份（已有 DI，加 --force 才重算）" if skipped else ""))
    for snap, _stats, _di, total in todo[:20]:
        print(f"  {snap.project} {snap.snapshot_date}  {snap.total} 条 → DI {total}")
    if len(todo) > 20:
        print(f"  …… 另 {len(todo) - 20} 份")
    if missing:
        print(f"\n补不回来的 {len(missing)} 份（明细文件不在了，接口会继续如实报「DI 未回算」）：")
        for m in missing[:20]:
            print(f"  {m}")

    if not todo:
        return 0
    if not args.apply:
        print("\n以上仅为预演，未写入数据库。确认无误后加 --apply 执行。")
        return 0

    for snap, stats, di_by_dim, _total in todo:
        for st in stats:
            # 这一档在明细里没有对应的单（维度取值变过）就落 0.0：
            # 它属于"算过了，是 0 分"，而不是"没算过"。
            st.score = di_by_dim.get(st.dimension, {}).get(st.dim_key, 0.0)
    db.commit()
    print(f"\n已回算 {len(todo)} 份快照的 DI。趋势页刷新即可看到，明细文件一个字没动。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
