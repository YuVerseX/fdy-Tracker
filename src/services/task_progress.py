"""长任务进度上报辅助。"""
from typing import Any, Callable

ProgressCallback = Callable[[dict[str, Any]], None]
CancelCheck = Callable[[], bool]


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


def emit_progress(
    progress_callback: ProgressCallback | None,
    *,
    stage_key: str,
    stage_label: str,
    progress_mode: str,
    metrics: dict[str, Any] | None = None,
) -> None:
    """向调用方发送一条进度快照。"""
    if not progress_callback:
        return

    progress_callback({
        "stage_key": stage_key,
        "stage_label": stage_label,
        "progress_mode": progress_mode,
        "metrics": metrics or {},
    })
