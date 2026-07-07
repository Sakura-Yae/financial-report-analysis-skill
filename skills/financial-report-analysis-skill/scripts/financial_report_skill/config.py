from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Literal

from .errors import SkillInputError

DEFAULT_FORCED_ACCOUNTS = {
    "应收账款",
    "其他应收款",
    "应付账款",
    "其他应付款",
    "在建工程",
    "销售费用",
    "管理费用",
    "财务费用",
    "净利润",
    "营业收入",
    "经营活动现金流入小计",
    "经营活动现金流出小计",
    "经营活动产生的现金流量净额",
    "投资活动现金流入小计",
    "投资活动现金流出小计",
    "投资活动产生的现金流量净额",
    "筹资活动现金流入小计",
    "筹资活动现金流出小计",
    "筹资活动产生的现金流量净额",
}


@dataclass
class SkillConfig:
    input_path: Path
    output_dir: Path
    company_name: str = "auto"
    is_wind_report: Literal["auto", "true", "false", True, False] = "auto"
    input_unit_is_wanyuan: bool = True
    max_periods: int = 4
    major_ratio_threshold: float = 10.0
    major_yoy_threshold: float = 30.0
    simplified_ratio_threshold: float = 0.05
    forced_accounts_mode: Literal["append_default", "replace", "none"] = "append_default"
    forced_accounts: list[str] = field(default_factory=list)
    alias_map_bs: Dict[str, str] = field(default_factory=dict)
    alias_map_pl: Dict[str, str] = field(default_factory=dict)
    alias_map_cf: Dict[str, str] = field(default_factory=dict)
    separate_cash_flow_group: bool = True
    round_digits: int = 2
    write_standardized_even_if_standard: bool = True

    def to_jsonable(self) -> dict:
        d = asdict(self)
        d["input_path"] = str(self.input_path)
        d["output_dir"] = str(self.output_dir)
        return d

    @property
    def resolved_forced_accounts(self) -> set[str]:
        user_accounts = {str(x).strip() for x in self.forced_accounts if str(x).strip()}
        if self.forced_accounts_mode == "none":
            return set()
        if self.forced_accounts_mode == "replace":
            return user_accounts
        return set(DEFAULT_FORCED_ACCOUNTS) | user_accounts


def _as_bool(x: Any, default: bool = True) -> bool:
    if isinstance(x, bool):
        return x
    if x is None:
        return default
    s = str(x).strip().lower()
    if s in {"true", "1", "yes", "y", "是"}:
        return True
    if s in {"false", "0", "no", "n", "否"}:
        return False
    return default


def _clean_company_name_from_file(path: Path) -> str:
    name = path.stem
    name = re.sub(r"^[【\[]?(Wind导出|标准人工)[】\]]?", "", name, flags=re.I)
    name = re.sub(r"[_\- ]?(Wind清洗版|标准化财务报表)$", "", name)
    name = name.strip(" _-【】[]")
    return name or path.stem


def load_config(config_path: str | Path) -> SkillConfig:
    config_path = Path(config_path)
    if not config_path.exists():
        raise SkillInputError(f"配置文件不存在：{config_path}")
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if "input_path" not in raw:
        raise SkillInputError("配置文件缺少 input_path。")
    input_path = Path(raw["input_path"])
    output_dir = Path(raw.get("output_dir") or input_path.with_suffix("").parent / f"financial_report_output_{input_path.stem}")
    company_name = raw.get("company_name", "auto")
    if not company_name or str(company_name).lower() == "auto":
        company_name = _clean_company_name_from_file(input_path)

    mode = raw.get("forced_accounts_mode", "append_default")
    if mode not in {"append_default", "replace", "none"}:
        raise SkillInputError("forced_accounts_mode 只能为 append_default、replace 或 none。")

    is_wind = raw.get("is_wind_report", "auto")
    if isinstance(is_wind, str):
        is_wind = is_wind.strip().lower()
        if is_wind not in {"auto", "true", "false"}:
            raise SkillInputError("is_wind_report 只能为 auto、true 或 false。")

    return SkillConfig(
        input_path=input_path,
        output_dir=output_dir,
        company_name=str(company_name),
        is_wind_report=is_wind,
        input_unit_is_wanyuan=_as_bool(raw.get("input_unit_is_wanyuan", True), True),
        max_periods=int(raw.get("max_periods", 4)),
        major_ratio_threshold=float(raw.get("major_ratio_threshold", 10.0)),
        major_yoy_threshold=float(raw.get("major_yoy_threshold", 30.0)),
        simplified_ratio_threshold=float(raw.get("simplified_ratio_threshold", 0.05)),
        forced_accounts_mode=mode,
        forced_accounts=list(raw.get("forced_accounts", [])),
        alias_map_bs=dict(raw.get("alias_map_bs", {})),
        alias_map_pl=dict(raw.get("alias_map_pl", {})),
        alias_map_cf=dict(raw.get("alias_map_cf", {})),
        separate_cash_flow_group=_as_bool(raw.get("separate_cash_flow_group", True), True),
        round_digits=int(raw.get("round_digits", 2)),
        write_standardized_even_if_standard=_as_bool(raw.get("write_standardized_even_if_standard", True), True),
    )
