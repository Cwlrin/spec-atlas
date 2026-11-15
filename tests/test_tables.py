"""表格清单页的摘要：对构建产物断言，接缝仍是 tools/build.py（data + site -> dist）。

三条状态语义不同，摘要必须逐项陈述，且数字要与表格各行数得出来的一致：
generated 由寄存器数据渲染、collected 是本站整理的表、pending 尚未收录。
摘要只用一个口径（例如「已结构化」）时，generated 与 collected 混在一起，
读者看到的数字就与表格正文打架（#13）。

期望文案不写死在测试里：按 site/i18n.json 的模板填入固定数据的真实计数，
再与构建出的摘要逐字比较。文案措辞可以改，数字不能改。
"""

import html as html_module
import json
import re
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import build  # noqa: E402

TABLES_DATA = ROOT / "tests" / "fixtures" / "tables-data"
TABLES_DIST = ROOT / "dist-probe-tables"
TABLES_PAGE = TABLES_DIST / "sff-8472" / "12.4" / "tables.html"
REGISTRY = TABLES_DATA / "sff-8472" / "rev-12.4" / "table-registry.json"
COPY_FILE = ROOT / "site" / "i18n.json"

LEDE = re.compile(r'<p class="lede">(.*?)</p>', re.S)
SLOT = re.compile(r"\{(\w+)\}")
# status -> 状态列用的文案键；和构建里那份清单分别陈述同一件约定。
STATUS_COPY = {
    "generated": "tables.status.generated",
    "collected": "tables.status.collected",
    "pending": "index.pending",
}


def lede_node(page):
    """摘要那一段的双语节点原文：页面上其他双语节点（面包屑、页脚）不算。"""
    match = LEDE.search(page)
    if match is None:
        raise AssertionError('页面里没有 <p class="lede"> 摘要段')
    return match.group(1)


def bilingual_attr(lede, attr):
    """取 lede 双语节点里某一语言的原文（属性值已转义，比较前先还原）。"""
    match = re.search(r'%s="([^"]*)"' % (attr,), lede)
    if match is None:
        raise AssertionError("摘要里没有带 %s 的双语节点" % (attr,))
    return html_module.unescape(match.group(1))


def table_counts(tables):
    return {
        status: sum(1 for table in tables if table["status"] == status)
        for status in STATUS_COPY
    }


class TableSummaryTest(unittest.TestCase):
    """摘要的三个数字来自数据，而不是写死的 0。"""

    @classmethod
    def setUpClass(cls):
        build("--data", str(TABLES_DATA), "--dist", str(TABLES_DIST))
        cls.html = TABLES_PAGE.read_text(encoding="utf-8")
        lede = lede_node(cls.html)
        cls.zh = bilingual_attr(lede, "data-zh")
        cls.en = bilingual_attr(lede, "data-en")
        cls.registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        cls.copy = json.loads(COPY_FILE.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TABLES_DIST, ignore_errors=True)

    def counts(self):
        return table_counts(self.registry["tables"])

    def filled(self, lang):
        """文案模板填上固定数据的真实计数：这就是摘要该长成的样子。"""
        counts = self.counts()
        values = dict(counts, total=len(self.registry["tables"]))
        return SLOT.sub(lambda m: str(values[m.group(1)]), self.copy["tables.lede"][lang])

    def test_fixture_really_covers_three_statuses(self):
        """固定数据必须三种状态都有，且三个数字互不相同。

        数字相同（例如都填 2 张）时，把某一种状态的计数写成另一种也读不出差别，
        下面的断言就成了摆设：这份数据本身要让「串位」可见。
        """
        counts = self.counts()
        for status, count in counts.items():
            self.assertGreater(count, 0, "固定数据里没有 %s 的表" % (status,))
        self.assertEqual(
            len(set(counts.values())), 3, "三种状态的表数必须互不相同：%r" % (counts,)
        )
        self.assertEqual(sum(counts.values()), len(self.registry["tables"]))

    def test_lede_asks_for_all_three_counts(self):
        """文案模板必须同时取三种计数：只取一种就无法逐项陈述。"""
        slots = {
            lang: set(SLOT.findall(self.copy["tables.lede"][lang])) for lang in ("zh", "en")
        }
        # 两版占位符必须一致，否则一版会静默漏数或在构建期报缺值。
        self.assertEqual(slots["zh"], slots["en"])
        self.assertEqual(slots["zh"], set(STATUS_COPY) | {"total"})

    def test_summary_numbers_come_from_the_data(self):
        """摘要逐字等于「模板 + 真实计数」：措辞可改，数字不能改错。"""
        for lang, rendered in (("zh", self.zh), ("en", self.en)):
            self.assertEqual(rendered, self.filled(lang), "%s 摘要与数据不一致" % (lang,))

    def test_each_count_sits_next_to_its_own_status_label(self):
        """数字必须紧挨它自己那一种状态的名字（标签取自文案表，不是摘要模板本身）。

        填空式断言只能证明占位符被替换过：模板把 {generated} 说成「已收录」，
        填出来的期望值也会跟着错。这里换个问法——读者读到的每个数字，
        后面跟的是不是它那一种状态的名字。
        """
        patterns = {
            "zh": "%d 张%s",
            "en": "%d %s",
        }
        rendered = {"zh": self.zh, "en": self.en}
        for status, key in STATUS_COPY.items():
            for lang, pattern in patterns.items():
                label = self.copy[key][lang]
                expected = pattern % (self.counts()[status], label)
                self.assertIn(expected, rendered[lang], "%s 摘要里缺 %r" % (lang, expected))

    def test_summary_never_claims_a_single_structured_total(self):
        """单一「已结构化 N 张」口径会与 generated 行冲突，必须消失。"""
        self.assertNotIn("structured", self.copy["tables.lede"]["en"])
        self.assertNotIn("张表，已结构化", self.copy["tables.lede"]["zh"])

    def test_summary_numbers_match_the_rows_they_describe(self):
        """摘要数字 = 表格里各状态行数：两个视角必须数出同一份数据。"""
        counts = self.counts()
        for status in STATUS_COPY:
            rows = len(re.findall(r'<tr class="%s"' % (status,), self.html))
            self.assertEqual(rows, counts[status], "%s 行的数量与数据不符" % (status,))
        self.assertEqual(sum(counts.values()), len(self.registry["tables"]))

    def test_status_column_and_row_class_agree(self):
        """一行一个状态：class 与状态单元格不能各说各话（generated 曾被写成 collected）。"""
        expected = {
            status: self.copy[key]["zh"] for status, key in STATUS_COPY.items()
        }
        rows = re.findall(r'<tr class="(\w+)">(.*?)</tr>', self.html, re.S)
        self.assertEqual(len(rows), len(self.registry["tables"]))
        for status, row in rows:
            self.assertIn(status, expected, "行 class %r 不是已知状态" % (status,))
            cell = re.findall(r'<td><span class="i18n" data-zh="([^"]*)"', row)[-1]
            self.assertEqual(
                html_module.unescape(cell),
                expected[status],
                "class=%s 的行状态列不符" % (status,),
            )

    def test_pending_rows_are_never_linked(self):
        """死链规则不变：待补的表不管摘要怎么写都不给链接。"""
        for row in re.findall(r"<tr[^>]*>.*?</tr>", self.html, re.S):
            if 'class="pending"' in row:
                self.assertNotIn("<a ", row, "待补的表不得给链接：%r" % (row,))
        self.assertNotIn('href="tables/table-', self.html)


class CopyParityTest(unittest.TestCase):
    """中英两版缺一版就构建期失败，摘要不许只有一版。"""

    def test_lede_has_both_languages_in_the_copy_file(self):
        copy = json.loads(COPY_FILE.read_text(encoding="utf-8"))
        entry = copy["tables.lede"]
        self.assertTrue(entry["zh"].strip())
        self.assertTrue(entry["en"].strip())
        # 占位符必须两版一致：只改一版会在构建期报「缺少占位符取值」或静默漏数
        placeholders = sorted(set(SLOT.findall(entry["zh"])))
        self.assertEqual(placeholders, sorted(set(SLOT.findall(entry["en"]))))


if __name__ == "__main__":
    unittest.main()
