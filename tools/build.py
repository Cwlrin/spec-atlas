"""构建入口（单一接缝）：data/ + site/ -> dist/。

顺序：先按 schema 与位置校验数据，任何一处不合法就整个构建失败；
然后渲染字段页、块索引页与表格清单页，最后拷贝静态资源。产物只由输入决定
（无时间戳、无随机顺序），因此连续两次构建的产物逐字节一致。

双语：每条用户可见文案都渲染成中英两版并存的一个节点（<span class="i18n">），
由根元素 <html data-lang="zh|en"> 决定显示哪一版。切换只改这个属性，
不重建页面、不换 URL，所以切换后停在当前页。界面文案在 site/i18n.json；
字段名与说明直接复用 data/ 里成对存放的 {zh, en}。

地址与条目是两层：一条 byte 覆盖 [address, address+length)，索引按条目列
（多字节字段给地址范围、只链到首地址），字段页则每个地址一页，页面上说清
「这是哪个字段的第几个字节」以及所属分组。
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
COPY_FILE = "i18n.json"

LANGS = ("zh", "en")
DEFAULT_LANG = "zh"

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

TEMPLATE_SLOT = re.compile(r"\{\{(\w+)(?::(raw|attr))?\}\}")
# 只有 {{bi:...}} / {{bi_plain:...}} 是文案槽；其余 {{...}} 归 render() 管，
# 两者不能抢同一个占位符。
COPY_SLOT = re.compile(r"\{\{(bi|bi_plain):(\w+(?:\.\w+)*)\}\}")
FIELD_SLOT = re.compile(r"\{(\w+)\}")
MARKUP = re.compile(r"</?(?:strong|em|b|i|code|br)\s*/?>")

_ALLOWED_MARKUP = ("<strong>", "</strong>", "<em>", "</em>", "<code>", "</code>")


def fail(message):
    """构建失败的唯一出口：说清哪里错了，别丢一段 traceback 给使用者。"""
    raise SystemExit("构建失败：" + message)


def escape_copy(text):
    """界面文案允许少量固定标签（强调、代码），其余尖括号与 & 全部转义。"""
    kept = []

    def stash(match):
        kept.append(match.group(0))
        return "\x00%d\x00" % (len(kept) - 1,)

    text = MARKUP.sub(stash, text)
    text = html.escape(text, quote=False)
    for index, tag in enumerate(kept):
        if tag not in _ALLOWED_MARKUP:
            fail("文案里出现了不支持的标签 %r（只允许 strong/em/code）" % (tag,))
        text = text.replace("\x00%d\x00" % (index,), tag)
    return text


def escape_data(text):
    """数据里的字符串一律当纯文本：数据不该夹带 HTML，尖括号全部转义。"""
    return html.escape(text, quote=False)


def plain(text):
    """把文案里的标签剥掉，留下可放进属性或 <title> 的纯文本。"""
    return html.unescape(MARKUP.sub("", escape_copy(text)))


def substitute(pattern, template, values, mode):
    """单遍替换占位符。

    mode="copy"：取值是界面文案，先过 escape_copy；缺失直接构建失败
                 （文案表与代码必须同步）。
    mode="page"：取值是页面片段或算好的字符串，缺失容忍（返回原样）。
    """
    missing = []

    def replace(match):
        key = match.group(1)
        if key not in values:
            missing.append(key)
            return match.group(0)
        value = str(values[key])
        if mode == "copy":
            return escape_copy(value)
        return value

    filled = pattern.sub(replace, template)
    if missing and mode == "copy":
        fail("文案缺少占位符取值: %s" % ", ".join(sorted(set(missing))))
    return filled


def bilingual(zh_html, en_html):
    """中英两版并存的一个节点：属性里存两版原文，内层按语言显示其中一版。

    入参必须是**已经转义过**的 HTML：转义策略由调用方决定，模型层不代劳。
    """
    return (
        '<span class="i18n" data-zh="%s" data-en="%s">'
        '<span class="i18n-zh" lang="zh-CN">%s</span>'
        '<span class="i18n-en" lang="en">%s</span>'
        "</span>"
        % tuple(
            [
                html.escape(html.unescape(zh_html), quote=True),
                html.escape(html.unescape(en_html), quote=True),
                zh_html,
                en_html,
            ]
        )
    )


def load_copy(site_dir):
    """读界面文案表：每个键都必须同时有中英两版，缺一版就构建失败。"""
    path = Path(site_dir) / COPY_FILE
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        fail("读不到文案表 %s：%s" % (path, exc))
    except json.JSONDecodeError as exc:
        fail("文案表 %s 不是合法 JSON：%s" % (path, exc))
    problems = []
    for key, value in entries.items():
        if not isinstance(value, dict):
            problems.append("%s: 必须是 {zh, en} 对象" % (key,))
            continue
        for lang in LANGS:
            text = value.get(lang)
            if not isinstance(text, str) or not text.strip():
                problems.append("%s: 缺少 %s 版文案" % (key, lang))
    if problems:
        fail("文案表不完整（%d 处）：%s" % (len(problems), "; ".join(problems)))
    return entries


class Copy:
    """模板取文案的唯一入口：一个键 -> 已转义的中英两版。

    来源有两处：site/i18n.json 的界面文案，和数据里本就成对的 {zh, en}
    （字段名、说明）。后者原样转义，不参与占位符填充。
    """

    def __init__(self, entries, values):
        self.entries = entries
        self.values = values

    def pair(self, key):
        entry = self.entries.get(key)
        if entry is not None:
            return tuple(
                substitute(FIELD_SLOT, entry[lang], self.values, "copy")
                for lang in LANGS
            )
        field = self.values.get(key)
        if isinstance(field, dict) and "zh" in field and "en" in field:
            return tuple(escape_data(field[lang]) for lang in LANGS)
        fail("文案表缺少键 %r" % (key,))

    def expand(self, template):
        """把 {{bi:key}} 展开成双语节点，{{bi_plain:key}} 展开成纯文本节点。"""

        def replace(match):
            kind, key = match.group(1), match.group(2)
            zh, en = self.pair(key)
            if kind == "bi_plain":
                return bilingual(plain(zh), plain(en))
            return bilingual(zh, en)

        return COPY_SLOT.sub(replace, template)

    def with_values(self, **extra):
        """同一份文案表、换一套占位符取值（例如把校验和区间填进去）。"""
        return Copy(self.entries, dict(self.values, **extra))


def render(template, values):
    """替换 {{key}} / {{key:raw}} / {{key:attr}}；页面片段用 :raw 原样插入。"""

    def replace(match):
        key, mode = match.group(1), match.group(2)
        if key not in values:
            fail("模板缺少占位符取值: %s" % (key,))
        value = str(values[key])
        if mode == "raw":
            return value
        if mode == "attr":
            return html.escape(value, quote=True)
        return html.escape(value)

    return TEMPLATE_SLOT.sub(replace, template)


def revision_label(store_name):
    """存储目录 rev-12.4 -> 展示与 URL 用的 12.4。"""
    return store_name[4:] if store_name.startswith("rev-") else store_name


def hex_address(address):
    return "0x%02X" % address


def block_label(block):
    """a0 -> A0h"""
    return block[0].upper() + block[1:] + "h"


def load_blocks(data_dir):
    """读出每个寄存器块，以及与之同目录的表登记。

    返回 (blocks, registries)：blocks 是 [(spec, revision, block, document)]，
    registries 是 {(spec, revision): 表登记文档}。
    """
    blocks = []
    registries = {}
    for path in sorted(Path(data_dir).rglob("*.json")):
        relative = path.relative_to(Path(data_dir))
        if len(relative.parts) != 3:
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        spec, revision_dir = relative.parts[0], relative.parts[1]
        if schema_check.is_registry(path):
            registries[(spec, revision_label(revision_dir))] = document
            continue
        blocks.append((spec, revision_label(revision_dir), path.stem, document))
    return blocks, registries


def byte_pair(field):
    """数据里的 {zh, en} 字段 -> 已转义的 (zh, en)。"""
    return escape_data(field["zh"]), escape_data(field["en"])


class SitePage:
    """站点某一页的公共部分：文案表、相对路径、语言切换器。

    字段页、索引页、表格清单页只有各自的内容块不同，外壳与路径算法共用一份。
    """

    def __init__(self, entries, spec, revision, depth):
        self.entries = entries
        self.spec = spec
        self.revision = revision
        self.values = {
            "default_lang": DEFAULT_LANG,
            "spec": spec.upper(),
            "revision": revision,
            "style_href": "../" * depth + "style.css",
            "lang_href": "../" * depth + "lang.js",
        }

    def finish(self, template, switch_template, values):
        """填模板：先补语言切换器，再渲染。子类把自己的内容块放进 values。"""
        self.copy = Copy(self.entries, dict(self.values, **values))
        return render(
            self.copy.expand(template),
            dict(
                self.values,
                **values,
                lang_switch=self.switcher(switch_template),
            ),
        )

    def switcher(self, template):
        """语言切换器：两个状态按钮，当前状态由 aria-pressed 表达。"""
        return render(
            self.copy.expand(template),
            {
                "pressed_zh": "true" if DEFAULT_LANG == "zh" else "false",
                "pressed_en": "true" if DEFAULT_LANG == "en" else "false",
            },
        )

    def titles(self, key):
        """<title> 与 data-title-*：纯文本，不带标签。"""
        zh, en = self.copy.pair(key)
        return plain(zh), plain(en)


class Page(SitePage):
    """一个寄存器块的一页：字段内容、地址定位、各类片段。"""

    def __init__(self, entries, spec, revision, block, document, depth, registry):
        super().__init__(entries, spec, revision, depth)
        self.block = block
        self.document = document
        self.registry = registry
        self.values.update(
            {
                "block": block_label(block),
                "size": document["size"],
                # 字段页与索引页同目录，索引导航就是相邻文件，不必绕回站点根。
                "index_href": "index.html",
            }
        )
        self.copy = Copy(entries, self.values)

    # ---- 地址 -> 条目 ---------------------------------------------------

    def entry_of(self, address):
        for byte in self.document["bytes"]:
            if byte["address"] <= address < byte["address"] + byte.get("length", 1):
                return byte
        fail("地址 %d 没有任何定义" % (address,))

    def section_of(self, address):
        for section in self.document.get("sections", []):
            if section["start"] <= address <= section["end"]:
                return section
        return None

    def rule(self, rule_id):
        for rule in self.document.get("checksums", []):
            if rule["id"] == rule_id:
                return rule
        return None

    # ---- 各种片段 -------------------------------------------------------

    def byte_copy(self, byte, address):
        """页面文案的占位符：address 是**当前访问的地址**，不是条目起点。

        多字节字段每个地址一页，标题里的地址必须是这一页的地址，否则
        0x14-0x23 的十六页会全都自称 0x14。
        """
        return Copy(
            self.entries,
            dict(
                self.values,
                address=address,
                address_hex=hex_address(address),
                field_address_hex=hex_address(byte["address"]),
                length=byte.get("length", 1),
                name_zh=byte["name"]["zh"],
                name_en=byte["name"]["en"],
                name=byte["name"],
                description=byte["description"],
            ),
        )

    def section_html(self, address):
        section = self.section_of(address)
        if section is None:
            return ""
        return "%s（%s–%s）" % (
            bilingual(*byte_pair(section["name"])),
            hex_address(section["start"]),
            hex_address(section["end"]),
        )

    def field_html(self, byte):
        """字段名 + 地址范围，让「这个地址属于哪个字段」一眼可见。"""
        name = bilingual(*byte_pair(byte["name"]))
        length = byte.get("length", 1)
        start = hex_address(byte["address"])
        if length == 1:
            return "%s（%s）" % (name, start)
        return "%s（%s-%s）" % (name, start, hex_address(byte["address"] + length - 1))

    def offset_html(self, byte, offset):
        """多字节字段要说清自己是第几个字节，否则读者无法定位。"""
        length = byte.get("length", 1)
        if length == 1:
            return ""
        copy = self.copy.with_values(offset=offset + 1, length=length)
        return '<p class="byte-offset">%s</p>' % (
            bilingual(*copy.pair("byte.offset_value")),
        )

    def reserved_html(self, byte):
        if not byte.get("reserved"):
            return ""
        return '<p class="byte-reserved">%s</p>' % (
            bilingual(*self.copy.pair("byte.reserved")),
        )

    def bits_html(self, byte):
        """位定义表：一位一行；保留位也写出来，免得读者以为漏了。"""
        bits = byte.get("bits")
        if not bits:
            return ""
        head = "".join(
            "<th>%s</th>" % (bilingual(*self.copy.pair(key)),)
            for key in ("bit.col.bit", "bit.col.name", "bit.col.description")
        )
        rows = []
        for bit in sorted(bits, key=lambda item: -item["bit"]):
            rows.append(
                '<tr class="%s"><td><code>%d</code></td><td>%s</td><td>%s</td></tr>'
                % (
                    "reserved" if bit.get("reserved") else "defined",
                    bit["bit"],
                    bilingual(*byte_pair(bit["name"])),
                    bilingual(*byte_pair(bit["description"])),
                )
            )
        return (
            '<section class="bits"><h2>%s</h2><table class="bit-table">'
            "<thead><tr>%s</tr></thead><tbody>%s</tbody></table></section>"
            % (bilingual(*self.copy.pair("byte.bits")), head, "".join(rows))
        )

    def checksum_html(self, byte, address):
        """校验和：本字节是什么校验和，以及本字节被哪条规则覆盖。"""
        parts = []
        rule_id = byte.get("checksumFor")
        if rule_id:
            rule = self.rule(rule_id)
            if rule is None:
                fail("地址 %d 声明 checksumFor %r，但没有这条规则" % (address, rule_id))
            copy = self.copy.with_values(
                start=hex_address(rule["start"]), end=hex_address(rule["end"])
            )
            parts.append(
                "<p><strong>%s</strong> · %s</p>"
                % (
                    bilingual(*byte_pair(rule["name"])),
                    bilingual(*copy.pair("byte.checksum_rule")),
                )
            )

        covering = [
            rule
            for rule in self.document.get("checksums", [])
            if rule["start"] <= address <= rule["end"]
        ]
        if covering:
            parts.append(
                '<p class="byte-covered">%s：%s</p>'
                % (
                    bilingual(*self.copy.pair("byte.checksum_target_of")),
                    "、".join(bilingual(*byte_pair(item["name"])) for item in covering),
                )
            )
        if not parts:
            return ""
        return '<section class="checksum">%s</section>' % ("".join(parts),)

    def tables_html(self, byte):
        numbers = byte.get("tableRefs") or []
        if not numbers:
            return ""
        refs = []
        for number in numbers:
            copy = self.copy.with_values(number=number)
            refs.append(bilingual(*copy.pair("byte.table_ref")))
        return '<p class="byte-tables">%s：%s</p>' % (
            bilingual(*self.copy.pair("byte.tables")),
            "、".join(refs),
        )

    # ---- 整页 -----------------------------------------------------------

    def render_byte(self, template, address):
        byte = self.entry_of(address)
        offset = address - byte["address"]
        copy = self.byte_copy(byte, address)
        zh, en = copy.pair("byte.title")
        title_zh, title_en = plain(zh), plain(en)
        return render(
            copy.expand(template),
            dict(
                self.values,
                title_zh=title_zh,
                title_en=title_en,
                address_hex=hex_address(address),
                length=byte.get("length", 1),
                section=self.section_html(address),
                field=self.field_html(byte),
                offset=self.offset_html(byte, offset),
                reserved=self.reserved_html(byte),
                bits=self.bits_html(byte),
                checksum=self.checksum_html(byte, address),
                tables=self.tables_html(byte),
            ),
        )

    def render_index(self, template):
        title_zh, title_en = self.titles("index.title")
        return render(
            self.copy.expand(template),
            dict(
                self.values,
                title_zh=title_zh,
                title_en=title_en,
                rows=self.rows(),
                tables_link=self.tables_link(),
            ),
        )

    def tables_link(self):
        if not self.registry:
            return ""
        return '<a href="../tables.html">%s</a>' % (
            bilingual(*self.copy.pair("nav.tables")),
        )

    def rows(self):
        """索引表按条目列：多字节字段给地址范围、只链到首地址。"""
        rows = []
        for byte in sorted(self.document["bytes"], key=lambda item: item["address"]):
            length = byte.get("length", 1)
            start = byte["address"]
            span = (
                hex_address(start)
                if length == 1
                else "%s-%s" % (hex_address(start), hex_address(start + length - 1))
            )
            name = bilingual(*byte_pair(byte["name"]))
            description = bilingual(*byte_pair(byte["description"]))
            if byte.get("reserved"):
                rows.append(
                    '<tr class="reserved"><td>%s</td><td>%s</td><td>%s</td></tr>'
                    % (span, name, description)
                )
            else:
                rows.append(
                    '<tr class="collected"><td>%s</td><td>%s%s</td><td>%s</td></tr>'
                    % (span, '<a href="%d.html">%s</a>' % (start, name), self.offsets_html(byte), description)
                )
        return "\n      ".join(rows)

    def offsets_html(self, byte):
        """多字节字段里的每个地址也要能从索引直达，否则「按地址打开」只剩首地址。

        链接放在字段名之后的同一格里，用全角中点分隔，扫读时仍是一行一个字段。
        """
        length = byte.get("length", 1)
        if length == 1:
            return ""
        start = byte["address"]
        links = "".join(
            '<a href="%d.html">%s</a>' % (address, hex_address(address))
            for address in range(start + 1, start + length)
        )
        return ' <span class="offsets">%s</span>' % (links,)


def copy_with(values):
    """占位符取值：模板缺哪个键就在构建期失败，不留空位。"""
    return dict(values)


class TablesPage(SitePage):
    """一个修订版的表格清单页：每张表一行，未收录的标「待补」且不给链接。"""

    def __init__(self, entries, spec, revision, registry, depth):
        super().__init__(entries, spec, revision, depth)
        self.registry = registry
        tables = registry.get("tables", [])
        self.values.update(
            {
                "block": "",
                "size": 0,
                # 与文案一致：structured = 已结构化的表数（pending 与 generated 都不算）。
                "structured": sum(1 for table in tables if table.get("status") == "collected"),
                "total": len(tables),
            }
        )
        self.copy = Copy(entries, self.values)

    def rows(self):
        rows = []
        pending = bilingual(*self.copy.pair("index.pending"))
        for table in self.registry.get("tables", []):
            status = table.get("status")
            if status == "collected":
                cell = bilingual(*self.copy.pair("tables.status.collected"))
            elif status == "generated":
                cell = bilingual(*self.copy.pair("tables.status.generated"))
            else:
                cell = pending
            rows.append(
                '<tr class="%s"><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                % (
                    "pending" if status == "pending" else "collected",
                    bilingual(
                        *self.copy.with_values(number=table["number"]).pair("byte.table_ref")
                    ),
                    escape_data(table["section"]),
                    bilingual(*byte_pair(table["title"])),
                    cell,
                )
            )
        return "\n      ".join(rows)

    def render(self, template, switch_template):
        title_zh, title_en = self.titles("tables.title")
        return self.finish(
            template,
            switch_template,
            {"title_zh": title_zh, "title_en": title_en, "rows": self.rows()},
        )


def build(data_dir, dist_dir, site_dir, schema_dir):
    _, errors = schema_check.validate_data_dir(data_dir, schema_dir)
    if errors:
        for message in errors:
            print(message, file=sys.stderr)
        fail("数据未通过校验（%d 处）" % (len(errors),))

    entries = load_copy(site_dir)
    templates = Path(site_dir) / "templates"
    byte_template = (templates / "byte.html").read_text(encoding="utf-8")
    index_template = (templates / "index.html").read_text(encoding="utf-8")
    tables_template = (templates / "tables.html").read_text(encoding="utf-8")
    switch_template = (templates / "lang-switch.html").read_text(encoding="utf-8")

    dist = Path(dist_dir).resolve()
    root = ROOT.resolve()
    if dist == root or root.is_relative_to(dist):
        fail("--dist %s 不安全（不能是仓库根或它的上级目录）" % (dist,))
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)

    shutil.copyfile(Path(site_dir) / "style.css", dist / "style.css")
    shutil.copyfile(Path(site_dir) / "lang.js", dist / "lang.js")

    blocks, registries = load_blocks(data_dir)
    revisions = set()
    for spec, revision, block, document in blocks:
        registry = registries.get((spec, revision))
        out_dir = dist / spec / revision / block
        out_dir.mkdir(parents=True)
        depth = len(out_dir.relative_to(dist).parts)
        page = Page(entries, spec, revision, block, document, depth, registry)
        page.values["lang_switch"] = page.switcher(switch_template)

        # 每个地址一页：条目覆盖了哪些地址，就为哪些地址生成页面。
        for address in range(document["size"]):
            rendered = page.render_byte(byte_template, address)
            (out_dir / ("%d.html" % address)).write_text(
                rendered, encoding="utf-8", newline="\n"
            )
        (out_dir / "index.html").write_text(
            page.render_index(index_template), encoding="utf-8", newline="\n"
        )
        revisions.add((spec, revision))

    for spec, revision in sorted(revisions):
        registry = registries.get((spec, revision))
        if registry is None:
            continue
        rev_dir = dist / spec / revision
        rev_dir.mkdir(parents=True, exist_ok=True)
        depth = len(rev_dir.relative_to(dist).parts)
        page = TablesPage(entries, spec, revision, registry, depth)
        (rev_dir / "tables.html").write_text(
            page.render(tables_template, switch_template), encoding="utf-8", newline="\n"
        )

    print("构建完成：%d 个寄存器块，产物在 %s" % (len(blocks), dist))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="把 data/ 渲染成静态站点 dist/")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="数据目录，默认 data/")
    parser.add_argument("--dist", default=str(DEFAULT_DIST), help="产物目录，默认 dist/")
    parser.add_argument("--site", default=str(DEFAULT_SITE), help="站点源目录（templates/、style.css、lang.js、i18n.json），默认 site/")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="schema 目录，默认 schema/")
    args = parser.parse_args(argv)
    return build(args.data, args.dist, args.site, args.schema)


if __name__ == "__main__":
    sys.exit(main())
