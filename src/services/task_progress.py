"""长任务进度上报辅助。"""
from typing import Any, Callable

ProgressCallback = Callable[[dict[str, Any]], None]
CancelCheck = Callable[[], bool]
CANONICAL_STAGES = {"submitted", "collecting", "persisting", "finalizing"}
STAGE_KEY_CANONICAL_MAP = {
    "persist-posts": "persisting",
    "persist-attachments": "persisting",
    "write-groups": "persisting",
    "analyze-posts": "persisting",
    "extract-post-jobs": "persisting",
    "count-remaining": "finalizing",
    "backfill-ready": "finalizing",
    "write-complete": "finalizing",
    "no-pending-posts": "finalizing",
    "no-posts-in-range": "finalizing",
    "select-unchecked": "collecting",
    "select-recheck-range": "collecting",
    "start-backfill": "collecting",
    "start-recheck-range": "collecting",
    "load-candidates": "collecting",
    "group-candidates": "collecting",
    "compare-candidates": "collecting",
    "reset-marks": "collecting",
}


class TaskCancellationRequested(RuntimeError):
    """协作式取消：在安全检查点停止后续处理。"""

    def __init__(
        self,
        reason: str = "user_requested",
        *,
        result: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.result = dict(result or {})

def raise_if_cancel_requested(
    cancel_check: CancelCheck | None,
    *,
    on_cancel: Callable[[], None] | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    """在安全检查点检查是否已收到取消请求。"""
    if cancel_check and cancel_check():
        if on_cancel is not None:
            on_cancel()
        raise TaskCancellationRequested("user_requested", result=result)


def resolve_canonical_stage(stage: str | None = None, stage_key: str | None = None) -> str:
    """把运行时 stage / stage_key 收口成 canonical stage。"""
    normalized_stage = str(stage or "").strip().lower()
    normalized_stage_key = str(stage_key or "").strip().lower()

    if normalized_stage in CANONICAL_STAGES:
        return normalized_stage
    if normalized_stage_key in CANONICAL_STAGES:
        return normalized_stage_key

    for token in (normalized_stage_key, normalized_stage):
        if token in CANONICAL_STAGES:
            return token
        if token in STAGE_KEY_CANONICAL_MAP:
            return STAGE_KEY_CANONICAL_MAP[token]
        if token.startswith(("persist", "write", "save", "store")):
            return "persisting"
        if token.startswith(("count", "finish", "final", "cancel", "cleanup", "no-posts", "no-pending")):
            return "finalizing"
        if token.startswith((
            "select",
            "start",
            "load",
            "group",
            "compare",
            "collect",
            "crawl",
            "scrap",
            "fetch",
            "scan",
            "analy",
            "process",
            "reset",
        )):
            return "collecting"

    return "submitted" if not normalized_stage and not normalized_stage_key else "collecting"


def emit_progress(
    progress_callback: ProgressCallback | None,
    *,
    stage: str | None = None,
    stage_key: str,
    stage_label: str,
    progress_mode: str,
    metrics: dict[str, Any] | None = None,
) -> None:
    """向调用方发送一条进度快照。"""
    if not progress_callback:
        return

    progress_callback({
        "stage": resolve_canonical_stage(stage, stage_key),
        "stage_key": stage_key,
        "stage_label": stage_label,
        "progress_mode": progress_mode,
        "live_metrics": metrics or {},
        "metrics": metrics or {},
    })
