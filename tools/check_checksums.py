"""对一份寄存器转储校验校验和：按 data/ 里声明的规则求和，逐条比对。

转储是 JSON：{"block": "a0", "bytes": {"0": 3, "1": 4, ...}}，键是十进制地址，
值是 0-255 的整数。校验和规则来自数据块自己的 checksums，所以「规则」和
「数据」只有一处真相，改了布局不会漏改校验逻辑。

失败时逐条报出目标字节地址、规则名、期望值与实际值——只说「校验失败」
等于没说，读者需要知道是哪个字节、差多少。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data"

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ALGORITHMS = {
    "sum-low8": lambda values: sum(values) & 0xFF,
}


def fail(message):
    raise SystemExit("校验失败：" + message)


def hex_address(address):
    return "0x%02X" % address


def find_block(data_dir, spec, revision, block):
    path = Path(data_dir) / spec / ("rev-" + revision) / (block + ".json")
    if not path.is_file():
        fail("找不到数据块 %s" % (path,))
    return json.loads(path.read_text(encoding="utf-8"))


def load_dump(path):
    try:
        dump = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        fail("读不到转储 %s：%s" % (path, exc))
    except json.JSONDecodeError as exc:
        fail("转储 %s 不是合法 JSON：%s" % (path, exc))
    if not isinstance(dump, dict) or "bytes" not in dump:
        fail("转储 %s 缺少 bytes 字段" % (path,))
    raw = dump["bytes"]
    if isinstance(raw, list):
        values = {index: value for index, value in enumerate(raw)}
    elif isinstance(raw, dict):
        values = {}
        for key, value in raw.items():
            try:
                values[int(key)] = value
            except ValueError:
                fail("转储里的地址 %r 不是整数" % (key,))
    else:
        fail("转储的 bytes 必须是对象或数组")
    for address, value in values.items():
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 255:
            fail("地址 %s 的值 %r 不是 0-255 的整数" % (hex_address(address), value))
    return dump, values


def check(data_dir, dump_path):
    dump, values = load_dump(dump_path)
    spec = dump.get("spec", "sff-8472")
    revision = dump.get("revision", "12.4")
    block = dump.get("block", "a0")
    document = find_block(data_dir, spec, revision, block)
    size = document["size"]
    label = dump.get("label") or Path(dump_path).name

    problems = []

    missing = [address for address in range(size) if address not in values]
    if missing:
        problems.append(
            "转储缺 %d 个字节：%s"
            % (len(missing), ", ".join(hex_address(address) for address in missing))
        )
    extra = sorted(address for address in values if address >= size)
    if extra:
        problems.append(
            "转储多出 %d 个字节（块大小 %d）：%s"
            % (len(extra), size, ", ".join(hex_address(address) for address in extra))
        )

    checked = 0
    for rule in document.get("checksums", []):
        algorithm = rule["algorithm"]
        compute = ALGORITHMS.get(algorithm)
        if compute is None:
            problems.append("规则 %r 用了未知算法 %r" % (rule["id"], algorithm))
            continue
        start, end, target = rule["start"], rule["end"], rule["target"]
        span = range(start, end + 1)
        if any(address not in values for address in span) or target not in values:
            continue  # 缺字节已经在上面报过了，别重复
        expected = compute([values[address] for address in span])
        actual = values[target]
        checked += 1
        if expected != actual:
            problems.append(
                "%s 不符：%s 应为 %s 至 %s 之和的低 8 位 = %d (%s)，转储中该字节是 %d (%s)"
                % (
                    rule["name"]["zh"],
                    hex_address(target),
                    hex_address(start),
                    hex_address(end),
                    expected,
                    hex_address(expected),
                    actual,
                    hex_address(actual),
                )
            )

    if problems:
        for message in problems:
            print("%s: %s" % (label, message), file=sys.stderr)
        print("校验失败：%s，%d 处问题" % (label, len(problems)), file=sys.stderr)
        return 1
    print(
        "校验通过：%s，%d 条校验和（%s）"
        % (
            label,
            checked,
            "、".join(rule["name"]["en"] for rule in document.get("checksums", [])),
        )
    )
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="按 data/ 里的规则校验寄存器转储的校验和")
    parser.add_argument("--dump", required=True, help="转储 JSON 文件")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="数据目录，默认 data/")
    args = parser.parse_args(argv)
    return check(args.data, args.dump)


if __name__ == "__main__":
    sys.exit(main())
