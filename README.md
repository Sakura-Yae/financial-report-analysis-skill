# Financial Report Analysis Skill

This repository is a GitHub-ready AI agent skill for processing Chinese financial statement Excel workbooks. It supports:

- Wind standard exported financial statements
- Manually standardized three-statement Excel workbooks
- Balance-sheet structure ratio analysis
- YoY analysis tables
- Major account text generation
- Simplified major account text generation
- Financial indicator calculation
- Warning logs, parameter notes, error reports, and `manifest.json`

The skill is intentionally designed as an embedded Python package. The LLM should call the package entrypoint and must not manually simulate calculations.

## Repository layout

```text
financial-report-analysis-skill/
├─ SKILL.md
├─ README.md
├─ requirements.txt
├─ example_config.json
├─ scripts/
│  └─ financial_report_skill/
│     ├─ run.py
│     ├─ env_check.py
│     ├─ pipeline.py
│     ├─ wind_cleaner.py
│     ├─ validators.py
│     ├─ structure_yoy.py
│     ├─ major_accounts.py
│     ├─ indicators.py
│     └─ text_outputs.py
└─ docs/
   ├─ GITHUB_MINIMAX_IMPORT.md
   └─ API_TOOL_SCHEMA.md
```

## Runtime requirements

- Python 3.10+
- pandas
- numpy
- openpyxl
- File read/write access

The entry script checks these dependencies before running the analysis. If a dependency is missing, it writes a failed `manifest.json` and an error text file. It does not automatically run `pip install`.

## Run locally or in an agent runtime

1. Copy `example_config.json` and edit `input_path` / `output_dir`.
2. Run:

```bash
python scripts/financial_report_skill/run.py --config example_config.json
```

On success, inspect `manifest.json` in the configured output directory.

## Use with MiniMax GitHub skill import

This repository is structured so that `SKILL.md` is in the repository root. If MiniMax imports skills from GitHub, provide the repository URL.

Import success does not guarantee execution success. The MiniMax runtime still needs Python execution, file access, and required packages. See:

- `docs/GITHUB_MINIMAX_IMPORT.md`

## Use with GLM / MiniMax Tool Calling / other LLMs

If the target platform cannot execute repository Python code directly, deploy this skill as an external API service and call it with Function Calling / Tool Calling / HTTP Tool. See:

- `docs/API_TOOL_SCHEMA.md`

## Security notes

Do not commit real issuer financial statements, client data, output files, or logs to GitHub. The included `.gitignore` excludes common Excel and output files by default.
