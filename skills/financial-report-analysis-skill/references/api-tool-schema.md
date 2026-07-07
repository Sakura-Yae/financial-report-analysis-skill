# 外部 API / Tool Calling 接入参考

如果目标 LLM 平台不能直接执行本仓库中的 Python 代码，可以将本 skill 部署为后端服务，再通过 Function Calling、Tool Calling 或自建插件调用。

## 建议接口

`POST /run-financial-report-analysis`

请求体：

```json
{
  "input_file_url": "https://example.com/uploaded.xlsx",
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
  "alias_map_cf": {}
}
```

响应体：

```json
{
  "status": "success",
  "company_name": "auto",
  "detected_report_type": "wind_or_standard",
  "manifest_url": "https://example.com/output/manifest.json",
  "outputs": [
    {
      "name": "财务指标表",
      "type": "xlsx",
      "url": "https://example.com/output/财务指标.xlsx"
    }
  ],
  "warnings_count": 0
}
```

失败响应：

```json
{
  "status": "failed",
  "error_code": "E_RUNTIME_ERROR",
  "error_message": "错误说明",
  "error_file_url": "https://example.com/output/报错说明.txt"
}
```

## OpenAPI 片段

```yaml
openapi: 3.0.0
info:
  title: Financial Report Analysis Skill
  version: 1.0.0
paths:
  /run-financial-report-analysis:
    post:
      operationId: runFinancialReportAnalysis
      summary: Run financial report analysis for an uploaded Excel workbook.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [input_file_url]
              properties:
                input_file_url:
                  type: string
                company_name:
                  type: string
                  default: auto
                is_wind_report:
                  type: string
                  enum: [auto, true, false]
                  default: auto
                input_unit_is_wanyuan:
                  type: boolean
                  default: true
                max_periods:
                  type: integer
                  default: 4
                major_ratio_threshold:
                  type: number
                  default: 10.0
                major_yoy_threshold:
                  type: number
                  default: 30.0
                simplified_ratio_threshold:
                  type: number
                  default: 0.05
                forced_accounts_mode:
                  type: string
                  enum: [append_default, replace, none]
                  default: append_default
                forced_accounts:
                  type: array
                  items:
                    type: string
                alias_map_bs:
                  type: object
                  additionalProperties:
                    type: string
                alias_map_pl:
                  type: object
                  additionalProperties:
                    type: string
                alias_map_cf:
                  type: object
                  additionalProperties:
                    type: string
      responses:
        "200":
          description: Analysis result.
```
