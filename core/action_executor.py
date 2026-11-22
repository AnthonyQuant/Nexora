"""Single-step execution dispatcher handling condition guards, approval gates, and failure captures."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time
from typing import TYPE_CHECKING, Any

from selenium.webdriver.remote.webdriver import WebDriver

import config
from actions.base_action import BaseAction
from core.selector_manager import SelectorManager
from models.execution_record import StepExecutionResult
from models.workflow_step import WorkflowStep

if TYPE_CHECKING:
    from core.browser_manager import BrowserManager

ApprovalCallback = Callable[[WorkflowStep, int, dict[str, Any]], bool]


@dataclass
class StepDispatchResult:
    """Pairs a recorded `StepExecutionResult` with a workflow halt directive."""

    record: StepExecutionResult
    should_stop: bool = False


class ActionExecutor:
    """Executes individual `WorkflowStep` items with pre-checks, approval gates, and diagnostics."""

    def __init__(
        self,
        browser_manager: BrowserManager | None = None,
        approval_callback: ApprovalCallback | None = None,
        capture_screenshot_on_failure: bool = True,
    ) -> None:
        self.browser_manager: BrowserManager | None = browser_manager
        self.approval_callback: ApprovalCallback | None = approval_callback
        self.capture_screenshot_on_failure: bool = bool(capture_screenshot_on_failure)

    @staticmethod
    def _allows_continue_on_error(step: WorkflowStep) -> bool:
        """Return True when a step is explicitly configured not to halt the workflow on error."""
        if bool(getattr(step, "continue_on_error", False)):
            return True
        if bool(step.options.get("continue_on_error", False)):
            return True
        on_error = str(getattr(step, "on_error", "stop")).strip().lower()
        return on_error == "continue"

    def _capture_failure_screenshot(
        self,
        driver: WebDriver | None,
        step_index: int,
        step: WorkflowStep,
    ) -> str:
        """Capture a failure screenshot via `BrowserManager` or fallback directly to `driver`."""
        if not self.capture_screenshot_on_failure:
            return ""

        label = f"step_{step_index}_{step.action_type or 'action'}"
        if self.browser_manager is not None:
            return self.browser_manager.capture_screenshot(label=label)

        if driver is not None:
            try:
                config.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
                stamp = time.strftime("%Y%m%d_%H%M%S")
                path = config.SCREENSHOTS_DIR / f"{label}_{stamp}.png"
                if driver.save_screenshot(str(path)) and path.exists():
                    return str(path)
            except Exception:
                return ""
        return ""

    def _evaluate_condition(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        step_index: int,
        row_index: int,
        context: dict[str, Any],
    ) -> StepDispatchResult | None:
        """Evaluate step execution conditions; return a `StepDispatchResult` if skipped or halted."""
        always_flag = getattr(config, "CONDITION_ALWAYS", "always")
        condition = (step.condition or always_flag).strip().lower()
        if not condition or condition == always_flag:
            return None

        raw_target = step.condition_target.strip() or step.selector_value.strip()
        resolved_target = BaseAction.resolve_placeholders(raw_target, context).strip()
        strategy = (
            str(step.options.get("condition_strategy", step.selector_strategy)).strip()
            or step.selector_strategy
        )

        if not resolved_target:
            msg = (
                f"Condition '{condition}' on step '{step.display_name}' requires a target selector, "
                "but none was provided."
            )
            screenshot = self._capture_failure_screenshot(driver, step_index, step)
            record = StepExecutionResult(
                step_index=step_index,
                step_id=step.step_id,
                step_name=step.display_name,
                action_type=step.action_type,
                status=config.STEP_STATUS_FAILED,
                duration_ms=0.0,
                attempts=1,
                row_index=row_index,
                message=msg,
                screenshot_path=screenshot,
            )
            return StepDispatchResult(record=record, should_stop=not self._allows_continue_on_error(step))

        exists = SelectorManager.element_exists(driver, strategy, resolved_target)

        if condition in (
            getattr(config, "CONDITION_IF_ELEMENT_EXISTS", "if_element_exists"),
            getattr(config, "CONDITION_SKIP_IF_MISSING", "skip_if_missing"),
        ):
            if not exists:
                record = StepExecutionResult(
                    step_index=step_index,
                    step_id=step.step_id,
                    step_name=step.display_name,
                    action_type=step.action_type,
                    status=config.STEP_STATUS_SKIPPED,
                    duration_ms=0.0,
                    attempts=0,
                    row_index=row_index,
                    message=(
                        f"Skipped '{step.display_name}': guard element [{strategy}: {resolved_target}] "
                        "was not present."
                    ),
                )
                return StepDispatchResult(record=record, should_stop=False)
            return None

        if condition == getattr(config, "CONDITION_STOP_IF_MISSING", "stop_if_missing"):
            if not exists:
                screenshot = self._capture_failure_screenshot(driver, step_index, step)
                record = StepExecutionResult(
                    step_index=step_index,
                    step_id=step.step_id,
                    step_name=step.display_name,
                    action_type=step.action_type,
                    status=config.STEP_STATUS_FAILED,
                    duration_ms=0.0,
                    attempts=1,
                    row_index=row_index,
                    message=(
                        f"Stopped workflow: required guard element [{strategy}: {resolved_target}] "
                        "was not found."
                    ),
                    screenshot_path=screenshot,
                )
                return StepDispatchResult(record=record, should_stop=True)
            return None

        return None

    def _check_approval_gate(
        self,
        step: WorkflowStep,
        step_index: int,
        row_index: int,
        context: dict[str, Any],
    ) -> StepDispatchResult | None:
        """Pause for human-in-the-loop confirmation when `step.requires_approval` is enabled."""
        if not step.requires_approval:
            return None

        if bool(context.get("auto_approve", False)):
            return None

        callback = context.get("approval_callback") or self.approval_callback
        approved = False
        if callable(callback):
            approved = bool(callback(step, row_index, context))

        if approved:
            return None

        record = StepExecutionResult(
            step_index=step_index,
            step_id=step.step_id,
            step_name=step.display_name,
            action_type=step.action_type,
            status=config.STEP_STATUS_REJECTED,
            duration_ms=0.0,
            attempts=0,
            row_index=row_index,
            message=f"Execution halted: step '{step.display_name}' was rejected at the approval gate.",
        )
        return StepDispatchResult(record=record, should_stop=True)

    def execute_step(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        step_index: int,
        row_index: int = 1,
        context: dict[str, Any] | None = None,
    ) -> StepDispatchResult:
        """Run condition checks, approval gates, and action execution for a single step."""
        ctx: dict[str, Any] = context if context is not None else {}

        condition_outcome = self._evaluate_condition(
            driver=driver,
            step=step,
            step_index=step_index,
            row_index=row_index,
            context=ctx,
        )
        if condition_outcome is not None:
            return condition_outcome

        approval_outcome = self._check_approval_gate(
            step=step,
            step_index=step_index,
            row_index=row_index,
            context=ctx,
        )
        if approval_outcome is not None:
            return approval_outcome

        started = time.perf_counter()
        try:
            from actions import get_action_handler

            handler = get_action_handler(step.action_type)
        except ValueError as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            screenshot = self._capture_failure_screenshot(driver, step_index, step)
            record = StepExecutionResult(
                step_index=step_index,
                step_id=step.step_id,
                step_name=step.display_name,
                action_type=step.action_type,
                status=config.STEP_STATUS_FAILED,
                duration_ms=elapsed_ms,
                attempts=1,
                row_index=row_index,
                message=str(exc),
                screenshot_path=screenshot,
            )
            return StepDispatchResult(
                record=record,
                should_stop=not self._allows_continue_on_error(step),
            )

        outcome = handler.execute(driver=driver, step=step, context=ctx)
        message = outcome.message
        if outcome.warning:
            message = f"{message} [Warning: {outcome.warning}]".strip()

        if outcome.success:
            record = StepExecutionResult(
                step_index=step_index,
                step_id=step.step_id,
                step_name=step.display_name,
                action_type=step.action_type,
                status=config.STEP_STATUS_SUCCESS,
                duration_ms=outcome.duration_ms,
                attempts=outcome.attempts,
                row_index=row_index,
                message=message,
                extracted_data=outcome.extracted_data,
            )
            return StepDispatchResult(record=record, should_stop=False)

        screenshot = self._capture_failure_screenshot(driver, step_index, step)
        record = StepExecutionResult(
            step_index=step_index,
            step_id=step.step_id,
            step_name=step.display_name,
            action_type=step.action_type,
            status=config.STEP_STATUS_FAILED,
            duration_ms=outcome.duration_ms,
            attempts=outcome.attempts,
            row_index=row_index,
            message=message,
            extracted_data=outcome.extracted_data,
            screenshot_path=screenshot,
        )
        return StepDispatchResult(
            record=record,
            should_stop=not self._allows_continue_on_error(step),
        )