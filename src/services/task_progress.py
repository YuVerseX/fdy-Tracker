"""长任务进度上报辅助。"""
from typing import Any, Callable

ProgressCallback = Callable[[dict[str, Any]], None]


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
