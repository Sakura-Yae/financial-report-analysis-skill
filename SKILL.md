---
name: financial_report_analysis_skill
description: "Use this skill to analyze Chinese financial statement Excel workbooks, including Wind standard exports and manually standardized three-statement workbooks. It generates standardized statements, balance-sheet structure ratios, YoY analysis tables, major account text, simplified major account text, financial indicators, warning logs, parameter notes, and a manifest."
---

# Purpose

This skill processes a user-uploaded `.xlsx` financial statement workbook using the embedded Python package in `scripts/financial_report_skill`. The LLM must not manually calculate financial ratios, manually infer account substitutions, or rewrite formulas. All calculations, cleaning, validation, and output generation must come from the embedded code.

# Required runtime

This skill requires a runtime that can execute Python code and read/write files. The embedded code requires:

- Python 3.10+
- pandas
- numpy
- openpyxl

If Python code execution is unavailable, stop and tell the user that the current AI LLM environment does not support this skill because it cannot execute Python code or read/write Excel files.

If Python is available but required packages are missing, run the entry script; it will stop and produce an environment error manifest/text. Do not attempt `pip install`, do not ask the user to install packages inside the run, and do not manually simulate the result.

# Inputs

The user must provide one `.xlsx` workbook. The workbook may be either:

1. A Wind standard export workbook; or
2. A manually standardized workbook with three recognizable sheets:
   - 资产负债表
   - 利润表
   - 现金流量表

For manually standardized workbooks, the first column must be `科目`, later columns must be report dates, and the balance sheet must contain section markers sufficient to locate current assets/current liabilities/owners' equity, such as `流动资产：`, `流动负债：`, and `所有者权益：` or `股东权益：`.

# Parameters

Use a JSON config file. If the user does not provide parameters, use these defaults:

```json
{
  "company_name": "auto",
  "is_wind_report": "auto",
  "input_unit_is_wanyuan": true,
  "max_periods": 4,
  "major_ratio_threshold": 10.0,
  "major_yoy_threshold": 30.0,
  "simplified_ratio_threshold": 0.05,
  "forced_accounts_mode": "append_default",
  "forced_accounts": [],
  "alias_map_bs": {},
  "alias_map_pl": {},
  "alias_map_cf": {},
  "separate_cash_flow_group": true
}
```

Notes:

- `is_wind_report` accepts `auto`, `true`, or `false`.
- `simplified_ratio_threshold` is a percentage number. `0.05` means 0.05%, not 5%.
- `forced_accounts_mode` accepts:
  - `append_default`: use default forced accounts plus user-provided accounts.
  - `replace`: use only user-provided accounts.
  - `none`: disable forced addition.
- `alias_map_bs`, `alias_map_pl`, and `alias_map_cf` map candidate account names to the actual account names that should be matched in the statements. These mappings only affect candidate matching and do not rewrite source Excel files.

# Procedure

When running this skill:

1. Locate the uploaded `.xlsx` file.
2. Create a config JSON file using the user's parameters and defaults.
3. Run the embedded entry script:

```bash
python scripts/financial_report_skill/run.py --config /path/to/config.json
```

4. Do not call user-local code or external scripts.
5. Do not modify the embedded Python code during a normal run.
6. Read `manifest.json` from the configured output directory.
7. Reply with status, key parameters, and output files. Do not manually calculate values.

# Validation behavior

The embedded code validates:

- `.xlsx` existence and format;
- whether the workbook is a Wind export or a standardized workbook;
- whether the three core statements can be identified;
- date columns;
- balance-sheet section markers;
- core denominator/anchor accounts;
- Wind metadata and tail rows;
- generated-column contamination such as `_金额`, `_占比`, `_同比` in the input.

If validation fails, the skill must stop and return the generated error manifest/text. Do not continue with partial calculations unless the embedded code has already created a success manifest.

# Outputs

On success, the output directory contains:

- `01_标准化输入/标准化财务报表_<company>.xlsx`
- `02_占比表/资产负债结构化表_<company>.xlsx`
- `03_同比表/同比分析表_<company>.xlsx`
- `04_汇总表/占比同比汇总表_<company>.xlsx`
- `05_文本分析/重大会计科目分析_<company>.txt`
- `05_文本分析/简化重大会计科目_<company>_阈值<threshold>.txt`
- `05_文本分析/重大会计科目清单_<company>.xlsx`
- `06_财务指标/财务指标_<company>.xlsx`
- `07_提示与日志/财务指标计算提示单_<company>.txt`
- `07_提示与日志/运行参数说明_<company>.txt`
- `07_提示与日志/Wind清洗日志_<company>.txt`
- `manifest.json`

On failure, the output directory contains:

- `manifest.json`
- `07_提示与日志/报错说明.txt`

# LLM constraints

The LLM must obey these constraints:

- Do not manually compute financial indicators.
- Do not manually infer substitute accounts.
- Do not silently treat missing values as zero.
- Do not treat a Wind export as a standardized workbook unless the code does so.
- Do not skip validation.
- Do not invent output files that do not appear in the manifest.
- Do not claim success unless `manifest.json` has `"status": "success"`.
- If `manifest.json` has `"status": "failed"`, explain the error and link the error text file.

# Example command

```bash
python /path/to/financial_report_analysis_skill/scripts/financial_report_skill/run.py \
  --config /path/to/financial_skill_config.json
```

# GitHub-imported runtime note

If this skill is imported from GitHub into MiniMax or another agent platform, importing the repository is not sufficient by itself. Before claiming that the skill can run, confirm that the runtime can execute the embedded Python entry script and access user-uploaded files.

Required command pattern:

```bash
python scripts/financial_report_skill/run.py --config <config_path>
```

If the platform only reads `SKILL.md` as a qualitative instruction and does not execute repository code, stop and explain that the current platform can import the skill description but cannot run this executable financial analysis skill. Do not manually simulate calculations.
