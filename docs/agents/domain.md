# Domain Docs

工程类技能在探索代码库时，如何消费本仓库的领域文档。

## 布局：single-context

本仓库是 **single-context**：一个仓库共用**一份根目录的 `GLOSSARY.md`**，架构与取舍决定放 `docs/adr/`。
不设 `GLOSSARY-MAP.md`，也不为子目录另建 `GLOSSARY.md`——除非将来真的拆出第二个上下文。

## 探索前先读

- **`GLOSSARY.md`**（仓库根）：术语与措辞约定。
- **`docs/adr/`**：读与当前工作区域相关的 ADR。

这些文件不存在时**静默继续**，不要提示“建议先创建”。`/domain-modeling` 会在第一个词条或决定真正落定时才创建文件。

## 用词规则

- 输出的概念名（issue 标题、spec 段、提交信息、UI 文案）沿用 `GLOSSARY.md` 的词。
- 告警（alarm）与警告（warning）不得混用；阈值写作“阈值”，不写“门限”（引用厂商原话除外）。
- 发现新概念：先补 `GLOSSARY.md`，再写实现；改已定稿的词要写 ADR。

## 与其他文档的关系

| 文件 | 作用 |
|---|---|
| `GLOSSARY.md` | 术语与措辞（唯一来源） |
| `DECISIONS.md` | 本轮已拍板的产品/技术决策清单 |
| `docs/adr/` | 难以回退的决定，一条一个文件 |
| `SPEC.md` | 站点规格（待 `/to-spec` 填充） |
