from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .validators import read_standard_workbook, detect_sheet_name
from .utils import _account_row_mask, clean_account_name, format_date_col, split_balance_sheet_sections

class ValueStatus(Enum):
    OK = "OK"
    MISSING_VALUE = "MISSING_VALUE"
    MISSING_ITEM = "MISSING_ITEM"

DEBT_ITEMS = ["长期借款", "应付债券", "短期借款", "交易性金融负债", "应付票据", "应付短期债券", "一年内到期的非流动负债"]
BS_TOTAL_ASSET_CANDS = ["总资产", "资产总计", "资产合计"]
BS_TOTAL_LIAB_CANDS = ["总负债", "负债总计", "负债合计"]
BS_TOTAL_EQUITY_CANDS = ["所有者权益合计", "股东权益合计", "所有者权益总计", "股东权益总计"]
BS_CUR_ASSET_CANDS = ["流动资产合计", "流动资产总计"]
BS_CUR_LIAB_CANDS = ["流动负债合计", "流动负债总计"]
BS_AR_CANDS = ["应收账款"]
BS_INV_CANDS = ["存货"]
PL_REV_CANDS = ["营业收入"]
PL_COGS_CANDS = ["营业成本"]
PL_PROFIT_TOTAL_CANDS = ["利润总额"]
PL_NETPROFIT_CANDS = ["净利润"]
PL_INTEREST_CANDS = ["利息费用", "利息支出", "其中利息费用", "其中:利息费用"]
CF_OPERATE_CANDS = ["经营活动产生的现金流量净额"]
CF_INVEST_CANDS = ["投资活动产生的现金流量净额"]
CF_FINANCE_CANDS = ["筹资活动产生的现金流量净额"]
PL_INVEST_INCOME_CANDS = ["投资收益", "投资损益", "投资损失", "投资净收益"]
PL_FAIR_VALUE_CANDS = ["公允价值变动收益", "公允价值变动损益", "公允价值变动损失", "公允价值变动净收益"]
PL_CREDIT_IMPAIR_CANDS = ["信用减值损失", "信用减值损益", "信用减值收益"]
PL_ASSET_IMPAIR_CANDS = ["资产减值损失", "资产减值损益", "资产减值收益"]
PL_ASSET_DISPOSE_CANDS = ["资产处置收益", "资产处置损益", "资产处置损失"]
PL_NONOPER_INCOME_CANDS = ["营业外收入"]
PL_NONOPER_EXP_CANDS = ["营业外支出"]
PL_OTHER_INCOME_CANDS = ["其他收益", "其他损益", "其他损失"]


def safe_get_value_with_status(df: pd.DataFrame, cands: list, col, alias_map: dict, indicator: str = "", period=None, table_tag: str = ""):
    item_col = df.columns[0]
    _df = df.copy()
    _df["_clean_item"] = _df[item_col].astype(str).apply(clean_account_name)
    for cand in cands:
        target = alias_map.get(cand, cand)
        target_clean = clean_account_name(str(target))
        rows = _df.index[_df["_clean_item"] == target_clean].tolist()
        if not rows:
            continue
        row_idx = rows[0]
        raw_val = _df.loc[row_idx, col]
        val = pd.to_numeric(raw_val, errors="coerce")
        if pd.isna(val):
            return 0.0, ValueStatus.MISSING_VALUE, f"[{indicator}][{period}] {table_tag} 科目「{cand}」本期未披露，按0处理"
        return float(val), ValueStatus.OK, None
    return 0.0, ValueStatus.MISSING_ITEM, f"[{indicator}][{period}] {table_tag} 未识别到科目 {cands}"


def safe_get_value(df: pd.DataFrame, account_name: str, col: str, alias_map: dict | None = None, indicator: str = "", period: str | None = None, table_tag: str = ""):
    alias_map = alias_map or {}
    if col not in df.columns:
        return np.nan, False, f"[{indicator}][{period}] {table_tag} 表中不存在列 {col}"
    item_col = df.columns[0]
    candidates = [account_name]
    if account_name in alias_map:
        candidates.append(alias_map[account_name])
    candidates_clean = [clean_account_name(x) for x in candidates]
    pool = df.copy()
    pool["_clean_name"] = pool[item_col].astype(str).apply(clean_account_name)
    rows = pool.index[pool["_clean_name"].isin(candidates_clean)].tolist()
    if not rows:
        return np.nan, False, f"[{indicator}][{period}] {table_tag} 表中未识别到科目「{account_name}」"
    row_idx = rows[0]
    acct_mask = _account_row_mask(df)
    is_account_row = bool(acct_mask.loc[row_idx])
    val = pd.to_numeric(pool.loc[row_idx, col], errors="coerce")
    if pd.isna(val):
        if is_account_row:
            return 0.0, True, f"[{indicator}][{period}] {table_tag} 科目「{account_name}」本期未披露，按 0 处理"
        return np.nan, False, f"[{indicator}][{period}] {table_tag} 科目「{account_name}」为说明性行，未取值"
    return float(val), True, None


def safe_get_value_from_cands(df: pd.DataFrame, cands: list, col, alias_map: dict, indicator: str = "", period=None, table_tag: str = ""):
    if df is None or not cands:
        return np.nan, False, None
    item_col = df.columns[0]
    _df = df.copy()
    _df["_clean_item"] = _df[item_col].astype(str).apply(clean_account_name)
    for cand in cands:
        target = alias_map.get(cand, cand)
        target_clean = clean_account_name(str(target))
        mask = _df["_clean_item"] == target_clean
        rows = _df.index[mask].tolist()
        if not rows:
            continue
        row_idx = rows[0]
        raw_name = _df.loc[row_idx, item_col]
        val = pd.to_numeric(_df.loc[row_idx, col], errors="coerce")
        msg = None
        if clean_account_name(str(raw_name)) != clean_account_name(str(cand)):
            msg = f"[{indicator}][{period}] 使用候选科目「{raw_name}」替代「{cand}」。"
        return float(val) if pd.notna(val) else np.nan, True, msg
    return np.nan, False, None


def get_parent_netprofit_fuzzy(pl, period_col, *, keyword="母公司"):
    df = pl.copy()
    item_col = df.columns[0]
    df["_raw_item"] = df[item_col].astype(str)
    df["_clean_item"] = df[item_col].astype(str).apply(clean_account_name)
    hits = df[df["_clean_item"].str.contains(keyword, regex=False)]
    if hits.empty:
        return 0.0, False, None
    row = hits.iloc[0]
    raw_name = row["_raw_item"]
    val = pd.to_numeric(row.get(period_col, np.nan), errors="coerce")
    if pd.isna(val):
        return 0.0, False, raw_name
    return float(val), True, raw_name


def _to_yiyuan(x, input_unit_is_wanyuan=True):
    if pd.isna(x):
        return np.nan
    return x / 10000 if input_unit_is_wanyuan else x


def calc_debt_and_leverage_indicators(*, bs, bs_liab, periods, alias_map_bs, input_unit_is_wanyuan, warnings, results):
    for end_col in periods:
        period_label = end_col
        debt_sum = 0.0
        for item in DEBT_ITEMS:
            v, status, msg = safe_get_value_with_status(bs_liab, [item], end_col, alias_map_bs, indicator="全部债务", period=period_label, table_tag="BS")
            if msg:
                warnings.setdefault("全部债务", {}).setdefault(period_label, []).append(msg)
            if status == ValueStatus.OK:
                debt_sum += v
        results.loc["全部债务（亿元）", end_col] = _to_yiyuan(debt_sum, input_unit_is_wanyuan)
        liab, ok_l, msg1 = safe_get_value_from_cands(bs, BS_TOTAL_LIAB_CANDS, end_col, alias_map_bs, indicator="资产负债率", period=period_label, table_tag="BS")
        asset, ok_a, msg2 = safe_get_value_from_cands(bs, BS_TOTAL_ASSET_CANDS, end_col, alias_map_bs, indicator="资产负债率", period=period_label, table_tag="BS")
        if ok_l and ok_a and asset != 0:
            results.loc["资产负债率（%）", end_col] = liab / asset * 100
        else:
            results.loc["资产负债率（%）", end_col] = np.nan
            warnings.setdefault("资产负债率", {}).setdefault(period_label, []).extend([x for x, ok in [("总负债", ok_l), ("总资产", ok_a)] if not ok])
        for m in (msg1, msg2):
            if m:
                warnings.setdefault("资产负债率", {}).setdefault(period_label, []).append(m)
        equity, ok_e, msg_e = safe_get_value_from_cands(bs, BS_TOTAL_EQUITY_CANDS, end_col, alias_map_bs, indicator="债务资本比率", period=period_label, table_tag="BS")
        if ok_e and (debt_sum + equity) != 0:
            results.loc["债务资本比率（%）", end_col] = debt_sum / (debt_sum + equity) * 100
        else:
            results.loc["债务资本比率（%）", end_col] = np.nan
            warnings.setdefault("债务资本比率", {}).setdefault(period_label, []).append("全部债务或所有者权益缺失")
        if msg_e:
            warnings.setdefault("债务资本比率", {}).setdefault(period_label, []).append(msg_e)


def calc_profitability_indicators(*, pl, periods, alias_map_pl, warnings, results):
    for end_col in periods:
        rev, ok_r, msg1 = safe_get_value_from_cands(pl, PL_REV_CANDS, end_col, alias_map_pl, indicator="营业毛利率", period=end_col, table_tag="PL")
        cogs, ok_c, msg2 = safe_get_value_from_cands(pl, PL_COGS_CANDS, end_col, alias_map_pl, indicator="营业毛利率", period=end_col, table_tag="PL")
        if ok_r and ok_c and rev != 0:
            results.loc["营业毛利率（%）", end_col] = (rev - cogs) / rev * 100
        else:
            results.loc["营业毛利率（%）", end_col] = np.nan
            warnings.setdefault("营业毛利率", {}).setdefault(end_col, []).extend([x for x, ok in [("营业收入", ok_r), ("营业成本", ok_c)] if not ok])
        for m in (msg1, msg2):
            if m:
                warnings.setdefault("营业毛利率", {}).setdefault(end_col, []).append(m)


def calc_return_indicators(*, bs, pl, periods, alias_map_bs, alias_map_pl, warnings, results):
    for i, end_col in enumerate(periods):
        start_col = periods[i + 1] if i + 1 < len(periods) else None
        if start_col is None:
            results.loc["平均总资产回报率（%）", end_col] = np.nan
            warnings.setdefault("ROA", {}).setdefault(end_col, []).append("缺少期初总资产数据，平均总资产报酬率不可计算")
            continue
        pt, st_pt, msg_pt = safe_get_value_with_status(pl, PL_PROFIT_TOTAL_CANDS, end_col, alias_map_pl, indicator="ROA", period=end_col, table_tag="PL")
        interest, st_i, msg_i = safe_get_value_with_status(pl, PL_INTEREST_CANDS, end_col, alias_map_pl, indicator="ROA", period=end_col, table_tag="PL")
        ta_end, st_t1, msg1 = safe_get_value_with_status(bs, BS_TOTAL_ASSET_CANDS, end_col, alias_map_bs, indicator="ROA", period=end_col, table_tag="BS")
        ta_start, st_t0, msg2 = safe_get_value_with_status(bs, BS_TOTAL_ASSET_CANDS, start_col, alias_map_bs, indicator="ROA", period=end_col, table_tag="BS")
        for m in (msg_pt, msg_i, msg1, msg2):
            if m:
                warnings.setdefault("ROA", {}).setdefault(end_col, []).append(m)
        if st_pt != ValueStatus.OK or st_t1 != ValueStatus.OK or st_t0 != ValueStatus.OK or st_i == ValueStatus.MISSING_ITEM:
            results.loc["平均总资产回报率（%）", end_col] = np.nan
            warnings.setdefault("ROA", {}).setdefault(end_col, []).append("关键科目缺失（利润总额 / 利息费用 / 期初或期末总资产），平均总资产报酬率不可计算")
            continue
        if (ta_end + ta_start) == 0:
            results.loc["平均总资产回报率（%）", end_col] = np.nan
            warnings.setdefault("ROA", {}).setdefault(end_col, []).append("期初与期末总资产合计为 0，平均总资产报酬率不可计算")
            continue
        avg_ta = (ta_end + ta_start) / 2
        results.loc["平均总资产回报率（%）", end_col] = (pt + interest) / avg_ta * 100
        if st_i == ValueStatus.MISSING_VALUE:
            results.loc["ROA（不含利息费用，参考）（%）", end_col] = pt / avg_ta * 100


def calc_scale_indicators(*, bs, pl, cf, periods, alias_map_bs, alias_map_pl, alias_map_cf, input_unit_is_wanyuan, warnings, results):
    for end_col in periods:
        for cands, warn_name, label, table, alias in [
            (BS_TOTAL_ASSET_CANDS, "总资产", "总资产（亿元）", bs, alias_map_bs),
            (BS_TOTAL_LIAB_CANDS, "总负债", "总负债（亿元）", bs, alias_map_bs),
            (BS_TOTAL_EQUITY_CANDS, "所有者权益", "所有者权益（亿元）", bs, alias_map_bs),
        ]:
            v, ok, msg = safe_get_value_from_cands(table, cands, end_col, alias, indicator=warn_name, period=end_col, table_tag="BS")
            results.loc[label, end_col] = _to_yiyuan(v, input_unit_is_wanyuan) if ok else np.nan
            if not ok:
                warnings.setdefault(warn_name, {}).setdefault(end_col, []).append(f"未识别到{warn_name}")
            if msg:
                warnings.setdefault(warn_name, {}).setdefault(end_col, []).append(msg)
        for acc, label in [("营业总收入", "营业总收入（亿元）"), ("利润总额", "利润总额（亿元）"), ("净利润", "净利润（亿元）")]:
            v, ok, msg = safe_get_value(pl, acc, end_col, alias_map_pl, indicator=acc, period=end_col, table_tag="PL")
            results.loc[label, end_col] = _to_yiyuan(v, input_unit_is_wanyuan) if ok else np.nan
            if not ok:
                warnings.setdefault(acc, {}).setdefault(end_col, []).append(f"未识别到{acc}")
            if msg:
                warnings.setdefault(acc, {}).setdefault(end_col, []).append(msg)
        v, ok, raw_item = get_parent_netprofit_fuzzy(pl, end_col, keyword="母公司")
        results.loc["归属于母公司所有者的净利润（亿元）", end_col] = _to_yiyuan(v, input_unit_is_wanyuan) if ok else np.nan
        if not ok:
            warnings.setdefault("归母净利润", {}).setdefault(end_col, []).append("未识别到归母净利润")
        else:
            warnings.setdefault("归母净利润", {}).setdefault(end_col, []).append(f"归母净利润采用模糊匹配科目：{raw_item}")
        for cands, name, label in [(CF_OPERATE_CANDS, "经营活动产生现金流量净额", "经营活动产生现金流量净额（亿元）"), (CF_INVEST_CANDS, "投资活动产生现金流量净额", "投资活动产生现金流量净额（亿元）"), (CF_FINANCE_CANDS, "筹资活动产生现金流量净额", "筹资活动产生现金流量净额（亿元）")]:
            v, ok, msg = safe_get_value_from_cands(cf, cands, end_col, alias_map_cf, indicator=name, period=end_col, table_tag="CF")
            results.loc[label, end_col] = _to_yiyuan(v, input_unit_is_wanyuan) if ok else np.nan
            if not ok:
                warnings.setdefault(name, {}).setdefault(end_col, []).append(f"未识别到{name}")
            if msg:
                warnings.setdefault(name, {}).setdefault(end_col, []).append(msg)


def calc_liquidity_indicators(*, bs, periods, alias_map_bs, warnings, results):
    for end_col in periods:
        ca, st_ca, msg_ca = safe_get_value_with_status(bs, BS_CUR_ASSET_CANDS, end_col, alias_map_bs, indicator="流动性指标", period=end_col, table_tag="BS")
        cl, st_cl, msg_cl = safe_get_value_with_status(bs, BS_CUR_LIAB_CANDS, end_col, alias_map_bs, indicator="流动性指标", period=end_col, table_tag="BS")
        inv, st_inv, msg_inv = safe_get_value_with_status(bs, BS_INV_CANDS, end_col, alias_map_bs, indicator="速动比率", period=end_col, table_tag="BS")
        for m in (msg_ca, msg_cl, msg_inv):
            if m:
                warnings.setdefault("流动性指标", {}).setdefault(end_col, []).append(m)
        if st_ca != ValueStatus.OK or st_cl != ValueStatus.OK or cl == 0:
            results.loc["流动比率", end_col] = np.nan
            warnings.setdefault("流动比率", {}).setdefault(end_col, []).append("关键科目缺失或流动负债为0，流动比率不可计算")
        else:
            results.loc["流动比率", end_col] = ca / cl
        if st_ca != ValueStatus.OK or st_cl != ValueStatus.OK or st_inv != ValueStatus.OK or cl == 0:
            results.loc["速动比率", end_col] = np.nan
            warnings.setdefault("速动比率", {}).setdefault(end_col, []).append("关键科目缺失或流动负债为0，速动比率不可计算")
        else:
            results.loc["速动比率", end_col] = (ca - inv) / cl


def calc_turnover_indicators(*, bs, pl, periods, alias_map_bs, alias_map_pl, warnings, results):
    for i, end_col in enumerate(periods):
        start_col = periods[i + 1] if i + 1 < len(periods) else None
        if start_col is None:
            results.loc["应收账款周转率", end_col] = np.nan
            results.loc["存货周转率", end_col] = np.nan
            warnings.setdefault("周转率", {}).setdefault(end_col, []).append("缺少期初数据")
            continue
        rev, ok_r, _ = safe_get_value_from_cands(pl, PL_REV_CANDS, end_col, alias_map_pl, indicator="应收账款周转率", period=end_col, table_tag="PL")
        cogs, ok_c, _ = safe_get_value_from_cands(pl, PL_COGS_CANDS, end_col, alias_map_pl, indicator="存货周转率", period=end_col, table_tag="PL")
        ar_end, ok_ar1, _ = safe_get_value_from_cands(bs, BS_AR_CANDS, end_col, alias_map_bs, indicator="应收账款周转率", period=end_col, table_tag="BS")
        ar_start, ok_ar0, _ = safe_get_value_from_cands(bs, BS_AR_CANDS, start_col, alias_map_bs, indicator="应收账款周转率", period=end_col, table_tag="BS")
        inv_end, ok_i1, _ = safe_get_value_from_cands(bs, BS_INV_CANDS, end_col, alias_map_bs, indicator="存货周转率", period=end_col, table_tag="BS")
        inv_start, ok_i0, _ = safe_get_value_from_cands(bs, BS_INV_CANDS, start_col, alias_map_bs, indicator="存货周转率", period=end_col, table_tag="BS")
        if ok_r and ok_ar1 and ok_ar0 and (ar_end + ar_start) != 0:
            results.loc["应收账款周转率", end_col] = rev / ((ar_end + ar_start) / 2)
        else:
            results.loc["应收账款周转率", end_col] = np.nan
            warnings.setdefault("应收账款周转率", {}).setdefault(end_col, []).append("营业收入或应收账款缺失")
        if ok_c and ok_i1 and ok_i0 and (inv_end + inv_start) != 0:
            results.loc["存货周转率", end_col] = cogs / ((inv_end + inv_start) / 2)
        else:
            results.loc["存货周转率", end_col] = np.nan
            warnings.setdefault("存货周转率", {}).setdefault(end_col, []).append("营业成本或存货缺失")


def calc_roe_indicators(*, bs, pl, periods, alias_map_bs, alias_map_pl, warnings, results):
    for i, end_col in enumerate(periods):
        start_col = periods[i + 1] if i + 1 < len(periods) else None
        if start_col is None:
            results.loc["加权平均净资产收益率（%）", end_col] = np.nan
            warnings.setdefault("ROE", {}).setdefault(end_col, []).append("缺少期初数据")
            continue
        np_val, ok_np, _ = safe_get_value(pl, "净利润", end_col, alias_map_pl, indicator="ROE", period=end_col, table_tag="PL")
        eq_end, ok_e1, msg1 = safe_get_value_from_cands(bs, BS_TOTAL_EQUITY_CANDS, end_col, alias_map_bs, indicator="ROE", period=end_col, table_tag="BS")
        eq_start, ok_e0, msg2 = safe_get_value_from_cands(bs, BS_TOTAL_EQUITY_CANDS, start_col, alias_map_bs, indicator="ROE", period=end_col, table_tag="BS")
        if ok_np and ok_e1 and ok_e0 and (eq_end + eq_start) != 0:
            results.loc["加权平均净资产收益率（%）", end_col] = np_val / ((eq_end + eq_start) / 2) * 100
        else:
            results.loc["加权平均净资产收益率（%）", end_col] = np.nan
            warnings.setdefault("ROE", {}).setdefault(end_col, []).append("净利润或期初/期末所有者权益缺失")
        for m in (msg1, msg2):
            if m:
                warnings.setdefault("ROE", {}).setdefault(end_col, []).append(m)


def calc_deducted_profit_and_roe_indicators(*, bs, pl, periods, alias_map_bs, alias_map_pl, warnings, results, input_unit_is_wanyuan=True):
    nonrec_components = [("投资收益", PL_INVEST_INCOME_CANDS, +1), ("公允价值变动收益", PL_FAIR_VALUE_CANDS, +1), ("信用减值损失", PL_CREDIT_IMPAIR_CANDS, +1), ("资产减值损失", PL_ASSET_IMPAIR_CANDS, +1), ("资产处置收益", PL_ASSET_DISPOSE_CANDS, +1), ("营业外收入", PL_NONOPER_INCOME_CANDS, +1), ("营业外支出", PL_NONOPER_EXP_CANDS, -1), ("其他收益", PL_OTHER_INCOME_CANDS, +1)]
    for i, end_col in enumerate(periods):
        start_col = periods[i + 1] if i + 1 < len(periods) else None
        np_val, ok_np, msg_np = safe_get_value_from_cands(pl, PL_NETPROFIT_CANDS, end_col, alias_map_pl, indicator="扣非净利润", period=end_col, table_tag="PL")
        if msg_np:
            warnings.setdefault("扣非净利润", {}).setdefault(end_col, []).append(msg_np)
        if not ok_np:
            results.loc["扣除非经常性损益后净利润（亿元）", end_col] = np.nan
            results.loc["扣除非经常性损益后加权平均净资产收益率（%）", end_col] = np.nan
            warnings.setdefault("扣非净利润", {}).setdefault(end_col, []).append("未识别到净利润")
            continue
        nonrec_sum = 0.0
        for item_name, item_cands, sign in nonrec_components:
            v, status, msg = safe_get_value_with_status(pl, item_cands, end_col, alias_map_pl, indicator="非经常性损益", period=end_col, table_tag="PL")
            if msg:
                warnings.setdefault("非经常性损益", {}).setdefault(end_col, []).append(msg)
            if status == ValueStatus.OK:
                nonrec_sum += sign * v
        deducted_np = np_val - nonrec_sum
        results.loc["扣除非经常性损益后净利润（亿元）", end_col] = _to_yiyuan(deducted_np, input_unit_is_wanyuan)
        if start_col is None:
            results.loc["扣除非经常性损益后加权平均净资产收益率（%）", end_col] = np.nan
            warnings.setdefault("扣非ROE", {}).setdefault(end_col, []).append("缺少期初数据")
            continue
        eq_end, ok_e1, msg1 = safe_get_value_from_cands(bs, BS_TOTAL_EQUITY_CANDS, end_col, alias_map_bs, indicator="扣非ROE", period=end_col, table_tag="BS")
        eq_start, ok_e0, msg0 = safe_get_value_from_cands(bs, BS_TOTAL_EQUITY_CANDS, start_col, alias_map_bs, indicator="扣非ROE", period=end_col, table_tag="BS")
        for m in (msg1, msg0):
            if m:
                warnings.setdefault("扣非ROE", {}).setdefault(end_col, []).append(m)
        if not (ok_e1 and ok_e0) or (eq_end + eq_start) == 0:
            results.loc["扣除非经常性损益后加权平均净资产收益率（%）", end_col] = np.nan
            warnings.setdefault("扣非ROE", {}).setdefault(end_col, []).append("所有者权益缺失或为0")
            continue
        results.loc["扣除非经常性损益后加权平均净资产收益率（%）", end_col] = deducted_np / ((eq_end + eq_start) / 2) * 100


def calc_expense_rate_indicators(*, pl, periods, alias_map_pl, warnings, results):
    for end_col in periods:
        rev, ok_rev, msg_rev = safe_get_value(pl, "营业收入", end_col, alias_map_pl, indicator="期间费用率", period=end_col, table_tag="PL")
        if not ok_rev or rev == 0:
            for name in ["销售费用率（%）", "管理费用率（%）", "研发费用率（%）", "财务费用率（%）"]:
                results.loc[name, end_col] = np.nan
            warnings.setdefault("期间费用率", {}).setdefault(end_col, []).append("缺少营业收入")
            if msg_rev:
                warnings.setdefault("期间费用率", {}).setdefault(end_col, []).append(msg_rev)
            continue
        for acc_name, indicator_name in {"销售费用": "销售费用率（%）", "管理费用": "管理费用率（%）", "研发费用": "研发费用率（%）", "财务费用": "财务费用率（%）"}.items():
            val, ok, msg = safe_get_value(pl, acc_name, end_col, alias_map_pl, indicator=indicator_name, period=end_col, table_tag="PL")
            if ok:
                results.loc[indicator_name, end_col] = val / rev * 100
            else:
                results.loc[indicator_name, end_col] = np.nan
                warnings.setdefault(indicator_name, {}).setdefault(end_col, []).append(f"未识别到{acc_name}")
            if msg:
                warnings.setdefault(indicator_name, {}).setdefault(end_col, []).append(msg)


def compute_indicators(file_path, alias_map_bs=None, alias_map_pl=None, alias_map_cf=None, input_unit_is_wanyuan=True, max_periods=4):
    alias_map_bs = alias_map_bs or {}
    alias_map_pl = alias_map_pl or {}
    alias_map_cf = alias_map_cf or {}
    sheets = read_standard_workbook(file_path)
    bs = sheets[detect_sheet_name(sheets, "资产负债表")].copy().dropna(how="all").reset_index(drop=True)
    pl = sheets[detect_sheet_name(sheets, "利润表")].copy().dropna(how="all").reset_index(drop=True)
    cf = sheets[detect_sheet_name(sheets, "现金流量表")].copy().dropna(how="all").reset_index(drop=True)
    for df in (bs, pl, cf):
        df.columns = ["科目"] + [format_date_col(c) for c in df.columns[1:]]
    sections = split_balance_sheet_sections(bs)
    bs_liab = sections["负债"]
    periods = list(bs.columns[1:])[:max_periods]
    indicator_index = ["总资产（亿元）", "总负债（亿元）", "全部债务（亿元）", "所有者权益（亿元）", "营业总收入（亿元）", "利润总额（亿元）", "净利润（亿元）", "归属于母公司所有者的净利润（亿元）", "扣除非经常性损益后净利润（亿元）", "经营活动产生现金流量净额（亿元）", "投资活动产生现金流量净额（亿元）", "筹资活动产生现金流量净额（亿元）", "流动比率", "速动比率", "资产负债率（%）", "债务资本比率（%）", "营业毛利率（%）", "平均总资产回报率（%）", "加权平均净资产收益率（%）", "扣除非经常性损益后加权平均净资产收益率（%）", "应收账款周转率", "存货周转率", "销售费用率（%）", "管理费用率（%）", "研发费用率（%）", "财务费用率（%）"]
    results = pd.DataFrame(index=indicator_index, columns=periods, dtype="float64")
    warnings = {}
    calc_scale_indicators(bs=bs, pl=pl, cf=cf, periods=periods, alias_map_bs=alias_map_bs, alias_map_pl=alias_map_pl, alias_map_cf=alias_map_cf, input_unit_is_wanyuan=input_unit_is_wanyuan, warnings=warnings, results=results)
    calc_debt_and_leverage_indicators(bs=bs, bs_liab=bs_liab, periods=periods, alias_map_bs=alias_map_bs, input_unit_is_wanyuan=input_unit_is_wanyuan, warnings=warnings, results=results)
    calc_liquidity_indicators(bs=bs, periods=periods, alias_map_bs=alias_map_bs, warnings=warnings, results=results)
    calc_profitability_indicators(pl=pl, periods=periods, alias_map_pl=alias_map_pl, warnings=warnings, results=results)
    calc_return_indicators(bs=bs, pl=pl, periods=periods, alias_map_bs=alias_map_bs, alias_map_pl=alias_map_pl, warnings=warnings, results=results)
    calc_roe_indicators(bs=bs, pl=pl, periods=periods, alias_map_bs=alias_map_bs, alias_map_pl=alias_map_pl, warnings=warnings, results=results)
    calc_deducted_profit_and_roe_indicators(bs=bs, pl=pl, periods=periods, alias_map_bs=alias_map_bs, alias_map_pl=alias_map_pl, warnings=warnings, results=results, input_unit_is_wanyuan=input_unit_is_wanyuan)
    calc_turnover_indicators(bs=bs, pl=pl, periods=periods, alias_map_bs=alias_map_bs, alias_map_pl=alias_map_pl, warnings=warnings, results=results)
    calc_expense_rate_indicators(pl=pl, periods=periods, alias_map_pl=alias_map_pl, warnings=warnings, results=results)
    if "全部债务（亿元）" in results.index:
        results.loc["全部债务（万元）"] = results.loc["全部债务（亿元）"] * 1e4
    roa_ref_row = "ROA（不含利息费用，参考）（%）"
    if roa_ref_row in results.index and results.loc[roa_ref_row].isna().all():
        results = results.drop(index=roa_ref_row)
    return results.round(2), warnings


def export_indicator_warnings(warnings: dict, output_path: Path):
    lines = ["【财务指标计算提示说明】", ""]
    if not warnings:
        lines.append("本次未产生财务指标计算提示。")
    for indicator, period_map in warnings.items():
        lines.append(f"================ {indicator} ================")
        for period, msgs in period_map.items():
            period_label = period.strftime("%Y-%m-%d") if hasattr(period, "strftime") else str(period)
            lines.append(f"【报告期：{period_label}】")
            for msg in msgs:
                prefix = "[近似科目替换]" if "替代" in str(msg) else "[缺少必要数据]" if "缺少" in str(msg) or "不可计算" in str(msg) else "[检查科目]"
                lines.append(f"{prefix} {msg}")
            lines.append("")
        lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
