"""模板渲染辅助：时间/列名格式化（服务端与本地同机，可换算本地时区）。"""
from datetime import datetime
from typing import Any


def ts(value: Any) -> str:
    """时间值 → 本地化 'YYYY-MM-DD HH:MM:SS'；空值返回 '-';用于 <time> 类单元格。"""
    if value is None:
        return "-"
    if isinstance(value, datetime):
        try:
            value = value.astimezone()
        except (ValueError, OSError):
            pass
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def ts_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def is_time_column(name: str) -> bool:
    return name.endswith("_at") or name in ("occurred_at", "received_at", "created_at", "updated_at", "local_date") or name.endswith("_date")


COLUMN_LABELS = {
    "task_id": "任务", "attempt_id": "尝试", "event_id": "事件", "meal_id": "餐食",
    "release_id": "版本", "invocation_id": "调用", "result_id": "结果",
    "capture_session_id": "采集会话", "image_id": "图片", "item_id": "条目",
    "status": "状态", "trace_id": "Trace", "event_type": "事件类型", "task_type_code": "任务类型",
    "release_version": "版本号", "requester_service": "来源服务", "service": "服务",
    "aggregate_id": "聚合 ID", "aggregate_type": "聚合类型", "subject_id": "用户",
    "failure_code": "错误码", "failure_message": "失败信息", "last_error": "最后错误",
    "analysis_status": "分析状态", "capture_status": "采集状态", "task_status": "任务状态",
    "meal_type": "餐次", "notes": "备注", "display_name": "名称",
    "payload_sha256": "载荷哈希", "schema_version": "Schema", "attempt_no": "第几次",
    "published_at": "发布时间", "processed_at": "处理时间", "received_at": "接收时间",
    "created_at": "创建时间", "updated_at": "更新时间", "started_at": "开始", "finished_at": "结束",
    "completed_at": "完成", "next_attempt_at": "下次重试", "retention_until": "保留至",
    "destination_key": "目标 topic", "partition_key": "分区键", "producer": "生产者",
    "source_service": "来源服务", "attempt_count": "尝试数", "lock_version": "锁版本",
    "duration_ms": "耗时(ms)", "timeout_ms": "超时(ms)", "deadline_at": "截止",
    "promoted_at": "提升时间", "retired_at": "退役时间", "tools": "绑定工具",
    "priority": "优先级", "scheduled_at": "计划时间", "workflow_version": "Workflow 版本",
    "dify_workflow_id": "Workflow ID", "dify_app_id": "App ID", "dify_workspace_id": "Workspace",
    "confirmed_images": "确认图片", "input_schema_sha256": "入参哈希", "output_schema_sha256": "出参哈希",
    "outcome": "结果", "action": "操作", "actor": "操作者", "reason": "原因",
    "occurred_at": "发生时间", "operation_id": "操作 ID", "target": "对象", "matched": "命中方式",
    "client_request_id": "客户端请求", "bucket": "存储桶", "object_key": "对象键",
    "content_type": "类型", "content_length": "大小", "slot_no": "槽位", "expires_at": "过期",
    "overall_status": "总状态", "analysis_requested_at": "请求分析", "failed_at": "失败时间",
    "user_id": "用户 ID", "timezone": "时区", "local_date": "日期", "consumed_at": "食用时间",
    "entry_source": "来源", "deleted_at": "删除时间", "source": "来源", "id": "ID", "count": "数量",
    "refusal": "拒绝原因", "state": "状态", "confidence": "置信度",
}


def column_label(name: str) -> str:
    return COLUMN_LABELS.get(name, name)


def badge_class(status: str) -> str:
    """状态值 → 徽章语义色（前端亦有一套映射兜底）。"""
    value = (status or "").lower()
    ok_words = ("succeeded", "processed", "published", "completed", "active", "ok", "healthy", "confirmed", "success", "ready")
    warn_words = ("pending", "queued", "publishing", "processing", "analysing", "running", "ready_for_analysis", "warn")
    err_words = ("failed", "timed_out", "expired", "cancelled", "denied", "error", "bad", "stale", "paused")
    if value in ok_words or value.startswith("nutrition.analysis.completed"):
        return "b-ok"
    if value in err_words or value in ("timed_out",) or value.endswith("failed") or "fail" in value:
        return "b-err"
    if value in warn_words or value == "created" or value == "uploading":
        return "b-warn"
    return "b-info"
