"""产物测试：只对构建产物断言，不测内部函数。

接缝是构建命令 tools/build.py（data + site -> dist）。
测试数据放在 tests/fixtures/ 下，不在运行时建临时目录：
本机沙箱对运行时新建的目录不放行写入，固定数据更稳，也更能说明输入是什么。
"""

import hashlib
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT / "data" / "sff-8472" / "rev-12.4" / "a0.json"
PROBE_DATA = ROOT / "tests" / "fixtures" / "probe-data"
BAD_DATA = ROOT / "tests" / "fixtures" / "bad-data"
BAD_SCHEMA = ROOT / "tests" / "fixtures" / "bad-schema"
PROBE_DIST = ROOT / "dist-probe"
PROBE_ABORT = ROOT / "dist-probe-abort"
DIST = ROOT / "dist"
BYTE_PAGE = DIST / "sff-8472" / "12.4" / "a0" / "0.html"
INDEX_PAGE = DIST / "sff-8472" / "12.4" / "a0" / "index.html"


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


def snapshot(dist):
    """把产物目录压成 {相对路径: sha256}，用于比较两次构建。"""
    out = {}
    for path in sorted(dist.rglob("*")):
        if path.is_file():
            out[path.relative_to(dist).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return out


class BuildArtifactTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.first = build()
        cls.before = snapshot(DIST)
        cls.second = build()
        cls.after = snapshot(DIST)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(PROBE_DIST, ignore_errors=True)
        shutil.rmtree(PROBE_ABORT, ignore_errors=True)

    def test_data_json_passes_schema(self):
        result = run(["tools/validate.py"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_byte_page_exists(self):
        self.assertTrue(BYTE_PAGE.is_file(), "缺少 A0h 字节 0 的字段页")

    def test_byte_page_content_comes_from_structured_json(self):
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        byte = next(b for b in data["bytes"] if b["address"] == 0)
        html = BYTE_PAGE.read_text(encoding="utf-8")
        for text in (
            byte["name"]["zh"],
            byte["name"]["en"],
            byte["description"]["zh"],
            byte["description"]["en"],
        ):
            self.assertIn(text, html)

    def test_byte_page_shows_address_and_length(self):
        html = BYTE_PAGE.read_text(encoding="utf-8")
        self.assertIn("0x00", html)
        self.assertIn("A0h", html)
        self.assertIn("字节数", html)

    def test_byte_page_links_back_to_index(self):
        html = BYTE_PAGE.read_text(encoding="utf-8")
        self.assertIn('href="index.html"', html)

    def test_index_marks_uncollected_bytes_as_pending(self):
        html = INDEX_PAGE.read_text(encoding="utf-8")
        self.assertIn("待补", html)
        # 只有已收录的字节 0 有链接；其余字节不得产生链接
        self.assertIn('href="0.html"', html)
        for address in (1, 2, 127):
            self.assertNotIn('href="%d.html"' % address, html)

    def test_build_is_repeatable(self):
        self.assertEqual(self.first.returncode, 0)
        self.assertEqual(self.second.returncode, 0)
        self.assertEqual(
            self.before,
            self.after,
            "连续两次构建的产物不一致，构建不可重复",
        )

    def test_template_is_not_hardcoded(self):
        """换一份数据（固定数据里的探测值），产物跟着变，且模板里没有数据原文。"""
        build("--data", str(PROBE_DATA), "--dist", str(PROBE_DIST))
        html = (PROBE_DIST / "sff-8472" / "12.4" / "a0" / "0.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("探测用字段名", html)
        self.assertIn("探测用说明", html)
        # 数据里的 < 与 & 必须转义，不能当 HTML 插入
        self.assertIn("&lt;description&gt; &amp; more", html)
        self.assertNotIn("收发器类型（见表 5-1）", html)
        # 模板与构建脚本里不得出现数据原文
        for source in (
            ROOT / "site" / "templates" / "byte.html",
            ROOT / "tools" / "build.py",
        ):
            text = source.read_text(encoding="utf-8")
            self.assertNotIn("探测用字段名", text)

    def test_disclaimer_on_every_page(self):
        for page in (BYTE_PAGE, INDEX_PAGE):
            text = page.read_text(encoding="utf-8")
            self.assertIn("非官方", text)
            self.assertIn("SNIA", text)
            self.assertIn("unofficial", text)

    def test_build_aborts_on_invalid_data(self):
        shutil.rmtree(PROBE_ABORT, ignore_errors=True)
        result = run(["tools/build.py", "--data", str(BAD_DATA), "--dist", str(PROBE_ABORT)])
        self.assertNotEqual(result.returncode, 0, "数据不合法时构建必须失败")
        self.assertFalse(
            (PROBE_ABORT / "sff-8472").exists(), "数据不合法时不得产出页面"
        )

    def test_unsupported_schema_keyword_is_an_error(self):
        result = run(["tools/validate.py", "--schema", str(BAD_SCHEMA)])
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, "schema 里未实现的关键字必须报错")
        self.assertIn("minPropertiesX", output)
        self.assertIn("未实现的关键字", output)

    def test_invalid_data_fails_validation(self):
        result = run(["tools/validate.py", "--data", str(BAD_DATA)])
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, "缺字段的数据应当校验失败")
        self.assertIn("description", output)
        self.assertIn("a0.json", output)


if __name__ == "__main__":
    unittest.main()
