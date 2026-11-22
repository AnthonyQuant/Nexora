"""Unit tests for Nexora JSON/CSV storage managers and AnalyticsManager aggregations."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import pytest

from models.workflow import Workflow
from storage.analytics_manager import AnalyticsManager
from storage.csv_manager import CSVManager
from storage.log_manager import LogManager, StepExecutionLog, WorkflowRunRecord
from storage.profile_manager import ProfileManager


def _build_sample_runs() -> list[WorkflowRunRecord]:
    """Create a deterministic set of completed, partial, and failed run records for today."""
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT10:00:00Z")
    later_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT11:30:00Z")

    run_1 = WorkflowRunRecord(
        run_id="run_analytics_01",
        workflow_id="wf_intake",
        workflow_name="Client Intake Flow",
        status="completed",
        started_at=today_iso,
        finished_at=today_iso,
        duration_ms=1200,
        rows_processed=3,
        rows_succeeded=3,
        rows_failed=0,
        extracted_count=3,
        step_logs=[
            StepExecutionLog(
                step_index=1,
                step_id="s1",
                action_type="open_url",
                description="Open Portal",
                status="success",
                duration_ms=400,
                output_value="Opened",
            ),
            StepExecutionLog(
                step_index=2,
                step_id="s2",
                action_type="click_element",
                description="Dismiss Optional Banner",
                status="skipped",
                duration_ms=0,
                output_value="Skipped",
            ),
            StepExecutionLog(
                step_index=3,
                step_id="s3",
                action_type="extract_text",
                description="Extract Receipt",
                status="success",
                duration_ms=800,
                output_value="NX-1001",
            ),
        ],
    )

    run_2 = WorkflowRunRecord(
        run_id="run_analytics_02",
        workflow_id="wf_intake",
        workflow_name="Client Intake Flow",
        status="partial",
        started_at=later_iso,
        finished_at=later_iso,
        duration_ms=1800,
        rows_processed=2,
        rows_succeeded=1,
        rows_failed=1,
        extracted_count=1,
        error_summary="Row 2 timed out waiting for confirmation badge",
        step_logs=[
            StepExecutionLog(
                step_index=1,
                step_id="s1",
                action_type="open_url",
                description="Open Portal",
                status="success",
                duration_ms=500,
                output_value="Opened",
            ),
            StepExecutionLog(
                step_index=2,
                step_id="s2",
                action_type="click_element",
                description="Submit Form",
                status="failed",
                duration_ms=1300,
                error_message="Element #submit-btn not clickable",
            ),
        ],
    )

    run_3 = WorkflowRunRecord(
        run_id="run_analytics_03",
        workflow_id="wf_scraper",
        workflow_name="Directory Table Scraper",
        status="failed",
        started_at=later_iso,
        finished_at=later_iso,
        duration_ms=900,
        rows_processed=1,
        rows_succeeded=0,
        rows_failed=1,
        extracted_count=0,
        error_summary="Target table #records-table missing",
        step_logs=[
            StepExecutionLog(
                step_index=1,
                step_id="s1",
                action_type="extract_table",
                description="Extract Client Table",
                status="failed",
                duration_ms=900,
                error_message="NoSuchElementException: #records-table",
            ),
        ],
    )

    return [run_1, run_2, run_3]


def test_profile_manager_crud_import_export(
    profile_manager: ProfileManager,
    sample_workflow: Workflow,
    tmp_path: Path,
) -> None:
    saved_path = profile_manager.save_workflow(sample_workflow)
    assert saved_path.exists()

    profiles = profile_manager.list_profiles()
    assert len(profiles) == 1
    assert profiles[0].workflow_id == sample_workflow.workflow_id

    by_name = profile_manager.get_workflow_by_name("sample intake automation")
    assert by_name is not None
    assert by_name.workflow_id == sample_workflow.workflow_id

    # Export and re-import with a fresh workflow ID
    export_dest = tmp_path / "exported_workflow.json"
    profile_manager.export_workflow(sample_workflow.workflow_id, export_dest)
    assert export_dest.exists()

    imported = profile_manager.import_workflow(export_dest, assign_new_id=True)
    assert imported.workflow_id != sample_workflow.workflow_id
    assert len(profile_manager.list_profiles()) == 2

    # Duplicate and delete
    dup = profile_manager.duplicate_workflow(sample_workflow.workflow_id, new_name="Duplicate Flow")
    assert len(profile_manager.list_profiles()) == 3
    assert profile_manager.delete_workflow(dup.workflow_id) is True
    assert len(profile_manager.list_profiles()) == 2


def test_profile_manager_seed_default_profiles(profile_manager: ProfileManager) -> None:
    if not profile_manager.sample_workflows_path.exists():
        pytest.skip("data/sample_workflows.json not found")

    seeded = profile_manager.seed_default_profiles(overwrite=True)
    assert len(seeded) >= 1
    for wf in seeded:
        assert wf.is_template is False
        assert wf.target_url.startswith("file:///")


def test_csv_manager_load_and_export(csv_manager: CSVManager, tmp_path: Path) -> None:
    source_csv = tmp_path / "clients.csv"
    with source_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["full_name", "email", "department"])
        writer.writeheader()
        writer.writerow(
            {"full_name": "Katherine Johnson", "email": "kj@orbital.org", "department": "Research"}
        )
        writer.writerow(
            {"full_name": "Dorothy Vaughan", "email": "dv@langley.gov", "department": "Operations"}
        )

    headers, rows = csv_manager.load_csv(source_csv)
    assert headers == ["full_name", "email", "department"]
    assert len(rows) == 2
    assert rows[0]["full_name"] == "Katherine Johnson"

    exported_path = csv_manager.export_run_results(
        workflow_name="Client Onboarding",
        records=[{"full_name": "Katherine Johnson", "receipt": "NX-2048"}],
    )
    assert exported_path.exists()
    assert exported_path in csv_manager.list_exports()


def test_log_manager_save_filter_and_delete(log_manager: LogManager) -> None:
    for run in _build_sample_runs():
        log_manager.save_run(run)

    all_runs = log_manager.list_runs()
    assert len(all_runs) == 3

    intake_runs = log_manager.list_runs(workflow_id="wf_intake")
    assert len(intake_runs) == 2

    log_manager.delete_run("run_analytics_03")
    assert len(log_manager.list_runs()) == 2


def test_analytics_manager_empty_state(log_manager: LogManager) -> None:
    analytics = AnalyticsManager(log_manager=log_manager)

    overview = analytics.get_overview_metrics()
    assert overview["total_runs"] == 0
    assert overview["success_rate"] == 0.0
    assert overview["row_success_rate"] == 0.0
    assert overview["last_run_at"] == ""

    assert analytics.get_workflow_breakdown() == []
    assert analytics.get_action_type_stats() == []
    assert analytics.get_recent_failures() == []

    daily = analytics.get_daily_activity(days=5)
    assert len(daily) == 5
    assert all(day["total_runs"] == 0 for day in daily)


def test_analytics_manager_aggregations_and_failure_reports(log_manager: LogManager) -> None:
    for run in _build_sample_runs():
        log_manager.save_run(run)

    analytics = AnalyticsManager(log_manager=log_manager)

    # 1. Overview KPI metrics
    overview = analytics.get_overview_metrics()
    assert overview["total_runs"] == 3
    assert overview["completed_runs"] == 1
    assert overview["partial_runs"] == 1
    assert overview["failed_runs"] == 1
    assert overview["success_rate"] == 33.3
    assert overview["total_rows_processed"] == 6
    assert overview["total_rows_succeeded"] == 4
    assert overview["total_rows_failed"] == 2
    assert overview["row_success_rate"] == 66.7
    assert overview["total_extracted"] == 4
    assert overview["total_duration_ms"] == 3900
    assert overview["avg_duration_ms"] == 1300

    # 2. Per-workflow breakdown
    breakdown = analytics.get_workflow_breakdown()
    assert len(breakdown) == 2
    by_wf = {item["workflow_id"]: item for item in breakdown}
    assert by_wf["wf_intake"]["total_runs"] == 2
    assert by_wf["wf_intake"]["completed_runs"] == 1
    assert by_wf["wf_intake"]["success_rate"] == 50.0
    assert by_wf["wf_scraper"]["failed_runs"] == 1

    # 3. Daily UTC activity window
    daily = analytics.get_daily_activity(days=3)
    assert len(daily) == 3
    today_bucket = daily[-1]
    assert today_bucket["total_runs"] == 3
    assert today_bucket["completed_runs"] == 1
    assert today_bucket["failed_runs"] == 1
    assert today_bucket["rows_processed"] == 6
    assert today_bucket["extracted_count"] == 4

    # 4. Action-type performance telemetry
    action_stats = analytics.get_action_type_stats()
    by_action = {item["action_type"]: item for item in action_stats}
    assert by_action["open_url"]["total_executions"] == 2
    assert by_action["open_url"]["succeeded"] == 2
    assert by_action["open_url"]["success_rate"] == 100.0
    assert by_action["click_element"]["skipped"] == 1
    assert by_action["click_element"]["failed"] == 1
    assert by_action["extract_table"]["failed"] == 1

    # 5. Recent failures & partial runs report
    failures = analytics.get_recent_failures(limit=5)
    assert len(failures) == 2
    assert all(f["status"] in {"failed", "partial"} for f in failures)
    assert all(len(f["failed_steps"]) == 1 for f in failures)