from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

# Allow this script to be executed directly from the embedded skill folder.
CURRENT = Path(__file__).resolve()
SCRIPTS_DIR = CURRENT.parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from financial_report_skill.config import load_config
from financial_report_skill.env_check import assert_environment_supported
from financial_report_skill.pipeline import run_pipeline, write_error_manifest


def main() -> int:
    warnings.filterwarnings("ignore", category=FutureWarning)
    parser = argparse.ArgumentParser(description="Run financial report analysis skill.")
    parser.add_argument("--config", required=True, help="Path to JSON config file.")
    args = parser.parse_args()

    config = None
    output_dir = Path("financial_report_output")
    try:
        config_path = Path(args.config)
        # Parse output_dir with standard library first, so env errors can be written into the requested folder.
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            output_dir = Path(raw.get("output_dir") or output_dir)
        except Exception:
            pass
        assert_environment_supported(output_dir)
        config = load_config(config_path)
        manifest = run_pipeline(config)
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        manifest = write_error_manifest(output_dir, e, config)
        print(json.dumps(manifest, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
