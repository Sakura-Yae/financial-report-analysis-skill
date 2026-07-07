# Tested

This repository package was smoke-tested in the current runtime after GitHub-readiness updates.

## Environment

- Python code execution: available
- Required packages: pandas, numpy, openpyxl available

## Test inputs used locally only

The test Excel files were not included in the repository package because real or sample issuer workbooks should not be committed to a public skill repository.

- Standard manually prepared workbook: `【标准人工】温州水务.xlsx`
- Wind exported workbook: `【Wind导出】温州现代.xlsx`

## Result

Both test runs completed successfully and generated success `manifest.json` files.

| Case | Detected report type | Status | Output entries |
|---|---:|---:|---:|
| Standard manual workbook | standard | success | 11 |
| Wind export workbook | wind | success | 11 |

## Command pattern

```bash
python scripts/financial_report_skill/run.py --config <config_path>
```
