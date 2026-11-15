# Triage Labels

技能用五个固定的 triage 角色说话；本文件把角色映射到仓库里实际使用的标签字符串。
本仓库**保留默认命名**，即角色名与标签名相同。

## 五角色

| 角色 | 本仓库标签 | 含义 |
|---|---|---|
| needs-triage | `needs-triage` | 需要维护者评估 |
| needs-info | `needs-info` | 等待报告者补充信息 |
| ready-for-agent | `ready-for-agent` | 已完全规格化，可交给 agent 离线实现 |
| ready-for-human | `ready-for-human` | 需要人来实现 |
| wontfix | `wontfix` | 不做 |

技能里提到某个角色（例如“打上 AFK-ready 标签”），就用上表对应字符串。

## Wayfinder 标签

探索地图（`/wayfinder`）会用到这五个：

| 标签 | 用于 |
|---|---|
| `wayfinder:map` | 探索地图本体 |
| `wayfinder:research` | 研究类决策工单 |
| `wayfinder:prototype` | 原型类决策工单 |
| `wayfinder:grilling` | 访谈类决策工单 |
| `wayfinder:task` | 实施类决策工单 |

## 创建状态

**尚未创建**：本机没有 `gh`，无法调用 GitHub API。安装并登录 `gh` 后执行：

```bash
gh label create needs-triage    --color FBCA04 --description "需要维护者评估"
gh label create needs-info      --color D4C5F9 --description "等待报告者补充信息"
gh label create ready-for-agent --color 0E8A16 --description "已规格化，可交给 agent"
gh label create ready-for-human --color 1D76DB --description "需要人来实现"
gh label create wontfix         --color FFFFFF --description "不做"
gh label create wayfinder:map        --color 5319E7 --description "探索地图"
gh label create wayfinder:research   --color 1D76DB --description "研究类决策工单"
gh label create wayfinder:prototype  --color 0E8A16 --description "原型类决策工单"
gh label create wayfinder:grilling   --color D93F0B --description "访谈类决策工单"
gh label create wayfinder:task       --color C2E0C6 --description "实施类决策工单"
```
