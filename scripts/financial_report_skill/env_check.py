from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from .errors import SkillEnvironmentError

REQUIRED_PACKAGES = {
    "pandas": "pandas",
    "numpy": "numpy",
    "openpyxl": "openpyxl",
}


def check_python_version(min_version=(3, 10)) -> None:
    if sys.version_info < min_version:
        raise SkillEnvironmentError(
            f"当前 Python 版本为 {sys.version.split()[0]}，本 skill 至少需要 Python {min_version[0]}.{min_version[1]}。"
        )


def find_missing_packages() -> list[str]:
    missing = []
    for import_name, package_name in REQUIRED_PACKAGES.items():
        if importlib.util.find_spec(import_name) is None:
            missing.append(package_name)
    return missing


def assert_environment_supported(output_dir: str | Path) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    check_python_version()
    missing = find_missing_packages()
    if missing:
        raise SkillEnvironmentError(
            "当前 AI LLM 运行环境缺少必要 Python packages："
            + "、".join(missing)
            + "。本 skill 需要 pandas、numpy、openpyxl 才能读取和输出 Excel。"
        )
