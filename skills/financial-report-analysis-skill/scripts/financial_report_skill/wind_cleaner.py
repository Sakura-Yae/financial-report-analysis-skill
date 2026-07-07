from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .errors import WindFinancialStatementValidationError

WIND_HEADER_META_ROWS = {"报告期", "报表类型"}
WIND_TAIL_START_KEYWORDS = {
    "显示币种", "原始币种", "转换汇率", "汇率类型", "税率", "审计意见", "审计意见(境内)",
    "公告日期", "数据来源", "数据来源：Wind",
}
WIND_KEEP_CHILD_ACCOUNTS = {"利息费用", "所得税", "应收票据", "应收账款", "应付票据", "应付账款", "营业收入"}
WIND_DROP_CHILD_ACCOUNTS = {"持续经营净利润"}
WIND_DROP_PARENT_KEEP_CHILDREN = {
    "应收票据及应收账款": {"应收票据", "应收账款"},
    "应付票据及应付账款": {"应付票据", "应付账款"},
}
WIND_ACCOUNT_NAME_ALIAS = {"递延收益-非流动负债": "递延收益"}


def _wind_leading_space_count(x) -> int:
    if pd.isna(x):
        return 0
    s = str(x)
    return len(s) - len(s.lstrip())


def _wind_normalize_account_for_check(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip().replace("（", "(").replace("）", ")")
    s = re.sub(r"^[一二三四五六七八九十]+、", "", s)
    s = re.sub(r"^[（(]?[一二三四五六七八九十]+[）)]", "", s)
    s = re.sub(r"^(其中|其中：|加：|减：|减|加)", "", s)
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"（[^）]*）", "", s)
    return s.replace("：", "").replace(":", "").strip()


def _wind_normalize_final_account_name(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip().replace("（", "(").replace("）", ")")
    return WIND_ACCOUNT_NAME_ALIAS.get(s, s)


def _wind_format_col_name(x):
    if pd.isna(x):
        return ""
    dt = pd.to_datetime(x, errors="coerce")
    if pd.notna(dt):
        return dt.strftime("%Y-%m-%d")
    return str(x).strip()


def _wind_detect_sheet_type(sheet_name: str) -> str:
    name = str(sheet_name)
    if "资产负债" in name:
        return "资产负债表"
    if "利润" in name:
        return "利润表"
    if "现金流量" in name or "现金流" in name:
        return "现金流量表"
    return name


def _wind_standardize_sheet(raw_df: pd.DataFrame, sheet_type: str) -> pd.DataFrame:
    if raw_df.empty:
        return raw_df
    df = raw_df.copy().dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    if df.empty:
        return df
    header_row = df.iloc[0].tolist()
    columns = ["科目"] + [_wind_format_col_name(x) for x in header_row[1:]]
    df = df.iloc[1:].copy()
    df.columns = columns[: len(df.columns)]
    item_col = df.columns[0]
    df[item_col] = df[item_col].astype(str)
    df = df.replace(r"^\s*$", pd.NA, regex=True).dropna(how="all").reset_index(drop=True)
    if df.empty:
        return df
    item_col = df.columns[0]
    if sheet_type == "现金流量表":
        item_stripped = df[item_col].astype(str).str.strip()
        supplement_pos = None
        for i, name in enumerate(item_stripped):
            if str(name).strip().startswith("补充资料"):
                supplement_pos = i
                break
        if supplement_pos is not None:
            df = df.iloc[:supplement_pos].copy().reset_index(drop=True)
    if df.empty:
        return df
    item_col = df.columns[0]
    item_stripped = df[item_col].astype(str).str.strip()
    item_norm = item_stripped.apply(_wind_normalize_account_for_check)
    tail_start = None
    for i, name in enumerate(item_stripped):
        if name in WIND_TAIL_START_KEYWORDS or item_norm.iloc[i] in WIND_TAIL_START_KEYWORDS or str(name).startswith("数据来源"):
            tail_start = i
            break
    if tail_start is not None:
        df = df.iloc[:tail_start].copy().reset_index(drop=True)
    if df.empty:
        return df
    item_col = df.columns[0]
    item_stripped = df[item_col].astype(str).str.strip()
    item_norm = item_stripped.apply(_wind_normalize_account_for_check)
    meta_mask = item_stripped.isin(WIND_HEADER_META_ROWS) | item_norm.isin(WIND_HEADER_META_ROWS)
    df = df.loc[~meta_mask].reset_index(drop=True)
    df = df.replace(r"^\s*$", pd.NA, regex=True).dropna(how="all").reset_index(drop=True)
    return df


def _wind_remove_child_account_rows(df: pd.DataFrame, sheet_type: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    log_columns = ["工作表", "上级科目", "删除子科目", "删除原因"]
    if df.empty:
        return df, pd.DataFrame(columns=log_columns)
    item_col = df.columns[0]
    rows = df.copy()
    names_raw = rows[item_col].astype(str)
    names_stripped = names_raw.str.strip()
    norm_names = names_stripped.apply(_wind_normalize_account_for_check)
    indents = names_raw.apply(_wind_leading_space_count)
    drop_idx = set()
    delete_logs = []

    def add_drop(row_pos: int, parent_name: str, reason: str, force: bool = False):
        child_name = names_stripped.iloc[row_pos]
        child_norm = norm_names.iloc[row_pos]
        if not force and child_norm in WIND_KEEP_CHILD_ACCOUNTS:
            return
        idx = rows.index[row_pos]
        if idx in drop_idx:
            return
        drop_idx.add(idx)
        delete_logs.append({"工作表": sheet_type, "上级科目": parent_name, "删除子科目": child_name, "删除原因": reason})

    for i in range(len(rows)):
        if norm_names.iloc[i] in WIND_DROP_CHILD_ACCOUNTS:
            add_drop(i, "强制删除规则", "指定不分析子科目", force=True)

    for i in range(len(rows) - 1):
        cur_raw = names_stripped.iloc[i]
        cur_norm = norm_names.iloc[i]
        cur_indent = indents.iloc[i]
        if not cur_norm:
            continue
        is_aggregate_parent = ("(合计)" in cur_raw or "（合计）" in cur_raw or cur_raw.endswith("合计") or cur_raw.endswith("总计") or cur_raw.endswith("总额"))
        if not is_aggregate_parent:
            continue
        j = i + 1
        while j < len(rows):
            next_norm = norm_names.iloc[j]
            next_indent = indents.iloc[j]
            if not next_norm:
                j += 1
                continue
            if next_indent <= cur_indent:
                break
            add_drop(j, cur_raw, "合计科目下属子科目")
            j += 1

    if sheet_type == "资产负债表":
        for i in range(len(rows)):
            cur_norm = norm_names.iloc[i]
            if cur_norm in WIND_DROP_PARENT_KEEP_CHILDREN:
                kept_children = "、".join(sorted(WIND_DROP_PARENT_KEEP_CHILDREN[cur_norm]))
                add_drop(i, "并列汇总科目特殊规则", f"删除并列汇总上级科目，保留子科目：{kept_children}", force=True)
        for i in range(len(rows) - 1):
            cur_raw = names_stripped.iloc[i]
            cur_norm = norm_names.iloc[i]
            cur_indent = indents.iloc[i]
            if not cur_norm or cur_norm in WIND_DROP_PARENT_KEEP_CHILDREN:
                continue
            is_combined_parent = "及" in cur_norm and not cur_norm.endswith("合计")
            if not is_combined_parent:
                continue
            j = i + 1
            while j < len(rows):
                next_norm = norm_names.iloc[j]
                next_indent = indents.iloc[j]
                if not next_norm:
                    j += 1
                    continue
                if next_indent <= cur_indent:
                    break
                if next_norm in cur_norm:
                    add_drop(j, cur_raw, "并列汇总科目下属子科目")
                j += 1

    if sheet_type == "利润表":
        for i in range(len(rows)):
            raw = names_stripped.iloc[i]
            if raw.startswith("其中") or raw.startswith("其中："):
                add_drop(i, "其中明细", "利润表其中项子科目")

    cleaned = rows.drop(index=list(drop_idx)).reset_index(drop=True)
    cleaned[item_col] = cleaned[item_col].apply(_wind_normalize_final_account_name)
    log_df = pd.DataFrame(delete_logs, columns=log_columns)
    return cleaned, log_df


def clean_wind_exported_financial_workbook(input_path: str | Path, output_path: str | Path) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    input_path = Path(input_path)
    output_path = Path(output_path)
    raw_book = pd.read_excel(input_path, sheet_name=None, header=None)
    cleaned_sheets = {}
    delete_logs = []
    for sheet_name, raw_df in raw_book.items():
        sheet_type = _wind_detect_sheet_type(sheet_name)
        if sheet_type not in {"资产负债表", "利润表", "现金流量表"}:
            continue
        std_df = _wind_standardize_sheet(raw_df, sheet_type=sheet_type)
        cleaned_df, log_df = _wind_remove_child_account_rows(std_df, sheet_type=sheet_type)
        cleaned_sheets[sheet_type] = cleaned_df
        if not log_df.empty:
            delete_logs.append(log_df)
    if not cleaned_sheets:
        raise WindFinancialStatementValidationError("未在输入文件中识别到资产负债表、利润表或现金流量表。请检查是否为 Wind 默认导出财报。")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_type in ["资产负债表", "利润表", "现金流量表"]:
            if sheet_type in cleaned_sheets:
                cleaned_sheets[sheet_type].to_excel(writer, sheet_name=sheet_type, index=False)
    delete_log_df = pd.concat(delete_logs, ignore_index=True) if delete_logs else pd.DataFrame(columns=["工作表", "上级科目", "删除子科目", "删除原因"])
    return cleaned_sheets, delete_log_df


def validate_wind_cleaned_financial_workbook(cleaned_sheets: dict[str, pd.DataFrame], delete_log_df: pd.DataFrame | None = None) -> None:
    required_sheets = {"资产负债表", "利润表", "现金流量表"}
    missing_sheets = sorted(required_sheets - set(cleaned_sheets.keys()))
    if missing_sheets:
        raise WindFinancialStatementValidationError(f"未识别到完整三张核心报表，缺少：{missing_sheets}。")
    for sheet_type in ["资产负债表", "利润表", "现金流量表"]:
        df = cleaned_sheets[sheet_type]
        if df.empty:
            raise WindFinancialStatementValidationError(f"{sheet_type} 清洗后为空。")
        if df.columns[0] != "科目":
            raise WindFinancialStatementValidationError(f"{sheet_type} 第一列不是“科目”，当前第一列为：{df.columns[0]}。")
        parsed = [c for c in df.columns[1:] if pd.notna(pd.to_datetime(c, errors="coerce"))]
        if len(parsed) < 2:
            raise WindFinancialStatementValidationError(f"{sheet_type} 可识别日期列少于 2 个。")
        names = df[df.columns[0]].astype(str).str.strip()
        norm_names = names.apply(_wind_normalize_account_for_check)
        forbidden_keywords = WIND_HEADER_META_ROWS | WIND_TAIL_START_KEYWORDS | {"资产负债率", "流动负债占比"}
        remained = [raw for raw, norm in zip(names, norm_names) if raw in forbidden_keywords or norm in forbidden_keywords or str(raw).startswith("数据来源")]
        if remained:
            raise WindFinancialStatementValidationError(f"{sheet_type} 清洗后仍残留 Wind 元信息或尾部说明行：{remained[:10]}。")
        norm_nonblank = norm_names[norm_names != ""]
        duplicated = sorted(norm_nonblank[norm_nonblank.duplicated()].unique())
        if duplicated:
            raise WindFinancialStatementValidationError(f"{sheet_type} 清洗后存在重复科目名：{duplicated[:20]}。")
    _validate_required_accounts(cleaned_sheets["资产负债表"], "资产负债表", {"流动资产", "非流动资产", "资产总计", "流动负债", "非流动负债", "负债合计", "所有者权益合计"})
    _validate_required_accounts(cleaned_sheets["利润表"], "利润表", {"营业收入", "营业成本", "利润总额", "净利润"})
    _validate_required_accounts(cleaned_sheets["现金流量表"], "现金流量表", {"经营活动现金流入小计", "经营活动现金流出小计", "经营活动产生的现金流量净额", "投资活动产生的现金流量净额", "筹资活动产生的现金流量净额"})
    if delete_log_df is not None and not delete_log_df.empty:
        required_cols = {"工作表", "上级科目", "删除子科目", "删除原因"}
        if not required_cols.issubset(delete_log_df.columns):
            raise WindFinancialStatementValidationError(f"子科目删除日志字段不完整，缺少：{sorted(required_cols - set(delete_log_df.columns))}。")


def _validate_required_accounts(df: pd.DataFrame, sheet_type: str, required_accounts: set[str]) -> None:
    names = df[df.columns[0]].astype(str).str.strip()
    norm_set = set(names.apply(_wind_normalize_account_for_check))
    missing = sorted([name for name in required_accounts if name not in norm_set])
    if missing:
        raise WindFinancialStatementValidationError(f"{sheet_type} 缺少核心科目锚点：{missing}。")


def wind_cleaning_log_to_text(delete_log_df: pd.DataFrame) -> str:
    lines = ["【Wind 子科目删除日志】", ""]
    if delete_log_df is None or delete_log_df.empty:
        lines.append("未删除任何子科目。")
        return "\n".join(lines)
    for sheet_name, sub_df in delete_log_df.groupby("工作表", sort=False):
        lines.append(f"{sheet_name}：删除 {len(sub_df)} 个科目")
        for _, row in sub_df.iterrows():
            lines.append(f"- 已删除：{row['上级科目']} 上级科目中的 {row['删除子科目']} 子科目（{row['删除原因']}）")
        lines.append("")
    return "\n".join(lines)
