"""模拟数据生成器：按字段规则生成确定性的模拟记录。

种子数据与运行期的批次生成共用这一套解析与生成逻辑，
保证「生成条数汇总」与「实际记录数」始终来自同一个出口。
"""
from __future__ import annotations

import hashlib
import random
from typing import Any

SUPPORTED_TYPES = {"string", "int", "integer", "long", "float", "double", "decimal", "bool", "boolean", "date"}


def parse_field_rules(rule_text: Any) -> list[tuple[str, str]]:
    """把「user_id:string,age:int」解析成 [(字段名, 类型)]；缺类型的片段按 string 处理。"""
    fields: list[tuple[str, str]] = []
    text = str(rule_text or "").replace("，", ",").replace("：", ":")
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, sep, ftype = chunk.partition(":")
        ftype = ftype.strip().lower() if sep else "string"
        if ftype not in SUPPORTED_TYPES:
            ftype = "string"
        fields.append((name.strip(), ftype))
    return fields


def generate_records(rule_text: Any, count: int, seed_key: str) -> list[dict[str, Any]]:
    """按字段规则生成 count 条记录；以 seed_key 保证同一批次重放结果一致。"""
    fields = parse_field_rules(rule_text)
    digest = hashlib.md5(str(seed_key).encode("utf-8")).hexdigest()
    rng = random.Random(int(digest[:8], 16))
    records: list[dict[str, Any]] = []
    for index in range(1, count + 1):
        record: dict[str, Any] = {}
        for name, ftype in fields:
            record[name] = _gen_value(name, ftype, index, rng)
        records.append(record)
    return records


def _gen_value(name: str, ftype: str, index: int, rng: random.Random) -> Any:
    if ftype in ("int", "integer", "long"):
        return rng.randint(1, 1000)
    if ftype in ("float", "double", "decimal"):
        return round(rng.uniform(1, 1000), 2)
    if ftype in ("bool", "boolean"):
        return rng.choice([True, False])
    if ftype == "date":
        return f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    return f"{name}_{index:04d}"
