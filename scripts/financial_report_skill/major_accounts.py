from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional

import numpy as np
import pandas as pd

from .utils import (
    calc_delta,
    clean_account_name,
    fmt_amount_with_unit,
    fmt_pct_no_sign,
    join_with_and,
    parse_report_period_label,
)

@dataclass
class DisplayPeriod:
    period: pd.Timestamp
    label: str
    amount: float
    ratio: Optional[float] = None

@dataclass
class ComparisonBlock:
    subject: str
    cur_label: str
    prev_label: str
    cur_amount: float
    prev_amount: float
    delta_amount: float
    yoy_rate: float
    significant: bool
    comparison_type: Literal["年度同比", "一期同比"]

@dataclass
class AccountTextContext:
    clean_name: str
    mode: Literal["BS", "FLOW"]
    bs_subtype: Optional[str]
    source_table: Optional[str]
    display_periods: List[DisplayPeriod]
    comparisons: List[ComparisonBlock]


def build_bs_subtype_map(asset_structure_df: pd.DataFrame, liab_structure_df: pd.DataFrame, equity_structure_df: pd.DataFrame | None = None) -> dict:
    subtype_map = {}
    for raw in asset_structure_df["项目"].astype(str):
        subtype_map[clean_account_name(raw)] = "资产"
    for raw in liab_structure_df["项目"].astype(str):
        subtype_map[clean_account_name(raw)] = "负债"
    if equity_structure_df is not None:
        for raw in equity_structure_df["项目"].astype(str):
            subtype_map[clean_account_name(raw)] = "权益"
    return subtype_map


def _latest_two_cols(cols: list[str], suffix: str) -> list[str]:
    pairs = []
    for c in cols:
        d = pd.to_datetime(str(c).replace(suffix, ""), errors="coerce")
        if pd.notna(d):
            pairs.append((d, c))
    pairs.sort(key=lambda x: x[0])
    return [c for _, c in pairs[-2:]]


def _new_major_entry(clean: str, bs_subtype=None):
    return {
        "clean_name": clean,
        "raw_names": set(),
        "bs_subtype": bs_subtype,
        "sources": {"资产负债表": False, "利润表": False, "现金流量表": False},
        "triggers": {"结构占比>=阈值": False, "同比变动>=阈值": False, "强制纳入": False},
    }


def identify_major_accounts(asset_structure_df: pd.DataFrame, liab_structure_df: pd.DataFrame, yoy_tables: dict, ratio_threshold: float = 10.0, yoy_threshold: float = 30.0, equity_structure_df: pd.DataFrame | None = None) -> dict:
    bs_subtype_map = build_bs_subtype_map(asset_structure_df, liab_structure_df, equity_structure_df)
    major_map = {}

    def _merge_structure_hits(struct_df: pd.DataFrame):
        ratio_cols = [c for c in struct_df.columns if str(c).endswith("_占比")]
        recent_ratio_cols = _latest_two_cols(ratio_cols, "_占比")
        mask = struct_df[recent_ratio_cols].ge(ratio_threshold).any(axis=1) if recent_ratio_cols else pd.Series(False, index=struct_df.index)
        for raw in struct_df.loc[mask, "项目"].astype(str):
            clean = clean_account_name(raw)
            entry = major_map.setdefault(clean, _new_major_entry(clean, bs_subtype_map.get(clean)))
            entry["raw_names"].add(raw)
            entry["sources"]["资产负债表"] = True
            entry["triggers"]["结构占比>=阈值"] = True

    _merge_structure_hits(asset_structure_df)
    _merge_structure_hits(liab_structure_df)

    for table_name, df in yoy_tables.items():
        yoy_cols = [c for c in df.columns if str(c).endswith("_同比")]
        recent_yoy_cols = _latest_two_cols(yoy_cols, "_同比")
        mask = df[recent_yoy_cols].abs().ge(yoy_threshold).any(axis=1) if recent_yoy_cols else pd.Series(False, index=df.index)
        for raw in df.loc[mask, "项目"].astype(str):
            clean = clean_account_name(raw)
            entry = major_map.setdefault(clean, _new_major_entry(clean, bs_subtype_map.get(clean)))
            entry["raw_names"].add(raw)
            entry["triggers"]["同比变动>=阈值"] = True
            if table_name in {"资产同比表", "负债同比表", "所有者权益同比表"}:
                entry["sources"]["资产负债表"] = True
            elif table_name == "利润表同比表":
                entry["sources"]["利润表"] = True
            elif table_name == "现金流量表同比表":
                entry["sources"]["现金流量表"] = True
    return major_map


def force_add_major_accounts(major_accounts: dict, forced_accounts: set[str], bs_asset_df: pd.DataFrame, bs_liab_df: pd.DataFrame, pl_yoy_df: pd.DataFrame, cf_yoy_df: pd.DataFrame | None = None):
    def _match_rows(df: pd.DataFrame | None, name: str) -> pd.DataFrame:
        if df is None or df.empty or "项目" not in df.columns:
            return pd.DataFrame()
        return df[df["项目"].apply(lambda x: clean_account_name(str(x)) == name)]

    for name in sorted(forced_accounts):
        name = clean_account_name(name)
        if not name:
            continue
        if name in major_accounts:
            major_accounts[name]["triggers"]["强制纳入"] = True
            continue
        asset_rows = _match_rows(bs_asset_df, name)
        if not asset_rows.empty:
            major_accounts[name] = _new_major_entry(name, "资产")
            major_accounts[name]["raw_names"] = set(asset_rows["项目"].astype(str))
            major_accounts[name]["sources"]["资产负债表"] = True
            major_accounts[name]["triggers"]["强制纳入"] = True
            continue
        liab_rows = _match_rows(bs_liab_df, name)
        if not liab_rows.empty:
            major_accounts[name] = _new_major_entry(name, "负债")
            major_accounts[name]["raw_names"] = set(liab_rows["项目"].astype(str))
            major_accounts[name]["sources"]["资产负债表"] = True
            major_accounts[name]["triggers"]["强制纳入"] = True
            continue
        pl_rows = _match_rows(pl_yoy_df, name)
        if not pl_rows.empty:
            major_accounts[name] = _new_major_entry(name, None)
            major_accounts[name]["raw_names"] = set(pl_rows["项目"].astype(str))
            major_accounts[name]["sources"]["利润表"] = True
            major_accounts[name]["triggers"]["强制纳入"] = True
            continue
        cf_rows = _match_rows(cf_yoy_df, name)
        if not cf_rows.empty:
            major_accounts[name] = _new_major_entry(name, None)
            major_accounts[name]["raw_names"] = set(cf_rows["项目"].astype(str))
            major_accounts[name]["sources"]["现金流量表"] = True
            major_accounts[name]["triggers"]["强制纳入"] = True
            continue


def sort_major_accounts_for_text(major_accounts: dict, asset_order: dict, liab_order: dict) -> list[tuple[str, dict]]:
    def sort_key(item):
        clean_name, info = item
        if info.get("bs_subtype") == "资产":
            return (0, asset_order.get(clean_name, 10_000))
        if info.get("bs_subtype") == "负债":
            return (1, liab_order.get(clean_name, 10_000))
        if info.get("sources", {}).get("利润表"):
            return (2, 10_000)
        if info.get("sources", {}).get("现金流量表"):
            return (3, 10_000)
        return (4, 10_000)
    return sorted(major_accounts.items(), key=sort_key)


def build_account_text_context(clean_name: str, info: dict, tables: Dict[str, pd.DataFrame], asset_structure_df: Optional[pd.DataFrame], liab_structure_df: Optional[pd.DataFrame], yoy_threshold: float = 30.0) -> Optional[AccountTextContext]:
    raw_names = info["raw_names"]
    source_table = None
    if info.get("bs_subtype") in ("资产", "负债", "权益"):
        mode = "BS"
        yoy_df = tables[f"{info['bs_subtype']}同比表"]
        struct_df = asset_structure_df if info["bs_subtype"] == "资产" else liab_structure_df if info["bs_subtype"] == "负债" else None
        source_table = "资产负债表"
    elif info.get("sources", {}).get("利润表"):
        mode = "FLOW"
        yoy_df = tables["利润表同比表"]
        struct_df = None
        source_table = "利润表"
    elif info.get("sources", {}).get("现金流量表"):
        mode = "FLOW"
        yoy_df = tables["现金流量表同比表"]
        struct_df = None
        source_table = "现金流量表"
    else:
        return None

    row = yoy_df.loc[yoy_df["项目"].astype(str).isin(raw_names)]
    if row.empty:
        row = yoy_df[yoy_df["项目"].astype(str).apply(lambda x: clean_account_name(x) == clean_name)]
    if row.empty:
        return None
    row = row.iloc[0]
    value_cols = [c for c in yoy_df.columns if str(c).endswith("_金额")]
    pairs = []
    for c in value_cols:
        dt = pd.to_datetime(str(c).replace("_金额", ""), errors="coerce")
        if pd.notna(dt):
            pairs.append((dt, c))
    pairs.sort(key=lambda x: x[0])
    dates_sorted = [dt for dt, _ in pairs]
    date_to_col = dict(pairs)
    display_periods: List[DisplayPeriod] = []

    if mode == "FLOW":
        annual = sorted([(dt, c) for dt, c in pairs if dt.month == 12 and dt.day == 31], key=lambda x: x[0])
        interim = sorted([(dt, c) for dt, c in pairs if not (dt.month == 12 and dt.day == 31)], key=lambda x: x[0])
        for dt, col in annual:
            amt = pd.to_numeric(row[col], errors="coerce")
            display_periods.append(DisplayPeriod(dt, parse_report_period_label(dt, "FLOW")[1], float(amt) if not pd.isna(amt) else 0.0))
        if interim:
            dt, col = interim[-1]
            amt = pd.to_numeric(row[col], errors="coerce")
            display_periods.append(DisplayPeriod(dt, parse_report_period_label(dt, "FLOW")[1], float(amt) if not pd.isna(amt) else 0.0))
    else:
        for dt, col in pairs:
            amt = pd.to_numeric(row[col], errors="coerce")
            ratio = None
            if struct_df is not None:
                sr = struct_df.loc[struct_df["项目"].astype(str).isin(raw_names)]
                if sr.empty:
                    sr = struct_df[struct_df["项目"].astype(str).apply(lambda x: clean_account_name(x) == clean_name)]
                if not sr.empty:
                    for ratio_col in [c for c in struct_df.columns if str(c).endswith("_占比")]:
                        ratio_date = pd.to_datetime(str(ratio_col).replace("_占比", ""), errors="coerce")
                        if pd.notna(ratio_date) and ratio_date.date() == dt.date():
                            ratio_val = pd.to_numeric(sr.iloc[0][ratio_col], errors="coerce")
                            if pd.notna(ratio_val):
                                ratio = float(ratio_val)
                            break
            display_periods.append(DisplayPeriod(dt, parse_report_period_label(dt, "BS")[0], float(amt) if not pd.isna(amt) else 0.0, ratio))

    comparisons: List[ComparisonBlock] = []
    if mode == "FLOW":
        annual_dates = sorted([dt for dt, _ in pairs if dt.month == 12 and dt.day == 31])
        for i in range(1, len(annual_dates)):
            dt_prev, dt_cur = annual_dates[i - 1], annual_dates[i]
            col_prev, col_cur = date_to_col[dt_prev], date_to_col[dt_cur]
            amt_prev = pd.to_numeric(row[col_prev], errors="coerce")
            amt_cur = pd.to_numeric(row[col_cur], errors="coerce")
            delta = calc_delta(amt_cur, amt_prev)
            yoy_rate = pd.to_numeric(row.get(col_cur.replace("_金额", "_同比"), np.nan), errors="coerce")
            comparisons.append(ComparisonBlock(f"发行人{clean_name}", parse_report_period_label(dt_cur, "FLOW")[1], parse_report_period_label(dt_prev, "FLOW")[1], float(amt_cur) if not pd.isna(amt_cur) else 0.0, float(amt_prev) if not pd.isna(amt_prev) else 0.0, delta, float(yoy_rate) if not pd.isna(yoy_rate) else 0.0, abs(yoy_rate) >= yoy_threshold if not pd.isna(yoy_rate) else False, "年度同比"))
        interim_dates = sorted([dt for dt, _ in pairs if not (dt.month == 12 and dt.day == 31)])
        if len(interim_dates) >= 2:
            dt_cur = interim_dates[-1]
            candidates = [dt for dt in interim_dates if dt.month == dt_cur.month and dt.day == dt_cur.day and dt < dt_cur]
            if candidates:
                dt_prev = max(candidates)
                col_prev, col_cur = date_to_col[dt_prev], date_to_col[dt_cur]
                amt_prev = pd.to_numeric(row[col_prev], errors="coerce")
                amt_cur = pd.to_numeric(row[col_cur], errors="coerce")
                delta = calc_delta(amt_cur, amt_prev)
                yoy_rate = pd.to_numeric(row.get(col_cur.replace("_金额", "_同比"), np.nan), errors="coerce")
                comparisons.append(ComparisonBlock(f"发行人{clean_name}", parse_report_period_label(dt_cur, "FLOW")[1], parse_report_period_label(dt_prev, "FLOW")[1], float(amt_cur) if not pd.isna(amt_cur) else 0.0, float(amt_prev) if not pd.isna(amt_prev) else 0.0, delta, float(yoy_rate) if not pd.isna(yoy_rate) else 0.0, abs(yoy_rate) >= yoy_threshold if not pd.isna(yoy_rate) else False, "一期同比"))
    else:
        for i in range(len(dates_sorted) - 1):
            dt_prev, dt_cur = dates_sorted[i], dates_sorted[i + 1]
            col_prev, col_cur = date_to_col[dt_prev], date_to_col[dt_cur]
            amt_prev = pd.to_numeric(row[col_prev], errors="coerce")
            amt_cur = pd.to_numeric(row[col_cur], errors="coerce")
            delta = calc_delta(amt_cur, amt_prev)
            yoy_rate = pd.to_numeric(row.get(col_cur.replace("_金额", "_同比"), np.nan), errors="coerce")
            comparisons.append(ComparisonBlock(f"发行人{clean_name}", parse_report_period_label(dt_cur, "BS")[0], parse_report_period_label(dt_prev, "BS")[0], float(amt_cur) if not pd.isna(amt_cur) else 0.0, float(amt_prev) if not pd.isna(amt_prev) else 0.0, delta, float(yoy_rate) if not pd.isna(yoy_rate) else 0.0, abs(yoy_rate) >= yoy_threshold if not pd.isna(yoy_rate) else False, "年度同比"))
    return AccountTextContext(clean_name, mode, info.get("bs_subtype"), source_table, display_periods, comparisons)


def build_all_text_contexts(major_accounts: dict, tables: dict, asset_structure_df: pd.DataFrame, liab_structure_df: pd.DataFrame, asset_order: dict, liab_order: dict, yoy_threshold: float = 30.0) -> Dict[str, AccountTextContext]:
    result = {}
    for clean_name, info in sort_major_accounts_for_text(major_accounts, asset_order, liab_order):
        ctx = build_account_text_context(clean_name, info, tables, asset_structure_df, liab_structure_df, yoy_threshold)
        if ctx is not None:
            result[clean_name] = ctx
    return result


def render_account_text(ctx: AccountTextContext) -> str:
    lines = []
    labels = [p.label for p in ctx.display_periods]
    amounts = [fmt_amount_with_unit(p.amount) for p in ctx.display_periods]
    time_str = join_with_and(labels)
    amt_str = join_with_and(amounts)
    if ctx.mode == "BS":
        lines.append(f"截至{time_str}，发行人{ctx.clean_name}分别为{amt_str}。")
    else:
        lines.append(f"{time_str}，发行人{ctx.clean_name}分别为{amt_str}。")
    if ctx.mode == "BS":
        ratios = [p.ratio for p in ctx.display_periods if p.ratio is not None]
        if ratios:
            ratio_str = join_with_and([fmt_pct_no_sign(r) for r in ratios])
            denom = "总资产" if ctx.bs_subtype == "资产" else "总负债" if ctx.bs_subtype == "负债" else "所有者权益"
            lines.append(f"占{denom}比例分别为{ratio_str}。")
    if ctx.comparisons:
        lines.append(f"{ctx.clean_name}")
        for comp in ctx.comparisons:
            delta_amt = fmt_amount_with_unit(abs(comp.delta_amount))
            direction = "增加" if comp.delta_amount >= 0 else "减少"
            rate = abs(comp.yoy_rate)
            reason = "主要系【】" if comp.significant else "变动较小"
            lines.append(f"{comp.cur_label}较{comp.prev_label}{direction}{delta_amt}，{'增幅' if comp.delta_amount >= 0 else '降幅'}为{rate:.2f}%，{reason}。")
    return "".join(lines)


def export_account_texts(text_contexts: dict[str, AccountTextContext], output_path: str | Path, separate_cash_flow_group: bool = True):
    groups = {"资产": [], "负债": [], "权益": [], "利润": [], "现金流": []}
    for name, ctx in text_contexts.items():
        if ctx.mode == "BS":
            groups[ctx.bs_subtype or "权益"].append(name)
        else:
            if separate_cash_flow_group and ctx.source_table == "现金流量表":
                groups["现金流"].append(name)
            else:
                groups["利润"].append(name)
    lines = []
    for group in ["资产", "负债", "权益", "利润", "现金流"]:
        names = groups.get(group, [])
        if not names:
            continue
        lines.append(f"【{group}类科目】")
        lines.append("")
        for name in names:
            ctx = text_contexts[name]
            lines.append(name)
            lines.append(render_account_text(ctx))
            lines.append("")
        lines.append("")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def build_simplified_text_contexts(text_contexts: dict[str, AccountTextContext], major_accounts: dict, ratio_threshold: float) -> dict[str, AccountTextContext]:
    result = {}
    for name, ctx in text_contexts.items():
        info = major_accounts.get(name, {})
        triggers = info.get("triggers", {})
        if triggers.get("强制纳入"):
            result[name] = ctx
            continue
        if ctx.mode == "FLOW":
            result[name] = ctx
            continue
        ratios = [p.ratio for p in ctx.display_periods if p.ratio is not None]
        if ratios and (sum(ratios) / len(ratios)) > ratio_threshold:
            result[name] = ctx
    return result


def major_accounts_to_dataframe(major_accounts: dict) -> pd.DataFrame:
    rows = []
    for name, info in major_accounts.items():
        rows.append({
            "科目": name,
            "原始科目名": "、".join(sorted(info.get("raw_names", []))),
            "资产负债表类别": info.get("bs_subtype") or "",
            "来源-资产负债表": info.get("sources", {}).get("资产负债表", False),
            "来源-利润表": info.get("sources", {}).get("利润表", False),
            "来源-现金流量表": info.get("sources", {}).get("现金流量表", False),
            "触发-结构占比": info.get("triggers", {}).get("结构占比>=阈值", False),
            "触发-同比变动": info.get("triggers", {}).get("同比变动>=阈值", False),
            "触发-强制纳入": info.get("triggers", {}).get("强制纳入", False),
        })
    return pd.DataFrame(rows)
