# 术语表

状态：`定稿` = 已核对行业用法并采纳，后续 JSON key 与 UI 文案沿用；改词需走 ADR。

| 中文 | English | 依据 | 备注 |
|---|---|---|---|
| 寄存器 / 寄存器映射 | register / register map | CodingBox「寄存器映射」；新华三 E010 系列文档「寄存器」 | 单字节称寄存器，整块称寄存器映射 |
| 字节 | byte | 通用 | 表格列头统一「字节」 |
| 位 | bit | 原文 Bit；中文表格惯例 | 表格内写「位」，正文解释写「比特位」 |
| 位域 | bit field | CodingBox「位域」；部分厂商写「位字段」 | 采用「位域」，首次出现注 bit field |
| 标志位 | flags | 原文 A/W flags；CodingBox、新华三均用「标志位」 | 简称「标志」；承载它的字节称「标志位字节」 |
| 阈值 | threshold | 华为「告警阈值」；CodingBox「阈值」；Fibertrixa 用「门限」 | 采用「阈值」，文末标注别名「门限」 |
| 告警 | alarm | 新华三：告警分 warning / alarm 两级；Fibertrixa「告警与警告门限」 | 需立即处理 |
| 警告 | warning | 同上；华为 Trap 描述为 exceed warning threshold | 超出保证范围但未必立即失效 |
| 校准 | calibration | 通用 | |
| 内部校准 | internal calibration | CodingBox / 译文一致 | 读绝对量 |
| 外部校准 | external calibration | CodingBox / 译文一致 | 读 A/D 计数，主机换算 |
| 页 | page | 通用；页选择字节 | |
| 地址切换 | address change | CodingBox「地址切换」 | 访问 A2h 前的序列 |
| 数字诊断 | digital diagnostics | 华为「数字诊断参数」；DDM = 数字诊断监控，DOM = 数字光监控 | 首次出现注 DDM/DOM |

## 措辞约定
- 「告警」与「警告」不混用；统称写「告警/警告阈值」。
- 原文 A/W 缩写，中文展开为「告警/警告」。
- 「阈值」不写成「门限」，除非引用厂商原话。

## 来源
- CodingBox《SFF-8472——SFP 诊断》《阈值、告警与标志位》, codingbox.info
- 新华三 光模块诊断相关告警文档, h3c.com
- 华为 S5700 配置指南「配置光功率告警阈值」, support.huawei.com
- Fibertrixa《什么是 DOM 与 DDM》, fibertrixa.com
