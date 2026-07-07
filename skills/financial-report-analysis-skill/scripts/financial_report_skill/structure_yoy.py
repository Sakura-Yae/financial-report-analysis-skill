from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from .validators import read_standard_workbook, detect_sheet_name
from .utils import (
    ASSET_TOTAL_KEYWORDS,
    LIAB_TOTAL_KEYWORDS,
    EQUITY_TOTAL_KEYWORDS,
    _account_row_mask,
    _parse_date,
    clean_account_name,
    format_date_col,
    identify_denominator_fixed,
    split_balance_sheet_sections,
)


def build_structure_table_fixed(df: pd.DataFrame, denominator: pd.Series, ratio_round=2) -> pd.DataFrame:
    item_col = df.columns[0]
    value_cols = df.columns[1:]
    out = pd.DataFrame({"项目": df[item_col]})
    amt_num_all = df[value_cols].apply(lambda col: pd.to_numeric(col, errors="coerce"))
    is_account_row = amt_num_all.notna().any(axis=1)
    for c in value_cols:
        out[f"{c}_金额"] = df[c]
        amt = pd.to_numeric(df[c], errors="coerce")
        ratio = pd.Series(np.nan, index=df.index, dtype="float64")
        denom = pd.to_numeric(denominator[c], errors="coerce")
        if pd.notna(denom) and float(denom) != 0:
            ratio.loc[is_account_row] = amt.loc[is_account_row].fillna(0) / float(denom) * 100.0
        out[f"{c}_占比"] = ratio.round(ratio_round)
    return out


def build_structure_tables(input_file: str | Path, ratio_round=2) -> Tuple[pd.DataFrame, pd.DataFrame]:
    sheets = read_standard_workbook(input_file)
    bs_name = detect_sheet_name(sheets, "资产负债表")
    bs = sheets[bs_name].copy().dropna(how="all").reset_index(drop=True)
    bs.columns = ["科目"] + [format_date_col(c) for c in bs.columns[1:]]
    sections = split_balance_sheet_sections(bs)
    asset_denominator = identify_denominator_fixed(sections["资产"], ASSET_TOTAL_KEYWORDS, table_name="资产结构表")
    liab_denominator = identify_denominator_fixed(sections["负债"], LIAB_TOTAL_KEYWORDS, table_name="负债结构表")
    asset_structure = build_structure_table_fixed(sections["资产"], asset_denominator, ratio_round=ratio_round)
    liab_structure = build_structure_table_fixed(sections["负债"], liab_denominator, ratio_round=ratio_round)
    return asset_structure, liab_structure


def yoy_percent(cur: float, prev: float) -> float:
    if pd.isna(cur) or pd.isna(prev):
        return np.nan
    if prev == 0:
        if cur > 0:
            return 100.0
        if cur < 0:
            return -100.0
        return 0.0
    return (cur - prev) / abs(prev) * 100.0


def build_yoy_table(df: pd.DataFrame, yoy_mode: str, table_name: str = "") -> pd.DataFrame:
    item_col = df.columns[0]
    value_cols = list(df.columns[1:])
    out = pd.DataFrame({"项目": df[item_col]})
    numeric_vals = df[value_cols].apply(lambda col: pd.to_numeric(col, errors="coerce"))
    col_dates = {c: _parse_date(c) for c in value_cols}
    col_md = {c: (d.strftime("%m-%d") if d is not None else None) for c, d in col_dates.items()}
    acct_mask = _account_row_mask(df)
    for i, c in enumerate(value_cols):
        out[f"{c}_金额"] = df[c]
        yoy_series = pd.Series(np.nan, index=df.index, dtype="float64")
        prev_col = None
        if yoy_mode == "BS":
            if i < len(value_cols) - 1:
                prev_col = value_cols[i + 1]
        elif yoy_mode == "FLOW":
            d_cur = col_dates[c]
            md_cur = col_md[c]
            if d_cur is not None and md_cur is not None:
                candidates = [
                    (other, col_dates[other])
                    for other in value_cols
                    if other != c and col_dates.get(other) is not None and col_md.get(other) == md_cur and col_dates[other] < d_cur
                ]
                if candidates:
                    prev_col = max(candidates, key=lambda x: x[1])[0]
        else:
            raise ValueError("yoy_mode must be 'BS' or 'FLOW'")
        if prev_col is not None:
            cur = numeric_vals[c].copy()
            prev = numeric_vals[prev_col].copy()
            cur.loc[acct_mask & cur.isna()] = 0.0
            prev.loc[acct_mask & prev.isna()] = 0.0
            yoy_calc = pd.Series([yoy_percent(cur.iloc[k], prev.iloc[k]) for k in range(len(df))], index=df.index, dtype="float64")
            yoy_series.loc[acct_mask] = yoy_calc.loc[acct_mask]
        out[f"{c}_同比"] = yoy_series.round(2)
    return out


def build_yoy_tables(input_file: str | Path) -> Dict[str, pd.DataFrame]:
    sheets = read_standard_workbook(input_file)
    bs_name = detect_sheet_name(sheets, "资产负债表")
    bs = sheets[bs_name].dropna(how="all").copy().reset_index(drop=True)
    bs.columns = ["科目"] + [format_date_col(c) for c in bs.columns[1:]]
    sections = split_balance_sheet_sections(bs)
    _ = identify_denominator_fixed(sections["资产"], ASSET_TOTAL_KEYWORDS, "资产同比表分母识别")
    _ = identify_denominator_fixed(sections["负债"], LIAB_TOTAL_KEYWORDS, "负债同比表分母识别")
    _ = identify_denominator_fixed(sections["所有者权益"], EQUITY_TOTAL_KEYWORDS, "所有者权益同比表分母识别")
    pl_name = detect_sheet_name(sheets, "利润表")
    pl = sheets[pl_name].dropna(how="all").copy().reset_index(drop=True)
    pl.columns = ["科目"] + [format_date_col(c) for c in pl.columns[1:]]
    cf_name = detect_sheet_name(sheets, "现金流量表")
    cf = sheets[cf_name].dropna(how="all").copy().reset_index(drop=True)
    cf.columns = ["科目"] + [format_date_col(c) for c in cf.columns[1:]]
    return {
        "资产同比表": build_yoy_table(sections["资产"], yoy_mode="BS", table_name="资产同比表"),
        "负债同比表": build_yoy_table(sections["负债"], yoy_mode="BS", table_name="负债同比表"),
        "所有者权益同比表": build_yoy_table(sections["所有者权益"], yoy_mode="BS", table_name="所有者权益同比表"),
        "利润表同比表": build_yoy_table(pl, yoy_mode="FLOW", table_name="利润表同比表"),
        "现金流量表同比表": build_yoy_table(cf, yoy_mode="FLOW", table_name="现金流量表同比表"),
    }


def build_account_order_index(df: pd.DataFrame) -> dict:
    order = {}
    for i, raw in enumerate(df["项目"]):
        clean = clean_account_name(str(raw))
        if clean not in order:
            order[clean] = i
    return order


def export_structure_yoy_outputs(asset_structure_df: pd.DataFrame, liab_structure_df: pd.DataFrame, yoy_tables: dict, out_paths: dict) -> None:
    with pd.ExcelWriter(out_paths["structure"], engine="openpyxl") as writer:
        asset_structure_df.to_excel(writer, sheet_name="资产结构表", index=False)
        liab_structure_df.to_excel(writer, sheet_name="负债结构表", index=False)
    with pd.ExcelWriter(out_paths["yoy"], engine="openpyxl") as writer:
        for sheet_name, df in yoy_tables.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    with pd.ExcelWriter(out_paths["merged"], engine="openpyxl") as writer:
        asset_structure_df.to_excel(writer, sheet_name="资产结构表", index=False)
        liab_structure_df.to_excel(writer, sheet_name="负债结构表", index=False)
        for sheet_name, df in yoy_tables.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
