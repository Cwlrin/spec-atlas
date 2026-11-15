"""最小 JSON Schema 校验器：只实现本项目 schema 用到的关键字。

本机没有 jsonschema 依赖，这里按需实现一个子集，避免为了几个关键字引入第三方包。
支持的关键字见 SUPPORTED_KEYWORDS；schema 里出现未实现的关键字会直接报错，
不允许「写了但静默不生效」。

另有两层不在 schema 里的检查，因为它们跨字段或依赖目录布局：
- location_errors：spec / revision / block 必须与所在目录名、文件名一致；
- consistency_errors：地址不重复、覆盖范围不越界、handEdited 必须有 handEditNote。
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
    """当前只有一种数据：<spec>/rev-<x.y>/<block>.json -> register-block。"""
    parts = Path(data_file).relative_to(data_dir).parts
    if len(parts) != 3:
        raise ValueError(
            "位置不对：期望 <spec>/rev-<x.y>/<block>.json，实际是 %s" % ("/".join(parts),)
        )
    return Path(schema_dir) / REGISTER_SCHEMA


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
    if document.get("block") != Path(filename).stem:
        errors.append(
            "block 字段 %r 与文件名 %r 不一致" % (document.get("block"), filename)
        )
    return errors


def consistency_errors(document):
    """跨字段约束：这些不该靠 schema 的位置表达，也不该让构建静默吞掉。"""
    errors = []
    if document.get("handEdited") and not document.get("handEditNote"):
        errors.append("handEdited 为真时必须写 handEditNote，说明哪些字段是手改的")
    size = document.get("size", 0)
    seen = {}
    for index, byte in enumerate(document.get("bytes", [])):
        if not isinstance(byte, dict):
            continue
        address = byte.get("address")
        if address in seen:
            errors.append(
                "地址 %r 重复出现在 bytes[%d] 与 bytes[%d]" % (address, seen[address], index)
            )
        else:
            seen[address] = index
        if isinstance(address, int):
            end = address + byte.get("length", 1)
            if end > size:
                errors.append("bytes[%d] 覆盖到 %d，超出块大小 %d" % (index, end, size))
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
        if not schema_errors:
            for message in location_errors(document, file_path, data_path):
                errors.append("%s: %s" % (label, message))
            for message in consistency_errors(document):
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
