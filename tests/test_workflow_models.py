"""Unit tests for Nexora WorkflowStep, Workflow, and ExecutionRecord data models."""

from __future__ import annotations

import config
from models.execution_record import ExecutionRecord, StepExecutionResult
from models.workflow import Workflow
from models.workflow_step import WorkflowStep


def test_workflow_step_defaults_and_display_name() -> None:
    unnamed = WorkflowStep(action_type=config.ACTION_OPEN_URL, input_value="https://example.com")
    assert unnamed.step_id.startswith("step_")
    assert unnamed.display_name == "Open URL"
    assert unnamed.timeout == config.DEFAULT_TIMEOUT
    assert unnamed.max_retries == config.DEFAULT_MAX_RETRIES

    named = WorkflowStep(
        name="Navigate Home",
        action_type=config.ACTION_OPEN_URL,
        input_value="https://example.com",
    )
    assert named.display_name == "Navigate Home"


def test_workflow_step_dict_roundtrip_and_clone() -> None:
    original = WorkflowStep(
        name="Enter Client Email",
        action_type=config.ACTION_ENTER_TEXT,
        selector_strategy="id",
        selector_value="email-address",
        input_value="fallback@example.com",
        csv_column="email",
        output_key="entered_email",
        condition=config.CONDITION_IF_ELEMENT_EXISTS,
        condition_target="email-address",
        requires_approval=True,
        timeout=15.0,
        max_retries=3,
        options={"clear_first": True},
    )

    serialized = original.to_dict()
    restored = WorkflowStep.from_dict(serialized)

    assert restored.step_id == original.step_id
    assert restored.name == original.name
    assert restored.action_type == original.action_type
    assert restored.selector_strategy == "id"
    assert restored.selector_value == "email-address"
    assert restored.csv_column == "email"
    assert restored.output_key == "entered_email"
    assert restored.condition == config.CONDITION_IF_ELEMENT_EXISTS
    assert restored.requires_approval is True
    assert restored.timeout == 15.0
    assert restored.max_retries == 3
    assert restored.options == {"clear_first": True}

    cloned = original.clone()
    assert cloned.step_id != original.step_id
    assert cloned.name == original.name
    assert cloned.selector_value == original.selector_value
    assert cloned.options == original.options


def test_workflow_json_roundtrip_and_clone(sample_workflow: Workflow) -> None:
    raw_json = sample_workflow.to_json(indent=2)
    restored = Workflow.from_json(raw_json)

    assert restored.workflow_id == sample_workflow.workflow_id
    assert restored.name == sample_workflow.name
    assert restored.description == sample_workflow.description
    assert restored.target_url == sample_workflow.target_url
    assert len(restored.steps) == len(sample_workflow.steps)
    assert [s.step_id for s in restored.steps] == [s.step_id for s in sample_workflow.steps]

    cloned_wf = sample_workflow.clone(new_name="Cloned Intake Workflow", as_template=False)
    assert cloned_wf.workflow_id != sample_workflow.workflow_id
    assert cloned_wf.name == "Cloned Intake Workflow"
    assert cloned_wf.is_template is False
    assert len(cloned_wf.steps) == len(sample_workflow.steps)
    assert all(
        c.step_id != orig.step_id
        for c, orig in zip(cloned_wf.steps, sample_workflow.steps, strict=True)
    )


def test_execution_record_status_and_extraction_aggregation() -> None:
    record = ExecutionRecord(workflow_id="wf_demo_01", workflow_name="Demo Batch Run")
    record.batch_rows_processed = 2

    record.record_step_result(
        StepExecutionResult(
            step_index=1,
            step_id="s1",
            step_name="Extract Client 1",
            action_type=config.ACTION_EXTRACT_TEXT,
            status=config.STEP_STATUS_SUCCESS,
            duration_ms=35.0,
            attempts=1,
            row_index=1,
            message="Extracted client 1",
            extracted_data={"full_name": "Ada Lovelace", "status": "Verified"},
        )
    )
    record.record_step_result(
        StepExecutionResult(
            step_index=2,
            step_id="s2",
            step_name="Optional Promo Close",
            action_type=config.ACTION_CLICK_ELEMENT,
            status=config.STEP_STATUS_SKIPPED,
            duration_ms=0.0,
            attempts=0,
            row_index=1,
            message="Banner not present",
        )
    )
    record.finalize()

    assert record.status == config.RUN_STATUS_SUCCESS
    assert record.total_actions == 2
    assert record.successful_actions == 1
    assert record.skipped_actions == 1
    assert record.failed_actions == 0

    rows = record.collect_extracted_rows()
    assert len(rows) == 1
    assert rows[0]["full_name"] == "Ada Lovelace"


def test_execution_record_partial_and_failed_statuses() -> None:
    partial_rec = ExecutionRecord(workflow_id="wf_2", workflow_name="Partial Run")
    partial_rec.record_step_result(
        StepExecutionResult(
            step_index=1,
            step_id="s1",
            step_name="Step 1",
            action_type=config.ACTION_OPEN_URL,
            status=config.STEP_STATUS_SUCCESS,
            duration_ms=10.0,
            attempts=1,
            row_index=1,
            message="OK",
        )
    )
    partial_rec.record_step_result(
        StepExecutionResult(
            step_index=2,
            step_id="s2",
            step_name="Step 2",
            action_type=config.ACTION_CLICK_ELEMENT,
            status=config.STEP_STATUS_FAILED,
            duration_ms=50.0,
            attempts=2,
            row_index=1,
            message="Element not found",
        )
    )
    partial_rec.finalize()
    assert partial_rec.status == config.RUN_STATUS_PARTIAL

    failed_rec = ExecutionRecord(workflow_id="wf_3", workflow_name="Failed Run")
    failed_rec.record_step_result(
        StepExecutionResult(
            step_index=1,
            step_id="s1",
            step_name="Step 1",
            action_type=config.ACTION_OPEN_URL,
            status=config.STEP_STATUS_FAILED,
            duration_ms=15.0,
            attempts=1,
            row_index=1,
            message="Invalid URL",
        )
    )
    failed_rec.finalize()
    assert failed_rec.status == config.RUN_STATUS_FAILED