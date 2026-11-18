"""图 4-1：双线字段框图（接缝仍是 tools/build.py，断言只落在 dist/）。

AC1「SVG 绘制、缩放不糊」看内联 <svg> 与 viewBox，不看有没有图片标签；
AC2「标出 A0h 与 A2h 的分区与页选择」按表 4-1/4-2/4-3 的地址边界判定，
    分区的字节数由地址区间算出来（data-bytes），不是另写一份；
    PDF 截图里的刻度是 55/95/119/126（差一个字节），照抄就不算过；
AC3「嵌入概览页并与正文对应」按图在首页中的位置与正文用词判定；
AC4「不依赖位图资源」在图内禁掉一切位图引用。

图里的分区表是唯一声明处（tools/build.py 的 FIGURE_A0 / FIGURE_A2 / FIGURE_PAGES），
所以这里不重复抄一遍区间与像素，改为钉住它必须成立的性质：
两个地址列共用一把尺子、框与文字层同尺寸、页选择真的扇出到四类页。
哪块是哪块由图自己的 <g class="bus-column"> / <g class="bus-pages"> 说明。
"""

import re
import unittest

from artifacts import DIST, build

HOME = DIST / "index.html"
FIGURE = re.compile(r'<figure\b[^>]*class="bus-map"[^>]*>.*?</figure>', re.S)
SVG_TAG = re.compile(r"<svg\b[^>]*>")
BAND_RANGE = re.compile(r'<p class="band-range">([^<]*)</p>')
BAND_LABEL = re.compile(r'<p class="band-(?:name|head)">(.*?)</p>', re.S)
BAND_BOX = re.compile(
    r'<rect class="band-box[^"]*" x="(-?[\d.]+)" y="(-?[\d.]+)"'
    r' width="(-?[\d.]+)" height="(-?[\d.]+)" data-bytes="(\d+)"'
)
FIGURE_GROUP = re.compile(
    r'<rect class="figure-group" x="(-?[\d.]+)" y="(-?[\d.]+)"'
    r' width="(-?[\d.]+)" height="(-?[\d.]+)" data-bytes="(\d+)"'
)
FOREIGN = re.compile(
    r'<foreignObject x="(-?[\d.]+)" y="(-?[\d.]+)"'
    r' width="(-?[\d.]+)" height="(-?[\d.]+)"'
)
COLUMN = re.compile(r'<g class="bus-column">(.*?)</g>', re.S)
PAGES = re.compile(r'<g class="bus-pages">(.*?)</g>', re.S)
FLOW = re.compile(r'<path class="flow"[^>]*marker-end="url\(#[^)]+\)"')


def normalized(text):
    """连接号与空白归一：连字符、短破折号、全角半角在断言里当成同一个。

    PDF 与表格里同一个区间可能写成 en dash，逐字比对会把正确的写法判成错的。
    """
    for dash in ("\u2013", "\u2014", "\u2011", "\u2012"):
        text = text.replace(dash, "-")
    return re.sub(r"\s+", " ", text)


def spans(ranges):
    """把写出的区间还原成字节数：「127」是一字节，「92-95」是四字节。"""
    counts = []
    for text in ranges:
        begin, dash, end = text.partition("-")
        counts.append(int(end) - int(begin) + 1 if dash else 1)
    return counts


class FigureFourOneTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build()
        cls.html = HOME.read_text(encoding="utf-8") if HOME.is_file() else ""
        found = FIGURE.search(cls.html)
        cls.figure = normalized(found.group(0)) if found else ""
        cls.columns = [normalized(part) for part in COLUMN.findall(cls.figure)]
        pages = PAGES.search(cls.figure)
        cls.pages = normalized(pages.group(1)) if pages else ""

    def svg_tag(self):
        """<svg> 开标签；缺了就先给一句人话，而不是在后面某处抛 AttributeError。"""
        found = SVG_TAG.search(self.figure)
        self.assertIsNotNone(found, "图 4-1 不是内联 SVG")
        return found.group(0)

    def assertZone(self, zone, start, stop):
        """一个区里的区间必须首尾相接、不重不漏地铺满 start-stop。"""
        ranges = [text.strip() for text in BAND_RANGE.findall(zone)]
        self.assertTrue(ranges, "这个区里没有写出任何字节区间")
        pairs = []
        for text in ranges:
            begin, dash, end = text.partition("-")
            pairs.append((int(begin), int(end) if dash else int(begin)))
        self.assertEqual(pairs[0][0], start, "分区没有从 %d 开始" % (start,))
        self.assertEqual(pairs[-1][1], stop, "分区没有铺到 %d" % (stop,))
        for (begin, end), (next_begin, _) in zip(pairs, pairs[1:]):
            self.assertEqual(
                next_begin,
                end + 1,
                "%d-%d 与下一段 %d 之间断开或重叠" % (begin, end, next_begin),
            )

    def test_overview_embeds_the_figure(self):
        self.assertTrue(self.figure, '首页没有 <figure class="bus-map">')

    def test_figure_is_drawn_with_svg(self):
        self.assertRegex(
            self.svg_tag(),
            r'viewBox="\s*-?[\d.]+ -?[\d.]+ [\d.]+ [\d.]+"',
            "SVG 没有 viewBox，缩放会糊",
        )

    def test_figure_has_an_accessible_name(self):
        svg = self.svg_tag()
        self.assertIn('role="img"', svg, "SVG 没有声明成一张图")
        label = re.search(r'aria-labelledby="([^"]+)"', svg)
        self.assertIsNotNone(label, "SVG 没有可访问名")
        self.assertIn(
            'id="%s"' % (label.group(1),),
            self.figure,
            "aria-labelledby 指向的说明不在图里",
        )

    def test_figure_does_not_depend_on_bitmaps(self):
        for banned in ("<image", "data:image", ".png", ".jpg", ".jpeg", ".gif", ".webp"):
            self.assertNotIn(banned, self.figure, "图 4-1 依赖了位图：%r" % (banned,))

    def test_shows_both_bus_addresses(self):
        """地址里的 X 是读写位的占位符，规范写作大写 X，图与正文都不许走样。"""
        for term in ("1010000X", "1010001X", "A0h", "A2h"):
            self.assertIn(term, self.figure, "图里缺少总线地址 %r" % (term,))
        self.assertNotIn(
            "1010000x", self.html, "首页把地址写成了小写 x，与规范的 1010000X 不一致"
        )

    def test_a0h_partitions_match_table_4_1(self):
        """表 4-1：基本与扩展标识 0-95、厂商特定 96-127、保留 128-255。"""
        self.assertEqual(len(self.columns), 2, "两个地址块不是各自成组")
        self.assertZone(self.columns[0], 0, 255)
        self.assertEqual(
            [text.strip() for text in BAND_RANGE.findall(self.columns[0])],
            ["0-95", "96-127", "128-255"],
            "A0h 的分区与表 4-1 不一致",
        )

    def test_a2h_partitions_match_table_4_2(self):
        """表 4-2：阈值 0-55、校准 56-91、保留与 CC_DMI 92-95、诊断 96-119、厂商 120-126、页选择 127。"""
        self.assertZone(self.columns[1], 0, 127)
        self.assertEqual(
            [text.strip() for text in BAND_RANGE.findall(self.columns[1])],
            ["0-55", "56-91", "92-95", "96-119", "120-126", "127"],
            "A2h 的分区与表 4-2 不一致",
        )

    def test_page_selection_fans_out_to_the_documented_pages(self):
        """表 4-3 与 §10.3：页 00h/01h、02h、03h-7Fh、80h-FFh，页行里是 128-255。"""
        self.assertTrue(self.pages, "图里没有页行")
        self.assertZone(self.pages, 128, 255)
        for term in ("页 00h/01h", "页 02h", "页 03h-7Fh", "页 80h-FFh"):
            self.assertIn(term, self.figure, "图里缺少 %r" % (term,))
        flows = FLOW.findall(self.figure)
        self.assertEqual(len(flows), 4, "页选择应扇出到四类页，实际画了 %d 条" % (len(flows),))

    def test_band_byte_counts_agree_with_their_ranges(self):
        """有区间的框，字节数必须等于区间宽度：抄错数字这里就断。

        页是整页（128-255），不切区间，所以只核对地址列里的框。
        """
        for zone, _start, _stop in ((self.columns[0], 0, 255), (self.columns[1], 0, 127)):
            declared = [
                int(count) for _x, _y, _w, _h, count in BAND_BOX.findall(zone)
            ]
            self.assertEqual(
                declared,
                spans([text.strip() for text in BAND_RANGE.findall(zone)]),
                "分区的字节数与它写出的区间不一致",
            )

    def test_each_declared_box_has_a_label_layer_of_the_same_size(self):
        """文字层与框同尺寸：框小的时候字不会被裁掉，也不会漏到框外。"""
        layers = {
            (float(x), float(y), float(width), float(height))
            for x, y, width, height in FOREIGN.findall(self.figure)
        }
        for x, y, width, height, _count in BAND_BOX.findall(self.figure):
            self.assertIn(
                (float(x), float(y), float(width), float(height)),
                layers,
                "分区框 (x=%s, y=%s) 没有同尺寸的文字层" % (x, y),
            )

    def test_columns_share_one_scale(self):
        """两个地址列共用一把尺子，框高才能跨列比较。

        旧图画成 1 字节 40px、24 字节 46px，两列总高 486 与 340 对不上，
        读者会误以为 A2h 比 A0h 小一半。这里钉住「高/字节」是同一个常数。
        """
        heights = []
        for column in self.columns:
            for x, y, width, height, count in BAND_BOX.findall(column):
                heights.append((float(height), int(count)))
        self.assertGreaterEqual(len(heights), 9, "地址列的分区不够，判定不可靠")
        ratios = [height / count for height, count in heights if count >= 8]
        self.assertLess(
            max(ratios) / min(ratios),
            1.1,
            "同一张图里的框高与字节数不成比例：%r" % ([round(r, 2) for r in ratios],),
        )

    def test_bands_stack_without_gaps_or_overlap(self):
        """同一列里的框首尾相接：高度由字节数算出来，不是手填的坐标。"""
        for column in self.columns:
            boxes = BAND_BOX.findall(column)
            for (x, y, _w, height, _b), (next_x, next_y, _nw, _nh, _nb) in zip(
                boxes, boxes[1:]
            ):
                self.assertEqual(next_x, x, "同一列的框跑到了别的列")
                self.assertAlmostEqual(
                    float(next_y),
                    float(y) + float(height),
                    places=1,
                    msg="第 %s 列的框之间断开或重叠" % (x,),
                )

    def test_columns_end_where_the_page_select_points(self):
        """扇出的起点在页选择之后：旧图从 A2h 中间引出，读者会以为页选择在别处。"""
        flows = FLOW.findall(self.figure)
        self.assertTrue(flows, "图里没有扇出线")
        select_y = float(BAND_BOX.findall(self.columns[1])[-1][1])
        self.assertAlmostEqual(
            float(flows[0].split("d=")[1].split()[1]),
            select_y + float(BAND_BOX.findall(self.columns[1])[-1][3]),
            places=1,
            msg="扇出线没有从页选择的下沿出发",
        )

    def test_labels_come_from_the_copy_table(self):
        """图上每一处文字都走文案表：双语节点在，占位符不在。"""
        self.assertNotIn("{{", self.figure, "图里有占位符没被展开")
        labels = BAND_LABEL.findall(self.figure)
        self.assertGreaterEqual(len(labels), 13, "分区与标题的文字层不够，图不全")
        for label in labels:
            self.assertIn('class="i18n"', label, "图里有不走文案表的裸文字：%r" % (label[:40],))
            self.assertIn('data-zh="', label, "图里的文字缺中文")

    def position(self, marker):
        """某个锚在首页里的位置；锚不见了就直接说清楚，不抛 ValueError。"""
        self.assertIn(marker, self.html, "首页缺少锚 %r" % (marker,))
        return self.html.index(marker)

    def test_figure_sits_between_the_prose_and_the_block_list(self):
        """AC3：图放在概念卡之后、块清单之前，读者按顺序读下来就是「先看图再看去处」。"""
        self.assertLess(
            self.position('class="card-grid"'),
            self.position('class="bus-map"'),
            "图没有放在概念卡之后",
        )
        self.assertLess(
            self.position('class="bus-map"'),
            self.position('class="block-list"'),
            "图插在了块清单之后",
        )

    def test_prose_explains_the_page_select(self):
        """AC3 的另一半：正文要先说清页选择，读者才看得懂图为什么扇出四类页。"""
        prose = re.split(r'<figure class="bus-map">', self.html)[0]
        self.assertIn("页选择", prose, "正文没有提前讲页选择，图里的扇出对读者是凭空出现的")

    def test_figure_speaks_the_same_vocabulary_as_the_prose(self):
        for term in ("校准", "阈值", "页"):
            self.assertIn(term, self.figure, "图里没有用到正文的词 %r" % (term,))


if __name__ == "__main__":
    unittest.main()
