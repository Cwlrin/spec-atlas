# Issue tracker: GitHub

本仓库的 issue 与 spec 都放在 GitHub Issues，仓库为 `Cwlrin/spec-atlas`。
所有读写通过 `gh` CLI（前置：安装 GitHub CLI 并 `gh auth login`，见文末“前置检查”）。

## 约定

- **建票**：`gh issue create --title "..." --body "..."`，多行正文用 heredoc。
- **读票**：`gh issue view <number> --json number,title,body,labels,comments`。
- **列票**：`gh issue list --state open --label <label> --json number,title,body,labels`。
- **子票**：`gh issue create --parent <parent> ...`，或事后 `gh issue edit <parent> --add-sub-issue <child>`（gh ≥ 2.94）。
  老版本用 `gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<child-db-id>`。
  若版本不支持子票，退化为在子票正文顶部写 `Part of #<parent>`。
- **阻塞边**：优先用 GitHub 原生 issue 依赖：
  `gh issue create --blocked-by <n>,<n> ...` 或 `gh issue edit <child> --add-blocked-by <blocker>`（gh ≥ 2.94）。
  老版本：`gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`，
  其中 `<blocker-db-id>` 是阻塞方的数据库 id（`gh api repos/<owner>/<repo>/issues/<n> --jq .id`）。
  两者都不可用时，在子票正文写 `Blocked by: #<n>`，并在父票正文维护顺序说明。

## spec 与 ticket 的落点

- `/to-spec` → 一个 **spec issue**（容器票），正文是规格；`Part of` 无。
- `/to-tickets` → 若干 **child issues**，挂到 spec 票下；每张声明阻塞边。
- `/implement` → 读 issue 正文与评论；完成后 PR 里写 `Fixes #<n>`。

## PR 作为需求入口

关闭（默认）。triae 队列只处理 issue；需要把外部 PR 纳入 triage 时再改本节。

## 网络

本机直连 GitHub API 不通，`gh` 调用需带代理（2026-11-15 实测）：

```bash
export HTTPS_PROXY=http://127.0.0.1:7890 HTTP_PROXY=http://127.0.0.1:7890 ALL_PROXY=http://127.0.0.1:7890
```

`git push` 走 SSH，不需要代理。

## 前置检查

在本目录执行 `gh repo view --json nameWithOwner` 应打印 `Cwlrin/spec-atlas`。
若失败：`winget install GitHub.cli`（或 `scoop install gh`），再 `gh auth login`。
