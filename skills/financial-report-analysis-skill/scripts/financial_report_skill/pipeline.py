from __future__ import annotations

import shutil
import traceback
from pathlib import Path
from typing import Any

import pandas as pd

from .config import SkillConfig
from .errors import SkillError
from .indicators import compute_indicators, export_indicator_warnings
from .major_accounts import (
    build_all_text_contexts,
    build_simplified_text_contexts,
    export_account_texts,
    force_add_major_accounts,
    identify_major_accounts,
    major_accounts_to_dataframe,
)
from .structure_yoy import (
    build_account_order_index,
    build_structure_tables,
    build_yoy_tables,
    export_structure_yoy_outputs,
)
from .utils import dump_json, ensure_jsonable, split_balance_sheet_sections
from .validators import (
    detect_report_type,
    standardize_standard_workbook,
    validate_input_file,
    validate_standardized_workbook,
    read_standard_workbook,
    detect_sheet_name,
)
from .wind_cleaner import (
    clean_wind_exported_financial_workbook,
    validate_wind_cleaned_financial_workbook,
    wind_cleaning_log_to_text,
)


def _make_output_dirs(base: Path) -> dict[str, Path]:
    dirs = {
        "base": base,
        "standard": base / "01_标准化输入",
        "structure": base / "02_占比表",
        "yoy": base / "03_同比表",
        "merged": base / "04_汇总表",
        "text": base / "05_文本分析",
        "indicators": base / "06_财务指标",
        "logs": base / "07_提示与日志",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def _write_params_text(config: SkillConfig, detected_report_type: str, output_paths: dict[str, Path], path: Path) -> None:
    lines = ["【本次运行参数说明】", "", "一、输入文件"]
    lines.append(f"- 原始文件名：{config.input_path.name}")
    lines.append(f"- 识别报表类型：{'Wind标准导出' if detected_report_type == 'wind' else '标准人工表'}")
    lines.append(f"- 公司名称：{config.company_name}")
    lines.append(f"- 金额单位：{'万元' if config.input_unit_is_wanyuan else '已按亿元/原单位处理'}")
    lines.append(f"- 读取报告期数量：最多 {config.max_periods} 期")
    lines.append("")
    lines.append("二、重大会计科目识别参数")
    lines.append(f"- 结构占比阈值：{config.major_ratio_threshold:.2f}%")
    lines.append(f"- 同比变动阈值：{config.major_yoy_threshold:.2f}%")
    lines.append("- 识别窗口：最近1年1期")
    lines.append(f"- 强制纳入模式：{config.forced_accounts_mode}")
    lines.append(f"- 实际强制纳入科目清单：{'、'.join(sorted(config.resolved_forced_accounts)) if config.resolved_forced_accounts else '无'}")
    lines.append("")
    lines.append("三、简化重大科目参数")
    lines.append(f"- 简化占比阈值：{config.simplified_ratio_threshold:.2f}%")
    lines.append("- 强制纳入科目是否保留：是")
    lines.append("- 利润表/现金流量表科目是否全部保留：是")
    lines.append("")
    lines.append("四、财务指标参数")
    lines.append(f"- 输入单位是否为万元：{'是' if config.input_unit_is_wanyuan else '否'}")
    lines.append("- 输出单位：亿元、百分比、倍数")
    lines.append(f"- max_periods：{config.max_periods}")
    lines.append(f"- alias_map_bs：{config.alias_map_bs}")
    lines.append(f"- alias_map_pl：{config.alias_map_pl}")
    lines.append(f"- alias_map_cf：{config.alias_map_cf}")
    lines.append("")
    lines.append("五、输出文件")
    for key, p in output_paths.items():
        lines.append(f"- {key}：{p}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _safe_rel(base: Path, p: Path) -> str:
    try:
        return str(p.relative_to(base))
    except Exception:
        return str(p)


def run_pipeline(config: SkillConfig) -> dict[str, Any]:
    input_path = validate_input_file(config.input_path)
    dirs = _make_output_dirs(config.output_dir)
    detected_report_type = detect_report_type(input_path, config.is_wind_report)

    standard_path = dirs["standard"] / f"标准化财务报表_{config.company_name}.xlsx"
    wind_log_path = dirs["logs"] / f"Wind清洗日志_{config.company_name}.txt"

    if detected_report_type == "wind":
        cleaned_sheets, wind_delete_log_df = clean_wind_exported_financial_workbook(input_path, standard_path)
        validate_wind_cleaned_financial_workbook(cleaned_sheets, wind_delete_log_df)
        wind_log_path.write_text(wind_cleaning_log_to_text(wind_delete_log_df), encoding="utf-8")
    else:
        standardize_standard_workbook(input_path, standard_path)
        wind_log_path.write_text("【Wind 清洗日志】\n\n本次输入识别为标准人工表，未启用 Wind 清洗。", encoding="utf-8")

    normalized = validate_standardized_workbook(standard_path)

    asset_structure_df, liab_structure_df = build_structure_tables(standard_path, ratio_round=config.round_digits)
    yoy_tables = build_yoy_tables(standard_path)
    asset_order = build_account_order_index(asset_structure_df)
    liab_order = build_account_order_index(liab_structure_df)

    out_paths = {
        "标准化财务报表": standard_path,
        "资产负债结构化表": dirs["structure"] / f"资产负债结构化表_{config.company_name}.xlsx",
        "同比分析表": dirs["yoy"] / f"同比分析表_{config.company_name}.xlsx",
        "占比同比汇总表": dirs["merged"] / f"占比同比汇总表_{config.company_name}.xlsx",
        "重大会计科目分析": dirs["text"] / f"重大会计科目分析_{config.company_name}.txt",
        "简化重大会计科目分析": dirs["text"] / f"简化重大会计科目_{config.company_name}_阈值{config.simplified_ratio_threshold}.txt",
        "重大会计科目清单": dirs["text"] / f"重大会计科目清单_{config.company_name}.xlsx",
        "财务指标": dirs["indicators"] / f"财务指标_{config.company_name}.xlsx",
        "财务指标计算提示单": dirs["logs"] / f"财务指标计算提示单_{config.company_name}.txt",
        "运行参数说明": dirs["logs"] / f"运行参数说明_{config.company_name}.txt",
        "Wind清洗日志": wind_log_path,
    }
    export_structure_yoy_outputs(
        asset_structure_df,
        liab_structure_df,
        yoy_tables,
        {"structure": out_paths["资产负债结构化表"], "yoy": out_paths["同比分析表"], "merged": out_paths["占比同比汇总表"]},
    )

    # Need BS split for forced additions.
    sheets = read_standard_workbook(standard_path)
    bs = sheets[detect_sheet_name(sheets, "资产负债表")].copy().dropna(how="all").reset_index(drop=True)
    bs.columns = ["科目"] + [str(c) for c in bs.columns[1:]]
    sections = split_balance_sheet_sections(bs)

    major_accounts = identify_major_accounts(
        asset_structure_df=asset_structure_df,
        liab_structure_df=liab_structure_df,
        yoy_tables=yoy_tables,
        ratio_threshold=config.major_ratio_threshold,
        yoy_threshold=config.major_yoy_threshold,
    )
    force_add_major_accounts(
        major_accounts=major_accounts,
        forced_accounts=config.resolved_forced_accounts,
        bs_asset_df=asset_structure_df,
        bs_liab_df=liab_structure_df,
        pl_yoy_df=yoy_tables["利润表同比表"],
        cf_yoy_df=yoy_tables["现金流量表同比表"],
    )
    text_contexts = build_all_text_contexts(
        major_accounts=major_accounts,
        tables={
            "资产同比表": yoy_tables["资产同比表"],
            "负债同比表": yoy_tables["负债同比表"],
            "权益同比表": yoy_tables["所有者权益同比表"],
            "利润表同比表": yoy_tables["利润表同比表"],
            "现金流量表同比表": yoy_tables["现金流量表同比表"],
        },
        asset_structure_df=asset_structure_df,
        liab_structure_df=liab_structure_df,
        asset_order=asset_order,
        liab_order=liab_order,
        yoy_threshold=config.major_yoy_threshold,
    )
    export_account_texts(text_contexts, out_paths["重大会计科目分析"], separate_cash_flow_group=config.separate_cash_flow_group)
    simple_contexts = build_simplified_text_contexts(text_contexts, major_accounts, config.simplified_ratio_threshold)
    export_account_texts(simple_contexts, out_paths["简化重大会计科目分析"], separate_cash_flow_group=config.separate_cash_flow_group)
    major_accounts_to_dataframe(major_accounts).to_excel(out_paths["重大会计科目清单"], sheet_name="重大会计科目清单", index=False)

    indicators_df, warnings = compute_indicators(
        file_path=standard_path,
        alias_map_bs=config.alias_map_bs,
        alias_map_pl=config.alias_map_pl,
        alias_map_cf=config.alias_map_cf,
        input_unit_is_wanyuan=config.input_unit_is_wanyuan,
        max_periods=config.max_periods,
    )
    indicators_df.to_excel(out_paths["财务指标"], sheet_name="财务指标", index=True)
    export_indicator_warnings(warnings, out_paths["财务指标计算提示单"])
    _write_params_text(config, detected_report_type, out_paths, out_paths["运行参数说明"])

    manifest = {
        "status": "success",
        "company_name": config.company_name,
        "input_file": str(input_path),
        "detected_report_type": detected_report_type,
        "parameters": config.to_jsonable() | {"resolved_forced_accounts": sorted(config.resolved_forced_accounts)},
        "outputs": [
            {"name": name, "path": str(path), "relative_path": _safe_rel(config.output_dir, path), "type": path.suffix.lower().lstrip(".")}
            for name, path in out_paths.items()
        ],
        "warnings_count": sum(len(msgs) for period_map in warnings.values() for msgs in period_map.values()),
        "manifest_path": str(dirs["base"] / "manifest.json"),
    }
    dump_json(dirs["base"] / "manifest.json", manifest)
    return manifest


def write_error_manifest(output_dir: str | Path, error: Exception, config: SkillConfig | None = None) -> dict[str, Any]:
    output_dir = Path(output_dir)
    logs_dir = output_dir / "07_提示与日志"
    logs_dir.mkdir(parents=True, exist_ok=True)
    code = getattr(error, "code", "E_UNEXPECTED_ERROR")
    error_file = logs_dir / "报错说明.txt"
    lines = ["【报错说明】", "", f"错误代码：{code}", f"错误信息：{str(error)}", ""]
    if config is not None:
        lines.extend(["【已读取参数】", ""])
        for k, v in config.to_jsonable().items():
            lines.append(f"- {k}: {v}")
        lines.append("")
    lines.extend(["【Traceback】", traceback.format_exc()])
    error_file.write_text("\n".join(lines), encoding="utf-8")
    manifest = {
        "status": "failed",
        "error_code": code,
        "error_message": str(error),
        "error_file": str(error_file),
    }
    dump_json(output_dir / "manifest.json", manifest)
    return manifest
