"""Aggregates workflow run logs into KPI metrics, per-workflow breakdowns, and daily trends."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from storage.log_manager import LogManager, WorkflowRunRecord


def _parse_iso_date(timestamp_str: str) -> str:
    """Extract a `YYYY-MM-DD` UTC date string from an ISO-8601 timestamp."""
    cleaned = timestamp_str.strip()
    if not cleaned:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        normalized = cleaned.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return cleaned[:10]


class AnalyticsManager:
    """Computes dashboard KPIs, workflow summaries, step performance, and failure reports."""

    def __init__(self, log_manager: LogManager | None = None) -> None:
        self.log_manager: LogManager = log_manager if log_manager is not None else LogManager()

    def get_overview_metrics(self, workflow_id: str | None = None) -> dict[str, Any]:
        """Compute top-level KPI metrics across all runs or for a single workflow."""
        runs = self.log_manager.list_runs(workflow_id=workflow_id)
        total_runs = len(runs)
        if total_runs == 0:
            return {
                "total_runs": 0,
                "completed_runs": 0,
                "partial_runs": 0,
                "failed_runs": 0,
                "stopped_runs": 0,
                "success_rate": 0.0,
                "total_rows_processed": 0,
                "total_rows_succeeded": 0,
                "total_rows_failed": 0,
                "row_success_rate": 0.0,
                "total_extracted": 0,
                "avg_duration_ms": 0,
                "total_duration_ms": 0,
                "last_run_at": "",
            }

        completed_runs = sum(1 for r in runs if r.status.lower() == "completed")
        partial_runs = sum(1 for r in runs if r.status.lower() == "partial")
        failed_runs = sum(1 for r in runs if r.status.lower() == "failed")
        stopped_runs = sum(1 for r in runs if r.status.lower() == "stopped")

        total_rows_processed = sum(r.rows_processed for r in runs)
        total_rows_succeeded = sum(r.rows_succeeded for r in runs)
        total_rows_failed = sum(r.rows_failed for r in runs)
        total_extracted = sum(r.extracted_count for r in runs)
        total_duration_ms = sum(r.duration_ms for r in runs)

        success_rate = round((completed_runs / total_runs) * 100.0, 1)
        row_success_rate = (
            round((total_rows_succeeded / total_rows_processed) * 100.0, 1)
            if total_rows_processed > 0
            else 0.0
        )
        avg_duration_ms = round(total_duration_ms / total_runs)

        return {
            "total_runs": total_runs,
            "completed_runs": completed_runs,
            "partial_runs": partial_runs,
            "failed_runs": failed_runs,
            "stopped_runs": stopped_runs,
            "success_rate": success_rate,
            "total_rows_processed": total_rows_processed,
            "total_rows_succeeded": total_rows_succeeded,
            "total_rows_failed": total_rows_failed,
            "row_success_rate": row_success_rate,
            "total_extracted": total_extracted,
            "avg_duration_ms": avg_duration_ms,
            "total_duration_ms": total_duration_ms,
            "last_run_at": runs[0].started_at,
        }

    def get_workflow_breakdown(self) -> list[dict[str, Any]]:
        """Group execution history by workflow and return per-workflow metrics."""
        runs = self.log_manager.list_runs()
        grouped: dict[str, list[WorkflowRunRecord]] = {}

        for record in runs:
            key = record.workflow_id.strip() or record.workflow_name.strip() or "unknown"
            grouped.setdefault(key, []).append(record)

        summaries: list[dict[str, Any]] = []
        for wf_key, wf_runs in grouped.items():
            wf_runs.sort(key=lambda r: r.started_at, reverse=True)
            latest = wf_runs[0]
            total = len(wf_runs)
            completed = sum(1 for r in wf_runs if r.status.lower() == "completed")
            failed = sum(1 for r in wf_runs if r.status.lower() == "failed")
            total_rows = sum(r.rows_processed for r in wf_runs)
            total_extracted = sum(r.extracted_count for r in wf_runs)
            avg_duration = round(sum(r.duration_ms for r in wf_runs) / total)
            success_rate = round((completed / total) * 100.0, 1)

            summaries.append(
                {
                    "workflow_id": latest.workflow_id or wf_key,
                    "workflow_name": latest.workflow_name,
                    "total_runs": total,
                    "completed_runs": completed,
                    "failed_runs": failed,
                    "success_rate": success_rate,
                    "total_rows_processed": total_rows,
                    "total_extracted": total_extracted,
                    "avg_duration_ms": avg_duration,
                    "last_run_at": latest.started_at,
                    "last_status": latest.status,
                }
            )

        summaries.sort(key=lambda item: item["last_run_at"], reverse=True)
        return summaries

    def get_daily_activity(
        self,
        days: int = 7,
        workflow_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return chronological daily run and row counts over the past `days` UTC days."""
        window = max(1, days)
        today_utc = datetime.now(timezone.utc).date()
        start_date = today_utc - timedelta(days=window - 1)

        buckets: dict[str, dict[str, Any]] = {}
        for offset in range(window):
            day_str = (start_date + timedelta(days=offset)).isoformat()
            buckets[day_str] = {
                "date": day_str,
                "total_runs": 0,
                "completed_runs": 0,
                "failed_runs": 0,
                "rows_processed": 0,
                "extracted_count": 0,
            }

        for record in self.log_manager.list_runs(workflow_id=workflow_id):
            day_key = _parse_iso_date(record.started_at)
            if day_key not in buckets:
                continue
            bucket = buckets[day_key]
            bucket["total_runs"] += 1
            status_lower = record.status.lower()
            if status_lower == "completed":
                bucket["completed_runs"] += 1
            elif status_lower == "failed":
                bucket["failed_runs"] += 1
            bucket["rows_processed"] += record.rows_processed
            bucket["extracted_count"] += record.extracted_count

        return list(buckets.values())

    def get_action_type_stats(self, workflow_id: str | None = None) -> list[dict[str, Any]]:
        """Aggregate step-level success rates and average durations by `action_type`."""
        runs = self.log_manager.list_runs(workflow_id=workflow_id)
        stats_map: dict[str, dict[str, Any]] = {}

        for record in runs:
            for step in record.step_logs:
                action = step.action_type.strip() or "unknown"
                entry = stats_map.setdefault(
                    action,
                    {
                        "action_type": action,
                        "total_executions": 0,
                        "succeeded": 0,
                        "failed": 0,
                        "skipped": 0,
                        "total_duration_ms": 0,
                    },
                )
                entry["total_executions"] += 1
                entry["total_duration_ms"] += step.duration_ms
                step_status = step.status.lower()
                if step_status == "success":
                    entry["succeeded"] += 1
                elif step_status == "failed":
                    entry["failed"] += 1
                elif step_status == "skipped":
                    entry["skipped"] += 1

        results: list[dict[str, Any]] = []
        for entry in stats_map.values():
            total = entry["total_executions"]
            success_rate = round((entry["succeeded"] / total) * 100.0, 1) if total > 0 else 0.0
            avg_duration = round(entry["total_duration_ms"] / total) if total > 0 else 0
            results.append(
                {
                    "action_type": entry["action_type"],
                    "total_executions": total,
                    "succeeded": entry["succeeded"],
                    "failed": entry["failed"],
                    "skipped": entry["skipped"],
                    "success_rate": success_rate,
                    "avg_duration_ms": avg_duration,
                }
            )

        results.sort(key=lambda item: item["total_executions"], reverse=True)
        return results

    def get_recent_failures(
        self,
        limit: int = 10,
        workflow_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return recent failed or partial runs along with their failing step details."""
        runs = self.log_manager.list_runs(workflow_id=workflow_id)
        failures: list[dict[str, Any]] = []

        for record in runs:
            if record.status.lower() not in {"failed", "partial"}:
                continue

            failed_steps = [
                {
                    "step_index": step.step_index,
                    "action_type": step.action_type,
                    "description": step.description,
                    "error_message": step.error_message,
                }
                for step in record.step_logs
                if step.status.lower() == "failed"
            ]

            failures.append(
                {
                    "run_id": record.run_id,
                    "workflow_id": record.workflow_id,
                    "workflow_name": record.workflow_name,
                    "status": record.status,
                    "started_at": record.started_at,
                    "error_summary": record.error_summary,
                    "failed_steps": failed_steps,
                }
            )
            if len(failures) >= max(0, limit):
                break

        return failures