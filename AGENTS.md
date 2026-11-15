# AGENTS.md

给在本仓库工作的 agent 的约定。

## 硬规则
1. `specs/` 只读。修订 = 新目录 + 新 manifest，不在原文件上改。
2. `data/` 必须可由 `tools/build_data.py` 重建；手改字段加 `handEdited: true`。
3. 双语放同一对象：`{"zh": "...", "en": "..."}`。长章节按 `chapter-XX.zh.md` / `.en.md` 成对，共用 anchor。
4. 一张表一个文件：`tables/table-5-1.json`。
5. 版本差异是算出来的（diff_revisions），不要手写进 data。
6. PDF 不入库；新增资料先更新 manifest 的 sha256。
7. 多协议按 `发布者-编号` 命名，如 `sff-8472`、`ieee-802-3`。

## 内容边界
- 事实（地址、位、取值）可公开；译文正文与表格说明属受版权保护的表达，公开前另行评估。
- 站点必须包含中英文免责声明（非官方、版权归 SNIA、译文仅供参考）。
