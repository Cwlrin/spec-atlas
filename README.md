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

## 当前进度

- 设计原型：[prototype/sff8472-prototype.html](prototype/sff8472-prototype.html)，四套皮肤 B/J/E/M 可切换
- 规格：[issue #1](https://github.com/Cwlrin/spec-atlas/issues/1)（v1 范围 = A0h 全 128 + A2h 0-127）
- 任务：[issue #2](https://github.com/Cwlrin/spec-atlas/issues/2) ~ [#11](https://github.com/Cwlrin/spec-atlas/issues/11)，共 10 张垂直切片票
- **下一步**：从 #2（走通一个字节）开始，它是唯一没有前置的票

## 新会话怎么开工

1. 读 `AGENTS.md`（硬规则与提交规范）、`GLOSSARY.md`（术语）、`docs/agents/*.md`（tracker 与标签）
2. 看一眼 issue #1 的规格与 #2 的验收条件
3. `/implement` 带上票号：`/implement #2`；它内部会驱动 `/tdd` 与 `/code-review`
4. 一票做完再开下一票，中间用 `/clear` 换干净窗口

## 环境要点

- **gh 需要代理**：`export HTTPS_PROXY=http://127.0.0.1:7890 HTTP_PROXY=http://127.0.0.1:7890 ALL_PROXY=http://127.0.0.1:7890`
- **git push 走 SSH**，不需要代理
- **PDF 与译文 md 不入库**，只在本地用于抽取；入库的是 `data/` 下的结构化 JSON
- 提交信息遵循约定式提交（钩子已启用，中文标题可用）

## 尚未实现

`tools/build.py`、`tools/validate.py`、`schema/`、`data/`、`site/` 目前都是空骨架，由 #2 起逐步填充。
