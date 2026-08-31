"""历史快照的「客户面 / 所属小组」重算：把被短名字吃掉的那些行改回来。

这两列都不是问题单自带的，是采集时由后端**匹配出来的**，而匹配过去都是朴素的子串包含：

- 客户面（`_match_customer`）从标题里认客户主数据。`"1号机" in "11号机"` 是真的
  （从第二个字符起就是），于是「11号机」的单会落到「1号机」那一档。
- 所属小组（`_match_group`）从责任人姓名认配置里的小组名单。同理「张伟」会认走
  「张伟明」的单——名单里根本没有张伟明，他的单却被记进了张伟所在的组。

两种错的共同点是**数字都还对得上**：两台机器的单混进一行、同一台机器的单散在两行、
组级负载偏一点——每一份单独看都挺正常，没人会当 bug 报上来。采集侧已经各加了一道边界，
但**已经落盘的快照不会自己重算**，趋势图与历史交叉表里那段仍然是错的。

本脚本按当前的匹配规则（直接 import `routers.issues`，规则只有一份）重算每份快照明细里
的 `customer` / `group` 字段，并重建 `issue_snapshot_stats` 里对应维度的数字。

三件事**不动**：
- `issue_snapshot_flows`（新增/解决差分）按缺陷编号算，与这两列无关，重算它反而会
  凭空造出一批假新增/假解决；
- 明细里的其它字段（责任人本身、部门、严重程度）——只改由匹配推导出来的两列；
- `data/issue_excel/` 下的历史 Excel 备份，那是当天的存档，重写等于篡改历史。
  需要的话重算后在页面上重新导出。

    python scripts/repair_issue_dimensions.py                    # 只读预演，不动任何文件
    python scripts/repair_issue_dimensions.py --project YLS3000  # 只看某个项目
    python scripts/repair_issue_dimensions.py --only group       # 只重算一个维度
    python scripts/repair_issue_dimensions.py --apply            # 真的写回

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
    ap = argparse.ArgumentParser(description="重算历史快照的客户面 / 所属小组")
    ap.add_argument("--db", default=str(BACKEND / "app.db"), help="app.db 路径")
    ap.add_argument("--project", default="", help="只处理这个项目（默认全部）")
    ap.add_argument("--only", choices=["customer", "group"], default="",
                    help="只重算一个维度（默认两个都算）")
    ap.add_argument("--apply", action="store_true", help="真的写回；默认只读预演")
    args = ap.parse_args()

    db_path = pathlib.Path(args.db)
    if not db_path.exists():
        print(f"找不到数据库：{db_path}")
        return 1

    import models
    import routers.issues as ri

    db = _session(db_path)
    want_customer = args.only in ("", "customer")
    want_group = args.only in ("", "group")

    # 两个维度各有一份「基准数据」，缺了就不能重算——把整列清空比留着旧数据更糟。
    matchers = ri._load_customer_matchers(db) if want_customer else []
    if want_customer and not matchers:
        print("客户主数据是空的（customers / customer_aliases 里没有可匹配的名字），"
              "重算只会把客户面整列清空——先去「客户面管理」把客户和别名补齐。")
        return 1
    groups = ri._load_issue_groups(ri._load_config()) if want_group else []
    if want_group and not groups:
        print("配置里一个小组都没有（config.issue_groups 为空），重算只会把小组整列"
              "清空——先去「问题单管理 → 配置」把小组名单补齐。")
        return 1
    if want_customer:
        print(f"客户主数据：{len(matchers)} 条可匹配名字（code / 全称 / 别名）")
    if want_group:
        print(f"小组名单：{len(groups)} 个组、"
              f"{sum(len(m) for _, m in groups)} 个人")

    root = ri._snapshot_root()
    q = db.query(models.IssueSnapshot)
    if args.project:
        q = q.filter(models.IssueSnapshot.project == args.project)
    snaps = q.order_by(models.IssueSnapshot.project,
                       models.IssueSnapshot.snapshot_date).all()
    if not snaps:
        print("没有快照可处理。")
        return 0

    moves = {"customer": Counter(), "group": Counter()}   # (旧, 新) → 条数
    touched, missing = [], []
    rows_changed = {"customer": 0, "group": 0}

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

        dims = set()
        for r in raw:
            # 这两列在源数据里本来就没有，一律是匹配出来的，所以无条件重算
            if want_customer:
                old = (r.get("customer") or "").strip()
                new = ri._match_customer(r.get("title", ""), matchers)
                if new != old:
                    moves["customer"][(old or "（未匹配）", new or "（未匹配）")] += 1
                    rows_changed["customer"] += 1
                    r["customer"] = new
                    dims.add("customer")
            if want_group:
                old = (r.get("group") or "").strip()
                new = ri._match_group(r.get("owner", ""), groups) or ri.UNGROUPED_GROUP
                if new != old:
                    moves["group"][(old or "（空）", new)] += 1
                    rows_changed["group"] += 1
                    r["group"] = new
                    dims.add("group")
        if dims:
            touched.append((snap, fp, raw, dims))

    total_rows = rows_changed["customer"] + rows_changed["group"]
    print(f"\n扫描快照 {len(snaps)} 份，需要改动 {len(touched)} 份："
          f"客户面 {rows_changed['customer']} 行、所属小组 {rows_changed['group']} 行。")
    if missing:
        print(f"明细文件缺失/读不动 {len(missing)} 份（跳过）：{', '.join(missing[:5])}"
              + (" …" if len(missing) > 5 else ""))
    for dim, label in (("customer", "客户面"), ("group", "所属小组")):
        if moves[dim]:
            print(f"\n{label}改动汇总（旧 → 新 ： 条数）：")
            for (old, new), cnt in moves[dim].most_common():
                print(f"  {old:<16} → {new:<16} {cnt}")
    if not touched:
        scope = "客户面 / 所属小组" if not args.only else \
            ("客户面" if args.only == "customer" else "所属小组")
        print(f"\n历史快照的{scope}已经是对的，无需修复。 ✔")
        return 0
    if moves["group"]:
        print(f"\n注意：转到「{ri.UNGROUPED_GROUP}」的行不是丢了，是名单里没有这个人——"
              "在「问题单管理 → 配置」的未归组责任人里能看到，补完名单再跑一次即可。")

    if not args.apply:
        print(f"\n以上仅为预演（共 {total_rows} 行），未写入任何文件。"
              "确认无误后加 --apply 执行。")
        return 0

    for snap, fp, raw, dims in touched:
        fp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        # 只重建真的变了的维度，severity 没动就别去碰它的数字
        for dim in dims:
            db.query(models.IssueSnapshotStat).filter(
                models.IssueSnapshotStat.snapshot_id == snap.id,
                models.IssueSnapshotStat.dimension == dim,
            ).delete(synchronize_session=False)
            for key, cnt in ri._count_by(raw, dim).items():
                db.add(models.IssueSnapshotStat(
                    snapshot_id=snap.id, dimension=dim, dim_key=key, count=cnt,
                ))
    db.commit()
    print(f"\n已写回：{len(touched)} 份快照明细 + 对应的趋势数字（共 {total_rows} 行）。")
    print("新增/解决差分（issue_snapshot_flows）按缺陷编号算，与这两列无关，未改动。")
    print("data/issue_excel/ 下的历史 Excel 备份是当天存档，未改写；需要的话在页面上重新导出。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
