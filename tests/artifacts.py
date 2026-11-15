"""测试共用的接缝与产物小工具。

两个测试模块都要跑构建、解析产物里的标签与双语节点，这些不重复写：
改一处就该处处生效，否则两份副本迟早说法不一致。
"""

import html.parser
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def run(args):
    return subprocess.run(
        [sys.executable] + args,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def build(*extra):
    result = run(["tools/build.py"] + list(extra))
    if result.returncode != 0:
        raise AssertionError(
            "build failed (%s)\nstdout:\n%s\nstderr:\n%s"
            % (result.returncode, result.stdout, result.stderr)
        )
    return result


def node(probe, scenario):
    """跑 node 侧的行为桩：真实浏览器行为由它代替，桩自己声明用哪个文件。"""
    result = subprocess.run(
        ["node", str(probe), scenario],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise AssertionError(
            "node 场景 %s 失败（%s）\nstdout:\n%s\nstderr:\n%s"
            % (scenario, result.returncode, result.stdout, result.stderr)
        )
    return json.loads(result.stdout)


class TagCollector(html.parser.HTMLParser):
    """只收开始标签及其属性；不看文本内容。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def tags(source):
    collector = TagCollector()
    collector.feed(source)
    return [attrs for _, attrs in collector.tags]


def bilingual_nodes(source):
    """每一对 {中文, 英文}：data-zh / data-en 成对出现的一个节点。"""
    return [
        (attrs.get("data-zh"), attrs.get("data-en"))
        for attrs in tags(source)
        if "data-zh" in attrs or "data-en" in attrs
    ]


def pages():
    """dist/ 下所有页面：以后新增页面自动纳入全站断言。"""
    return sorted(DIST.rglob("*.html"))
