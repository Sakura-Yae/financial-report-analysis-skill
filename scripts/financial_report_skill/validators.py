from __future__ import annotations

from pathlib import Path
import re

import pandas as pd

from .errors import SkillInputError, SkillValidationError
from .utils import (
    ASSET_TOTAL_KEYWORDS,
    LIAB_TOTAL_KEYWORDS,
    EQUITY_TOTAL_KEYWORDS,
    clean_account_name,
    format_date_col,
    identify_denominator_fixed,
    split_balance_sheet_sections,
)

SHEET_ALIASES = {
    "资产负债表": ["资产负债"],
    "利润表": ["利润"],
    "现金流量表": ["现金流量", "现金流"],
}


def validate_input_file(path: str | Path) -> Path:
    path = Path(path)
    if not path.exists():
        raise SkillInputError(f"未找到输入文件：{path}")
    if path.suffix.lower() != ".xlsx":
        raise SkillInputError(f"输入文件格式不支持：{path.name}。请上传 .xlsx 文件。")
    return path


def read_standard_workbook(path: str | Path) -> dict[str, pd.DataFrame]:
    path = Path(path)
    try:
        return pd.read_excel(path, sheet_name=None)
    except Exception as e:
        raise SkillInputError(f"Excel 文件读取失败：{path}；错误：{repr(e)}") from e


def detect_sheet_name(sheets: dict[str, pd.DataFrame], target: str) -> str:
    aliases = SHEET_ALIASES[target]
    for name in sheets:
        if any(a in str(name) for a in aliases):
            return name
    raise SkillValidationError(f"未找到{target}工作表。请确认工作表名称包含：{aliases}")


def standardize_standard_workbook(input_path: str | Path, output_path: str | Path) -> dict[str, pd.DataFrame]:
    sheets = read_standard_workbook(input_path)
    result = {}
    for target in ["资产负债表", "利润表", "现金流量表"]:
        sheet_name = detect_sheet_name(sheets, target)
        df = sheets[sheet_name].copy().dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
        if df.empty:
            raise SkillValidationError(f"{target} 为空。")
        df.columns = ["科目"] + [format_date_col(c) for c in df.columns[1:]]
        result[target] = df
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for name in ["资产负债表", "利润表", "现金流量表"]:
            result[name].to_excel(writer, sheet_name=name, index=False)
    return result


def detect_report_type(input_path: str | Path, user_flag="auto") -> str:
    if isinstance(user_flag, bool):
        return "wind" if user_flag else "standard"
    flag = str(user_flag).strip().lower()
    if flag == "true":
        return "wind"
    if flag == "false":
        return "standard"
    if flag != "auto":
        raise SkillInputError("is_wind_report 只能为 auto、true 或 false。")
    # Auto infer via raw workbook text in top/tail signature rows.
    try:
        raw_book = pd.read_excel(input_path, sheet_name=None, header=None, nrows=12)
    except Exception as e:
        raise SkillInputError(f"无法读取 Excel 文件以判断报表类型：{repr(e)}") from e
    wind_tokens = {"报告期", "报表类型", "显示币种", "原始币种", "数据来源"}
    score = 0
    for _, raw in raw_book.items():
        vals = raw.fillna("").astype(str).values.ravel().tolist()
        text = "\n".join(vals)
        for token in wind_tokens:
            if token in text:
                score += 1
    return "wind" if score >= 2 else "standard"


def _validate_date_columns(df: pd.DataFrame, sheet_name: str) -> None:
    if df.empty:
        raise SkillValidationError(f"{sheet_name} 为空。")
    if str(df.columns[0]).strip() != "科目":
        raise SkillValidationError(f"{sheet_name} 第一列必须为“科目”，当前为：{df.columns[0]}。")
    date_cols = list(df.columns[1:])
    parsed = [pd.to_datetime(c, errors="coerce") for c in date_cols]
    parsed_ok = [x for x in parsed if pd.notna(x)]
    if len(parsed_ok) < 2:
        raise SkillValidationError(f"{sheet_name} 可识别日期列少于 2 个，当前列：{date_cols}。")


def _validate_no_generated_cols(df: pd.DataFrame, sheet_name: str) -> None:
    bad = [str(c) for c in df.columns if str(c).endswith("_金额") or str(c).endswith("_占比") or str(c).endswith("_同比")]
    if bad:
        raise SkillValidationError(f"{sheet_name} 中疑似包含已生成的占比/同比列：{bad[:10]}。请上传原始财务报表三表。")


def _validate_required_accounts_by_clean(df: pd.DataFrame, sheet_name: str, required: set[str]) -> None:
    clean_set = set(df[df.columns[0]].astype(str).map(clean_account_name))
    missing = sorted([x for x in required if clean_account_name(x) not in clean_set])
    if missing:
        raise SkillValidationError(f"{sheet_name} 缺少核心科目：{missing}。")


def validate_standardized_workbook(path: str | Path) -> dict[str, pd.DataFrame]:
    sheets = read_standard_workbook(path)
    normalized = {}
    for target in ["资产负债表", "利润表", "现金流量表"]:
        sheet_name = detect_sheet_name(sheets, target)
        df = sheets[sheet_name].copy().dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
        if len(df.columns) == 0:
            raise SkillValidationError(f"{target} 没有有效列。")
        if str(df.columns[0]).strip() != "科目":
            # Standardized workbooks should already have header row. Avoid guessing here.
            raise SkillValidationError(f"{target} 第一列不是“科目”，请确认报表已标准化或启用 Wind 清洗。")
        df.columns = ["科目"] + [format_date_col(c) for c in df.columns[1:]]
        _validate_date_columns(df, target)
        _validate_no_generated_cols(df, target)
        normalized[target] = df

    # BS section and denominators.
    sections = split_balance_sheet_sections(normalized["资产负债表"])
    _ = identify_denominator_fixed(sections["资产"], ASSET_TOTAL_KEYWORDS, "资产结构表分母识别")
    _ = identify_denominator_fixed(sections["负债"], LIAB_TOTAL_KEYWORDS, "负债结构表分母识别")
    _ = identify_denominator_fixed(sections["所有者权益"], EQUITY_TOTAL_KEYWORDS, "权益分母识别")
    _validate_required_accounts_by_clean(normalized["利润表"], "利润表", {"营业收入", "营业成本", "利润总额", "净利润"})
    _validate_required_accounts_by_clean(normalized["现金流量表"], "现金流量表", {"经营活动现金流入小计", "经营活动现金流出小计", "经营活动产生的现金流量净额", "投资活动产生的现金流量净额", "筹资活动产生的现金流量净额"})
    return normalized
