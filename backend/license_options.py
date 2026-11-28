"""客户面授权词表。配置缺键时使用默认值；显式空列表保持为空。"""
import json

from fastapi import HTTPException

DEFAULTS = {
    "customer_machine_models": ["YLS3000", "YLS5000", "YLS3000Y", "YLS5000Y"],
    "license_throughput_packages": [],
    "license_algorithms": [],
    "license_optional_features": [],
}


def options():
    from routers.config import _load
    config = _load()
    return {key: config.get(key, default) for key, default in DEFAULTS.items()}


def validate_choice(key, value, previous=""):
    value = (value or "").strip()
    # 历史值可原样保留；新填值必须来自配置，不影响老数据读取。
    if value and value != previous and value not in options()[key]:
        raise HTTPException(400, f"选项「{value}」未配置，请先在客户面信息配置中添加")
    return value


def validate_config(payload, db):
    import models
    for key in DEFAULTS.keys() & payload.keys():
        values = payload[key]
        if (not isinstance(values, list) or len(values) > 200
                or any(not isinstance(v, str) or not v.strip() or len(v.strip()) > 128 for v in values)):
            raise HTTPException(400, "客户面选项必须是非空文本列表，每项不超过 128 字，最多 200 项")
        values = list(dict.fromkeys(v.strip() for v in values))
        if key == "customer_machine_models":
            used = {r[0] for r in db.query(models.CustomerStatus.model).distinct() if r[0]}
        else:
            col = {"license_throughput_packages": "throughput_package",
                   "license_algorithms": "algorithm", "license_optional_features": "optional_features_json"}[key]
            used = set()
            for (v,) in db.query(getattr(models.MachineLicense, col)).distinct():
                used.update(json.loads(v or "[]") if key == "license_optional_features" else ([v] if v else []))
        # 只拦当前配置中仍在使用的选项，历史未配置的自由值不妨碍配置保存。
        removed = (set(options()[key]) - set(values)) & used
        if removed:
            raise HTTPException(400, "以下选项正在使用，不能删除：" + "、".join(sorted(removed)))
        payload[key] = values
