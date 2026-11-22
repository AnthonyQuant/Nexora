"""Orchestrates end-to-end workflow execution, CSV batch iteration, logging, and exports."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import json
from pathlib import Path
import re
import threading
import time
from typing import Any

import config
from actions.base_action import BaseAction
from core.action_executor import ActionExecutor, ApprovalCallback
from core.browser_manager import BrowserManager
from core.selector_manager import SelectorManager
from models.execution_record import ExecutionRecord, StepExecutionResult
from models.workflow import Workflow
from models.workflow_step import WorkflowStep
from storage.csv_manager import CSVManager
from storage.log_manager import LogManager, StepExecutionLog, WorkflowRunRecord

StepStartCallback = Callable[[WorkflowStep, int, int, int], None]
StepCompleteCallback = Callable[[StepExecutionResult, int, int], None]
RowCompleteCallback = Callable[[int, int, bool], None]
LogCallback = Callable[[str, str], None]

_PLACEHOLDER_TOKEN_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")


def _map_run_status_for_log(record_status: str) -> str:
    """Normalize `ExecutionRecord.status` labels into `WorkflowRunRecord.status` values."""
    normalized = (record_status or "").strip().lower()
    if normalized in ("success", "completed"):
        return "completed"
    if normalized == "partial":
        return "partial"
    if normalized == "stopped":
        return "stopped"
    return "failed"


def _map_step_status_for_log(step_status: str) -> str:
    """Normalize `StepExecutionResult.status` labels into `StepExecutionLog.status` values."""
    normalized = (step_status or "").strip().lower()
    if normalized == "success":
        return "success"
    if normalized == "skipped":
        return "skipped"
    return "failed"


def _stringify_extracted(payload: Any) -> str:
    """Convert extracted step data into a compact string for `StepExecutionLog.output_value`."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(payload)


class WorkflowEngine:
    """Coordinates browser lifecycle, pre-flight validation, step dispatch, and batch runs."""

    def __init__(
        self,
        browser_manager: BrowserManager | None = None,
        log_manager: LogManager | None = None,
        csv_manager: CSVManager | None = None,
        approval_callback: ApprovalCallback | None = None,
        capture_screenshot_on_failure: bool = True,
    ) -> None:
        self.browser_manager: BrowserManager = browser_manager or BrowserManager()
        self.log_manager: LogManager = log_manager or LogManager()
        self.csv_manager: CSVManager = csv_manager or CSVManager()
        self.approval_callback: ApprovalCallback | None = approval_callback
        self.capture_screenshot_on_failure: bool = bool(capture_screenshot_on_failure)

        self._stop_event: threading.Event = threading.Event()
        self._is_running: bool = False
        self._state_lock: threading.Lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        """Return True while a workflow execution is actively in progress."""
        with self._state_lock:
            return self._is_running

    def stop(self) -> None:
        """Signal cooperative cancellation to an active workflow execution."""
        self._stop_event.set()

    def reset_stop_signal(self) -> None:
        """Clear any prior cancellation flag before starting a new run."""
        self._stop_event.clear()

    def validate_workflow(
        self,
        workflow: Workflow,
        csv_headers: Sequence[str] | None = None,
    ) -> list[str]:
        """Run static pre-flight checks on workflow steps, selectors, and CSV column bindings."""
        errors: list[str] = []

        if not workflow.steps:
            errors.append(f"Workflow '{workflow.name}' has no steps configured.")
            return errors

        selector_issues = SelectorManager.validate_workflow_selectors(workflow)
        for issue in selector_issues:
            errors.append(
                f"Step {issue['step_index']} ({issue['step_name']}): {issue['message']}"
            )

        if csv_headers is not None:
            available = {h.strip() for h in csv_headers if h and h.strip()}
            for idx, step in enumerate(workflow.steps, start=1):
                col = step.csv_column.strip()
                if col and col not in available:
                    errors.append(
                        f"Step {idx} ({step.display_name}) references missing CSV column '{col}'."
                    )

                for raw_text in (step.input_value, step.selector_value, step.condition_target):
                    for token in _PLACEHOLDER_TOKEN_RE.findall(raw_text or ""):
                        if token not in available:
                            errors.append(
                                f"Step {idx} ({step.display_name}) uses placeholder '{{{{{token}}}}}' "
                                "which is not present in the CSV headers."
                            )

        return errors

    def _resolve_batch_dataset(
        self,
        workflow: Workflow,
        csv_path: Path | str | None = None,
        csv_rows: Sequence[Mapping[str, Any]] | None = None,
    ) -> tuple[list[str] | None, list[dict[str, Any]]]:
        """Determine the list of input row dictionaries for single-pass or CSV batch execution."""
        if csv_rows is not None:
            cleaned_rows = [dict(row) for row in csv_rows]
            headers: list[str] = []
            seen: set[str] = set()
            for row in cleaned_rows:
                for key in row.keys():
                    col = str(key).strip()
                    if col and col not in seen:
                        seen.add(col)
                        headers.append(col)
            return headers, (cleaned_rows if cleaned_rows else [{}])

        effective_csv = csv_path or getattr(workflow, "csv_path", "")
        if effective_csv and str(effective_csv).strip():
            headers, loaded_rows = self.csv_manager.load_csv(Path(str(effective_csv).strip()))
            if not loaded_rows:
                raise ValueError(f"Input CSV file '{effective_csv}' contains no data rows.")
            return headers, [dict(row) for row in loaded_rows]

        return None, [{}]

    @staticmethod
    def _emit_log(on_log: LogCallback | None, level: str, message: str) -> None:
        """Safely forward a log event to an optional UI callback."""
        if callable(on_log):
            try:
                on_log(level, message)
            except Exception:
                pass

    def _persist_run_log(
        self,
        record: ExecutionRecord,
        rows_processed: int,
        rows_succeeded: int,
        rows_failed: int,
        export_path: str = "",
    ) -> Path:
        """Translate `ExecutionRecord` into a `WorkflowRunRecord` and save it via `LogManager`."""
        step_logs: list[StepExecutionLog] = []
        failed_messages: list[str] = []

        for step_res in record.step_results:
            log_status = _map_step_status_for_log(step_res.status)
            is_error = log_status == "failed"
            if is_error and step_res.message:
                failed_messages.append(f"Step {step_res.step_index}: {step_res.message}")

            step_logs.append(
                StepExecutionLog(
                    step_index=step_res.step_index,
                    step_id=step_res.step_id,
                    action_type=step_res.action_type,
                    description=step_res.step_name or step_res.action_type,
                    status=log_status,
                    duration_ms=round(step_res.duration_ms),
                    output_value="" if is_error else _stringify_extracted(step_res.extracted_data),
                    error_message=step_res.message if is_error else "",
                    timestamp=step_res.timestamp,
                )
            )

        extracted_rows = record.collect_extracted_rows()
        run_record = WorkflowRunRecord(
            run_id=record.execution_id,
            workflow_id=record.workflow_id,
            workflow_name=record.workflow_name,
            status=_map_run_status_for_log(record.status),
            started_at=record.start_time,
            finished_at=record.end_time,
            duration_ms=round(record.duration_seconds * 1000.0),
            rows_processed=rows_processed,
            rows_succeeded=rows_succeeded,
            rows_failed=rows_failed,
            extracted_count=len(extracted_rows),
            export_path=export_path,
            error_summary="; ".join(failed_messages[:5]),
            step_logs=step_logs,
        )
        return self.log_manager.save_run(run_record)

    def run_workflow(
        self,
        workflow: Workflow,
        csv_path: Path | str | None = None,
        csv_rows: Sequence[Mapping[str, Any]] | None = None,
        browser_name: str | None = None,
        headless: bool | None = None,
        timeout: float | None = None,
        auto_export: bool = False,
        export_path: Path | str | None = None,
        persist_log: bool = True,
        stop_batch_on_row_error: bool = False,
        approval_callback: ApprovalCallback | None = None,
        auto_approve: bool = False,
        on_step_start: StepStartCallback | None = None,
        on_step_complete: StepCompleteCallback | None = None,
        on_row_complete: RowCompleteCallback | None = None,
        on_log: LogCallback | None = None,
    ) -> ExecutionRecord:
        """Execute a `Workflow` across single or CSV batch inputs and return an `ExecutionRecord`."""
        with self._state_lock:
            if self._is_running:
                raise RuntimeError("Another workflow execution is already in progress.")
            self._is_running = True

        self.reset_stop_signal()
        record = ExecutionRecord(
            workflow_id=workflow.workflow_id,
            workflow_name=workflow.name,
        )

        rows_processed = 0
        rows_succeeded = 0
        rows_failed = 0
        user_stopped = False
        saved_export_path = ""

        try:
            csv_headers, dataset_rows = self._resolve_batch_dataset(
                workflow=workflow,
                csv_path=csv_path,
                csv_rows=csv_rows,
            )
            validation_errors = self.validate_workflow(workflow, csv_headers=csv_headers)
            if validation_errors:
                raise ValueError("Pre-flight validation failed: " + " | ".join(validation_errors))

            total_rows = len(dataset_rows)
            record.batch_rows_processed = total_rows

            resolved_browser = (
                browser_name
                or getattr(workflow, "browser", "")
                or self.browser_manager.browser_name
            )
            resolved_headless = (
                self.browser_manager.headless if headless is None else bool(headless)
            )
            resolved_timeout = (
                float(timeout)
                if timeout is not None
                else float(getattr(workflow, "timeout", self.browser_manager.timeout))
            )

            self._emit_log(
                on_log,
                "INFO",
                f"Starting workflow '{workflow.name}' ({len(workflow.steps)} step(s), {total_rows} row(s)).",
            )
            driver = self.browser_manager.start_session(
                browser_name=resolved_browser,
                headless=resolved_headless,
                timeout=resolved_timeout,
            )

            effective_approval = approval_callback or self.approval_callback
            executor = ActionExecutor(
                browser_manager=self.browser_manager,
                approval_callback=effective_approval,
                capture_screenshot_on_failure=self.capture_screenshot_on_failure,
            )

            shared_variables: dict[str, Any] = {}
            first_step_opens_url = (
                bool(workflow.steps)
                and workflow.steps[0].action_type == config.ACTION_OPEN_URL
            )

            for row_idx, row_data in enumerate(dataset_rows, start=1):
                if self._stop_event.is_set():
                    user_stopped = True
                    self._emit_log(on_log, "WARNING", "Execution stopped by user before next row.")
                    break

                rows_processed += 1
                row_had_failure = False
                halt_entire_batch = False

                context: dict[str, Any] = {
                    "row_index": row_idx,
                    "total_rows": total_rows,
                    "row_data": dict(row_data),
                    "variables": shared_variables,
                    "downloads_dir": self.browser_manager.downloads_dir,
                    "default_url": workflow.target_url,
                    "stop_event": self._stop_event,
                    "auto_approve": auto_approve,
                    "approval_callback": effective_approval,
                }

                # Automatically open workflow.target_url if step 1 does not already issue open_url
                if workflow.target_url.strip() and not first_step_opens_url:
                    resolved_entry_url = BaseAction.resolve_placeholders(
                        workflow.target_url, context
                    ).strip()
                    if resolved_entry_url:
                        driver.get(resolved_entry_url)

                for step_idx, step in enumerate(workflow.steps, start=1):
                    if self._stop_event.is_set():
                        user_stopped = True
                        self._emit_log(
                            on_log,
                            "WARNING",
                            f"Execution stopped by user at row {row_idx}, step {step_idx}.",
                        )
                        halt_entire_batch = True
                        break

                    if callable(on_step_start):
                        try:
                            on_step_start(step, step_idx, row_idx, total_rows)
                        except Exception:
                            pass

                    dispatch = executor.execute_step(
                        driver=driver,
                        step=step,
                        step_index=step_idx,
                        row_index=row_idx,
                        context=context,
                    )
                    step_result = dispatch.record
                    record.record_step_result(step_result)

                    level = "ERROR" if step_result.is_failed else "INFO"
                    self._emit_log(
                        on_log,
                        level,
                        f"[Row {row_idx}/{total_rows} | Step {step_idx}] {step_result.message}",
                    )

                    if callable(on_step_complete):
                        try:
                            on_step_complete(step_result, row_idx, total_rows)
                        except Exception:
                            pass

                    if step_result.is_failed:
                        row_had_failure = True

                    if dispatch.should_stop:
                        if step_result.status == config.STEP_STATUS_REJECTED:
                            user_stopped = True
                            halt_entire_batch = True
                        elif stop_batch_on_row_error or total_rows == 1:
                            halt_entire_batch = True
                        break

                if row_had_failure:
                    rows_failed += 1
                else:
                    rows_succeeded += 1

                if callable(on_row_complete):
                    try:
                        on_row_complete(row_idx, total_rows, not row_had_failure)
                    except Exception:
                        pass

                if halt_entire_batch:
                    break

            record.finalize(stopped=user_stopped)

            extracted_rows = record.collect_extracted_rows()
            if (auto_export or export_path is not None) and extracted_rows:
                exported_file = self.csv_manager.export_run_results(
                    workflow_name=workflow.name,
                    records=extracted_rows,
                    destination_path=export_path,
                )
                saved_export_path = str(exported_file)
                record.notes = f"Exported {len(extracted_rows)} record(s) to {saved_export_path}"
                self._emit_log(on_log, "INFO", record.notes)

        except Exception as exc:
            record.finalize(stopped=user_stopped, notes=str(exc))
            self._emit_log(on_log, "ERROR", f"Workflow '{workflow.name}' aborted: {exc}")
            raise
        finally:
            self.browser_manager.close_session()
            if persist_log:
                try:
                    self._persist_run_log(
                        record=record,
                        rows_processed=rows_processed,
                        rows_succeeded=rows_succeeded,
                        rows_failed=rows_failed,
                        export_path=saved_export_path,
                    )
                except Exception:
                    pass
            with self._state_lock:
                self._is_running = False

        return record