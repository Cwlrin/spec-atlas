"""双语两态：只对产物断言（接缝仍是 tools/build.py 与 tools/validate.py）。

AC1 在构建期判定：每一处用户可见文案都渲染成中英两版并存的一个节点，
两版同时存在于同一个文档里，由 <html data-lang="zh|en"> 决定显示哪一版。
因此切换不需要重建页面、也没有第二套 URL。

AC2/AC3 的行为（默认中文、记忆在本机、切换后不跳页）发生在浏览器里，
用 node 跑 site/lang.js + 一个最小 DOM 桩来测（tests/fixtures/lang-probe.js），
测的是规则本身，而不是模板里的字符串。

AC4 用 GLOSSARY.md 做交叉校验：中文用到了表里的词，英文就必须用表里给的
英文写法，不能换同义的说法。
"""

import html.parser
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BLOCK_DIR = DIST / "sff-8472" / "12.4" / "a0"
BYTE_PAGE = BLOCK_DIR / "0.html"
INDEX_PAGE = BLOCK_DIR / "index.html"
COPY_FILE = ROOT / "site" / "i18n.json"
DATA_DIR = ROOT / "data"
GLOSSARY = ROOT / "GLOSSARY.md"
STYLE_CSS = ROOT / "site" / "style.css"
PROBE = ROOT / "tests" / "fixtures" / "lang-probe.js"


def run(args, cwd=ROOT):
    return subprocess.run(
        [sys.executable] + args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def node(scenario):
    result = subprocess.run(
        ["node", str(PROBE), scenario],
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


def build(*extra):
    result = run(["tools/build.py"] + list(extra))
    if result.returncode != 0:
        raise AssertionError(
            "build failed (%s)\nstdout:\n%s\nstderr:\n%s"
            % (result.returncode, result.stdout, result.stderr)
        )
    return result


class _Attributes(html.parser.HTMLParser):
    """收集每个开始标签的全部属性，只关心双语配对与语言状态。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(dict(attrs))


def tags(html):
    parser = _Attributes()
    parser.feed(html)
    return parser.tags


class _BareText(html.parser.HTMLParser):
    """收集双语节点之外的可见文案。

    跳过 <head>（标题另由 data-title-zh/en 切换）与 script/style；
    不含任何文字的片段（0x00、数字、· 这类语言中立的值）不算文案。
    """

    SKIP = {"script", "style", "head", "title"}
    # 文字 = 至少一个 CJK 字符或一个 ASCII 字母；0x00、数字、标点都算语言中立。
    LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
    CJK = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")
    WORD = re.compile(r"[A-Za-z]{2,}")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []        # 每层是否双语节点
        self.skip = 0          # script/style/head/title 嵌套
        self.bare = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.SKIP:
            self.skip += 1
            self.stack.append(False)
            return
        self.stack.append("i18n" in (attrs.get("class") or "").split())

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        if self.stack:
            self.stack.pop()

    def handle_data(self, data):
        if self.skip or any(self.stack):
            return
        text = data.strip()
        if text and (self.CJK.search(text) or self.WORD.search(text)):
            self.bare.append(text)


def bare_text(html):
    """返回双语节点之外、带文字的可见文案片段。"""
    parser = _BareText()
    parser.feed(html)
    return parser.bare


def bilingual_nodes(html):
    """返回 [(zh, en)]：所有带 data-zh 的节点；缺 data-en 的 en 为 None。"""
    return [
        (tag.get("data-zh"), tag.get("data-en"))
        for tag in tags(html)
        if "data-zh" in tag or "data-en" in tag
    ]


class BilingualMarkupTest(unittest.TestCase):
    """AC1：每条文案都有中英两版，切换即时生效（同一文档内两版并存）。"""

    @classmethod
    def setUpClass(cls):
        build()

    def test_every_bilingual_node_pairs_zh_with_en(self):
        for path in (BYTE_PAGE, INDEX_PAGE):
            html = path.read_text(encoding="utf-8")
            nodes = bilingual_nodes(html)
            self.assertTrue(nodes, "%s: 没有找到任何双语节点" % (path.name,))
            for zh, en in nodes:
                self.assertTrue(zh, "%s: 有节点缺中文版：%r" % (path.name, en))
                self.assertTrue(en, "%s: 中文版 %r 缺英文版" % (path.name, zh))

    def test_both_languages_render_in_the_same_document(self):
        html = BYTE_PAGE.read_text(encoding="utf-8")
        for zh, en in bilingual_nodes(html):
            self.assertIn(zh, html)
            self.assertIn(en, html)

    def test_no_visible_copy_escapes_the_pairing(self):
        """页面上不该有「只此一版」的可见文案：双语节点之外不许有裸文本。"""
        for path in (BYTE_PAGE, INDEX_PAGE):
            leftovers = bare_text(path.read_text(encoding="utf-8"))
            self.assertEqual(
                leftovers, [],
                "%s: 这些文案没有中英两版：%r" % (path.name, leftovers),
            )

    def test_language_state_is_on_the_root_element(self):
        for path, page in ((BYTE_PAGE, "字段页"), (INDEX_PAGE, "索引页")):
            html = path.read_text(encoding="utf-8")
            root = next(tag for tag in tags(html) if tag.get("data-lang") is not None)
            self.assertEqual(root.get("data-lang"), "zh", page + "：默认必须是中文")
            self.assertIn('lang="zh-CN"', html)

    def test_switcher_offers_exactly_two_states(self):
        for path in (BYTE_PAGE, INDEX_PAGE):
            html = path.read_text(encoding="utf-8")
            values = [
                tag.get("data-lang-set")
                for tag in tags(html)
                if tag.get("data-lang-set") is not None
            ]
            self.assertEqual(sorted(values), ["en", "zh"], path.name)

    def test_css_hides_the_other_language_for_each_state(self):
        """切换靠 CSS 状态生效：改状态即可，不需要重建页面。"""
        css = STYLE_CSS.read_text(encoding="utf-8")
        squeezed = re.sub(r"\s+", "", css)

        def shows(selector_part):
            """该选择器的规则块里，display 必须不是 none。"""
            for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", squeezed):
                if selector_part not in selector:
                    continue
                display = re.search(r"display:([a-z-]+)", body)
                if display and display.group(1) != "none":
                    return True
            return False

        def hides(selector_part):
            for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", squeezed):
                if selector_part in selector and "display:none" in body:
                    return True
            return False

        self.assertTrue(hides('[data-lang="zh"].i18n>.i18n-en'), "中文态没藏起英文版")
        self.assertTrue(hides('[data-lang="en"].i18n>.i18n-zh'), "英文态没藏起中文版")
        self.assertTrue(shows('[data-lang="en"].i18n>.i18n-en'), "英文态下英文没显示")

    def test_lang_script_is_a_sibling_artifact_of_every_page(self):
        for path in (BYTE_PAGE, INDEX_PAGE):
            html = path.read_text(encoding="utf-8")
            href = re.search(r'<script src="([^"]+lang\.js)"></script>', html)
            self.assertIsNotNone(href, "%s: 页面没有引用 lang.js" % (path.name,))
            target = (path.parent / href.group(1)).resolve()
            self.assertTrue(target.is_file(), "lang.js 相对路径解析不到：%s" % (target,))
            self.assertEqual(target, (DIST / "lang.js").resolve())


class LanguageBehaviourTest(unittest.TestCase):
    """AC2/AC3：默认中文、选择记在本机、切换后不跳页。"""

    @classmethod
    def setUpClass(cls):
        build()

    def test_defaults_to_chinese_on_first_visit(self):
        state = node("fresh")
        self.assertEqual(state["lang"], "zh")
        self.assertEqual(state["langAttr"], "zh-CN")
        self.assertIsNone(state["stored"], "首次访问不该写入任何选择")

    def test_remembers_a_saved_english_choice(self):
        state = node("remembered-en")
        self.assertEqual(state["lang"], "en")
        self.assertEqual(state["langAttr"], "en")

    def test_unknown_saved_value_falls_back_to_chinese(self):
        state = node("corrupt")
        self.assertEqual(state["lang"], "zh")

    def test_switching_updates_state_and_stores_the_choice(self):
        to_en = node("switch-en")
        self.assertEqual(to_en["lang"], "en")
        self.assertEqual(to_en["pressed"], ["false", "true"], "按钮状态要跟着变")
        self.assertEqual(to_en["stored"], "en", "选择必须记在本机")

        back = node("switch-back-zh")
        self.assertEqual(back["lang"], "zh")
        self.assertEqual(back["pressed"], ["true", "false"])
        self.assertEqual(back["stored"], "zh")

    def test_switching_stays_on_the_current_page(self):
        """AC3：切换不跳转、不刷新，所以仍停在当前字段页。"""
        # 先证明这个桩真的能记账，否则下面的空数组什么也证明不了。
        control = node("navigate-control")
        self.assertTrue(
            control["navigations"], "桩没接上跳转，「没跳转」的断言会空转"
        )
        for scenario in ("switch-en", "switch-back-zh"):
            state = node(scenario)
            self.assertEqual(state["navigations"], [], "%s 触发了跳转" % (scenario,))

    def test_denied_storage_keeps_the_choice_for_this_page(self):
        state = node("storage-denied")
        self.assertEqual(state["lang"], "en", "写不进 localStorage 也要当次生效")


def glossary_terms():
    """从术语表读出对齐的 (中文, English) 对。

    单元格里可能是多个变体（「寄存器 / 寄存器映射」对「register / register map」），
    按 / 切开后按位对齐；两栏切出的数量不一致就当作解析不出来。
    """
    pairs = []
    for line in GLOSSARY.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        zh_cell, en_cell = cells[0], cells[1]
        if not zh_cell or not en_cell:
            continue
        if set(zh_cell) <= set("-: ") or zh_cell == "中文":
            continue
        zh_parts = [part.strip() for part in zh_cell.split("/")]
        en_parts = [part.strip() for part in en_cell.split("/")]
        if len(zh_parts) != len(en_parts):
            continue
        pairs.extend(zip(zh_parts, en_parts))
    return pairs


def rejected_terms():
    """从「措辞约定」读出被否掉的写法：「A」不写成「B」。"""
    text = GLOSSARY.read_text(encoding="utf-8")
    return [banned for _, banned in re.findall(r"「(.+?)」不写成「(.+?)」", text)]


class GlossaryConsistencyTest(unittest.TestCase):
    """AC4：英文模式下的术语沿用 GLOSSARY.md。"""

    @classmethod
    def setUpClass(cls):
        cls.copy = json.loads(COPY_FILE.read_text(encoding="utf-8"))
        cls.pairs = sorted(glossary_terms(), key=lambda pair: -len(pair[0]))

    def test_glossary_actually_parsed(self):
        self.assertGreaterEqual(len(self.pairs), 10, "术语表解析出太少条目，测试会空转")
        self.assertIn(("字节", "byte"), self.pairs)

    def test_chinese_copy_uses_glossary_english_counterpart(self):
        problems = []
        for label, entry in self.samples():
            zh, en = entry["zh"], entry["en"]
            # 长词先匹配并遮蔽，免得「位」这种短词命中「位域」内部
            masked_zh, masked_en = zh, en.lower()
            for zh_term, en_term in self.pairs:
                if zh_term not in masked_zh:
                    continue
                masked_zh = masked_zh.replace(zh_term, "\0" * len(zh_term))
                if en_term.lower() in masked_en:
                    masked_en = masked_en.replace(en_term.lower(), "\0" * len(en_term))
                else:
                    problems.append(
                        "%s: 中文用「%s」，英文应按术语表写「%s」，实际是 %r"
                        % (label, zh_term, en_term, entry["en"])
                    )
        self.assertEqual(problems, [], "\n".join(problems))

    def samples(self):
        """界面文案 + 数据里的字段名/说明：AC4 管的是整站的英文，不只是 UI 词条。"""
        items = [("i18n:%s" % key, entry) for key, entry in self.copy.items()]
        for path in sorted(DATA_DIR.rglob("*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            where = path.relative_to(ROOT).as_posix()
            for byte in document.get("bytes", []):
                for field in ("name", "description"):
                    items.append(
                        ("%s#%d.%s" % (where, byte["address"], field), byte[field])
                    )
        return items

    def test_copy_avoids_terms_the_glossary_rejects(self):
        banned = rejected_terms()
        self.assertTrue(banned, "术语表里没解析出被否掉的写法，测试会空转")
        problems = [
            "%s: 用了被否掉的写法「%s」" % (key, word)
            for key, entry in self.copy.items()
            for word in banned
            if word in entry["zh"] or word in entry["en"]
        ]
        self.assertEqual(problems, [], "\n".join(problems))


if __name__ == "__main__":
    unittest.main()