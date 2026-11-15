"""构建入口（单一接缝）：data/ + site/ -> dist/。

顺序：先按 schema 与位置校验数据，任何一处不合法就整个构建失败；
然后渲染字段页与索引页，最后拷贝静态资源。产物只由输入决定（无时间戳、
无随机顺序），因此连续两次构建的产物逐字节一致。

双语：每条用户可见文案都渲染成中英两版并存的一个节点（<span class="i18n">），
由根元素 <html data-lang="zh|en"> 决定显示哪一版。切换只改这个属性，
不重建页面、不换 URL，所以切换后停在当前页。界面文案在 site/i18n.json；
字段名与说明直接复用 data/ 里成对存放的 {zh, en}。
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

# 站点首页只讲这套接口的公共形状，不绑定某一个协议版本；块清单来自 data/。
HOME_SPEC = "sff-8472"

# 原样拷进产物的静态资源：页面只按相对路径引用它们。
ASSETS = ("style.css", "lang.js", "notice.js")

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

    mode="copy"：取值是界面文案，先过 escape_copy 再按 attribute 需要补引号，
                 缺失直接构建失败（文案表与代码必须同步）。
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
    （字段名、说明）。数据值不过占位符填充，原样转义使用。
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


def render(template, values):
    """替换 {{key}} / {{key:raw}} / {{key:attr}}；页码片段用 :raw 原样插入。"""

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


def byte_pair(field):
    """数据里的 {zh, en} 字段 -> 已转义的 (zh, en)。"""
    return escape_data(field["zh"]), escape_data(field["en"])


class Page:
    """一个寄存器块的一页：页面文案取值、资源相对路径、索引行。"""

    def __init__(self, entries, spec, revision, block, document, depth):
        self.entries = entries
        self.spec = spec
        self.revision = revision
        self.block = block
        self.document = document
        self.values = {
            "default_lang": DEFAULT_LANG,
            "spec": spec.upper(),
            "revision": revision,
            "block": block_label(block),
            "size": document["size"],
            "collected": sum(byte.get("length", 1) for byte in document["bytes"]),
            "style_href": "../" * depth + "style.css",
            "lang_href": "../" * depth + "lang.js",
            "notice_href": "../" * depth + "notice.js",
            # 从站点根回首页就是一块块往上走；深度即当前目录到 dist/ 的层数。
            "home_href": "../" * (depth + 1) + "index.html",
            # 字段页与索引页同目录，索引导航就是相邻文件，不必绕回站点根。
            "index_href": "index.html",
        }
        self.copy = Copy(entries, self.values)

    def switcher(self, template):
        """语言切换器：两个状态按钮，当前状态由 aria-pressed 表达。"""
        return render(
            self.copy.expand(template),
            {
                "pressed_zh": "true" if DEFAULT_LANG == "zh" else "false",
                "pressed_en": "true" if DEFAULT_LANG == "en" else "false",
            },
        )

    def byte_copy(self, byte):
        values = dict(self.values)
        values.update(
            {
                "address": byte["address"],
                "address_hex": hex_address(byte["address"]),
                "length": byte.get("length", 1),
                "name_zh": byte["name"]["zh"],
                "name_en": byte["name"]["en"],
                "name": byte["name"],
                "description": byte["description"],
            }
        )
        return Copy(self.entries, values)

    def titles(self, copy, key):
        """<title> 与 data-title-*：纯文本，不带标签。"""
        zh, en = copy.pair(key)
        return plain(zh), plain(en)

    def render_byte(self, template, byte):
        copy = self.byte_copy(byte)
        title_zh, title_en = self.titles(copy, "byte.title")
        return render(
            copy.expand(template),
            dict(
                self.values,
                title_zh=title_zh,
                title_en=title_en,
                address_hex=hex_address(byte["address"]),
                length=byte.get("length", 1),
            ),
        )

    def render_index(self, template):
        title_zh, title_en = self.titles(self.copy, "index.title")
        return render(
            self.copy.expand(template),
            dict(self.values, title_zh=title_zh, title_en=title_en, rows=self.rows()),
        )

    def rows(self):
        """索引表的一行：已收录的给链接与名称，未收录的标「待补」。"""
        collected = {byte["address"]: byte for byte in self.document["bytes"]}
        pending = bilingual(*self.copy.pair("index.pending"))
        rows = []
        for address in range(self.document["size"]):
            if address in collected:
                byte = collected[address]
                rows.append(
                    '<tr class="collected"><td>%s</td><td><a href="%d.html">%s</a></td><td>%s</td></tr>'
                    % (
                        hex_address(address),
                        address,
                        bilingual(*byte_pair(byte["name"])),
                        bilingual(*byte_pair(byte["description"])),
                    )
                )
            else:
                rows.append(
                    '<tr class="pending"><td>%s</td><td>%s</td><td></td></tr>'
                    % (hex_address(address), pending)
                )
        return "\n      ".join(rows)


def render_home(template, entries, blocks, switch_template, notice):
    """站点首页：讲清这条总线的形状，再把已收录的块列出去处。

    首页不依赖任何单个寄存器块，所以先渲染它；块清单来自 data/，
    收录了哪些块就列哪些，不在这里写死。
    """
    values = {
        "default_lang": DEFAULT_LANG,
        "spec": HOME_SPEC.upper(),
        "style_href": "style.css",
        "lang_href": "lang.js",
        "notice_href": "notice.js",
        "notice": notice,
    }
    copy = Copy(entries, values)
    title_zh, title_en = plain(copy.pair("home.title")[0]), plain(copy.pair("home.title")[1])
    values["lang_switch"] = render(
        copy.expand(switch_template),
        {
            "pressed_zh": "true" if DEFAULT_LANG == "zh" else "false",
            "pressed_en": "true" if DEFAULT_LANG == "en" else "false",
        },
    )
    values["blocks"] = render_home_blocks(copy, blocks)
    return render(
        copy.expand(template),
        dict(values, title_zh=title_zh, title_en=title_en),
    )


def render_home_blocks(copy, blocks):
    """已收录的块：一个块一行，链接到它自己的索引页。

    字节数取自 document["size"]，不写进文案：数据变了文案不该跟着错。
    """
    items = []
    for spec, revision, block, document in blocks:
        key = "home.block.%s" % (block,)
        blurb = copy.pair(key) if key in copy.entries else copy.pair("home.block.other")
        size = Copy(copy.entries, dict(copy.values, size=document["size"])).pair(
            "home.block.size"
        )
        items.append(
            '<li><a href="%s/%s/%s/index.html"><code>%s</code> '
            '<span class="block-go">%s</span></a>'
            '<span class="block-meta">%s · %s</span></li>'
            % (
                html.escape(spec),
                html.escape(revision),
                html.escape(block),
                block_label(block),
                bilingual(*copy.pair("home.open")),
                bilingual(*blurb),
                bilingual(*size),
            )
        )
    return "\n    ".join(items)



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
    switch_template = (templates / "lang-switch.html").read_text(encoding="utf-8")
    home_template = (templates / "home.html").read_text(encoding="utf-8")
    notice_template = (templates / "notice.html").read_text(encoding="utf-8")

    dist = Path(dist_dir).resolve()
    root = ROOT.resolve()
    if dist == root or root.is_relative_to(dist):
        fail("--dist %s 不安全（不能是仓库根或它的上级目录）" % (dist,))
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)

    for asset in ASSETS:
        shutil.copyfile(Path(site_dir) / asset, dist / asset)

    notice = render(Copy(entries, {"default_lang": DEFAULT_LANG}).expand(notice_template), {})

    blocks = load_blocks(data_dir)
    for spec, revision, block, document in blocks:
        out_dir = dist / spec / revision / block
        out_dir.mkdir(parents=True)
        depth = len(out_dir.relative_to(dist).parts)
        page = Page(entries, spec, revision, block, document, depth)
        page.values["lang_switch"] = page.switcher(switch_template)
        page.values["notice"] = notice

        for byte in sorted(document["bytes"], key=lambda item: item["address"]):
            rendered = page.render_byte(byte_template, byte)
            (out_dir / ("%d.html" % byte["address"])).write_text(
                rendered, encoding="utf-8", newline="\n"
            )
        (out_dir / "index.html").write_text(
            page.render_index(index_template), encoding="utf-8", newline="\n"
        )

    (dist / "index.html").write_text(
        render_home(home_template, entries, blocks, switch_template, notice),
        encoding="utf-8",
        newline="\n",
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