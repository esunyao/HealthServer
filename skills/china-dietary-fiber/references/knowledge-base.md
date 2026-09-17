# Dify 知识库资料规范

核查日期：2026-09-17。来源目录：`E:/ProjectSpace/AI食物健康分析系统/中国膳食纤维分析资料`。

## 本地资料实际情况

| 文件 | 当前已核查内容 | 使用边界 |
|---|---|---|
| 中国食物成分表-详细版.xls | `食物成份表` 1286 行、20 列；含名称、可食部分、膳食纤维等；另有 `新食物成份表` 和标准体重表 | 可准备食物检索库；出版版次、计量基准、纤维测定定义还需核实 |
| 中国居民膳食营养素参考摄入量(表).xls | 56 行、34 列；所读表头没有膳食纤维字段 | 不用它生成膳食纤维目标；未确认各字段单位、版次前不作为直接推荐来源 |
| 其余 PDF、DOCX、PPT | 文件名包括系统方案、日本菜谱、素食菜谱和开发提案；本次未做全文权威性校验 | 不因存放在此目录就当成中国官方指南 |

第一张表原始数字有 `9.899999618530273` 一类浮点尾数。第二个食物工作表在空值与 0 表示上存在差异，应选定并核验主版本，不直接混合去重。0 可能是测量零、未测或转录默认值，确认定义之前不要自动判为“无该营养素”。

尚未找到明确命名且已核实的“中国膳食纤维指南”原文。请补充确切书名、发布机构、年份及相关章节；不要把本文件当作指南替代品。

## 入库方法

将指南与食物成分分为两个集合，隔离来源和检索意图。

指南片段应保留：`source_id / title / issuer / edition_year / population / section / page / nutrient_definition / evidence_text / verified`。切片不要切断数值、人群、脚注、单位。OCR 后人工核对小数点、范围、年龄和表格对齐。缺失的定位写 unknown。

食物数据按“一种食物一条完整记录”整理；用字段名重复描述，避免 XLS 表头与数值被分到不同片段。字段：`food_id / food_name / aliases / raw_or_cooked / edible_basis / basis_weight_g / nutrient_code / value / unit / missing_reason / source_id / sheet / row / edition / verified`。基准未核实不能默认填 100。

示意（不是可直接投产的食物数据）：

```text
food_id: DEMO-001
food_name: 合成测试熟食
raw_or_cooked: cooked
edible_basis: edible_portion
basis_weight_g: 100
nutrient_code: DIETARY_FIBER
value: 4
unit: g
source_id: synthetic-test-only
verified: false
```

别把示意记录导入生产知识库。查询结果应带来源元数据；检索分数只表示相关性，不是营养证据的可信度。无结果时扩展同义词，仍无结果就保留未知。

## 可核对的官方入口

- [国家卫健委：关于膳食纤维相关建议的答复](https://www.nhc.gov.cn/wjw/jiany/202301/bd6c614391274ebd955fc9018f2032a2.shtml)：2023 年发布的答复引用 DRI 2013 的成人 19–50 岁纤维 AI 25–30 g/日。注意，这是带特定版次与人群的历史引用，不能改写为“所有人最新标准”。
- [中国营养学会：中国居民膳食指南 2022 工具包](https://www.cnsoc.org/activitykit2/6522002010.html)：核对食物组建议及其适用范围。

要采用更新版本时，先获取其可核对正文，保留旧版以便追踪；不能用网页发布日期替代指南版次，也不能用系统开发提案替代指南证据。
