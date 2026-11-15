# spec-atlas

> Bilingual, browsable SFF specs — register maps, tables, revision diffs.

把 SFF 系列规范做成可读、可对照、可版本比较的文档站。

## 当前范围
- 协议：SFF-8472（SFP+ 管理接口）
- 版本：Rev 12.4

## 目录
| 目录 | 作用 |
|---|---|
| `specs/` | 原始资料（PDF / 译文），只读；PDF 不入库 |
| `data/` | 从 specs 生成的结构化 JSON，可重建 |
| `schema/` | JSON Schema |
| `tools/` | 抽取、构建、校验、版本对比脚本 |
| `tests/` | 测试与固定数据 |
| `site/` | 站点源码（布局、组件、主题） |
| `prototype/` | 设计原型归档（只读） |
| `archive/legacy/` | 旧产物 |
| `docs/adr/` | 架构决策记录 |

## 命令（待实现）
```
python tools/build_data.py      # specs -> data
python tools/validate.py        # schema + 校验和 + 覆盖率
python tools/diff_revisions.py  # 两版差异 -> dist/diff
```
