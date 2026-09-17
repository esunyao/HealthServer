# HealthMind 兼容结果说明

以下依据本项目沟通中的既有契约整理，不替代当前 release 的真实 `output_schema`。本次技能编写没有查询生产数据库。

```json
{
  "overall_confidence": 0.8,
  "items": [
    {
      "name": "合成测试熟食",
      "weight_grams": 150,
      "confidence": 0.8,
      "nutrients": [
        {"code": "DIETARY_FIBER", "value": 6}
      ]
    }
  ]
}
```

合成示例仅展示字段和 4 g/100 g × 150 g = 6 g 换算，不是实际食物结论。

既有约定：items 为 1–100 项；name 非空且不超过 150 字符；weight_grams 为正数；confidence 和 overall_confidence 在 0–1；每项至少一个有依据的 nutrient，value 非负；禁止额外字段时不要塞入引用或解释。

| code | 单位 |
|---|---|
| ENERGY_KCAL | kcal |
| PROTEIN、FAT、CARBOHYDRATE、SUGAR、DIETARY_FIBER | g |
| SODIUM、CALCIUM、IRON、POTASSIUM、VITAMIN_C | mg |

code 与单位仍须对照实际部署。未测的纤维应省略对应项，而非报告 0；若本次目标必须有纤维且没有证据，改为复核分支。

机器业务结果与用户纤维报告分开输出。全天指南比较、引用、估计范围不应通过擅自添加字段破坏契约。
