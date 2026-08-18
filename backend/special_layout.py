"""专项详情页「版式」解析：把三份 JSON 收敛成一份有序分段清单。

一个专项的页面结构由 special_contents 上的三列共同决定：

    section_order_json    分段顺序        ["goal", "grid:abc", "risks", ...]
    section_config_json   分段标题/启停    {"sections": {"goal": {"title": "...", "enabled": false}}}
    extra_grids_json      自定义分段本体    [{gid, kind: grid/text/images, title, ...}]

三处消费方——详情页、Excel 导出、周报——**必须看到同一个顺序和同一批标题**。
以前导出与周报各自写死「一、目标 / 二、整体进展 / …」，自定义分段只有 Excel 认
且被丢到独立工作表；一旦分段可改名、可停用、可排序，那种写法必然和页面对不上。
所以顺序与标题的解析只留这一份实现，前端 reconcileOrder() 与本模块的
resolve_sections() 规则保持一致（改一处必须改另一处）。

模板（special_templates）也只是往这三列里写一份预设，运行时不依赖模板表：
模板改了、删了，已建专项的版式不受影响。
"""
import json
import uuid
from dataclasses import dataclass
from typing import Any, List, Optional

from enums import (GRID_COL_TYPES, GRID_LIGHT_DEFAULT_OPTIONS,
                   SPECIAL_SECTION_KEYS, SPECIAL_SECTIONS)

# 内置分段 key -> 内容形态，导出/周报按此分派渲染方式
_BUILTIN_KIND = {s["key"]: s["kind"] for s in SPECIAL_SECTIONS}
_BUILTIN_LABEL = {s["key"]: s["label"] for s in SPECIAL_SECTIONS}

# 自定义分段缺标题时的兜底名
_BLOCK_KIND_LABEL = {"grid": "附加表格", "text": "文本框", "images": "图片",
                    "milestones": "里程碑"}


def kind_label(kind: str) -> str:
    """专项 / 攻关：标题里的 {label} 占位符按此替换。"""
    return "攻关" if kind == "assault" else "专项"


def loads(raw: Any, default):
    """容错解析 JSON 列：脏值/空值一律退回默认，不让页面或导出因此 500。"""
    if not raw:
        return default
    try:
        val = json.loads(raw)
    except (ValueError, TypeError):
        return default
    return val if isinstance(val, type(default)) else default


@dataclass
class Section:
    """一个已解析的分段。

    key   内置 key（goal/plan/...）或自定义分段的 "grid:<gid>"
    title 最终标题：分段配置 > 自定义块自带 title > 内置默认名
    kind  内容形态：内置为 text/milestones/image/items/grid；
          自定义为 grid（表格）/ text（富文本）/ images（图片墙）/ milestones（时间轴）
          自定义 milestones 与内置 plan 同形态但不同数据源：前者存在块自己的
          milestones 字段里，后者存 content.milestones_json，一个专项可以两者并存
    block 自定义分段的原始 dict，内置分段为 None
    """
    key: str
    title: str
    kind: str
    block: Optional[dict] = None

    @property
    def is_custom(self) -> bool:
        return self.block is not None


def section_config(content) -> dict:
    """取分段配置里的 sections 映射；老数据（空/脏）返回 {} → 行为与改造前一致。"""
    cfg = loads(getattr(content, "section_config_json", None), {})
    sections = cfg.get("sections")
    return sections if isinstance(sections, dict) else {}


def template_meta(content) -> dict:
    """套用过的模板信息 {template_id, template_name}，仅用于展示。"""
    cfg = loads(getattr(content, "section_config_json", None), {})
    return {
        "template_id": cfg.get("template_id"),
        "template_name": cfg.get("template_name") or "",
    }


def _entry(sections: dict, key: str) -> dict:
    e = sections.get(key)
    return e if isinstance(e, dict) else {}


def default_title(key: str, label: str) -> str:
    """内置分段的默认标题（未被配置覆盖时用）。"""
    return _BUILTIN_LABEL.get(key, key).replace("{label}", label)


def dedupe(keys: List[str]) -> List[str]:
    """保序去重。顺序列里出现重复 key 会让同一分段渲染两次，两端都要防。"""
    seen = set()
    out = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def resolve_order(content) -> List[str]:
    """已存顺序 ∩ 当前实际存在的分段，新增的按默认序补到末尾。

    与前端 reconcileOrder() 同规则：保留已存顺序中仍存在的 key，
    再把新出现的（新增自定义分段、后续版本新增的内置分段）追加在后。
    """
    blocks = loads(getattr(content, "extra_grids_json", None), [])
    all_keys = list(SPECIAL_SECTION_KEYS)
    for b in blocks:
        if isinstance(b, dict) and b.get("gid"):
            all_keys.append(f"grid:{b['gid']}")
    all_keys = dedupe(all_keys)

    saved = loads(getattr(content, "section_order_json", None), [])
    saved = [k for k in saved if isinstance(k, str)]
    kept = dedupe([k for k in saved if k in set(all_keys)])
    keptset = set(kept)
    return kept + [k for k in all_keys if k not in keptset]


def resolve_sections(special, *, include_disabled: bool = False) -> List[Section]:
    """该专项当前的分段清单（默认只含启用的，顺序即页面顺序）。"""
    content = getattr(special, "content", None)
    if content is None:
        return []
    label = kind_label(getattr(special, "kind", "special"))
    sections = section_config(content)
    blocks = loads(getattr(content, "extra_grids_json", None), [])
    by_gid = {str(b["gid"]): b for b in blocks
              if isinstance(b, dict) and b.get("gid")}

    out: List[Section] = []
    for key in resolve_order(content):
        entry = _entry(sections, key)
        # enabled 缺省视为启用：老数据与后续新增的内置分段都不该凭空消失
        if not include_disabled and entry.get("enabled") is False:
            continue
        cfg_title = str(entry.get("title") or "").strip()
        if key.startswith("grid:"):
            block = by_gid.get(key[5:])
            if block is None:
                continue  # 顺序里残留的已删分段
            bkind = block.get("kind") or "grid"
            title = (cfg_title or str(block.get("title") or "").strip()
                     or _BLOCK_KIND_LABEL.get(bkind, "分段"))
            out.append(Section(key=key, title=title, kind=bkind, block=block))
        else:
            if key not in _BUILTIN_KIND:
                continue  # 未知 key（老库脏数据 / 降级回滚）
            out.append(Section(key=key, title=cfg_title or default_title(key, label),
                               kind=_BUILTIN_KIND[key]))
    return out


# ─── 模板套用 ──────────────────────────────────────────────────────────────

DEFAULT_COL_W = 130


def _norm_header(h) -> dict:
    if isinstance(h, dict):
        return {"text": str(h.get("text", "")),
                "colspan": max(1, int(h.get("colspan") or 1)),
                "align": h.get("align") or "center"}
    return {"text": str(h or ""), "colspan": 1, "align": "center"}


def _blank_cell() -> dict:
    return {"text": "", "align": "left", "color": "", "bold": False}


def _instantiate_block(tpl_block: dict, gid: str) -> dict:
    """模板里的分段定义 → 挂到具体专项上的分段实例。

    只搬「版式」（标题、表头、列格式），行数据一律留空：模板不带业务数据。
    前端 normBlock() 还会再规范化一遍，这里只需产出结构完整的对象。
    """
    kind = tpl_block.get("kind") or "grid"
    tkey = str(tpl_block.get("tkey") or "")
    base = {"gid": gid, "kind": kind, "tkey": tkey,
            "title": str(tpl_block.get("title") or "")}
    if kind == "text":
        base["html"] = ""
        return base
    if kind == "images":
        base["items"] = []
        return base
    if kind == "milestones":
        base["milestones"] = []
        return base

    headers = [_norm_header(h) for h in (tpl_block.get("headers") or [])]
    if not headers:
        headers = [_norm_header("列1"), _norm_header("列2")]
    ncol = sum(h["colspan"] for h in headers)

    def _align(seq, filler):
        seq = list(seq or [])
        if len(seq) < ncol:
            seq += [filler() for _ in range(ncol - len(seq))]
        return seq[:ncol]

    types = _align([t if t in GRID_COL_TYPES else "text"
                    for t in (tpl_block.get("colTypes") or [])], lambda: "text")
    options = _align([[str(x) for x in (o or [])] if isinstance(o, list) else []
                      for o in (tpl_block.get("colOptions") or [])], list)
    # 点灯列没配候选项时给一份默认红黄绿，省得建完还要手填
    for i, t in enumerate(types):
        if t == "light" and not options[i]:
            options[i] = list(GRID_LIGHT_DEFAULT_OPTIONS)
    widths = _align([int(w) or DEFAULT_COL_W for w in (tpl_block.get("colWidths") or [])],
                    lambda: DEFAULT_COL_W)

    # 模板用 row_count（预留几行空行），而不是 rows——rows 在真实分段里是单元格
    # 二维数组，两边同名会让「把现成分段存成模板」这种操作静默出错
    try:
        nrows = max(0, min(20, int(tpl_block.get("row_count", 2))))
    except (TypeError, ValueError):
        nrows = 2
    base.update({"headers": headers,
                 "rows": [[_blank_cell() for _ in range(ncol)] for _ in range(nrows)],
                 "colWidths": widths, "colTypes": types, "colOptions": options})
    return base


def apply_template(content, template) -> dict:
    """把模板版式写进 content 的三列（调用方负责 version += 1 与 commit）。

    **只增不删**：模板里没有的既有自定义分段保留、既有分段的行数据一律不动。
    版式是配置，填在里面的内容不是——套模板不该顺带具备删数据的能力
    （见 CLAUDE.md 的删除权限口径：别人长期跟踪的记录要拦）。
    重复套同一模板是幂等的：按 tkey 认领已挂上的分段，不会越套越多。

    返回 {"added": 新增分段数, "reused": 复用分段数} 供接口回话与审计。
    """
    layout = loads(getattr(template, "layout_json", None), {})
    tpl_order = [k for k in (layout.get("order") or []) if isinstance(k, str)]
    tpl_config = layout.get("config") if isinstance(layout.get("config"), dict) else {}
    tpl_blocks = [b for b in (layout.get("blocks") or []) if isinstance(b, dict)]

    blocks = [b for b in loads(getattr(content, "extra_grids_json", None), [])
              if isinstance(b, dict)]
    by_tkey = {str(b.get("tkey")): b for b in blocks if b.get("tkey")}

    added = reused = 0
    tkey_to_gid = {}
    for tb in tpl_blocks:
        tkey = str(tb.get("tkey") or "").strip()
        if not tkey:
            continue
        exist = by_tkey.get(tkey)
        if exist is not None and exist.get("gid"):
            tkey_to_gid[tkey] = str(exist["gid"])
            reused += 1
            continue
        gid = uuid.uuid4().hex[:10]
        blocks.append(_instantiate_block(tb, gid))
        tkey_to_gid[tkey] = gid
        added += 1

    # 顺序：模板顺序在前（tpl:<tkey> 换成实际 grid:<gid>），模板未提及的既有分段补在后
    order: List[str] = []
    for key in tpl_order:
        if key.startswith("tpl:"):
            gid = tkey_to_gid.get(key[4:])
            if gid:
                order.append(f"grid:{gid}")
        elif key in SPECIAL_SECTION_KEYS:
            order.append(key)
    order = dedupe(order)
    covered = set(order)
    for key in list(SPECIAL_SECTION_KEYS) + [f"grid:{b['gid']}" for b in blocks if b.get("gid")]:
        if key not in covered:
            order.append(key)

    # 分段配置：模板提到的键以模板为准，没提到的保留该专项原有设置
    cfg = loads(getattr(content, "section_config_json", None), {})
    sections = cfg.get("sections") if isinstance(cfg.get("sections"), dict) else {}
    merged = dict(sections)
    for key, entry in tpl_config.items():
        if key in SPECIAL_SECTION_KEYS and isinstance(entry, dict):
            merged[key] = {"title": str(entry.get("title") or "").strip(),
                           "enabled": entry.get("enabled") is not False}

    content.extra_grids_json = json.dumps(blocks, ensure_ascii=False)
    content.section_order_json = json.dumps(dedupe(order), ensure_ascii=False)
    content.section_config_json = json.dumps(
        {"template_id": getattr(template, "id", None),
         "template_name": getattr(template, "name", "") or "",
         "sections": merged},
        ensure_ascii=False,
    )
    return {"added": added, "reused": reused}


def builtin_registry(label: str = "专项") -> List[dict]:
    """内置分段清单，给模板编辑页列选项用。"""
    return [{"key": s["key"], "kind": s["kind"],
             "default_title": s["label"].replace("{label}", label)}
            for s in SPECIAL_SECTIONS]
