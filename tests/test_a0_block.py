"""A0h 全 128 字节、校验和与表登记：对构建产物与校验命令断言。

与 test_build.py 同一接缝：`tools/build.py`（data + site -> dist）、`tools/validate.py`、
`tools/build_data.py`（data-src -> data）、`tools/check_checksums.py`（转储求和）。
"""

import json
import re
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import build, run  # noqa: E402
A0_FILE = ROOT / "data" / "sff-8472" / "rev-12.4" / "a0.json"
TABLE_INDEX = ROOT / "data" / "sff-8472" / "rev-12.4" / "table-registry.json"
FIXTURES = ROOT / "tests" / "fixtures"
GAP_DATA = FIXTURES / "gap-data"
RESERVED_DATA = FIXTURES / "reserved-data"
OVERLAP_DATA = FIXTURES / "overlap-data"
PARTIAL_SECTIONS_DATA = FIXTURES / "partial-sections-data"
DUMPS = FIXTURES / "dumps"
DIST = ROOT / "dist"
BLOCK_DIR = DIST / "sff-8472" / "12.4" / "a0"
REV_DIR = DIST / "sff-8472" / "12.4"
TMP_DIST = ROOT / "dist-a0-tmp"


class A0CoverageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP_DIST, ignore_errors=True)

    def test_every_address_is_defined_exactly_once(self):
        document = json.loads(A0_FILE.read_text(encoding="utf-8"))
        seen = {}
        overlaps = []
        for index, byte in enumerate(document["bytes"]):
            for offset in range(byte.get("length", 1)):
                address = byte["address"] + offset
                if address in seen:
                    overlaps.append((address, seen[address], index))
                else:
                    seen[address] = index
        missing = [a for a in range(document["size"]) if a not in seen]
        self.assertEqual(missing, [], "A0h 有字节没有定义：%r" % (missing,))
        self.assertEqual(overlaps, [], "地址被多条定义覆盖：%r" % (overlaps,))

    def test_every_byte_entry_is_bilingual_and_has_description(self):
        document = json.loads(A0_FILE.read_text(encoding="utf-8"))
        for byte in document["bytes"]:
            for field in ("name", "description"):
                value = byte[field]
                self.assertIsInstance(value, dict, "%r 不是双语对象" % (field,))
                self.assertTrue(value["zh"].strip(), "%s 缺中文" % (field,))
                self.assertTrue(value["en"].strip(), "%s 缺英文" % (field,))

    def test_reserved_entries_are_explicit(self):
        """保留区必须显式标注，不能靠「没有定义」表达。

        A0h 里没有整块保留的字节（保留的是位），因此拿固定数据断言规则本身。
        """
        document = json.loads(
            (RESERVED_DATA / "sff-8472" / "rev-12.4" / "a0.json").read_text(
                encoding="utf-8"
            )
        )
        reserved = [byte for byte in document["bytes"] if byte.get("reserved")]
        self.assertTrue(reserved, "固定数据里必须有保留条目，否则这条断言空转")
        for byte in reserved:
            self.assertIn("保留", byte["name"]["zh"] + byte["description"]["zh"])

    def test_reserved_entry_renders_an_explicit_note(self):
        """保留条目在页面上要有一行说明，而不是靠「什么都没写」表达。"""
        fixture = json.loads(
            (RESERVED_DATA / "sff-8472" / "rev-12.4" / "a0.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertTrue(any(byte.get("reserved") for byte in fixture["bytes"]))
        build("--data", str(RESERVED_DATA), "--dist", str(TMP_DIST))
        try:
            html = (TMP_DIST / "sff-8472" / "12.4" / "a0" / "1.html").read_text(
                encoding="utf-8"
            )
        finally:
            shutil.rmtree(TMP_DIST, ignore_errors=True)
        self.assertIn('class="byte-reserved"', html)
        self.assertIn("保留", html)

    def test_every_address_has_a_page(self):
        pages = sorted(int(p.stem) for p in BLOCK_DIR.glob("*.html") if p.stem.isdigit())
        self.assertEqual(pages, list(range(128)), "字节页不是 0..127 全覆盖")

    def test_byte_page_inside_a_group_names_the_group_and_offset(self):
        """地址 25 落在「厂商名称 20-35」里，页面要说清它属于哪个字段。"""
        html = (BLOCK_DIR / "25.html").read_text(encoding="utf-8")
        self.assertIn("0x19", html)
        document = json.loads(A0_FILE.read_text(encoding="utf-8"))
        entry = next(b for b in document["bytes"] if b["address"] <= 25 < b["address"] + b.get("length", 1))
        self.assertIn(entry["name"]["zh"], html)
        self.assertIn("0x14", html)  # 字段起始地址

    def test_block_index_lists_entries_with_ranges(self):
        """一个字段一行：给地址范围、链到首地址；字段内其余地址在同一格里直链，
        这样「按地址打开某一页」不会只剩首地址可达。"""
        html = (BLOCK_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn("0x14-0x23", html)
        self.assertIn('href="20.html"', html)
        self.assertIn('href="25.html"', html)
        document = json.loads(A0_FILE.read_text(encoding="utf-8"))
        rows = len(re.findall(r'<tr class="(?:collected|reserved)"', html))
        self.assertEqual(rows, len(document["bytes"]), "索引行数必须等于字段条数")


class ChecksumTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build()

    def test_checksum_rules_are_declared(self):
        document = json.loads(A0_FILE.read_text(encoding="utf-8"))
        rules = {rule["id"]: rule for rule in document["checksums"]}
        self.assertIn("cc-base", rules)
        self.assertIn("cc-ext", rules)
        base = rules["cc-base"]
        self.assertEqual((base["start"], base["end"], base["target"]), (0, 62, 63))
        ext = rules["cc-ext"]
        self.assertEqual((ext["start"], ext["end"], ext["target"]), (64, 94, 95))

    def test_real_dump_passes_checksum(self):
        result = run("tools/check_checksums.py", "--dump", DUMPS / "a0-synthetic.json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("校验通过", result.stdout)

    def test_broken_dump_fails_and_names_the_byte(self):
        result = run("tools/check_checksums.py", "--dump", DUMPS / "a0-synthetic-broken.json")
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, "校验和不符时必须失败")
        self.assertIn("0x3F", output, "失败信息必须定位到具体字节")
        self.assertIn("CC_BASE", output)

    def test_truncated_dump_names_the_missing_byte(self):
        result = run("tools/check_checksums.py", "--dump", DUMPS / "a0-synthetic-short.json")
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("0x7F", output, "缺字节时必须说清缺的是哪个地址")

    def test_inconsistent_checksum_rule_fails_validation(self):
        """求和区间和目标字节重叠的规则，必须在构建前就被拦下。"""
        result = run("tools/validate.py", "--data", OVERLAP_DATA)
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, "自相矛盾的校验和规则必须报错")
        self.assertIn("校验和", output)
        self.assertIn("目标字节 3", output)

    def test_gap_in_coverage_fails_validation(self):
        """缺口必须点名缺的地址；只写「有缺口」无法定位。"""
        result = run("tools/validate.py", "--data", GAP_DATA)
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, "有字节没定义必须报错")
        self.assertIn("地址 1 没有任何定义", output, output)

    def test_reserved_block_covers_everything(self):
        """整块标为保留也算「有定义」，校验器不得把它当成缺口。"""
        result = run("tools/validate.py", "--data", RESERVED_DATA)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_sections_must_cover_the_whole_block(self):
        """分组只盖住一部分时，字段页上的「所属分组」会时有时无，必须报错。"""
        result = run("tools/validate.py", "--data", PARTIAL_SECTIONS_DATA)
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, "分组没盖满整块时必须报错")
        self.assertIn("分组", output)
        self.assertIn("3", output)


class TableRegistryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build()

    def test_registry_lists_every_table_of_the_revision(self):
        document = json.loads(TABLE_INDEX.read_text(encoding="utf-8"))
        numbers = [table["number"] for table in document["tables"]]
        self.assertEqual(len(numbers), len(set(numbers)), "表号重复")
        for expected in ("4-1", "4-2", "5-1", "5-3", "8-3", "8-8", "9-16", "10-6"):
            self.assertIn(expected, numbers)
        self.assertEqual(len(numbers), 45, "表数量与规范正文不符")

    def test_table_page_marks_uncollected_tables_as_pending(self):
        html = (REV_DIR / "tables.html").read_text(encoding="utf-8")
        self.assertIn("表 5-1", html)
        self.assertIn("待补", html)
        # 一张都还没收录，因此不得出现任何表页链接
        self.assertNotIn('href="tables/table-', html)

    def test_block_index_links_the_table_page(self):
        html = (BLOCK_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="../tables.html"', html)

    def test_no_dead_links_anywhere_in_dist(self):
        for page in sorted(DIST.rglob("*.html")):
            html = page.read_text(encoding="utf-8")
            for href in re.findall(r'href="([^"]+)"', html):
                if href.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                target = (page.parent / href.split("#")[0]).resolve()
                self.assertTrue(
                    target.is_file(), "%s 里的链接指向不存在的位置：%s" % (page, href)
                )


class DataRebuildTest(unittest.TestCase):
    def test_data_dir_is_rebuilt_from_source(self):
        result = run("tools/build_data.py", "--check")
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, "data/ 与 data-src/ 不一致，需要重建：\n%s" % output)

    def test_rebuild_is_deterministic(self):
        first = run("tools/build_data.py", "--check")
        second = run("tools/build_data.py", "--check")
        self.assertEqual((first.returncode, first.stdout), (second.returncode, second.stdout))


if __name__ == "__main__":
    unittest.main()
