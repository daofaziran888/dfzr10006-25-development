"""数据模拟服务业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.mockdata import generate_records, parse_field_rules
from app.store import store

MODULE = "mock"
BATCH_MODULE = "mock_batch"
REQUIRED_FIELDS = ["配置编号", "模拟对象", "数据模板"]
OPTIONAL_FIELDS = ["模板格式", "生成条数", "字段规则", "响应延迟", "错误概率", "配置状态"]
STATUS_ORDER = ["草稿", "生效中", "已暂停", "已关闭"]
ACTION_RULES = {"启用模拟": "草稿", "暂停模拟": "生效中", "关闭模拟": "已暂停"}
NEGATIVE_ACTIONS = []
BATCH_CURRENT = "有效"
BATCH_HISTORY = "历史"
MAX_BATCH_COUNT = 1000


class MockService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        mock_object: str | None = None,
        template: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("配置编号", ""))]
        if mock_object:
            rows = [row for row in rows if mock_object in str(row.get("模拟对象", ""))]
        if template:
            rows = [row for row in rows if template in str(row.get("数据模板", ""))]
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
        for field in OPTIONAL_FIELDS:
            if values.get(field) not in (None, ""):
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"模拟配置 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于数据模拟服务可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"模拟配置已{action}"

    # ------------------------------------------------------------------
    # 模拟数据批次：一次生成动作产生一个批次，归属（配置编号 + 数据模板）。
    # 同一配置同一模板只保留一个有效批次；重新生成时旧批次转为历史保留，
    # 但当前模拟响应只引用最新有效批次，历史批次不得混入。
    # ------------------------------------------------------------------
    def _batch_rows(self) -> list[dict[str, Any]]:
        return store.rows(BATCH_MODULE)

    def find_config(self, *, template: str | None = None, config_no: str | None = None) -> dict[str, Any] | None:
        """按数据模板或配置编号定位模拟配置，供批次浏览与加工转换引用。"""
        for row in store.rows(MODULE):
            if config_no and str(row.get("配置编号", "")) != config_no:
                continue
            if template and str(row.get("数据模板", "")) != template:
                continue
            return row
        return None

    def generate_batch(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """按配置的生成条数产出一个新批次，并把同配置同模板的旧有效批次转入历史。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"模拟配置 {entry_id} 不存在或已归档"
        template = str(entry.get("数据模板") or "").strip()
        if not template:
            return None, "模拟配置缺少数据模板，无法生成模拟数据批次"
        raw_count = values.get("生成条数") or entry.get("生成条数")
        try:
            count = int(str(raw_count).strip())
        except (TypeError, ValueError):
            return None, f"生成条数「{raw_count}」不是正整数，请先在模拟配置中维护生成条数"
        if count <= 0:
            return None, f"生成条数「{count}」必须大于 0"
        if count > MAX_BATCH_COUNT:
            return None, f"单次生成条数不能超过 {MAX_BATCH_COUNT}，请分批生成"

        config_no = str(entry.get("配置编号", ""))
        batches = self._batch_rows()
        for batch in batches:
            if (
                batch.get("配置编号") == config_no
                and batch.get("数据模板") == template
                and batch.get("批次状态") == BATCH_CURRENT
            ):
                batch["批次状态"] = BATCH_HISTORY
        seq = max((self._batch_seq(batch, config_no) for batch in batches), default=0) + 1
        batch_no = f"{config_no}-B{seq:03d}"
        records = generate_records(entry.get("字段规则", ""), count, batch_no)
        batch = {
            "id": max((int(row.get("id", 0)) for row in batches), default=0) + 1,
            "批次编号": batch_no,
            "配置编号": config_no,
            "模拟对象": entry.get("模拟对象", ""),
            "数据模板": template,
            "模板格式": entry.get("模板格式", ""),
            "生成条数": count,
            "实际条数": len(records),
            "字段规则": entry.get("字段规则", ""),
            "批次状态": BATCH_CURRENT,
            "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "records": records,
        }
        batches.append(batch)
        return batch, f"已生成批次 {batch_no}，计划 {count} 条、实际 {len(records)} 条"

    @staticmethod
    def _batch_seq(batch: dict[str, Any], config_no: str) -> int:
        batch_no = str(batch.get("批次编号", ""))
        prefix = f"{config_no}-B"
        if not batch_no.startswith(prefix):
            return 0
        try:
            return int(batch_no[len(prefix):])
        except ValueError:
            return 0

    def list_batches(
        self,
        *,
        template: str | None = None,
        mock_object: str | None = None,
        batch_no: str | None = None,
        config_no: str | None = None,
        status: str | None = None,
        page: int = 1,
        size = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """批次浏览：支持按数据模板搜索、按模拟对象查询、按批次编号定位。"""
        rows = self._batch_rows()
        if template:
            rows = [row for row in rows if template in str(row.get("数据模板", ""))]
        if mock_object:
            rows = [row for row in rows if mock_object in str(row.get("模拟对象", ""))]
        if batch_no:
            rows = [row for row in rows if batch_no in str(row.get("批次编号", ""))]
        if config_no:
            rows = [row for row in rows if config_no in str(row.get("配置编号", ""))]
        if status:
            rows = [row for row in rows if row.get("批次状态") == status]
        rows = sorted(rows, key=lambda row: int(row.get("id", 0)), reverse=True)
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self.batch_summary(row) for row in rows[start:start + size]], total

    def batch_summary(self, batch: dict[str, Any]) -> dict[str, Any]:
        """批次汇总：生成条数必须与实际记录数一致，并把一致性标记一并返回。"""
        actual = len(batch.get("records") or [])
        planned = int(batch.get("生成条数", 0))
        return {
            key: value for key, value in batch.items() if key != "records"
        } | {"实际条数": actual, "汇总一致": planned == actual}

    def get_batch(self, batch_no: str) -> dict[str, Any] | None:
        """批次明细：汇总信息 + 字段规则解析 + 全量模拟记录。"""
        for batch in self._batch_rows():
            if str(batch.get("批次编号", "")) == batch_no:
                fields = [
                    {"字段名": name, "类型": ftype}
                    for name, ftype in parse_field_rules(batch.get("字段规则", ""))
                ]
                return self.batch_summary(batch) | {
                    "字段列表": fields,
                    "records": batch.get("records") or [],
                }
        return None

    def latest_valid_batch(self, config_no: str, template: str | None = None) -> dict[str, Any] | None:
        """取配置（可限定模板）的最新有效批次；历史批次不参与。"""
        candidates = [
            batch for batch in self._batch_rows()
            if batch.get("配置编号") == config_no
            and batch.get("批次状态") == BATCH_CURRENT
            and (template is None or batch.get("数据模板") == template)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda batch: int(batch.get("id", 0)))

    def current_response(self, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        """当前模拟响应：只引用最新有效批次的记录，旧批次数据不得混入。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"模拟配置 {entry_id} 不存在或已归档"
        config_no = str(entry.get("配置编号", ""))
        batch = self.latest_valid_batch(config_no, str(entry.get("数据模板", "")))
        if batch is None:
            return None, f"模拟配置 {config_no} 尚无有效批次，请先生成模拟数据"
        records = batch.get("records") or []
        return {
            "配置编号": config_no,
            "模拟对象": entry.get("模拟对象", ""),
            "数据模板": batch.get("数据模板", ""),
            "模板格式": batch.get("模板格式", ""),
            "批次编号": batch.get("批次编号", ""),
            "批次状态": batch.get("批次状态", ""),
            "生成时间": batch.get("生成时间", ""),
            "记录数": len(records),
            "records": records,
        }, "当前模拟响应已取到最新有效批次"
