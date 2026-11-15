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

## 命令
```
py -3 tools/build.py                  # data + site -> dist（先校验，不合法即停止）
py -3 tools/validate.py               # schema 校验（校验和与覆盖率由后续票补）
py -3 -m unittest discover -s tests   # 产物测试
```

需要 Python ≥ 3.10（无第三方依赖）。Windows 上用 `py -3`（本机 `python` 是应用商店占位符）；
其他平台把 `py -3` 换成 `python`。
`dist/` 是构建产物，不进版本库：改 `data/` 或 `site/` 后重新构建即可。

`tools/build_data.py`（specs -> data）**尚未实现，归 #3**。在它落地之前 `data/` 是手写切片，
每条手写数据都在 JSON 里标 `handEdited` 与 `handEditNote`，内容取自 `specs/` 下的译文（PDF 与译文不入库）。

## 当前进度

- 设计原型：[prototype/sff8472-prototype.html](prototype/sff8472-prototype.html)，四套皮肤 B/J/E/M 可切换
- 规格：[issue #1](https://github.com/Cwlrin/spec-atlas/issues/1)（v1 范围 = A0h 全 128 + A2h 0-127）
- 任务：[issue #2](https://github.com/Cwlrin/spec-atlas/issues/2) ~ [#11](https://github.com/Cwlrin/spec-atlas/issues/11)，共 10 张垂直切片票
- #2（走通一个字节）已完成：数据 -> 校验 -> 站点 -> 测试的最小闭环
- #3（A0h 全 128 字节与校验和）进行中
- #4（概览页、全站免责声明、首次访问提示条）已完成
- **下一步**：等 #3 收口后开 #5

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

## 已实现（#2 最小切片）

- `data/sff-8472/rev-12.4/a0.json`：只收录字节 0，手写并标 `handEdited`（存储目录用 `rev-12.4`，站点 URL 用 `12.4`）
- `schema/register-block.schema.json` + `tools/validate.py`：无第三方依赖的最小 schema 校验，另校验 `spec`/`revision`/`block` 与所在目录一致
- `tools/build.py` + `site/templates/`：产物为 `dist/sff-8472/12.4/a0/0.html` 与索引页（未收录字节标「待补」）
- `tests/test_build.py`：产物测试（页面内容来自 JSON、构建可重复、坏数据中止构建、HTML 转义、footer 免责声明）
- footer 已带中英文免责声明（非官方 / 版权归 SNIA / 译文仅供参考）

**双语（#9 已完成）**：每条界面文案与字段名都渲染成中英两版并存的一个节点，
根元素 `<html data-lang="zh|en">` 配 CSS 决定显示哪一版；`site/lang.js` 负责默认中文、
记住选择（`localStorage["spec-atlas.lang"]`）、切换时只改属性不跳转。切换后仍停在当前字段页。

**概览与免责声明（#4 已完成）**：站点根 `dist/index.html` 是入口页，三张卡分别讲清
一条两线总线、A0h/A2h 两个地址、内部/外部两种校准，块清单从 `data/` 生成；块页面的
面包屑能点回首页。全站 footer 带中英双语免责声明（非官方 / 版权归 SNIA / 译文仅供参考），
`tests/` 里遍历 `dist/**/*.html` 断言，新增页面自动纳入。首次访问提示条随 HTML 下发、
默认 `hidden`，由 `site/notice.js` 揭开；关掉后记 `localStorage["spec-atlas.notice"]`，
回访不再出现；禁写 localStorage 时当次仍能关，连读都抛（禁 cookie/沙箱）时首次访问照样看得到。

**暂定**：皮肤归 #10，仍是临时形态。

## 尚未实现

- #3：A0h 其余 127 个字节、CC_BASE 校验和、覆盖率检查，以及从译文抽取的 `tools/build_data.py`
- 其余（位域、表引用、搜索、皮肤）：见 issue #1 的票列表