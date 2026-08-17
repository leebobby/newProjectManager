#!/usr/bin/env python
"""按项目拉取问题单（YLS3000 / YLS5000 / YLS8000）+ 数据梳理。

供「问题单管理」的 API 方式调用。后端以 `python fetch_issues_api.py <PROJECT>` 运行，本脚本：
  1) 调 DTS(queryList) 拉该项目全部缺陷（自动翻页）；
  2) 清洗去重、把嵌套对象字段拍平、从「缺陷业务编号」提取年/月/日、按「标题」关键词分类；
  3) 把结果以 **JSON 数组** 打印到 stdout，字段＝后端「原始数据」表（英文键）。

────────────────────────────────────────────────────────────────────────────
已按你调通的脚本接好 DTS(queryList)：POST，pbiName 走 URL，返回体 data.data 是记录、
data.total 是总数，自动翻页；字段值里的嵌套对象会自动拍平（取 cnName/codeName/realName…）。

日常你通常只需更新**凭证**：顶部 API_HEADERS 里的 Cookie（会话会过期）/ X-HW-APPKEY，
建议设环境变量 ISSUE_API_COOKIE / ISSUE_API_APPKEY / ISSUE_API_HWID，就不必改代码。

排障：`python fetch_issues_api.py YLS3000 --peek` —— 打印 HTTP 状态 / 总数 / 首条记录字段名 / 原文片段。
若某项目报「You do not have the permission…」= 你的账号对该产品没查询权限（换有权限的项目）。
────────────────────────────────────────────────────────────────────────────
"""
import json
import os
import sys

# 已接入真实 DTS API。若想先用示例数据跑通页面/链路，把这里改回 True
USE_SAMPLE = False


# ════════════════════════════════════════════════════════════════════════════
#  ★★★  API 接入配置（已按 DTS queryList 接好）：日常只需更新凭证  ★★★
# ════════════════════════════════════════════════════════════════════════════

# 接口地址（POST）；pbiName 拼在 URL 上（与你调通的脚本一致）
API_URL = os.environ.get(
    "ISSUE_API_URL",
    "https://apig.sicarrier.com/api/dtsService/apig/dts/queryList",
)

# ⚠️ 认证头是**明文凭证**：Cookie(会话)会过期，失效后更新；上线建议改环境变量（已留 env 回退）。
API_HEADERS = {
    "X-HW-ID":      os.environ.get("ISSUE_API_HWID",   "acc90a5778b04aad90a1509c66220042"),
    "X-HW-APPKEY":  os.environ.get("ISSUE_API_APPKEY", "yLF1HruQhOqFoBtmuwAWfw=="),
    "x-app-id":     os.environ.get("ISSUE_API_HWID",   "acc90a5778b04aad90a1509c66220042"),
    "Content-Type": "application/json",
    "Cookie":       os.environ.get("ISSUE_API_COOKIE", "prod_J_SESSION_ID=3bf42a272adba85f3f09f85aa17911bda5b678ddd5a3500e"),
}

PAGE_SIZE = 200   # 每页条数；按 data.total 自动翻页拉全

# 每个项目 → pbiName（产品基线名）。注意：账号对哪些产品有权限由后端授权决定
PROJECT_PARAMS = {
    "YLS3000": {"pbiName": "YLS3000 V100R001C00"},
    "YLS5000": {"pbiName": "YLS5000 V100R001C00"},
    "YLS8000": {"pbiName": "YLS8000 V100R001C00"},
}


def fetch_from_api(project: str) -> list:
    """调 DTS queryList 拉该项目全部缺陷（自动翻页），返回 list[dict]（平台原始记录）。"""
    try:
        import requests  # 若报「No module named requests」：pip install requests
    except ImportError:
        raise RuntimeError("缺少 requests，请先 `pip install requests`")

    pbi = PROJECT_PARAMS.get(project, {}).get("pbiName") or f"{project} V100R001C00"
    full_url = f"{API_URL}?pbiName={pbi}"

    def _page(page_no: int) -> dict:
        resp = requests.post(
            full_url,
            headers=API_HEADERS,
            data=json.dumps({"pageSize": str(PAGE_SIZE), "pageNo": str(page_no)}),
            timeout=60,
            # 若报 SSL 证书错误（内网自签），临时加上：verify=False
        )
        resp.raise_for_status()
        return resp.json()

    body = _page(1)
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        # data=null 一般是无权限/无数据；把服务端 message 抛出来，便于页面看到原因
        msg = body.get("message") if isinstance(body, dict) else str(body)[:200]
        raise RuntimeError(f"DTS 接口未返回数据（{msg or '结构异常'}）")

    total = int(data.get("total") or 0)
    rows = list(data.get("data") or [])
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total else 1
    for page in range(2, total_pages + 1):
        d = (_page(page).get("data") or {})
        rows.extend(d.get("data") or [])

    # pbiName 即版本信息：给每条补上「版本信息」字段（DTS 原本没有独立 version 时兜底）
    for r in rows:
        if isinstance(r, dict):
            r.setdefault("版本信息", pbi)
    return rows


# 平台原始字段名 → 中文标准字段名（★ 已按你调通脚本的 DTS 字段名对齐）
#   customer(客户面) DTS 字段名未知——用 --peek 看到后把左边补上，"按客户面"维度即生效。
FIELD_MAPPING = {
    "businessNo":            "缺陷业务编号",
    "title":                 "标题",
    "responsibleUser":       "当前责任人",
    "responsibleDepartment": "责任人部门",   # 部门过滤用；「小组」由后端按成员名单归组，不在此映射
    "featureReal":           "特性",
    "subSystemReal":         "子系统",
    "moduleReal":            "模块",
    "progress":              "进展",
    "severity":              "严重程度",
    # 客户面(customer)不在此映射：由后端从标题匹配客户主数据（客户面管理）得到。
    # 其它字段 DTS 里若有对应字段，把左边键名补上即可（没有就留空，不影响主流程）：
    # "priority": "优先级", "xxxDi": "严重程度DI值", "rootCause": "根因",
    # "solution": "解决措施", "progressRecord": "进展记录", "planCloseTime": "预计闭环时间",
}

# ════════════════════════════════════════════════════════════════════════════
#  ↓↓↓  以下为标准化处理，通常无需改动  ↓↓↓
# ════════════════════════════════════════════════════════════════════════════

# DTS 字段值常是嵌套对象，按优先级从中取「显示名」（移植自你调通脚本的 DISPLAY_KEYS）
_DISPLAY_KEYS = ["codeName", "cnName", "realName", "displayName", "name", "userName",
                 "lastName", "employeeName", "desc", "label", "value", "text", "cName"]


def _extract_value(val):
    """把 DTS 字段值（可能是对象/数组/标量）拍平成可读文本。"""
    if val is None:
        return ""
    if isinstance(val, bool):
        return "是" if val else "否"
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, dict):
        for k in _DISPLAY_KEYS:
            if k in val and val[k] not in (None, ""):
                return str(val[k])
        return json.dumps(val, ensure_ascii=False)
    if isinstance(val, list):
        parts = [str(_extract_value(x)) for x in val]
        return ", ".join(p for p in parts if p)
    return val


def _clean_text(val):
    import re
    if isinstance(val, str):
        val = re.sub(r"<[^>]+>", "", val)
        val = val.replace("\xa0", " ").replace("\n", " ").replace("\r", " ").replace("\t", " ")
        val = re.sub(r"\s+", " ", val).strip()
    return val


def _flat(val):
    """字段值拍平 + 清洗，得到干净文本（数字保持数字）。"""
    return _clean_text(_extract_value(val))


# 关键词 → 分类；未命中归入 DEFAULT_CATEGORY
CATEGORIES = {
    "PXW": ["830", "pxw", "pst"],
    "RBPS": ["rbps"],
    "出厂测试": ["出厂测试", "factory_test"],
}
DEFAULT_CATEGORY = "研发"

# 中文标准字段 → 后端「原始数据」表英文键（后端 _RAW_COLS 的键，勿改）
CN_TO_EN = {
    "版本信息": "version", "缺陷业务编号": "issue_id", "标题": "title",
    "当前责任人": "owner", "当前责任人所属小组": "group", "进展": "progress",
    "严重程度": "severity", "严重程度DI值": "severity_di", "根因": "root_cause",
    "解决措施": "solution", "进展记录": "progress_record",
    "预计闭环时间": "estimated_close", "优先级": "priority", "客户面": "customer",
    "责任人部门": "department", "特性": "feature", "子系统": "subsystem", "模块": "module",
}


def _to_standard(rec: dict) -> dict:
    """把一条记录规整成「中文标准字段」（值统一拍平），兼容三种来源键：
      ① 平台原始字段名（走 FIELD_MAPPING 映射）
      ② 记录本身已是中文标准名
      ③ 记录本身已是英文标准键（version/issue_id/...）
    """
    std = {}
    for raw_key, cn in FIELD_MAPPING.items():
        if raw_key in rec and rec[raw_key] is not None:
            std[cn] = _flat(rec[raw_key])
    for cn in CN_TO_EN:
        if cn in rec and rec[cn] is not None and cn not in std:
            std[cn] = _flat(rec[cn])
    for cn, en in CN_TO_EN.items():
        if en in rec and rec[en] is not None and cn not in std:
            std[cn] = _flat(rec[en])
    return std


# 责任人部门可能落在不同层级字段里，全部拼进 dept_path 供后端部门过滤匹配（移植自你调通脚本）
_DEPT_FIELDS = [
    "responsibleDepartment", "responsibleHigherlevelDepartment",
    "responsibleLevelOneDepartment", "responsibleLevelTwoDepartment",
    "responsibleLevelThreeDepartment", "responsibleLevelFourDepartment",
]


def _classify(title: str) -> str:
    t = (title or "").lower()
    for cat, kws in CATEGORIES.items():
        for kw in kws:
            if kw.lower() in t:
                return cat
    return DEFAULT_CATEGORY


def _process(records: list) -> list:
    """清洗去重 + 提取日期维度 + 标题分类。"""
    out, seen = [], set()
    for rec in records:
        if not isinstance(rec, dict):
            continue
        std = _to_standard(rec)
        did = str(std.get("缺陷业务编号", "") or "").strip()
        if not did or did in seen:           # 去空 + 按编号去重
            continue
        seen.add(did)

        is_sdts = did.startswith("SDTS")     # 编号格式 SDTS+年(4)+月(2)+日(2)+序号
        year = did[4:8] if is_sdts else ""
        month = did[8:10] if is_sdts else ""
        day = did[10:12] if is_sdts else ""

        row = {en: str(std.get(cn, "") or "").strip() for cn, en in CN_TO_EN.items()}
        row["is_sdts"] = "是" if is_sdts else ""
        row["year"] = year
        row["month"] = month
        row["date"] = day
        row["year_month"] = f"{year}-{month}" if is_sdts else ""
        row["category"] = _classify(row.get("title", ""))
        # 部门全路径（各级部门去重拼接）——供后端「按部门统计」匹配，兼容部门落在上级字段
        parts = [str(_flat(rec.get(f))).strip() for f in _DEPT_FIELDS if rec.get(f)]
        row["dept_path"] = " / ".join(dict.fromkeys(p for p in parts if p))
        out.append(row)
    return out


def _sample(project: str) -> list:
    """示例数据：SDTS 编号 + 含关键词标题 + 客户面，便于看到分组/客户面/趋势生效。

    数量随「当天」小幅波动（按日期取模），这样连续几天采集能看到趋势折线有变化。
    """
    import datetime as _dt
    sev = ["严重", "一般", "提示"]
    teams = ["AFK", "SE", "TFO"]
    customers = ["华东-A厂", "华南-B厂", "华北-C厂"]
    titles = ["[示例]PXW 830 偶发停机", "[示例]RBPS 流程异常",
              "[示例]出厂测试 用例失败", "[示例]在线分析卡顿"]
    n = 15 + (_dt.date.today().day % 6)   # 15~20 条，随日变化
    out = []
    for i in range(1, n + 1):
        did = f"SDTS2026{((i % 6) + 1):02d}{((i % 27) + 1):02d}{i:03d}"
        out.append({
            "版本信息": project, "缺陷业务编号": did, "标题": titles[i % len(titles)],
            "当前责任人": "张三", "当前责任人所属小组": teams[i % 3],
            "客户面": customers[i % len(customers)],
            "进展": "处理中", "严重程度": sev[i % 3],
        })
    return out


def _write(obj, indent=None):
    # 直接写 UTF-8 字节，避免 Windows 控制台/管道按 GBK 编码导致后端读到乱码
    sys.stdout.buffer.write(json.dumps(obj, ensure_ascii=False, indent=indent).encode("utf-8"))


def _peek(project: str):
    """排障：单页 raw 请求，打印 HTTP 状态 / 顶层结构 / 总数 / 首条字段名 / 原文片段。"""
    if USE_SAMPLE:
        recs = _sample(project)
        _write({"mode": "sample", "fetched": len(recs), "first_record": recs[0] if recs else {}}, indent=2)
        return
    import requests
    pbi = PROJECT_PARAMS.get(project, {}).get("pbiName") or f"{project} V100R001C00"
    resp = requests.post(f"{API_URL}?pbiName={pbi}", headers=API_HEADERS,
                         data=json.dumps({"pageSize": "5", "pageNo": "1"}), timeout=60)
    try:
        body = resp.json()
    except Exception:
        body = None
    data = body.get("data") if isinstance(body, dict) else None
    rows = data.get("data") if isinstance(data, dict) else (data if isinstance(data, list) else [])
    first = rows[0] if rows else {}
    _write({
        "project": project, "pbiName": pbi, "http_status": resp.status_code,
        "response_top_keys": sorted(body.keys()) if isinstance(body, dict) else None,
        "message": body.get("message") if isinstance(body, dict) else None,
        "total": data.get("total") if isinstance(data, dict) else None,
        "first_record_keys": sorted(first.keys()) if isinstance(first, dict) else [],
        "first_record": first,
        "raw_head": resp.text[:2000],
    }, indent=2)


def main():
    args = sys.argv[1:]
    peek = "--peek" in args
    positional = [a for a in args if not a.startswith("--")]
    project = positional[0] if positional else ""

    if not USE_SAMPLE and not project:
        sys.stderr.write(
            "用法: python fetch_issues_api.py <项目名> [--peek]\n"
            "  例如: python fetch_issues_api.py YLS3000\n"
            f"  可用项目: {', '.join(PROJECT_PARAMS) or '(见脚本顶部 PROJECT_PARAMS)'}\n"
        )
        sys.exit(2)

    if peek:
        _peek(project)
        return

    records = _sample(project) if USE_SAMPLE else fetch_from_api(project)
    _write(_process(records))


if __name__ == "__main__":
    main()
