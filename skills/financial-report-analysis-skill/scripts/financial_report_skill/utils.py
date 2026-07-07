from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

ASSET_TOTAL_KEYWORDS = ["总资产", "资产总计", "资产合计"]
LIAB_TOTAL_KEYWORDS = ["总负债", "负债总计", "负债合计"]
EQUITY_TOTAL_KEYWORDS = ["所有者权益合计", "股东权益合计", "所有者权益总计", "股东权益总计"]


def clean_account_name(name: str) -> str:
    if not isinstance(name, str):
        return str(name)
    s = name.strip()
    s = re.sub(r"^[一二三四五六七八九十]+[、\.．]\s*", "", s)
    s = re.sub(r"^\d+[\.、\)]\s*", "", s)
    s = re.sub(r"^[（(][一二三四五六七八九十\d]+[）)]\s*", "", s)
    s = re.sub(r"^其中[:：]?\s*", "", s)
    s = re.sub(r"^(加|减)[:：]?\s*", "", s)
    s = re.sub(r"[（(][^）)]*[）)]", "", s)
    s = s.replace("：", "").replace(":", "").strip()
    return s


def _parse_date(col_name: str) -> Optional[pd.Timestamp]:
    if isinstance(col_name, pd.Timestamp):
        return col_name
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(col_name))
    if m:
        return pd.Timestamp(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
    dt = pd.to_datetime(col_name, errors="coerce")
    return dt if pd.notna(dt) else None


def format_date_col(col) -> str:
    dt = _parse_date(col)
    if dt is not None and pd.notna(dt):
        return dt.strftime("%Y-%m-%d")
    return str(col).strip()


def _account_row_mask(df: pd.DataFrame) -> pd.Series:
    value_cols = df.columns[1:]
    if len(value_cols) == 0:
        return pd.Series(False, index=df.index)
    numeric_vals = df[value_cols].apply(lambda col: pd.to_numeric(col, errors="coerce"))
    return numeric_vals.notna().any(axis=1)


def split_balance_sheet_sections(bs: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    item_col = bs.columns[0]
    s = bs[item_col].astype(str).fillna("").apply(lambda x: re.sub(r"\s+", "", x))
    liab_start_candidates = bs.index[
        s.str.match(r"^负债[:：]?") | s.str.match(r"^流动负债[:：]?")
    ].tolist()
    if not liab_start_candidates:
        liab_start_candidates = bs.index[s.str.contains("流动负债", regex=False)].tolist()
    if not liab_start_candidates:
        raise ValueError("无法定位“负债”段起点，请确认资产负债表包含“流动负债：”或“负债：”标志行。")
    liab_start = liab_start_candidates[0]

    eq_start_candidates = bs.index[
        s.str.match(r"^所有者权益[:：]?")
        | s.str.match(r"^所有者权益.*[:：]")
        | s.str.match(r"^股东权益[:：]?")
        | s.str.match(r"^股东权益.*[:：]")
    ].tolist()
    if not eq_start_candidates:
        eq_start_candidates = bs.index[
            s.str.contains("所有者权益合计", regex=False) | s.str.contains("股东权益合计", regex=False)
        ].tolist()
    if not eq_start_candidates:
        raise ValueError("无法定位“所有者权益”段起点，请确认资产负债表包含“所有者权益：”或“股东权益：”标志行。")
    eq_start = eq_start_candidates[0]
    if not (bs.index.min() <= liab_start < eq_start <= bs.index.max()):
        raise ValueError(f"资产负债表分段定位异常：liab_start={liab_start}, eq_start={eq_start}")
    return {
        "资产": bs.loc[: liab_start - 1].copy(),
        "负债": bs.loc[liab_start : eq_start - 1].copy(),
        "所有者权益": bs.loc[eq_start :].copy(),
    }


def identify_denominator_fixed(df: pd.DataFrame, keywords: List[str], table_name: str) -> pd.Series:
    item_col = df.columns[0]
    value_cols = df.columns[1:]
    numeric = df.copy()
    for c in value_cols:
        numeric[c] = pd.to_numeric(numeric[c], errors="coerce")
    numeric_pool = numeric.loc[numeric[value_cols].notna().any(axis=1)].copy()
    candidates = numeric_pool.loc[
        numeric_pool[item_col].astype(str).apply(lambda x: any(k in x for k in keywords))
    ].copy()
    if candidates.empty:
        raise ValueError(f"{table_name}：未识别到名称匹配的分母候选科目。候选关键词：{keywords}")
    total_sum = candidates[value_cols].sum(axis=1, skipna=True)
    denom_idx = total_sum.idxmax()
    denom_row = candidates.loc[denom_idx]
    return denom_row[value_cols]


def parse_report_period_label(date_like, mode: str):
    if pd.isna(date_like):
        return None, None
    date_like = pd.to_datetime(date_like)
    y, m, d = date_like.year, date_like.month, date_like.day
    if mode == "BS":
        return (f"{y}年末" if (m == 12 and d == 31) else f"{y}年{m}月末"), None
    if mode == "FLOW":
        return None, (f"{y}年度" if (m == 12 and d == 31) else f"{y}年1-{m}月")
    raise ValueError("mode must be 'BS' or 'FLOW'")


def fmt_amount_with_unit(x):
    if pd.isna(x):
        x = 0.0
    return f"{x:,.2f}万元"


def fmt_pct_no_sign(x):
    if pd.isna(x):
        x = 0.0
    return f"{abs(x):.2f}%"


def join_with_and(items: list[str]) -> str:
    items = [x for x in items if x]
    if len(items) <= 1:
        return "".join(items)
    if len(items) == 2:
        return f"{items[0]}和{items[1]}"
    return "、".join(items[:-1]) + "和" + items[-1]


def calc_delta(cur: float, prev: float) -> float:
    if pd.isna(cur):
        cur = 0.0
    if pd.isna(prev):
        prev = 0.0
    return cur - prev


def ensure_jsonable(obj):
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, set):
        return sorted(list(obj))
    if isinstance(obj, (pd.Timestamp,)):
        return obj.strftime("%Y-%m-%d")
    if isinstance(obj, (np.integer, np.floating)):
        return obj.item()
    if pd.isna(obj) if not isinstance(obj, (dict, list, tuple, set, str)) else False:
        return None
    return obj


def dump_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=ensure_jsonable), encoding="utf-8")
