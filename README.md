# spec-atlas

> Bilingual, browsable SFF specs — register maps, tables, revision diffs.

把 SFF 系列规范做成可读、可对照、可版本比较的文档站。

## 当前范围
- 协议：SFF-8472（SFP+ 管理接口）
- 版本：Rev 12.4
- 寄存器块：A0h 字节 0-127（128 个字节全部收录）

## 目录
| 目录 | 作用 |
|---|---|
| `specs/` | 原始资料（PDF / 译文），只读；PDF 与译文不入库 |
| `data-src/` | 手写数据源（唯一手改的地方） |
| `data/` | 由 `tools/build_data.py` 从 `data-src/` 生成的结构化 JSON，不手改 |
| `schema/` | JSON Schema |
| `tools/` | 生成、构建、校验、校验和脚本 |
| `tests/` | 测试与固定数据 |
| `site/` | 站点源码（模板、样式、文案表） |
| `prototype/` | 设计原型归档（只读） |
| `archive/legacy/` | 旧产物 |
| `docs/adr/` | 架构决策记录 |

## 命令
```
py -3 tools/build_data.py             # data-src/ -> data/（规范化、排序、确定性输出）
py -3 tools/build_data.py --check     # 只比较不写；data/ 与 data-src/ 不一致就失败
py -3 tools/validate.py               # schema + 覆盖率 + 校验和规则 + 表引用
py -3 tools/build.py                  # data + site -> dist（先校验，不合法即停止）
py -3 tools/check_checksums.py --dump <file.json>   # 按数据里的规则校验转储校验和
py -3 -m unittest discover -s tests   # 全部测试
```

需要 Python ≥ 3.10（无第三方依赖）。Windows 上用 `py -3`（本机 `python` 是应用商店占位符）；
其他平台把 `py -3` 换成 `python`。
`dist/` 是构建产物，不进版本库：改 `data-src/` 或 `site/` 后重新生成即可。

## 数据怎么来的

`data-src/` 是唯一手写的地方：地址、字节长度、位号、取值这些**事实**按规范正文整理，
说明文字是本项目自写的，不复制译文。`tools/build_data.py` 只做确定性规范化
（键顺序、缩进、LF），把结果写到 `data/`，因此 `data/` 永远可重建，
`--check` 保证两者不会悄悄漂移。

覆盖规则是硬约束：`data/` 里每个地址必须恰好被一条定义覆盖，
保留区也要显式写成 `reserved: true` 的条目——「没有定义」不能当「保留」用，
否则读者分不清是漏了还是确实没含义。

## 当前进度

- 设计原型：[prototype/sff8472-prototype.html](prototype/sff8472-prototype.html)，四套皮肤 B/J/E/M 可切换
- 规格：[issue #1](https://github.com/Cwlrin/spec-atlas/issues/1)（v1 范围 = A0h 全 128 + A2h 0-127）
- 任务：[issue #2](https://github.com/Cwlrin/spec-atlas/issues/2) ~ [#11](https://github.com/Cwlrin/spec-atlas/issues/11)，共 10 张垂直切片票
- #2（走通一个字节）、#3（A0h 全 128 字节与校验和）已完成
- **下一步**：#5（表系统）或 #6（A2h）

## 新会话怎么开工

1. 读 `AGENTS.md`（硬规则与提交规范）、`GLOSSARY.md`（术语）、`docs/agents/*.md`（tracker 与标签）
2. 看一眼 issue #1 的规格与对应票的验收条件
3. `/implement` 带上票号：`/implement #5`；它内部会驱动 `/tdd` 与 `/code-review`
4. 一票做完再开下一票，中间用 `/clear` 换干净窗口

## 环境要点

- **gh 需要代理**：`export HTTPS_PROXY=http://127.0.0.1:7890 HTTP_PROXY=http://127.0.0.1:7890 ALL_PROXY=http://127.0.0.1:7890`
- **git push 走 SSH**，不需要代理
- **PDF 与译文 md 不入库**，只在本地用于抽取；入库的是 `data/` 下的结构化 JSON
- 提交信息遵循约定式提交（钩子已启用，中文标题可用）

## 已实现（#3：A0h 全 128 字节）

- `data-src/sff-8472/rev-12.4/a0.json`：A0h 字节 0-127 的 32 条定义（含多字节字段与保留区），
  三个分组（基本 / 扩展 / 厂商特定 ID 字段），两条校验和规则（CC_BASE、CC_EXT）
- 位域：字节 64、65（选项）、92（诊断监测类型）、93（增强选项）逐位展开，保留位也写出来
- `schema/register-block.schema.json`：新增 `sections`、`checksums`、`bits`、`tableRefs`
- `tools/validate.py`：除 schema 外还查覆盖率（缺口/重叠/越界）、校验和规则自洽、
  位域只出现在单字节字段上、字段引用的表必须在表登记里——每条错误都带地址
- `tools/check_checksums.py`：按数据里声明的规则核对一份转储，失败时说清
  「哪个字节、应为多少、实际多少」
- `tools/build.py`：128 个地址各一页；字段页给出所属分组、字段地址范围、字段内序号、
  位定义、校验和说明；索引页按字段列一行（多字节字段给地址范围、只链首地址）
- 表格清单页 `dist/sff-8472/12.4/tables.html`：45 张表全部列出，未收录的标「待补」且**不给链接**
- `data-src/sff-8472/rev-12.4/tables.json`：表登记（表号、章节、标题、收录状态）
- 测试：`tests/test_a0_block.py`（覆盖率、校验和、表登记、死链）与既有产物测试

## 尚未实现

- #5：表系统（表页、悬停解释、表清单链接、4-1/4-2 由寄存器数据生成）
- #6：A2h 字节 0-127 与位域
- 其余（搜索、皮肤、版本对比）：见 issue #1 的票列表
- 校验和的真实转储验证：`tests/fixtures/dumps/` 目前只有**合成**转储（生成规则写在文件里），
  真实模块转储的换算验证归 #7
