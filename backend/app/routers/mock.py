"""数据模拟服务接口：维护模拟配置与模拟数据批次，覆盖启用模拟、暂停模拟、关闭模拟等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.mock import MockService

router = APIRouter(prefix="/api/mock", tags=["数据模拟服务"])

service = MockService()

LIST_FIELDS = ["配置编号", "模拟对象", "数据模板", "模板格式", "生成条数", "字段规则", "响应延迟", "错误概率", "配置状态"]
STATUSES = ["草稿", "生效中", "已暂停", "已关闭"]
BATCH_STATUSES = ["有效", "历史"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按配置编号检索"),
    config_no: str | None = Query(default=None, alias="配置编号", description="按配置编号过滤"),
    mock_object: str | None = Query(default=None, alias="模拟对象", description="按模拟对象过滤"),
    template: str | None = Query(default=None, alias="数据模板", description="按数据模板过滤"),
    status: str | None = Query(default=None, description="草稿、生效中、已暂停、已关闭"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按配置编号、模拟对象、数据模板与状态过滤模拟配置；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword or config_no,
        mock_object=mock_object,
        template=template,
        status=status,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/batches", response_model=PageResult[dict])
def list_batches(
    template: str | None = Query(default=None, alias="数据模板", description="按数据模板搜索批次"),
    mock_object: str | None = Query(default=None, alias="模拟对象", description="按模拟对象查询批次"),
    batch_no: str | None = Query(default=None, alias="批次编号", description="按批次编号定位批次"),
    config_no: str | None = Query(default=None, alias="配置编号", description="按配置编号过滤批次"),
    status: str | None = Query(default=None, alias="批次状态", description="有效、历史"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """模拟数据批次浏览：生成条数汇总与实际记录数一并返回，供核对一致性。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_batches(
        template=template,
        mock_object=mock_object,
        batch_no=batch_no,
        config_no=config_no,
        status=status,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/batches/{batch_no}", response_model=dict)
def get_batch(batch_no: str) -> dict:
    """批次明细：查看该批次的模拟数据记录与字段规则；不存在时给出可读说明。"""
    batch = service.get_batch(batch_no)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"模拟批次 {batch_no} 不存在或已清理")
    return batch


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出数据模拟服务清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "mock", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条模拟配置明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"模拟配置 {entry_id} 不存在或已归档")
    return entry


@router.get("/{entry_id}/response", response_model=dict)
def current_response(entry_id: int) -> dict:
    """当前模拟响应：只引用该配置最新有效批次的记录，历史批次不得混入。"""
    payload, message = service.current_response(entry_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=message)
    return payload


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条模拟配置，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="模拟配置已登记", entry=entry)


@router.post("/{entry_id}/generate", response_model=ActionResult)
def generate_batch(entry_id: int, payload: EntryPayload) -> ActionResult:
    """按配置的生成条数生成一个模拟数据批次；同配置同模板的旧有效批次自动转入历史。"""
    batch, message = service.generate_batch(entry_id, payload.values)
    if batch is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=service.batch_summary(batch))


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条模拟配置执行启用模拟、暂停模拟、关闭模拟；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
