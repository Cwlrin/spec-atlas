"""概览页与免责声明：只对产物断言（接缝是 tools/build.py）。

AC1（首页讲清两线总线、A0h/A2h 分工、两种校准）在概览页文本上判定；
AC2（全站 footer 中英双语免责声明）遍历 dist/ 下**每一个** HTML 断言，
   以后新增页面自动纳入，不需要回来补测试；
AC3（首次访问提示条）的可关闭与「关过不再出现」是浏览器行为，
用 node 跑 site/notice.js + 最小 DOM 桩来测（tests/fixtures/notice-probe.js）。
"""

import re
import unittest
from pathlib import Path

from artifacts import DIST, bilingual_nodes, build, node, pages, tags

ROOT = Path(__file__).resolve().parents[1]
HOME = DIST / "index.html"
PROBE = ROOT / "tests" / "fixtures" / "notice-probe.js"


def notice(scenario):
    return node(PROBE, scenario)


class OverviewPageTest(unittest.TestCase):
    """AC1：首页在三分钟内讲清这套接口。"""

    @classmethod
    def setUpClass(cls):
        build()
        cls.html = HOME.read_text(encoding="utf-8") if HOME.is_file() else ""

    def test_site_root_has_an_entry_page(self):
        self.assertTrue(HOME.is_file(), "站点根没有入口页 dist/index.html")

    def test_explains_the_two_wire_bus(self):
        for term in ("两线", "two-wire"):
            self.assertIn(term, self.html, "首页没有讲两线总线：%r" % (term,))

    def test_explains_the_two_bus_addresses(self):
        for term in ("A0h", "A2h"):
            self.assertIn(term, self.html, "首页缺少总线地址 %s" % (term,))
        # 地址的二进制形态是「两种地址」的根据，不是装饰
        for bits in ("1010000", "1010001"):
            self.assertIn(bits, self.html, "首页缺少地址位型 %s" % (bits,))

    def test_explains_the_two_calibration_modes(self):
        for term in ("内部校准", "外部校准", "internal calibration", "external calibration"):
            self.assertIn(term, self.html, "首页没有讲清两种校准：%r" % (term,))

    def test_uses_the_glossary_words_not_synonyms(self):
        """术语表定过的词不许换说法（门限/警告 之类）。"""
        for banned in ("门限", "警告标志", "校正"):
            self.assertNotIn(banned, self.html, "首页用了术语表不认的说法：%r" % (banned,))

    def test_links_to_collected_register_blocks(self):
        self.assertIn('href="sff-8472/12.4/a0/index.html"', self.html)

    def test_is_bilingual_with_the_same_two_state_switch(self):
        nodes = bilingual_nodes(self.html)
        self.assertTrue(nodes, "首页没有双语节点")
        for zh, en in nodes:
            self.assertTrue(zh, "有节点缺中文版：%r" % (en,))
            self.assertTrue(en, "中文版 %r 缺英文版" % (zh,))
        root = next(attrs for attrs in tags(self.html) if "data-lang" in attrs)
        self.assertEqual(root["data-lang"], "zh", "首页默认必须是中文")
        values = [
            attrs["data-lang-set"]
            for attrs in tags(self.html)
            if "data-lang-set" in attrs
        ]
        self.assertEqual(sorted(values), ["en", "zh"], "首页要有两态切换")

    def test_every_page_can_reach_the_overview(self):
        """从任何一个页面都点得回首页：按真实路径解析，不是比字符串。"""
        for page in pages():
            relative = page.relative_to(DIST).as_posix()
            if page == HOME:
                continue
            text = page.read_text(encoding="utf-8")
            homes = [
                link
                for link in re.findall(r'href="([^"]*index\.html)"', text)
                if (page.parent / link).resolve() == HOME.resolve()
            ]
            self.assertTrue(
                homes,
                "%s 没有一条真正指回首页的链接（解析后的落点才算数）" % (relative,),
            )
        home_links = re.findall(r'href="([^"]+)"', self.html)
        for link in home_links:
            if link.startswith(("http", "#")):
                continue
            target = (DIST / link).resolve()
            self.assertTrue(
                target.is_file(),
                "首页链到了不存在的东西：%s" % (link,),
            )

    def test_carries_the_disclaimer(self):
        self.assertIn("非官方", self.html)
        self.assertIn("SNIA", self.html)
        self.assertIn("unofficial", self.html)


class SiteWideDisclaimerTest(unittest.TestCase):
    """AC2：全站 footer 展示中英双语免责声明。"""

    @classmethod
    def setUpClass(cls):
        build()

    def test_every_page_carries_both_languages(self):
        self.assertTrue(pages(), "dist/ 里没有任何页面")
        for page in pages():
            text = page.read_text(encoding="utf-8")
            relative = page.relative_to(DIST).as_posix()
            for term in ("非官方", "SNIA", "unofficial"):
                self.assertIn(term, text, "%s 的免责声明缺 %r" % (relative, term))

    def test_disclaimer_is_in_the_footer_of_every_page(self):
        for page in pages():
            text = page.read_text(encoding="utf-8")
            footer = re.search(r"<footer\b.*?</footer>", text, re.S)
            self.assertIsNotNone(
                footer, "%s 没有 footer" % (page.relative_to(DIST).as_posix(),)
            )
            for term in ("非官方", "SNIA", "unofficial"):
                self.assertIn(
                    term,
                    footer.group(0),
                    "%s 的免责声明不在 footer 里" % (page.relative_to(DIST).as_posix(),),
                )


class FirstVisitNoticeMarkupTest(unittest.TestCase):
    """AC3 的静态部分：提示条在所有页面上，脚本作为同级产物可达。"""

    @classmethod
    def setUpClass(cls):
        build()

    def test_every_page_has_the_notice_markup(self):
        self.assertTrue(pages(), "dist/ 里没有任何页面")
        for page in pages():
            text = page.read_text(encoding="utf-8")
            self.assertIn(
                "data-first-visit-notice",
                text,
                "%s 没有首次访问提示条" % (page.relative_to(DIST).as_posix(),),
            )
            self.assertIn(
                "data-notice-dismiss",
                text,
                "%s 的提示条没有关闭入口" % (page.relative_to(DIST).as_posix(),),
            )

    def test_every_page_loads_the_notice_script(self):
        for page in pages():
            text = page.read_text(encoding="utf-8")
            href = re.search(r'<script src="([^"]*notice\.js)"[^>]*></script>', text)
            self.assertIsNotNone(
                href,
                "%s 没有引用 notice.js" % (page.relative_to(DIST).as_posix(),),
            )
            target = (page.parent / href.group(1)).resolve()
            self.assertTrue(target.is_file(), "notice.js 解析不到：%s" % (target,))
            self.assertEqual(target, (DIST / "notice.js").resolve())

    def test_notice_copy_is_bilingual(self):
        text = HOME.read_text(encoding="utf-8")
        bar = re.search(r"<aside[^>]*data-first-visit-notice.*?</aside>", text, re.S)
        self.assertIsNotNone(bar, "首页找不到提示条片段")
        for zh, en in bilingual_nodes(bar.group(0)):
            self.assertTrue(zh and en, "提示条文案缺一版：%r/%r" % (zh, en))


class FirstVisitNoticeBehaviourTest(unittest.TestCase):
    """AC3 的行为：首次出现、关掉后不再出现。"""

    @classmethod
    def setUpClass(cls):
        build()

    def test_notice_shows_on_the_first_visit(self):
        state = notice("fresh")
        self.assertEqual(state["notice"], "shown")
        self.assertIsNone(state["stored"], "首次访问不该写入任何标记")

    def test_dismissing_hides_it_and_writes_the_marker(self):
        state = notice("dismiss-click")
        self.assertEqual(state["notice"], "dismissed", "点关闭后提示条必须消失")
        self.assertEqual(state["stored"], "1", "关闭状态要记在本机")

    def test_it_does_not_come_back_on_the_next_visit(self):
        """关过就不再出现：带着标记重新进站。"""
        state = notice("dismissed-before")
        self.assertEqual(state["notice"], "dismissed")
        self.assertEqual(state["dismisses"], 0, "已经关过，不该再让用户关一次")

    def test_unknown_saved_value_shows_the_notice_again(self):
        state = notice("corrupt")
        self.assertEqual(state["notice"], "shown", "脏值应当当没关过处理")

    def test_a_first_visitor_still_sees_it_when_storage_throws(self):
        """读 localStorage 本身就抛（禁 cookie / 沙箱）时，首次访问仍要看得到。"""
        state = notice("storage-blocked")
        self.assertEqual(state["notice"], "shown", "拿不到存储不该让提示条消失")

    def test_storage_denial_does_not_break_the_page(self):
        state = notice("storage-denied")
        self.assertEqual(state["notice"], "dismissed", "禁写时当次仍要能关掉")

    def test_the_probe_can_observe_a_real_change(self):
        """桩自检：证明这些断言不是空转的。"""
        baseline = notice("fresh")
        changed = notice("dismiss-click")
        self.assertNotEqual(baseline["notice"], changed["notice"])


if __name__ == "__main__":
    unittest.main()