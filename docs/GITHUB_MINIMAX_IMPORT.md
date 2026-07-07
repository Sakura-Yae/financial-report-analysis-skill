# GitHub / MiniMax 导入说明

本仓库设计为一个可导入的 AI agent skill。仓库根目录必须直接包含 `SKILL.md`。

## 一、上传到 GitHub

1. 新建 GitHub 仓库，建议名称：`financial-report-analysis-skill`。
2. 将本目录下的全部文件作为仓库根目录提交。
3. 不要上传真实客户财务报表、测试输出目录或任何包含敏感信息的文件。
4. 如需要让其他用户导入，仓库应设为 Public；如设为 Private，需要确保 MiniMax 或目标 agent runtime 具备访问权限。

推荐命令：

```bash
git init
git add .
git commit -m "Initial financial report analysis skill"
git branch -M main
git remote add origin https://github.com/<your-account>/financial-report-analysis-skill.git
git push -u origin main
```

## 二、MiniMax 导入后的判断标准

导入成功只代表 MiniMax 读取到了 `SKILL.md` 和仓库文件；真正可执行还需要 MiniMax 的运行环境支持：

- Python 3.10+
- 文件读写
- 用户上传 `.xlsx` 文件访问
- `pandas`
- `numpy`
- `openpyxl`

如果运行环境不支持上述条件，skill 必须终止，不能由 LLM 手工模拟财务计算。

## 三、导入后验证步骤

### 1. 验证 skill 是否被加载

向 MiniMax 输入：

```text
请说明你是否已加载 financial-report-analysis-skill，以及该 skill 的运行入口是什么。
```

理想回答应包含：

```bash
python scripts/financial_report_skill/run.py --config <config_path>
```

### 2. 验证环境是否支持运行

向 MiniMax 输入：

```text
请运行该 skill 的环境检查，不处理任何 Excel 文件。
```

如果环境不支持 Python 或缺少 packages，应返回环境不支持说明。

### 3. 用脱敏 Excel 测试

上传脱敏后的标准人工表或 Wind 导出表，并要求运行 skill。成功时应生成：

- `manifest.json`
- `01_标准化输入/`
- `02_占比表/`
- `03_同比表/`
- `04_汇总表/`
- `05_文本分析/`
- `06_财务指标/`
- `07_提示与日志/`

## 四、如果 MiniMax 只能读取说明，不能执行代码

如果导入后 MiniMax 只会阅读 `SKILL.md`，但无法执行仓库内 Python 代码，则该平台当前只能使用“说明型 skill”，不能真正运行本财务分析工具。

此时应改用以下任一路径：

1. 在支持 Python 执行的 agent runtime 中运行本仓库；或
2. 将本仓库打包为后端 API 服务，再由 MiniMax 通过 Tool Calling / HTTP Tool 调用。
