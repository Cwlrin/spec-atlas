"""把 data-src/ 的手写数据规范化为 data/，让 data/ 始终可重建。

分工：
- data-src/ 是唯一手写的地方（字段、位、校验和规则、表登记），改了就往这里改；
- data/ 是派生产物，供 build.py 与 validate.py 直接读取，不要手改。

规范化只做确定性的事：键顺序按本脚本定义的顺序、缩进 2、LF 换行、末尾补换行。
--check 只比较不写入，用来在测试里断言「data/ 与 data-src/ 一致」。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data-src"
DEFAULT_DATA = ROOT / "data"

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

# 顶层键顺序：先身份，再说明，最后内容。多出来的键按名字排在后面，保证确定性。
TOP_ORDER = (
    "spec",
    "revision",
    "block",
    "size",
    "handEdited",
    "handEditNote",
    "note",
    "sections",
    "checksums",
    "bytes",
    "tables",
)
# 条目内部键顺序，同样只是为了让产物稳定可 diff。
BYTE_ORDER = (
    "address",
    "length",
    "reserved",
    "name",
    "description",
    "note",
    "checksumFor",
    "tableRefs",
    "bits",
)
BIT_ORDER = ("bit", "reserved", "name", "description")
TABLE_ORDER = ("number", "section", "title", "status", "generatedFrom", "note")


def ordered(mapping, order):
    """按给定顺序排列键；未列出的键按名字排在后面，绝不丢字段。"""
    result = {key: mapping[key] for key in order if key in mapping}
    for key in sorted(mapping):
        if key not in result:
            result[key] = mapping[key]
    return result


def normalize(document):
    """把一份数据排成确定的样子；未知字段保留，避免静默丢数据。"""
    result = ordered(document, TOP_ORDER)
    if "bytes" in result:
        bytes_out = []
        for byte in document["bytes"]:
            entry = ordered(byte, BYTE_ORDER)
            if "bits" in entry:
                entry["bits"] = [ordered(bit, BIT_ORDER) for bit in entry["bits"]]
            bytes_out.append(entry)
        result["bytes"] = bytes_out
    if "tables" in result:
        result["tables"] = [ordered(table, TABLE_ORDER) for table in document["tables"]]
    return result


def render(document):
    return json.dumps(normalize(document), ensure_ascii=False, indent=2) + "\n"


def plan(source_dir, data_dir):
    """返回 [(源文件, 目标文件, 目标内容)]，按相对路径排序。"""
    source = Path(source_dir)
    if not source.is_dir():
        raise SystemExit("数据源目录不存在：%s" % (source,))
    jobs = []
    for path in sorted(source.rglob("*.json")):
        relative = path.relative_to(source)
        if len(relative.parts) != 3:
            raise SystemExit(
                "数据源位置不对：期望 <spec>/rev-<x.y>/<文件名>.json，实际是 %s"
                % (relative.as_posix(),)
            )
        document = json.loads(path.read_text(encoding="utf-8"))
        jobs.append((path, Path(data_dir) / relative, render(document)))
    if not jobs:
        raise SystemExit("数据源目录里没有任何 JSON：%s" % (source,))
    return jobs


def main(argv=None):
    parser = argparse.ArgumentParser(description="从 data-src/ 重新生成 data/")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="手写数据目录，默认 data-src/")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="产物目录，默认 data/")
    parser.add_argument(
        "--check",
        action="store_true",
        help="只比较不写入；data/ 与数据源不一致时以非零退出码失败",
    )
    args = parser.parse_args(argv)

    jobs = plan(args.source, args.data)
    stale = []
    for _source, target, content in jobs:
        current = target.read_text(encoding="utf-8") if target.is_file() else None
        if current != content:
            stale.append(target)
            if not args.check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")

    written = {target for _source, target, _content in jobs}
    orphans = [
        path
        for path in sorted(Path(args.data).rglob("*.json"))
        if path not in written
    ] if Path(args.data).is_dir() else []

    if args.check:
        if stale or orphans:
            for path in stale:
                print("需要重建：%s" % (path.relative_to(ROOT).as_posix(),), file=sys.stderr)
            for path in orphans:
                print(
                    "数据源里没有对应文件：%s" % (path.relative_to(ROOT).as_posix(),),
                    file=sys.stderr,
                )
            print(
                "data/ 与 data-src/ 不一致：%d 个文件待生成，%d 个文件多余"
                % (len(stale), len(orphans)),
                file=sys.stderr,
            )
            return 1
        print("data/ 与 data-src/ 一致：%d 个文件" % (len(jobs),))
        return 0

    for path in orphans:
        path.unlink()
        print("删除多余文件：%s" % (path.relative_to(ROOT).as_posix(),))
    print(
        "已生成 %d 个数据文件（其中 %d 个有变化）到 %s"
        % (len(jobs), len(stale), Path(args.data))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
