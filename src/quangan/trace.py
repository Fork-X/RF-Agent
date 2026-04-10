"""
Trace writer for Agent execution logging.

Writes structured JSONL records for each Agent.run() invocation,
enabling post-hoc debugging and performance analysis.

- One file per day: trace-YYYY-MM-DD.jsonl
- Append-only writes; safe for concurrent sessions
- Failures are silently swallowed to never break the main flow
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class TraceConfig:
    """Trace 行为配置。"""

    enabled: bool = True
    """是否启用 Trace 记录。设为 False 则所有 log() 调用静默跳过。"""

    log_llm_request: bool = True
    """是否记录 llm_request 事件（发给 LLM 的完整 Prompt）。"""

    log_llm_response: bool = True
    """是否记录 llm_response 事件（LLM 返回的完整响应）。"""

    log_tool_result: bool = True
    """是否记录 tool_result 事件（工具执行的完整结果）。"""

    include_full_messages: bool = True
    """llm_request 中是否包含完整消息内容。设为 False 则只记录消息元信息（角色、长度）。"""


class TraceWriter:
    """Lightweight JSONL trace logger for Agent runs."""

    def __init__(self, trace_dir: Path, config: TraceConfig | None = None) -> None:
        """
        Initialise the writer.

        Args:
            trace_dir: Directory where trace files are stored.
                       Created automatically if it does not exist.
            config:    Trace 行为配置。为 None 时使用默认配置（全量记录）。
        """
        self._trace_dir = trace_dir
        self._trace_dir.mkdir(parents=True, exist_ok=True)
        self._file: Path | None = None
        self._config = config or TraceConfig()
        self._trace_id: str = ""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_trace(self) -> str:
        """
        Begin a new trace session (called once per Agent.run()).

        Resolves the trace file for today so that subsequent `log()`
        calls append to the correct file.

        Returns:
            trace_id for this run, format: YYYYMMDD-HHMMSS-xxxx
        """
        today = datetime.now().strftime("%Y-%m-%d")
        self._file = self._trace_dir / f"trace-{today}.jsonl"
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._trace_id = f"{ts}-{uuid.uuid4().hex[:4]}"
        return self._trace_id

    def log(self, event_type: str, data: dict) -> None:
        """
        Append a single JSONL record to the current trace file.

        Each record contains:
        - ts:   ISO-8601 timestamp (second precision)
        - type: caller-defined event label (e.g. llm_request)
        - ...data fields spread into the record

        Args:
            event_type: Short label describing the event.
            data:       Arbitrary payload merged into the record.
        """
        if self._file is None or not self._config.enabled:
            # start_trace() was never called or tracing disabled; silently skip
            return

        # 按事件类型过滤
        if event_type == "llm_request" and not self._config.log_llm_request:
            return
        if event_type == "llm_response" and not self._config.log_llm_response:
            return
        if event_type == "tool_result" and not self._config.log_tool_result:
            return

        # 如果配置了摘要模式，对 llm_request 中的 messages 进行精简
        if event_type == "llm_request" and not self._config.include_full_messages:
            data = self._summarize_messages(data)

        try:
            record = {
                "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "trace_id": self._trace_id,
                "type": event_type,
                **data,
            }
            line = json.dumps(record, ensure_ascii=False)
            with self._file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:  # noqa: BLE001
            # Never let tracing break the main flow
            pass

    def _summarize_messages(self, data: dict) -> dict:
        """将 messages 精简为元信息（角色 + 长度），减少日志体积。"""
        messages = data.get("messages", [])
        summarized = []
        for msg in messages:
            content = msg.get("content", "")
            length = len(content) if isinstance(content, str) else len(json.dumps(content))
            summarized.append({
                "role": msg.get("role", "unknown"),
                "length": length,
            })
        return {**data, "messages": summarized}
