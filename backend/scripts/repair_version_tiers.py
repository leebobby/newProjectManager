"""版本三层体检 / 修复：把没挂上「版本」的迭代版本重新接回去。

背景：0010 迁移把两层劈成三层。它的数据回填有一道守卫——`release_versions`
非空就整段跳过（当时是为了重跑幂等）。这道守卫在**上一次迁移跑了一半**的库上会反过来
咬人：ADD COLUMN 已经落地、部分 release_versions 已经生成，于是重跑时直接跳过，
剩下的 `iteration_versions` 永远停在 `release_version_id IS NULL`。
这些行在页面上是不可见的（详情走 大版本 → 版本 → 迭代版本 三层嵌套），
看起来就像「版本信息全丢了，只剩第一层」——但数据都还在库里。

本脚本按 0010 完全相同的劈分规则（直接 import 那个迁移文件，避免两份规则漂移），
只处理**还没挂上版本**的迭代行，因此可以反复跑。

    python scripts/repair_version_tiers.py                 # 只读体检，不动库
    python scripts/repair_version_tiers.py --apply         # 执行修复
    python scripts/repair_version_tiers.py --db /path/app.db --apply

改库前请先备份：cp app.db app.db.bak（或 sqlite3 app.db ".backup app.db.bak"）。
"""
import argparse
import importlib.util
import pathlib
import sqlite3
import sys

BACKEND = pathlib.Path(__file__).resolve().parent.parent
_MIG = BACKEND / "alembic" / "versions" / "0010_version_three_tier.py"


def _load_split():
    """直接用 0010 里的 _split / _natural_key，规则只有一份。"""
    spec = importlib.util.spec_from_file_location("mig0010", _MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._split


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def main() -> int:
    ap = argparse.ArgumentParser(description="版本三层体检 / 修复")
    ap.add_argument("--db", default=str(BACKEND / "app.db"), help="SQLite 库路径，默认 backend/app.db")
    ap.add_argument("--apply", action="store_true", help="真的写库（不加就只体检）")
    args = ap.parse_args()

    path = pathlib.Path(args.db)
    if not path.exists():
        print(f"找不到数据库：{path}")
        return 2

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    tables = _tables(conn)

    missing = [t for t in ("major_versions", "iteration_versions", "release_versions")
               if t not in tables]
    if missing:
        print(f"缺表：{'、'.join(missing)}。先让后端正常启动一次（create_all 会建表），再跑本脚本。")
        return 2
    if "release_version_id" not in _cols(conn, "iteration_versions"):
        print("iteration_versions 还没有 release_version_id 列 —— 0010 迁移根本没跑成。\n"
              "先执行 alembic upgrade head 看报什么错，再回来跑本脚本。")
        return 2

    ver = conn.execute("SELECT version_num FROM alembic_version").fetchone()
    n_major = conn.execute("SELECT COUNT(*) FROM major_versions").fetchone()[0]
    n_rel = conn.execute("SELECT COUNT(*) FROM release_versions").fetchone()[0]
    n_iter = conn.execute("SELECT COUNT(*) FROM iteration_versions").fetchone()[0]
    n_orphan = conn.execute(
        "SELECT COUNT(*) FROM iteration_versions WHERE release_version_id IS NULL").fetchone()[0]

    split = _load_split()
    ref_tables = [t for t in ("iteration_requirements", "iteration_product_requirements")
                  if t in tables]

    # 「它本身其实是一个版本」的冗余行：没有 B<数字> 后缀的迭代行。
    # 0010 迁移日志里那个「因仍被需求引用而保留 K 条」说的就是它们，这里重新算一遍——
    # 迁移只在第一次追平时打印，日志滚掉就抓不到了。
    redundant_drop, redundant_keep = [], []
    for it in conn.execute(
        "SELECT iv.id, iv.version_no, mv.version_no AS major_no FROM iteration_versions iv "
        "JOIN major_versions mv ON mv.id = iv.major_version_id ORDER BY iv.id"
    ):
        _base, is_release = split(it["version_no"], it["major_no"])
        if not is_release:
            continue
        refs = sum(conn.execute(
            f"SELECT COUNT(*) FROM {t} WHERE target_version_id = ?", (it["id"],)
        ).fetchone()[0] for t in ref_tables)
        (redundant_keep if refs else redundant_drop).append(dict(it))

    print("── 体检 ──────────────────────────────────────────")
    print(f"库                : {path}")
    print(f"alembic 版本      : {ver['version_num'] if ver else '（未被 alembic 跟踪）'}")
    print(f"大版本            : {n_major}")
    print(f"版本              : {n_rel}")
    print(f"迭代版本          : {n_iter}，其中**没挂上版本**的 {n_orphan} 条")
    print(f"「本身就是版本」的冗余行: {len(redundant_drop) + len(redundant_keep)} 条"
          f"（可清理 {len(redundant_drop)}，被需求引用需人工处理 {len(redundant_keep)}）")
    for it in redundant_keep[:10]:
        print(f"    ! {it['major_no']} / {it['version_no']} —— 仍被需求的计划交付版本引用")
    if len(redundant_keep) > 10:
        print(f"    …… 另外 {len(redundant_keep) - 10} 条")

    if n_orphan == 0 and n_rel and not redundant_drop:
        print("\n三层都挂好了，也没有可清理的冗余行。"
              + ("\n仍有被引用的冗余行需要人工在页面上确认（见上面的 ! 行）。"
                 if redundant_keep else "")
              + "\n页面上看不到版本的话，问题不在数据。")
        return 0
    if n_iter == 0 and n_rel == 0:
        print("\n迭代版本表本身就是空的——这不是「挂丢了」，是库里确实没有这层数据。")
        return 0

    plan_new, plan_link = [], []
    for m in conn.execute("SELECT id, version_no FROM major_versions ORDER BY sort_order, id"):
        iters = conn.execute(
            "SELECT id, version_no, title, planned_date, sort_order FROM iteration_versions "
            "WHERE major_version_id = ? AND release_version_id IS NULL ORDER BY sort_order, id",
            (m["id"],)).fetchall()
        if not iters:
            continue
        # 已有的版本先认领，避免重复建号
        have = {r["version_no"]: r["id"] for r in conn.execute(
            "SELECT id, version_no FROM release_versions WHERE major_version_id = ?", (m["id"],))}
        seen_new = {}
        for it in iters:
            base, _is_release = split(it["version_no"], m["version_no"])
            if base in have:
                rid = have[base]
            elif base in seen_new:
                rid = seen_new[base]
            else:
                rid = None
                seen_new[base] = None
                plan_new.append((m["id"], m["version_no"], base, it))
            plan_link.append((it, m["version_no"], base, rid))

    print("\n── 修复方案 ──────────────────────────────────────")
    print(f"新建版本          : {len(plan_new)} 个")
    for _, mno, base, _ in plan_new[:20]:
        print(f"    {mno} → {base}")
    if len(plan_new) > 20:
        print(f"    …… 另外 {len(plan_new) - 20} 个")
    print(f"重新挂上的迭代版本: {len(plan_link)} 条")
    print(f"删除的冗余行      : {len(redundant_drop)} 条（它本身就是一个版本，且没有需求引用它）")
    print(f"保留待人工处理    : {len(redundant_keep)} 条（仍被需求的计划交付版本引用，"
          f"删了会丢别人填的数据）")

    if not args.apply:
        print("\n以上只是预演，没有改动任何数据。确认无误后加 --apply 执行（务必先备份 app.db）。")
        return 0

    # ── 执行 ──────────────────────────────────────────────
    cur = conn.cursor()
    rid_cache = {}
    for mid, _mno, base, src in plan_new:
        cur.execute(
            "INSERT INTO release_versions (major_version_id, version_no, title, description, "
            " planned_date, actual_release_date, sort_order, created_at, updated_at) "
            "VALUES (?, ?, '', '', NULL, NULL, "
            "        (SELECT COALESCE(MAX(sort_order) + 1, 0) FROM release_versions WHERE major_version_id = ?), "
            "        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (mid, base, mid))
        rid_cache[(mid, base)] = cur.lastrowid

    linked = 0
    for it, _mno, base, rid in plan_link:
        mid = cur.execute("SELECT major_version_id FROM iteration_versions WHERE id = ?",
                          (it["id"],)).fetchone()[0]
        target = rid or rid_cache.get((mid, base))
        if target is None:
            target = cur.execute(
                "SELECT id FROM release_versions WHERE major_version_id = ? AND version_no = ?",
                (mid, base)).fetchone()[0]
        cur.execute("UPDATE iteration_versions SET release_version_id = ? WHERE id = ?",
                    (target, it["id"]))
        linked += 1

    for it in redundant_drop:
        cur.execute("DELETE FROM iteration_versions WHERE id = ?", (it["id"],))

    conn.commit()
    left = conn.execute(
        "SELECT COUNT(*) FROM iteration_versions WHERE release_version_id IS NULL").fetchone()[0]
    print(f"\n已修复：新建版本 {len(rid_cache)} 个，挂回迭代版本 {linked} 条，"
          f"删除冗余行 {len(redundant_drop)} 条，保留 {len(redundant_keep)} 条。")
    print(f"剩余未挂上的迭代版本：{left} 条" + ("（应该是 0）" if left else " ✔"))
    print("重启后端即可在页面上看到三层。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
