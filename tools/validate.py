"""最小 JSON Schema 校验器：只实现本项目 schema 用到的关键字。

本机没有 jsonschema 依赖，这里按需实现一个子集，避免为了几个关键字引入第三方包。
支持的关键字见 SUPPORTED_KEYWORDS；schema 里出现未实现的关键字会直接报错，
不允许「写了但静默不生效」。

另有几层不在 schema 里的检查，因为它们跨字段或依赖目录布局：
- location_errors：spec / revision / block 必须与所在目录名、文件名一致；
- coverage_errors：每个地址必须恰好被一条定义覆盖，保留区也要显式写出来；
- checksum_errors：校验和规则必须与字节布局自洽（区间不越界、不覆盖自身、
  目标字节确实声明了这条规则）；
- table_errors：字段引用的表必须在该修订版的表登记里，登记的表也要有出处。
每个问题都带上地址，构建失败时才能定位到具体字节。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data"
DEFAULT_SCHEMA = ROOT / "schema"
REGISTER_SCHEMA = "register-block.schema.json"
TABLES_SCHEMA = "tables.schema.json"
TABLES_FILE = "table-registry.json"

# 文档种类只有一处定义：加新种类（例如表文件）时改这张表，不要在各处复制判断。
DOCUMENT_SCHEMAS = {TABLES_FILE: TABLES_SCHEMA}
DEFAULT_SCHEMA_FILE = REGISTER_SCHEMA


def document_kind(path):
    """文件在 <spec>/rev-<x.y>/ 下叫什么，就决定了它是什么文档。"""
    return Path(path).name


def is_registry(path):
    """这个文件是不是表登记（与寄存器块共用一层目录）。"""
    return document_kind(path) in DOCUMENT_SCHEMAS

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

SUPPORTED_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "$ref",
        "title",
        "type",
        "required",
        "properties",
        "additionalProperties",
        "definitions",
        "items",
        "minItems",
        "maxItems",
        "enum",
        "pattern",
        "minimum",
        "maximum",
        "minLength",
    }
)


def _json_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def _matches_type(value, expected):
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "string":
        return isinstance(value, str)
    if expected == "null":
        return value is None
    raise ValueError("schema 里出现未支持的类型: %r" % (expected,))


def _resolve_ref(root_schema, ref):
    if not ref.startswith("#/"):
        raise ValueError("只支持文档内 $ref，收到: %r" % (ref,))
    node = root_schema
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def unsupported_keywords(schema, path="#"):
    """递归找出 schema 里未实现的关键字，返回错误列表。"""
    errors = []
    if not isinstance(schema, dict):
        return errors
    for key, value in schema.items():
        if key not in SUPPORTED_KEYWORDS:
            errors.append("%s: schema 用了未实现的关键字 %r" % (path, key))
            continue
        if key in ("properties", "definitions") and isinstance(value, dict):
            for name, sub_schema in value.items():
                errors.extend(unsupported_keywords(sub_schema, "%s/%s" % (path, name)))
        elif key == "items":
            errors.extend(unsupported_keywords(value, "%s/items" % (path,)))
    return errors


def validate(instance, schema, root_schema=None, path="$"):
    """返回错误信息列表；空列表表示通过。"""
    if root_schema is None:
        root_schema = schema
    if "$ref" in schema:
        return validate(instance, _resolve_ref(root_schema, schema["$ref"]), root_schema, path)

    errors = []

    if "type" in schema and not _matches_type(instance, schema["type"]):
        return ["%s: 期望 %s，实际是 %s" % (path, schema["type"], _json_type(instance))]

    if "enum" in schema and not any(
        _matches_type(instance, "string") == _matches_type(value, "string") and instance == value
        for value in schema["enum"]
    ):
        errors.append("%s: 取值 %r 不在 %r 中" % (path, instance, schema["enum"]))

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append("%s: 长度 %d 小于 %d" % (path, len(instance), schema["minLength"]))
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append("%s: 取值 %r 不匹配 %s" % (path, instance, schema["pattern"]))

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append("%s: %r 小于 %s" % (path, instance, schema["minimum"]))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append("%s: %r 大于 %s" % (path, instance, schema["maximum"]))

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append("%s: 缺少必填字段 %r" % (path, key))
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in sorted(instance):
                if key not in properties:
                    errors.append("%s: 未声明的字段 %r" % (path, key))
        for key, sub_schema in properties.items():
            if key in instance:
                errors.extend(
                    validate(instance[key], sub_schema, root_schema, "%s.%s" % (path, key))
                )

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append("%s: 元素数 %d 小于 %d" % (path, len(instance), schema["minItems"]))
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append("%s: 元素数 %d 大于 %d" % (path, len(instance), schema["maxItems"]))
        if "items" in schema:
            for index, item in enumerate(instance):
                errors.extend(
                    validate(item, schema["items"], root_schema, "%s[%d]" % (path, index))
                )

    return errors


def schema_for(data_file, data_dir, schema_dir):
    """<spec>/rev-<x.y>/<block>.json -> register-block；同名目录下的 table-registry.json -> tables。"""
    parts = Path(data_file).relative_to(data_dir).parts
    if len(parts) != 3:
        raise ValueError(
            "位置不对：期望 <spec>/rev-<x.y>/<文件名>.json，实际是 %s" % ("/".join(parts),)
        )
    return Path(schema_dir) / DOCUMENT_SCHEMAS.get(
        document_kind(data_file), DEFAULT_SCHEMA_FILE
    )


def location_errors(document, file_path, data_dir):
    """schema 管形状，这里管「内容与所在位置对得上」。"""
    spec_dir, revision_dir, filename = Path(file_path).relative_to(data_dir).parts
    expected_revision = revision_dir[4:] if revision_dir.startswith("rev-") else revision_dir
    errors = []
    if document.get("spec") != spec_dir:
        errors.append("spec 字段 %r 与目录名 %r 不一致" % (document.get("spec"), spec_dir))
    if document.get("revision") != expected_revision:
        errors.append(
            "revision 字段 %r 与目录名 %r 不一致" % (document.get("revision"), revision_dir)
        )
    if is_registry(file_path):
        return errors
    if document.get("block") != Path(filename).stem:
        errors.append(
            "block 字段 %r 与文件名 %r 不一致" % (document.get("block"), filename)
        )
    return errors


def _covered(document):
    """展开成长度表：{地址: (条目下标, 条目内偏移)}。"""
    covered = {}
    overlaps = []
    for index, byte in enumerate(document.get("bytes", [])):
        if not isinstance(byte, dict):
            continue
        address = byte.get("address")
        if not isinstance(address, int):
            continue
        for offset in range(byte.get("length", 1)):
            key = address + offset
            if key in covered:
                overlaps.append((key, covered[key][0], index))
            else:
                covered[key] = (index, offset)
    return covered, overlaps


def _ranges(addresses):
    """[1,2,3,6] -> '1-3, 6'，报错时比逐个列可读。"""
    ordered = sorted(addresses)
    spans = []
    for address in ordered:
        if spans and address == spans[-1][1] + 1:
            spans[-1][1] = address
        else:
            spans.append([address, address])
    return ", ".join(
        "%d" % start if start == end else "%d-%d" % (start, end) for start, end in spans
    )


def coverage_errors(document):
    """每个地址恰好一条定义：缺一条要报，重叠也要报。"""
    errors = []
    size = document.get("size", 0)
    covered, overlaps = _covered(document)
    for address, first, second in overlaps:
        errors.append(
            "地址 %d 被 bytes[%d] 与 bytes[%d] 重复覆盖" % (address, first, second)
        )
    missing = [address for address in range(size) if address not in covered]
    if missing:
        errors.append(
            "地址 %s 没有任何定义（块大小 %d，缺 %d 个字节）"
            % (_ranges(missing), size, len(missing))
        )
    beyond = sorted(address for address in covered if address >= size)
    if beyond:
        errors.append("地址 %s 超出块大小 %d" % (_ranges(beyond), size))

    sections = document.get("sections", [])
    for index, section in enumerate(sections):
        start, end = section.get("start"), section.get("end")
        if isinstance(start, int) and isinstance(end, int) and start > end:
            errors.append("sections[%d]: 起点 %d 大于终点 %d" % (index, start, end))

    # 分组要么不写（单块字段的简单数据），要么把 0..size-1 完整分掉且不重叠：
    # 半截的分组会让字段页上的「所属分组」时有时无。
    if sections:
        spans = []
        for index, section in enumerate(sections):
            start, end = section.get("start"), section.get("end")
            if not all(isinstance(value, int) for value in (start, end)):
                continue
            for other_start, other_end, other_index in spans:
                if start <= other_end and other_start <= end:
                    errors.append(
                        "sections[%d] 的区间 %d-%d 与 sections[%d] 的 %d-%d 重叠"
                        % (index, start, end, other_index, other_start, other_end)
                    )
            spans.append((start, end, index))
        claimed = set()
        for start, end, _index in spans:
            claimed.update(range(start, end + 1))
        unclaimed = [address for address in range(size) if address not in claimed]
        if unclaimed:
            errors.append(
                "分组没有覆盖地址 %s（块大小 %d）" % (_ranges(unclaimed), size)
            )
    return errors


def checksum_errors(document):
    """校验和规则要和字节布局自洽，否则求和永远对不上。"""
    errors = []
    size = document.get("size", 0)
    rules = document.get("checksums", [])
    by_target = {}
    for index, rule in enumerate(rules):
        start, end, target = rule.get("start"), rule.get("end"), rule.get("target")
        if not all(isinstance(value, int) for value in (start, end, target)):
            continue
        if start > end:
            errors.append("checksums[%d]: 求和区间 %d-%d 起点大于终点" % (index, start, end))
        if target >= size or end >= size:
            errors.append(
                "校验和 %r 越界：区间 %d-%d、目标字节 %d，块大小 %d"
                % (rule.get("id"), start, end, target, size)
            )
        if start <= target <= end:
            errors.append(
                "校验和 %r 的求和区间 %d-%d 包含了目标字节 %d，求和自指"
                % (rule.get("id"), start, end, target)
            )
        by_target[target] = rule.get("id")
        for other in rules[:index]:
            o_start, o_end = other.get("start"), other.get("end")
            if not all(isinstance(value, int) for value in (o_start, o_end)):
                continue
            if start <= o_end and o_start <= end:
                errors.append(
                    "校验和 %r 的区间 %d-%d 与 %r 的区间 %d-%d 重叠"
                    % (rule.get("id"), start, end, other.get("id"), o_start, o_end)
                )

    covered, _ = _covered(document)
    for address in sorted(by_target):
        if address not in covered:
            errors.append("校验和目标字节 %d 没有对应的字节定义" % (address,))

    for index, byte in enumerate(document.get("bytes", [])):
        if not isinstance(byte, dict) or "checksumFor" not in byte:
            continue
        rule_id = byte["checksumFor"]
        if rule_id not in [rule.get("id") for rule in rules]:
            errors.append(
                "bytes[%d]（地址 %r）声明 checksumFor %r，但没有这条校验和规则"
                % (index, byte.get("address"), rule_id)
            )
            continue
        rule = next(rule for rule in rules if rule.get("id") == rule_id)
        if rule.get("target") != byte.get("address"):
            errors.append(
                "bytes[%d]（地址 %r）声明为校验和 %r 的目标，但规则指向字节 %r"
                % (index, byte.get("address"), rule_id, rule.get("target"))
            )
    return errors


def bit_errors(document):
    """位域只在单字节字段上成立，且一位只能有一条解释。"""
    errors = []
    for index, byte in enumerate(document.get("bytes", [])):
        if not isinstance(byte, dict) or "bits" not in byte:
            continue
        if byte.get("length", 1) != 1:
            errors.append(
                "bytes[%d]（地址 %r）长 %r 字节，不能写位域"
                % (index, byte.get("address"), byte.get("length", 1))
            )
        seen = {}
        for jndex, bit in enumerate(byte.get("bits", [])):
            if not isinstance(bit, dict):
                continue
            number = bit.get("bit")
            if number in seen:
                errors.append(
                    "地址 %r 的比特 %r 重复出现在 bits[%d] 与 bits[%d]"
                    % (byte.get("address"), number, seen[number], jndex)
                )
            else:
                seen[number] = jndex
    return errors


def table_errors(document, registry):
    """字段引用的表必须在表登记里；登记的表也要真的出现在规范里。"""
    errors = []
    if registry is None:
        for index, byte in enumerate(document.get("bytes", [])):
            if isinstance(byte, dict) and byte.get("tableRefs"):
                errors.append(
                    "bytes[%d]（地址 %r）引用了表 %r，但本修订版没有 table-registry.json"
                    % (index, byte.get("address"), byte["tableRefs"])
                )
        return errors
    known = {table.get("number") for table in registry.get("tables", [])}
    for index, byte in enumerate(document.get("bytes", [])):
        if not isinstance(byte, dict):
            continue
        for number in byte.get("tableRefs", []):
            if number not in known:
                errors.append(
                    "bytes[%d]（地址 %r）引用了表 %s，但表登记里没有这张表"
                    % (index, byte.get("address"), number)
                )
    return errors


def registry_errors(registry, block_names):
    """表登记自身：表号唯一、generatedFrom 指向真的数据块。"""
    errors = []
    seen = {}
    for index, table in enumerate(registry.get("tables", [])):
        if not isinstance(table, dict):
            continue
        number = table.get("number")
        if number in seen:
            errors.append(
                "tables[%d]: 表号 %r 与 tables[%d] 重复" % (index, number, seen[number])
            )
        else:
            seen[number] = index
        source = table.get("generatedFrom")
        if source and source not in block_names:
            # 数据块还没收录（例如 A2h 在 #6）：允许，但站点上必须还能标成待补，
            # 所以这里只接受 pending，不接受 collected。
            if table.get("status") != "pending":
                errors.append(
                    "tables[%d]: 表 %r 声明由 %r 生成，但没有这个数据块，因此不能标为 %r"
                    % (index, number, source, table.get("status"))
                )
        if table.get("status") == "generated" and not source:
            errors.append("tables[%d]: 表 %r 标为 generated，但没写 generatedFrom" % (index, number))
    return errors


def consistency_errors(document):
    """跨字段约束：这些不该靠 schema 的位置表达，也不该让构建静默吞掉。"""
    errors = []
    if document.get("handEdited") and not document.get("handEditNote"):
        errors.append("handEdited 为真时必须写 handEditNote，说明哪些字段是手改的")
    errors.extend(coverage_errors(document))
    errors.extend(checksum_errors(document))
    errors.extend(bit_errors(document))
    return errors


def load_schema(schema_path):
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    return schema, unsupported_keywords(schema)


def validate_data_dir(data_dir, schema_dir):
    """校验数据目录下所有 JSON，返回 (文件数, 错误列表)。"""
    data_path = Path(data_dir)
    errors = []
    files = sorted(data_path.rglob("*.json")) if data_path.is_dir() else []
    if not files:
        return 0, ["%s: 没有找到任何数据文件" % (data_path,)]

    registries = {}
    documents = []
    for file_path in files:
        label = file_path.relative_to(data_path.parent).as_posix()
        try:
            document = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append("%s: JSON 解析失败：%s" % (label, exc))
            continue
        if not isinstance(document, dict):
            errors.append("%s: 顶层必须是对象" % (label,))
            continue
        try:
            schema_path = schema_for(file_path, data_path, schema_dir)
        except ValueError as exc:
            errors.append("%s: %s" % (label, exc))
            continue
        try:
            schema, schema_problems = load_schema(schema_path)
        except OSError as exc:
            errors.append("%s: 无法加载 schema：%s" % (label, exc))
            continue
        for message in schema_problems:
            errors.append("%s: %s" % (label, message))
        schema_errors = validate(document, schema)
        for message in schema_errors:
            errors.append("%s: %s" % (label, message))
        if schema_errors:
            continue
        for message in location_errors(document, file_path, data_path):
            errors.append("%s: %s" % (label, message))
        if is_registry(file_path):
            registries[file_path.parent] = (label, document)
        else:
            documents.append((label, file_path, document))
            for message in consistency_errors(document):
                errors.append("%s: %s" % (label, message))

    for revision_dir, (_label, registry) in sorted(registries.items()):
        blocks = {
            path.stem
            for path in revision_dir.glob("*.json")
            if not is_registry(path)
        }
        for message in registry_errors(registry, blocks):
            errors.append("%s: %s" % (_label, message))

    for label, file_path, document in documents:
        registry_entry = registries.get(file_path.parent)
        registry = registry_entry[1] if registry_entry else None
        for message in table_errors(document, registry):
            errors.append("%s: %s" % (label, message))
    return len(files), errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="按 schema/ 校验 data/ 下的结构化 JSON")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="数据目录，默认 data/")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="schema 目录，默认 schema/")
    args = parser.parse_args(argv)

    count, errors = validate_data_dir(args.data, args.schema)
    if errors:
        for message in errors:
            print(message, file=sys.stderr)
        print("校验失败：%d 个数据文件，%d 处问题" % (count, len(errors)), file=sys.stderr)
        return 1
    print("校验通过：%d 个数据文件" % (count,))
    return 0


if __name__ == "__main__":
    sys.exit(main())
