# AGENTS.md

给在本仓库工作的 agent 的约定。

## 硬规则
1. `specs/` 只读。修订 = 新目录 + 新 manifest，不在原文件上改。
2. `data/` 必须可由 `tools/build_data.py` 重建；手改字段加 `handEdited: true`。
3. 双语放同一对象：`{"zh": "...", "en": "..."}`。长章节按 `chapter-XX.zh.md` / `.en.md` 成对，共用 anchor。
4. 一张表一个文件：`tables/table-5-1.json`。
5. 版本差异是算出来的（diff_revisions），不要手写进 data。
6. **PDF 与译文 markdown 都不入库**（版权：禁止向第三方分发）；新增资料先更新 manifest 的 sha256。入库的是 `data/` 下的结构化 JSON。
7. 多协议按 `发布者-编号` 命名，如 `sff-8472`、`ieee-802-3`。

## 内容边界
- 事实（地址、位、取值）可公开；译文正文与表格说明属受版权保护的表达，公开前另行评估。
- 站点必须包含中英文免责声明（非官方、版权归 SNIA、译文仅供参考）。

## 提交规范（Conventional Commits）
启用方式：`git config core.hooksPath .githooks`（已配置），提交模板 `.gitmessage`。

格式：`<type>(<scope>): <subject>`

| type | 用于 |
|---|---|
| feat | 新增能力（页面、组件、数据切片） |
| fix | 修正错误 |
| docs | 文档、注释、README |
| refactor | 不改变行为的重构 |
| perf | 性能 |
| test | 测试与固定数据 |
| build / ci | 构建、流水线 |
| chore | 仓库杂务（配置、依赖、迁移） |
| revert | 回滚 |

scope 取目录名：`specs` `data` `schema` `tools` `site` `docs` `repo`。

规则：
- subject 用祈使句、不加句号；**中文可用**（≤ 40 字），英文小写开头（≤ 72 字符）
- 破坏性变更写 `type(scope)!: ...`，正文加 `BREAKING CHANGE:`
- 正文解释「为什么」，不复述「改了什么」
- 示例：`feat(data): 补齐 A0h 寄存器映射`、`fix(site): 表格浮层在窄屏溢出`
