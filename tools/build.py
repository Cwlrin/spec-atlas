"""构建入口（单一接缝）：data/ + site/ -> dist/。

顺序：先按 schema 与位置校验数据，任何一处不合法就整个构建失败；
然后渲染字段页与索引页，最后拷贝静态资源。产物只由输入决定（无时间戳、
无随机顺序），因此连续两次构建的产物逐字节一致。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate as schema_check  # noqa: E402  同目录脚本，按路径导入

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data"
DEFAULT_DIST = ROOT / "dist"
DEFAULT_SITE = ROOT / "site"
DEFAULT_SCHEMA = ROOT / "schema"

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def render(template, raw=(), **values):
    """单遍替换 {{key}}：默认 HTML 转义，raw 里的键按原样插入（用于片段）。"""
    missing = []

    def replace(match):
        key = match.group(1)
        if key not in values:
            missing.append(key)
            return match.group(0)
        value = str(values[key])
        return value if key in raw else html.escape(value)

    rendered = PLACEHOLDER.sub(replace, template)
    if missing:
        raise KeyError("模板缺少占位符取值: %s" % ", ".join(sorted(set(missing))))
    return rendered


def revision_label(store_name):
    """存储目录 rev-12.4 -> 展示与 URL 用的 12.4。"""
    return store_name[4:] if store_name.startswith("rev-") else store_name


def hex_address(address):
    return "0x%02X" % address


def block_label(block):
    """a0 -> A0h"""
    return block[0].upper() + block[1:] + "h"


def relative_prefix(from_dir, to_path):
    """从 from_dir 回到 dist 根的相对前缀，统一用 /。"""
    return Path(*[".."] * len(from_dir.relative_to(to_path).parts)).as_posix()


def load_blocks(data_dir):
    blocks = []
    for path in sorted(Path(data_dir).rglob("*.json")):
        relative = path.relative_to(Path(data_dir))
        if len(relative.parts) != 3:
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        blocks.append(
            (relative.parts[0], revision_label(relative.parts[1]), path.stem, document)
        )
    return blocks


def render_byte_page(template, spec, revision, block, byte, style_href):
    label = block_label(block)
    address = byte["address"]
    return render(
        template,
        spec_label=spec.upper(),
        revision=revision,
        block_label=label,
        address=address,
        address_hex=hex_address(address),
        length=byte.get("length", 1),
        name_zh=byte["name"]["zh"],
        name_en=byte["name"]["en"],
        description_zh=byte["description"]["zh"],
        description_en=byte["description"]["en"],
        style_href=style_href,
        index_href="index.html",
    )


def render_index_rows(document):
    collected = {byte["address"]: byte for byte in document["bytes"]}
    rows = []
    for address in range(document["size"]):
        if address in collected:
            byte = collected[address]
            rows.append(
                '<tr class="collected">'
                "<td>%s</td>"
                '<td><a href="%d.html">%s</a></td>'
                "<td>%s</td>"
                "<td>%s</td>"
                "</tr>"
                % (
                    hex_address(address),
                    address,
                    html.escape(byte["name"]["zh"]),
                    html.escape(byte["name"]["en"]),
                    html.escape(byte["description"]["zh"]),
                )
            )
        else:
            rows.append(
                '<tr class="pending">'
                "<td>%s</td>"
                "<td>待补</td>"
                "<td></td>"
                "<td></td>"
                "</tr>" % (hex_address(address),)
            )
    return "\n      ".join(rows)


def build(data_dir, dist_dir, site_dir, schema_dir):
    _, errors = schema_check.validate_data_dir(data_dir, schema_dir)
    if errors:
        for message in errors:
            print(message, file=sys.stderr)
        print("构建失败：数据未通过校验（%d 处）" % (len(errors),), file=sys.stderr)
        return 1

    templates = Path(site_dir) / "templates"
    byte_template = (templates / "byte.html").read_text(encoding="utf-8")
    index_template = (templates / "index.html").read_text(encoding="utf-8")

    dist = Path(dist_dir).resolve()
    root = ROOT.resolve()
    if dist == root or root.is_relative_to(dist):
        print(
            "构建失败：--dist %s 不安全（不能是仓库根或它的上级目录）" % (dist,),
            file=sys.stderr,
        )
        return 1
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)

    shutil.copyfile(Path(site_dir) / "style.css", dist / "style.css")

    blocks = load_blocks(data_dir)
    for spec, revision, block, document in blocks:
        out_dir = dist / spec / revision / block
        out_dir.mkdir(parents=True)
        style_href = relative_prefix(out_dir, dist) + "/style.css"
        for byte in sorted(document["bytes"], key=lambda item: item["address"]):
            page = render_byte_page(
                byte_template, spec, revision, block, byte, style_href
            )
            (out_dir / ("%d.html" % byte["address"])).write_text(
                page, encoding="utf-8", newline="\n"
            )
        index_page = render(
            index_template,
            raw=("rows",),
            spec_label=spec.upper(),
            revision=revision,
            block_label=block_label(block),
            style_href=style_href,
            collected_count=sum(byte.get("length", 1) for byte in document["bytes"]),
            size=document["size"],
            rows=render_index_rows(document),
        )
        (out_dir / "index.html").write_text(index_page, encoding="utf-8", newline="\n")

    print("构建完成：%d 个寄存器块，产物在 %s" % (len(blocks), dist))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="把 data/ 渲染成静态站点 dist/")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="数据目录，默认 data/")
    parser.add_argument("--dist", default=str(DEFAULT_DIST), help="产物目录，默认 dist/")
    parser.add_argument("--site", default=str(DEFAULT_SITE), help="站点源目录（templates/、style.css），默认 site/")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="schema 目录，默认 schema/")
    args = parser.parse_args(argv)
    return build(args.data, args.dist, args.site, args.schema)


if __name__ == "__main__":
    sys.exit(main())
