"""数据加工转换业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.mockdata import parse_field_rules
from app.services.mock import MockService
from app.store import store

MODULE = "transform"
REQUIRED_FIELDS = ["规则编号", "输入格式", "输出格式"]
STATUS_ORDER = ["草稿", "生效中", "已暂停", "已关闭"]
ACTION_RULES = {"启用规则": "草稿", "暂停规则": "生效中", "关闭规则": "已暂停"}
NEGATIVE_ACTIONS = []

mock_service = MockService()


class TransformService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("规则编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"加工规则 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于数据加工转换可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"加工规则已{action}"

    # ------------------------------------------------------------------
    # 引用数据模拟服务的数据模板做加工转换：只读取模板的最新有效批次；
    # 格式或字段不匹配时拒绝转换，并把格式差异与字段差异说明白。
    # ------------------------------------------------------------------
    def convert_with_template(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        rule = store.find(MODULE, entry_id)
        if rule is None:
            return None, f"加工规则 {entry_id} 不存在或已归档"
        template = str(values.get("数据模板") or "").strip()
        config_no = str(values.get("配置编号") or "").strip()
        if not template and not config_no:
            return None, "请提供要引用的数据模板或配置编号"
        config = mock_service.find_config(template=template or None, config_no=config_no or None)
        if config is None:
            return None, f"未找到数据模板「{template or config_no}」对应的模拟配置，请先在数据模拟服务登记"
        template = str(config.get("数据模板", ""))
        batch = mock_service.latest_valid_batch(str(config.get("配置编号", "")), template)
        if batch is None:
            return None, f"数据模板「{template}」尚无有效批次，请先在数据模拟服务生成模拟数据"

        rule_format = str(rule.get("输入格式") or "").strip().upper()
        template_format = str(config.get("模板格式") or batch.get("模板格式") or "").strip().upper()
        template_fields = [name for name, _ in parse_field_rules(config.get("字段规则", ""))]
        wanted_fields = _split_fields(rule.get("字段过滤"))
        format_diff = ""
        if rule_format and template_format and rule_format != template_format:
            format_diff = f"格式不一致：规则输入格式 {rule_format}，模板格式 {template_format}"
        missing = [field for field in wanted_fields if field not in template_fields]
        if format_diff or missing:
            diffs = [format_diff] if format_diff else []
            if missing:
                diffs.append(
                    f"缺失字段：{'、'.join(missing)}（模板字段：{'、'.join(template_fields) or '无'}）"
                )
            unmapped = [field for field in template_fields if field not in wanted_fields]
            if unmapped:
                diffs.append(f"模板未映射字段：{'、'.join(unmapped)}")
            reason = "格式不匹配" if format_diff else "字段不匹配"
            return None, f"{reason}，已拒绝转换；" + "；".join(diffs)

        mappings = _parse_mappings(rule.get("映射表达式"))
        fields = wanted_fields or template_fields
        records = batch.get("records") or []
        converted: list[dict[str, Any]] = []
        for record in records:
            item: dict[str, Any] = {}
            for field in fields:
                if field in record:
                    item[mappings.get(field, field)] = record[field]
            converted.append(item)
        output_format = str(rule.get("输出格式") or "JSON").strip().upper()
        preview = _render_output(converted, output_format, fields, mappings)

        log_line = (
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 引用模板「{template}」"
            f"批次 {batch.get('批次编号', '')} 转换 {len(converted)} 条"
        )
        old_log = str(rule.get("转换日志") or "").strip()
        rule["转换日志"] = log_line if old_log in ("", "暂无") else f"{old_log}；{log_line}"

        return {
            "规则编号": rule.get("规则编号", ""),
            "配置编号": config.get("配置编号", ""),
            "数据模板": template,
            "批次编号": batch.get("批次编号", ""),
            "输入格式": rule_format,
            "输出格式": output_format,
            "转换条数": len(converted),
            "转换样例": converted[:3],
            "输出预览": preview,
        }, f"转换完成：引用模板「{template}」批次 {batch.get('批次编号', '')}，共 {len(converted)} 条"


def _split_fields(raw: Any) -> list[str]:
    text = str(raw or "").replace("，", ",")
    return [chunk.strip() for chunk in text.split(",") if chunk.strip()]


def _parse_mappings(raw: Any) -> dict[str, str]:
    """把「user_id->uid,user_name->name」解析成 {源字段: 目标字段}。"""
    mappings: dict[str, str] = {}
    for chunk in _split_fields(raw):
        if "->" in chunk:
            source, _, target = chunk.partition("->")
            source, target = source.strip(), target.strip()
            if source and target:
                mappings[source] = target
    return mappings


def _render_output(records: list[dict[str, Any]], output_format: str, fields: list[str], mappings: dict[str, str]) -> str:
    headers = [mappings.get(field, field) for field in fields]
    if output_format == "CSV":
        lines = [",".join(headers)]
        for record in records:
            lines.append(",".join(str(record.get(head, "")) for head in headers))
        return "\n".join(lines)
    if output_format == "XML":
        lines = ["<records>"]
        for record in records:
            body = "".join(f"<{head}>{record.get(head, '')}</{head}>" for head in headers)
            lines.append(f"  <record>{body}</record>")
        lines.append("</records>")
        return "\n".join(lines)
    return json.dumps(records, ensure_ascii=False)
