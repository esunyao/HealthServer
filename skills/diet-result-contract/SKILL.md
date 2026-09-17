---
name: diet-result-contract
description: 将有证据的餐食营养分析转换为 Dify 与 HealthMind 可校验的结构化结果。遇到 result、structured_output、营养素 code、Schema 校验、单份与每百克换算或结果落库格式时使用；不虚构缺失值，也不生成 Kafka 事件或业务 ID。
---

# 膳食结果契约校验

## 操作顺序

1. 取得调用方当前 release 的 `output_schema` 与营养素字典。没有时读取 [兼容说明](references/contract.md)，仅生成候选示例并标明尚未验证当前部署，不宣称可直接入库。
2. 检查分析是否 ready：食物、实际可食重量和每项营养值有依据；缺图、未知重量或关键冲突应走独立 `needs_review` 分支。不要为了通过 Schema 填 0、极小正数、空数组或自造重量。
3. 将营养值换成该份实际摄入量并统一单位；校验有限数值、非负值、置信度范围及 code 白名单。同一食物同一 code 不得重复，遇重复先核对是否重复计数，不直接相加。
4. 输出严格 JSON，不带 Markdown、注释或额外解释。来源、范围和安全提示存入独立报告，不藏在 name 字段中。保留不确定性的单值估计只有在有可解释估算依据且业务允许时才可使用。
5. 由调用方进行真正的 JSON Schema 校验及语义计算校验。Dify 成功分支让输出变量 `result` 指向对象，不是 JSON 字符串；模型对象内不要再额外套一层 result，除非真实 Schema 明确要求。

## 不做的事

不创建 task、attempt、meal ID；不发 Kafka、不写数据库、不重试任务。业务包装和任务关联由后端处理。大整数 ID 不经过浮点转换。结构合法只意味着格式通过，不等于内容真实或适用于当前患者。
