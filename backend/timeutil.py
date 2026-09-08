"""时间口径：库里存 UTC，出接口一律转北京时间。

## 为什么需要这个模块

全库的审计时间戳列（`created_at` / `updated_at` / `uploaded_at` / `started_at` …）默认值都是
`datetime.utcnow`，存的是**朴素 UTC**（naive，不带 tzinfo）。而这些值直接序列化给前端时：

- Pydantic 把朴素 datetime 输出成 `2026-08-17T02:26:00`，**没有时区后缀**；
- 前端 `new Date("2026-08-17T02:26:00")` 按 ES 规范会当作**本地时间**解析；
- 于是页面上显示 02:26，而这条记录实际发生在北京时间 10:26 —— 整体早 8 小时。

修法有两条路：把库改成存本地时间（要给几十张表的历史数据做 +8h 回填，风险高），
或者**保持 UTC 存储、在出口转换**。这里选后者，并且转成**带偏移量的 ISO**
（`2026-08-17T10:26:00+08:00`）——因为「不带时区的时间字符串」正是这个 bug 的根源，
输出自描述的时间戳才能让后续新增的页面不再踩同一个坑。

## 只转「服务端盖的时间戳」，不要碰「用户填的日期」

DateTime 列在本项目里有两类，口径完全不同：

- **服务端盖章**（`default=datetime.utcnow`）：审计与流水时间，存 UTC → 出口要转。
- **用户填写**（`planned_date` / `range_start` / `release_date` / `planned_close_date` …）：
  前端传什么存什么，本来就是本地时间 → **转了就会凭空多出 8 小时**。

所以 `LocalDT` 只挂在第一类字段上。判断标准是「这个值是谁写进去的」，
不是「它长得像不像时间」。
"""
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Optional

from pydantic import PlainSerializer

# 用固定 +08:00 而不是 zoneinfo("Asia/Shanghai")：中国大陆自 1991 年起无夏令时，
# 固定偏移与真实时区完全等价；且 Windows 上 zoneinfo 需要额外装 tzdata 包，
# 部署机（见 部署指南）是 Windows，少一个依赖少一个坑。
CN_TZ = timezone(timedelta(hours=8))

FMT = "%Y-%m-%d %H:%M:%S"


def to_local(dt: Optional[datetime]) -> Optional[datetime]:
    """朴素 UTC → 带偏移的北京时间。已带 tzinfo 的按其自身偏移换算。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CN_TZ)


def fmt_local(dt: Optional[datetime], fmt: str = FMT) -> str:
    """朴素 UTC → 北京时间字符串。给手写 dict 的接口用（不走 Pydantic 的那些）。"""
    local = to_local(dt)
    return local.strftime(fmt) if local else ""


def iso_local(dt: Optional[datetime]) -> Optional[str]:
    """朴素 UTC → 带偏移的 ISO 串，如 2026-08-17T10:26:00+08:00。"""
    local = to_local(dt)
    return local.isoformat() if local else None


def local_to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """反向：前端传来的本地时间 → 朴素 UTC，用于和库里的 UTC 列比较。

    查询条件不转的话，「按时间段筛操作日志」会整体错 8 小时。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CN_TZ)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


# Pydantic 出口类型：把 `created_at: datetime` 换成 `created_at: LocalDT` 即可。
# when_used="json" —— FastAPI 序列化 response_model 走 JSON 模式，而内部
# model_dump() 仍拿得到原始 datetime 对象，不影响服务端自己的计算。
LocalDT = Annotated[
    datetime,
    PlainSerializer(iso_local, return_type=Optional[str], when_used="json"),
]


# ─── 自由格式日期串 → date ────────────────────────────────────────────────
# 「预计闭环时间」（DTS 的 planCloseTime）、里程碑日期这类**用户/外系统填的**列
# 都是自由字符串：见过 2026-09-15、2026/9/15、2026-09-15 00:00:00、13 位毫秒
# 时间戳、2026年9月15日。**认不出来的一律算"没填"而不是算"没超期"**——后者会把
# 一批读不懂的日期悄悄记成达标，数字看着还挺好。
#
# 全系统只有这一份实现（`routers._issue_source` 再导出同一个函数）：两处分叉的
# 表现是同一个日期在两个页面上一个算超期一个不算，而两边看着都对。
_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S",
                 "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y年%m月%d日")


def parse_plan_date(value) -> Optional[date]:
    """自由格式的日期串 → date；认不出返回 None（＝「没填」，不是「达标」）。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    # 纯数字：秒 / 毫秒时间戳
    if s.isdigit() and len(s) in (10, 13):
        try:
            return datetime.fromtimestamp(int(s) / (1000 if len(s) == 13 else 1)).date()
        except (ValueError, OSError, OverflowError):
            return None
    head = s.replace("T", " ").split(" ")[0] if " " in s or "T" in s else s
    for fmt in _DATE_FORMATS:
        for cand in (s, head):
            try:
                return datetime.strptime(cand, fmt).date()
            except ValueError:
                continue
    return None
