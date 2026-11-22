"""Execution audit models for workflow runs and individual step results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import config


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _generate_execution_id() -> str:
    """Return a short unique identifier for a workflow execution run."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"exec_{stamp}_{uuid4().hex[:6]}"


def _parse_iso_timestamp(value: str) -> datetime | None:
    """Parse an ISO-8601 UTC timestamp string into an aware datetime object."""
    if not value:
        return None
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


@dataclass
class StepExecutionResult:
    """Captures the outcome, timing, extracted data, and diagnostics of one step."""

    step_index: int
    step_id: str = ""
    step_name: str = ""
    action_type: str = ""
    status: str = config.STEP_STATUS_SUCCESS
    duration_ms: float = 0.0
    attempts: int = 1
    row_index: int = 1
    message: str = ""
    extracted_data: Any = None
    screenshot_path: str = ""
    timestamp: str = field(default_factory=_utc_now_iso)

    @property
    def is_success(self) -> bool:
        """Return True when the step succeeded."""
        return self.status == config.STEP_STATUS_SUCCESS

    @property
    def is_failed(self) -> bool:
        """Return True when the step failed or was rejected at an approval gate."""
        return self.status in (config.STEP_STATUS_FAILED, config.STEP_STATUS_REJECTED)

    @property
    def is_skipped(self) -> bool:
        """Return True when the step was conditionally skipped."""
        return self.status == config.STEP_STATUS_SKIPPED

    def to_dict(self) -> dict[str, Any]:
        """Serialize step execution details into a dictionary."""
        return {
            "step_index": int(self.step_index),
            "step_id": self.step_id,
            "step_name": self.step_name,
            "action_type": self.action_type,
            "status": self.status,
            "duration_ms": round(float(self.duration_ms), 2),
            "attempts": int(self.attempts),
            "row_index": int(self.row_index),
            "message": self.message,
            "extracted_data": self.extracted_data,
            "screenshot_path": self.screenshot_path,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StepExecutionResult:
        """Deserialize a StepExecutionResult from a dictionary."""
        try:
            step_index = int(data.get("step_index", 0))
        except (TypeError, ValueError):
            step_index = 0

        try:
            duration_ms = float(data.get("duration_ms", 0.0))
        except (TypeError, ValueError):
            duration_ms = 0.0

        try:
            attempts = int(data.get("attempts", 1))
        except (TypeError, ValueError):
            attempts = 1

        try:
            row_index = int(data.get("row_index", 1))
        except (TypeError, ValueError):
            row_index = 1

        return cls(
            step_index=step_index,
            step_id=str(data.get("step_id", "")),
            step_name=str(data.get("step_name", "")),
            action_type=str(data.get("action_type", "")),
            status=str(data.get("status", config.STEP_STATUS_SUCCESS)),
            duration_ms=duration_ms,
            attempts=attempts,
            row_index=row_index,
            message=str(data.get("message", "")),
            extracted_data=data.get("extracted_data"),
            screenshot_path=str(data.get("screenshot_path", "")),
            timestamp=str(data.get("timestamp") or _utc_now_iso()),
        )


@dataclass
class ExecutionRecord:
    """Represents a complete workflow execution run and its step-level audit trail."""

    execution_id: str = field(default_factory=_generate_execution_id)
    workflow_id: str = ""
    workflow_name: str = "Untitled Workflow"
    start_time: str = field(default_factory=_utc_now_iso)
    end_time: str = ""
    total_actions: int = 0
    successful_actions: int = 0
    failed_actions: int = 0
    skipped_actions: int = 0
    status: str = config.RUN_STATUS_SUCCESS
    batch_rows_processed: int = 1
    notes: str = ""
    step_results: list[StepExecutionResult] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        """Calculate total run duration in seconds from start_time and end_time."""
        start_dt = _parse_iso_timestamp(self.start_time)
        end_dt = _parse_iso_timestamp(self.end_time) if self.end_time else datetime.now(timezone.utc)
        if start_dt is None or end_dt is None:
            return round(sum(item.duration_ms for item in self.step_results) / 1000.0, 3)
        elapsed = (end_dt - start_dt).total_seconds()
        return round(max(0.0, elapsed), 3)

    @property
    def success_rate(self) -> float:
        """Return percentage of successful actions among executed (non-skipped) actions."""
        executed = self.successful_actions + self.failed_actions
        if executed <= 0:
            return 100.0 if self.status == config.RUN_STATUS_SUCCESS else 0.0
        return round((self.successful_actions / executed) * 100.0, 2)

    def record_step_result(self, result: StepExecutionResult) -> None:
        """Append a step result and update aggregate action counters."""
        self.step_results.append(result)
        self.total_actions += 1
        if result.is_success:
            self.successful_actions += 1
        elif result.is_skipped:
            self.skipped_actions += 1
        else:
            self.failed_actions += 1

    def finalize(
        self,
        stopped: bool = False,
        end_time: str | None = None,
        notes: str | None = None,
    ) -> str:
        """Set end_time, compute final run status, and return the status label."""
        self.end_time = end_time or _utc_now_iso()
        if notes:
            self.notes = notes

        if stopped:
            self.status = config.RUN_STATUS_STOPPED
        elif self.failed_actions == 0:
            self.status = config.RUN_STATUS_SUCCESS
        elif self.successful_actions > 0:
            self.status = config.RUN_STATUS_PARTIAL
        else:
            self.status = config.RUN_STATUS_FAILED

        return self.status

    def collect_extracted_rows(self) -> list[dict[str, Any]]:
        """Flatten all extracted step payloads into tabular dictionaries for CSV export."""
        rows: list[dict[str, Any]] = []
        for item in self.step_results:
            if item.extracted_data is None:
                continue
            payload = item.extracted_data
            if isinstance(payload, list):
                for entry in payload:
                    if isinstance(entry, dict):
                        row = {"row_index": item.row_index, "step_name": item.step_name}
                        row.update(entry)
                        rows.append(row)
                    else:
                        rows.append(
                            {
                                "row_index": item.row_index,
                                "step_name": item.step_name,
                                "value": str(entry),
                            }
                        )
            elif isinstance(payload, dict):
                row = {"row_index": item.row_index, "step_name": item.step_name}
                row.update(payload)
                rows.append(row)
            else:
                rows.append(
                    {
                        "row_index": item.row_index,
                        "step_name": item.step_name,
                        "value": str(payload),
                    }
                )
        return rows

    def to_csv_row(self) -> dict[str, Any]:
        """Return a dictionary matching `config.EXECUTION_HISTORY_HEADERS`."""
        return {
            "execution_id": self.execution_id,
            "workflow_name": self.workflow_name,
            "start_time": self.start_time,
            "end_time": self.end_time or _utc_now_iso(),
            "total_actions": int(self.total_actions),
            "successful_actions": int(self.successful_actions),
            "failed_actions": int(self.failed_actions),
            "status": self.status,
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize the complete execution record and step trail into a dictionary."""
        return {
            "execution_id": self.execution_id,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_actions": int(self.total_actions),
            "successful_actions": int(self.successful_actions),
            "failed_actions": int(self.failed_actions),
            "skipped_actions": int(self.skipped_actions),
            "status": self.status,
            "batch_rows_processed": int(self.batch_rows_processed),
            "duration_seconds": self.duration_seconds,
            "notes": self.notes,
            "step_results": [step.to_dict() for step in self.step_results],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionRecord:
        """Deserialize an ExecutionRecord from a dictionary."""
        raw_steps = data.get("step_results")
        step_results: list[StepExecutionResult] = []
        if isinstance(raw_steps, list):
            for entry in raw_steps:
                if isinstance(entry, StepExecutionResult):
                    step_results.append(entry)
                elif isinstance(entry, dict):
                    step_results.append(StepExecutionResult.from_dict(entry))

        return cls(
            execution_id=str(data.get("execution_id") or _generate_execution_id()),
            workflow_id=str(data.get("workflow_id", "")),
            workflow_name=str(data.get("workflow_name", "Untitled Workflow")),
            start_time=str(data.get("start_time") or _utc_now_iso()),
            end_time=str(data.get("end_time", "")),
            total_actions=int(data.get("total_actions", 0)),
            successful_actions=int(data.get("successful_actions", 0)),
            failed_actions=int(data.get("failed_actions", 0)),
            skipped_actions=int(data.get("skipped_actions", 0)),
            status=str(data.get("status", config.RUN_STATUS_SUCCESS)),
            batch_rows_processed=int(data.get("batch_rows_processed", 1)),
            notes=str(data.get("notes", "")),
            step_results=step_results,
        )