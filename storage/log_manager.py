"""Execution run history and step-level audit log persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid

import config

_DEFAULT_LOGS_DIR: Path = getattr(
    config,
    "LOGS_DIR",
    getattr(config, "DATA_DIR", Path(__file__).resolve().parent.parent / "data") / "logs",
)


def _utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class StepExecutionLog:
    """Represents the execution outcome of a single workflow step."""

    step_index: int
    step_id: str = ""
    action_type: str = ""
    description: str = ""
    status: str = "success"  # "success" | "failed" | "skipped"
    duration_ms: int = 0
    output_value: str = ""
    error_message: str = ""
    timestamp: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the step log into a JSON-compatible dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StepExecutionLog:
        """Deserialize a dictionary into a `StepExecutionLog` instance."""
        return cls(
            step_index=int(data.get("step_index", 0)),
            step_id=str(data.get("step_id", "")),
            action_type=str(data.get("action_type", "")),
            description=str(data.get("description", "")),
            status=str(data.get("status", "success")),
            duration_ms=int(data.get("duration_ms", 0)),
            output_value=str(data.get("output_value", "")),
            error_message=str(data.get("error_message", "")),
            timestamp=str(data.get("timestamp", _utc_now_iso())),
        )


@dataclass
class WorkflowRunRecord:
    """Captures run metadata, row counts, and detailed step logs for one workflow execution."""

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    workflow_id: str = ""
    workflow_name: str = "Untitled Workflow"
    status: str = "completed"  # "completed" | "partial" | "failed" | "stopped"
    started_at: str = field(default_factory=_utc_now_iso)
    finished_at: str = field(default_factory=_utc_now_iso)
    duration_ms: int = 0
    rows_processed: int = 0
    rows_succeeded: int = 0
    rows_failed: int = 0
    extracted_count: int = 0
    export_path: str = ""
    error_summary: str = ""
    step_logs: list[StepExecutionLog] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entire run record into a dictionary."""
        payload = asdict(self)
        payload["step_logs"] = [log.to_dict() for log in self.step_logs]
        return payload

    def to_json(self, indent: int = 2) -> str:
        """Serialize the run record as a formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowRunRecord:
        """Deserialize a dictionary into a `WorkflowRunRecord` instance."""
        raw_logs = data.get("step_logs", [])
        parsed_logs = [
            StepExecutionLog.from_dict(item) for item in raw_logs if isinstance(item, dict)
        ]
        return cls(
            run_id=str(data.get("run_id") or uuid.uuid4().hex[:12]),
            workflow_id=str(data.get("workflow_id", "")),
            workflow_name=str(data.get("workflow_name", "Untitled Workflow")),
            status=str(data.get("status", "completed")),
            started_at=str(data.get("started_at", _utc_now_iso())),
            finished_at=str(data.get("finished_at", _utc_now_iso())),
            duration_ms=int(data.get("duration_ms", 0)),
            rows_processed=int(data.get("rows_processed", 0)),
            rows_succeeded=int(data.get("rows_succeeded", 0)),
            rows_failed=int(data.get("rows_failed", 0)),
            extracted_count=int(data.get("extracted_count", 0)),
            export_path=str(data.get("export_path", "")),
            error_summary=str(data.get("error_summary", "")),
            step_logs=parsed_logs,
        )

    @classmethod
    def from_json(cls, raw_text: str) -> WorkflowRunRecord:
        """Parse a JSON string into a `WorkflowRunRecord`."""
        data = json.loads(raw_text)
        if not isinstance(data, dict):
            raise ValueError("Workflow run record JSON must decode to an object.")
        return cls.from_dict(data)


class LogManager:
    """Persists, queries, filters, and prunes JSON workflow execution logs."""

    def __init__(
        self,
        logs_dir: Path | str | None = None,
        max_records: int = 250,
    ) -> None:
        self.logs_dir: Path = Path(logs_dir) if logs_dir else Path(_DEFAULT_LOGS_DIR)
        self.max_records: int = max(1, max_records)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _build_record_path(self, record: WorkflowRunRecord) -> Path:
        """Construct a timestamp-prefixed JSON filename for chronological sorting."""
        compact_ts = (
            record.started_at.replace("-", "")
            .replace(":", "")
            .replace("T", "_")
            .split("+")[0]
            .split("Z")[0]
        )
        safe_ts = "".join(ch for ch in compact_ts if ch.isalnum() or ch == "_") or "run"
        return self.logs_dir / f"{safe_ts}_{record.run_id}.json"

    def _find_record_file(self, run_id: str) -> Path | None:
        """Locate the JSON file corresponding to `run_id`."""
        if not self.logs_dir.exists():
            return None
        for file_path in self.logs_dir.glob("*.json"):
            if file_path.stem.endswith(f"_{run_id}") or file_path.stem == run_id:
                return file_path
        return None

    def save_run(self, record: WorkflowRunRecord) -> Path:
        """Save a `WorkflowRunRecord` to disk and prune oldest logs beyond `max_records`."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        existing = self._find_record_file(record.run_id)
        target = existing if existing is not None else self._build_record_path(record)
        target.write_text(record.to_json(indent=2), encoding="utf-8")
        self._prune_excess_records()
        return target

    def get_run(self, run_id: str) -> WorkflowRunRecord | None:
        """Retrieve a single execution record by `run_id`."""
        target = self._find_record_file(run_id)
        if target is None or not target.exists():
            return None
        try:
            return WorkflowRunRecord.from_json(target.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None

    def list_runs(
        self,
        workflow_id: str | None = None,
        status: str | None = None,
        limit: int | None = None,
    ) -> list[WorkflowRunRecord]:
        """Return saved run records sorted newest first, with optional filters."""
        if not self.logs_dir.exists():
            return []

        records: list[WorkflowRunRecord] = []
        target_wf = workflow_id.strip() if workflow_id else None
        target_status = status.strip().lower() if status else None

        for file_path in sorted(self.logs_dir.glob("*.json"), reverse=True):
            try:
                record = WorkflowRunRecord.from_json(file_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue

            if target_wf and record.workflow_id != target_wf:
                continue
            if target_status and record.status.lower() != target_status:
                continue

            records.append(record)
            if limit is not None and len(records) >= max(0, limit):
                break

        records.sort(key=lambda r: r.started_at, reverse=True)
        return records[: max(0, limit)] if limit is not None else records

    def get_recent_logs(self, limit: int = 20) -> list[WorkflowRunRecord]:
        """Convenience helper returning the most recent execution logs."""
        return self.list_runs(limit=limit)

    def delete_run(self, run_id: str) -> bool:
        """Delete a single execution log file by `run_id`. Returns True if removed."""
        target = self._find_record_file(run_id)
        if target and target.exists():
            target.unlink()
            return True
        return False

    def clear_logs(self, workflow_id: str | None = None) -> int:
        """Remove all log files (or only those matching `workflow_id`). Returns count deleted."""
        if not self.logs_dir.exists():
            return 0

        removed = 0
        target_wf = workflow_id.strip() if workflow_id else None

        for file_path in list(self.logs_dir.glob("*.json")):
            if target_wf is None:
                file_path.unlink(missing_ok=True)
                removed += 1
                continue

            try:
                record = WorkflowRunRecord.from_json(file_path.read_text(encoding="utf-8"))
                if record.workflow_id == target_wf:
                    file_path.unlink(missing_ok=True)
                    removed += 1
            except (OSError, ValueError, json.JSONDecodeError):
                continue

        return removed

    def _prune_excess_records(self) -> int:
        """Delete oldest JSON log files when total files exceed `max_records`."""
        files = sorted(self.logs_dir.glob("*.json"))
        excess = len(files) - self.max_records
        if excess <= 0:
            return 0

        removed = 0
        for stale_file in files[:excess]:
            stale_file.unlink(missing_ok=True)
            removed += 1
        return removed