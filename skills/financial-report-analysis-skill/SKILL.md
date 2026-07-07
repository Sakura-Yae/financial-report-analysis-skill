---
name: financial-report-analysis-skill
description: "Analyze Chinese financial statement Excel workbooks using embedded Python code. Supports Wind standard exports and manually standardized three-statement workbooks; generates standardized statements, balance-sheet structure ratios, YoY tables, major account text, simplified major account text, financial indicators, warning logs, parameter notes, and a manifest."
license: MIT
metadata:
  version: "1.0.0"
  category: finance
  sources:
    - Wind standard exported financial statements
    - Manually standardized financial statements
---

# Financial Report Analysis Skill

## Purpose

Use this skill when the user uploads a Chinese financial statement Excel workbook and asks for financial statement analysis, Wind report cleaning, balance-sheet structure ratios, YoY analysis, major account text, simplified major account text, or financial indicator calculation.

The skill is executable. The LLM must call the embedded Python package and must not manually calculate financial ratios, infer account substitutions, rewrite formulas, or invent output files.

## Runtime requirements

This skill requires an agent runtime that can:

- execute Python 3.10+;
- read and write files;
- access the user-uploaded `.xlsx` workbook;
- use the required Python packages: `pandas`, `numpy`, and `openpyxl`.

If Python execution is unavailable, stop and tell the user that the current MiniMax / LLM environment can import the skill description but cannot run this executable financial analysis skill.

If Python exists but required packages are missing, run the entry script. The script performs environment checks and writes a failed `manifest.json` and an error text file. Do not attempt `pip install` and do not manually simulate the result.

## Inputs

The user must provide one `.xlsx` workbook. The workbook may be either:

1. A Wind standard export workbook; or
2. A manually standardized workbook with three recognizable sheets:
   - `资产负债表`
   - `利润表`
   - `现金流量表`

For manually standardized workbooks, the first column must be `科目`, later columns must be report dates, and the balance sheet must contain section markers sufficient to locate assets, liabilities, and owners' equity, such as `流动资产：`, `流动负债：`, and `所有者权益：` or `股东权益：`.

## Parameters

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
- `forced_accounts_mode` accepts `append_default`, `replace`, or `none`.
- `alias_map_bs`, `alias_map_pl`, and `alias_map_cf` map candidate account names to actual account names for matching; they do not rewrite source Excel files.

## Procedure

When running this skill:

1. Locate the uploaded `.xlsx` file.
2. Create a config JSON file using the user's parameters and defaults.
3. Run the embedded entry script from this skill directory:

```bash
python scripts/financial_report_skill/run.py --config /path/to/config.json
```

4. Do not call user-local code or external scripts.
5. Do not modify the embedded Python code during a normal run.
6. Read `manifest.json` from the configured output directory.
7. Reply with status, key parameters, output files, and error files if any.

## Validation behavior

The embedded code validates:

- `.xlsx` existence and format;
- Wind export vs manually standardized workbook detection;
- three core financial statements;
- date columns;
- balance-sheet section markers;
- core denominator and anchor accounts;
- Wind metadata and tail rows;
- generated-column contamination such as `_金额`, `_占比`, `_同比` in the input.

If validation fails, stop and return the generated error manifest/text. Do not continue with partial calculations unless the embedded code has created a success manifest.

## Outputs

On success, the output directory contains:

- standardized financial statement workbook;
- balance-sheet structure workbook;
- YoY analysis workbook;
- structure + YoY summary workbook;
- major account text;
- simplified major account text;
- major account list workbook;
- financial indicator workbook;
- financial indicator warning text;
- runtime parameter notes;
- Wind cleaning log when applicable;
- `manifest.json`.

On failure, the output directory contains:

- `manifest.json`;
- `07_提示与日志/报错说明.txt`.

## LLM constraints

The LLM must obey these constraints:

- Do not manually compute financial indicators.
- Do not manually infer substitute accounts.
- Do not silently treat missing values as zero.
- Do not treat a Wind export as a standardized workbook unless the code does so.
- Do not skip validation.
- Do not invent output files that do not appear in the manifest.
- Do not claim success unless `manifest.json` has `"status": "success"`.
- If `manifest.json` has `"status": "failed"`, explain the error and link the error text file.
