"""Unit and integration tests for SelectorManager, ActionExecutor, WorkflowEngine, and presets."""

from __future__ import annotations

import csv
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import config
from actions.base_action import BaseAction
from core.action_executor import ActionExecutor
from core.selector_manager import SelectorManager
from core.workflow_engine import WorkflowEngine
from models.workflow import Workflow
from models.workflow_step import WorkflowStep
from storage.csv_manager import CSVManager
from storage.log_manager import LogManager
from workflows import get_preset_sample_csv, get_preset_workflow, list_presets


def _make_mock_browser_manager(mock_webdriver: MagicMock) -> MagicMock:
    """Create a mocked BrowserManager that yields `mock_webdriver` across session helpers."""
    mock_element = MagicMock()
    mock_element.is_displayed.return_value = True
    mock_element.is_enabled.return_value = True
    mock_element.text = "Registered NX-2026"
    mock_element.get_attribute.return_value = "https://example.com/resource"

    mock_webdriver.find_element.return_value = mock_element
    mock_webdriver.find_elements.return_value = [mock_element]

    bm = MagicMock()
    bm.driver = mock_webdriver
    bm.start_session.return_value = mock_webdriver
    bm.get_driver.return_value = mock_webdriver
    bm.launch_browser.return_value = mock_webdriver
    bm.create_driver.return_value = mock_webdriver
    bm.capture_screenshot.return_value = ""
    return bm


def test_selector_manager_syntax_validation() -> None:
    ok_css, _ = SelectorManager.validate_selector_syntax("css", "#submit-btn.primary")
    assert ok_css is True

    ok_xpath, _ = SelectorManager.validate_selector_syntax("xpath", "//button[@id='submit-btn']")
    assert ok_xpath is True

    bad_strategy, msg_strategy = SelectorManager.validate_selector_syntax("invalid_strat", "#id")
    assert bad_strategy is False
    assert msg_strategy

    bad_empty, msg_empty = SelectorManager.validate_selector_syntax("id", "   ")
    assert bad_empty is False
    assert msg_empty


def test_placeholder_interpolation() -> None:
    context = {
        "row_data": {"full_name": "Katherine Johnson", "department": "Research"},
        "variables": {"ticket_id": "NX-900"},
    }
    template = "Client {{full_name}} ({{department}}) -> Ticket {{ticket_id}}"
    resolved = BaseAction.resolve_placeholders(template, context)
    assert resolved == "Client Katherine Johnson (Research) -> Ticket NX-900"


def test_action_executor_condition_skip_and_approval_gate(
    mock_webdriver: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(SelectorManager, "element_exists", lambda *_args, **_kwargs: False)

    executor = ActionExecutor(capture_screenshot_on_failure=False)

    # 1. Step with skip_if_missing should be skipped cleanly when element is absent
    conditional_step = WorkflowStep(
        name="Dismiss Cookie Banner",
        action_type=config.ACTION_CLICK_ELEMENT,
        selector_strategy="id",
        selector_value="cookie-accept",
        condition=config.CONDITION_SKIP_IF_MISSING,
        condition_target="cookie-accept",
    )
    skip_outcome = executor.execute_step(
        driver=mock_webdriver,
        step=conditional_step,
        step_index=1,
        row_index=1,
        context={},
    )
    assert skip_outcome.record.status == config.STEP_STATUS_SKIPPED
    assert skip_outcome.should_stop is False

    # 2. Step with requires_approval should halt when rejected by callback
    gated_step = WorkflowStep(
        name="Submit Payment",
        action_type=config.ACTION_CLICK_ELEMENT,
        selector_strategy="id",
        selector_value="pay-now",
        requires_approval=True,
    )
    reject_outcome = executor.execute_step(
        driver=mock_webdriver,
        step=gated_step,
        step_index=2,
        row_index=1,
        context={"approval_callback": lambda *_args: False},
    )
    assert reject_outcome.record.status == config.STEP_STATUS_REJECTED
    assert reject_outcome.should_stop is True


def test_workflow_engine_single_pass_execution(
    sample_workflow: Workflow,
    mock_webdriver: MagicMock,
    log_manager: LogManager,
    csv_manager: CSVManager,
) -> None:
    bm = _make_mock_browser_manager(mock_webdriver)
    engine = WorkflowEngine(
        browser_manager=bm,
        log_manager=log_manager,
        csv_manager=csv_manager,
    )

    events: list[str] = []
    record = engine.run_workflow(
        workflow=sample_workflow,
        browser_name="chrome",
        headless=True,
        auto_export=True,
        on_step_start=lambda step, idx, _r, _t: events.append(f"start:{idx}:{step.display_name}"),
        on_step_complete=lambda res, _r, _t: events.append(f"done:{res.step_index}:{res.status}"),
    )

    assert record.status == config.RUN_STATUS_SUCCESS
    assert record.batch_rows_processed == 1
    assert record.successful_actions == len(sample_workflow.steps)
    assert record.failed_actions == 0
    assert len(events) == len(sample_workflow.steps) * 2
    assert len(log_manager.list_runs()) == 1
    assert len(csv_manager.list_exports()) == 1


def test_workflow_engine_csv_batch_execution(
    sample_workflow: Workflow,
    mock_webdriver: MagicMock,
    log_manager: LogManager,
    csv_manager: CSVManager,
    tmp_path: Path,
) -> None:
    batch_csv = tmp_path / "batch_clients.csv"
    with batch_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["full_name"])
        writer.writeheader()
        writer.writerow({"full_name": "Margaret Hamilton"})
        writer.writerow({"full_name": "Dorothy Vaughan"})
        writer.writerow({"full_name": "Mary Jackson"})

    bm = _make_mock_browser_manager(mock_webdriver)
    engine = WorkflowEngine(
        browser_manager=bm,
        log_manager=log_manager,
        csv_manager=csv_manager,
    )

    record = engine.run_workflow(
        workflow=sample_workflow,
        csv_path=batch_csv,
        browser_name="chrome",
        headless=True,
        auto_export=True,
    )

    assert record.status == config.RUN_STATUS_SUCCESS
    assert record.batch_rows_processed == 3
    assert record.successful_actions == 3 * len(sample_workflow.steps)
    extracted = record.collect_extracted_rows()
    assert len(extracted) == 3


def test_workflow_engine_cooperative_stop(
    sample_workflow: Workflow,
    mock_webdriver: MagicMock,
    log_manager: LogManager,
    csv_manager: CSVManager,
) -> None:
    bm = _make_mock_browser_manager(mock_webdriver)
    engine = WorkflowEngine(
        browser_manager=bm,
        log_manager=log_manager,
        csv_manager=csv_manager,
    )

    def _stop_after_first_step(_res, _row_idx: int, _total_rows: int) -> None:
        engine.stop()

    record = engine.run_workflow(
        workflow=sample_workflow,
        headless=True,
        on_step_complete=_stop_after_first_step,
    )

    assert record.status == config.RUN_STATUS_STOPPED
    assert record.total_actions < len(sample_workflow.steps)


def test_all_builtin_workflow_presets_validate() -> None:
    presets = list_presets()
    assert len(presets) == 5

    engine = WorkflowEngine()
    for item in presets:
        wf = get_preset_workflow(item["preset_id"])
        headers, rows = get_preset_sample_csv(item["preset_id"])
        errors = engine.validate_workflow(wf, csv_headers=headers if headers else None)
        assert not errors, f"Preset '{item['preset_id']}' failed validation: {errors}"
        if item["requires_csv"]:
            assert len(headers) > 0 and len(rows) > 0