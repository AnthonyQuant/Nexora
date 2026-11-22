"""Abstract base class, placeholder resolver, and bounded retry logic for browser actions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import re
import threading
import time
from typing import Any

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    InvalidSelectorException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.remote.webdriver import WebDriver

import config
from models.workflow_step import WorkflowStep

_PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")

RECOVERABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    TimeoutException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
    ElementNotInteractableException,
    NoSuchElementException,
    WebDriverException,
)


@dataclass
class ActionOutcome:
    """Structured result returned by an action handler after execution and retries."""

    success: bool
    message: str
    extracted_data: Any = None
    attempts: int = 1
    duration_ms: float = 0.0
    warning: str = ""


class BaseAction(ABC):
    """Base contract for all reusable Nexora browser actions using OOP inheritance."""

    action_type: str = ""

    @staticmethod
    def clamp_retries(max_retries: int | None) -> int:
        """Bound retry attempts within `[config.MIN_RETRIES, config.MAX_RETRIES]`."""
        raw = config.DEFAULT_MAX_RETRIES if max_retries is None else int(max_retries)
        return max(config.MIN_RETRIES, min(raw, config.MAX_RETRIES))

    @staticmethod
    def resolve_placeholders(text: str, context: dict[str, Any] | None = None) -> str:
        """Substitute `{{column_name}}` tokens using `context['row_data']` or `context['variables']`."""
        if not text or "{{" not in text:
            return text

        ctx = context or {}
        row_data = ctx.get("row_data") if isinstance(ctx.get("row_data"), dict) else {}
        variables = ctx.get("variables") if isinstance(ctx.get("variables"), dict) else {}

        def _replace(match: re.Match[str]) -> str:
            key = match.group(1).strip()
            if key in row_data:
                return str(row_data[key])
            if key in variables:
                return str(variables[key])
            return match.group(0)

        return _PLACEHOLDER_PATTERN.sub(_replace, text)

    @classmethod
    def resolve_step_values(
        cls,
        step: WorkflowStep,
        context: dict[str, Any] | None = None,
    ) -> dict[str, str]:
        """Resolve dynamic CSV/variable values for a step's selector, input, and condition."""
        ctx = context or {}
        row_data = ctx.get("row_data") if isinstance(ctx.get("row_data"), dict) else {}

        resolved_selector = cls.resolve_placeholders(step.selector_value, ctx).strip()
        resolved_condition_target = cls.resolve_placeholders(step.condition_target, ctx).strip()

        csv_col = step.csv_column.strip()
        if csv_col and csv_col in row_data:
            resolved_input = str(row_data[csv_col])
        else:
            resolved_input = cls.resolve_placeholders(step.input_value, ctx)

        return {
            "selector_value": resolved_selector,
            "input_value": resolved_input,
            "condition_target": resolved_condition_target,
        }

    @staticmethod
    def _wait_backoff(seconds: float, context: dict[str, Any] | None = None) -> bool:
        """Sleep for `seconds` unless `context['stop_event']` signals interruption."""
        if seconds <= 0:
            return True
        stop_event = (context or {}).get("stop_event")
        if isinstance(stop_event, threading.Event):
            interrupted = stop_event.wait(timeout=seconds)
            return not interrupted
        time.sleep(seconds)
        return True

    @abstractmethod
    def perform(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        resolved: dict[str, str],
        context: dict[str, Any],
    ) -> ActionOutcome:
        """Execute a single attempt of the concrete browser action."""

    def execute(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        context: dict[str, Any] | None = None,
    ) -> ActionOutcome:
        """Run `perform()` with placeholder resolution, bounded retries, and timing."""
        ctx: dict[str, Any] = context if context is not None else {}
        resolved = self.resolve_step_values(step, ctx)
        max_retries = self.clamp_retries(step.max_retries)
        total_allowed_attempts = 1 + max_retries

        started = time.perf_counter()
        last_error_msg = ""

        for attempt in range(1, total_allowed_attempts + 1):
            stop_event = ctx.get("stop_event")
            if isinstance(stop_event, threading.Event) and stop_event.is_set():
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                return ActionOutcome(
                    success=False,
                    message="Action aborted because workflow execution was stopped.",
                    attempts=attempt,
                    duration_ms=elapsed_ms,
                )

            try:
                outcome = self.perform(driver, step, resolved, ctx)
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                outcome.attempts = attempt
                outcome.duration_ms = elapsed_ms
                if outcome.success:
                    return outcome
                last_error_msg = outcome.message or f"Action '{step.display_name}' reported failure."
            except (ValueError, InvalidSelectorException) as non_recoverable_exc:
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                return ActionOutcome(
                    success=False,
                    message=f"Configuration/selector error: {non_recoverable_exc}",
                    attempts=attempt,
                    duration_ms=elapsed_ms,
                )
            except RECOVERABLE_EXCEPTIONS as recoverable_exc:
                detail = getattr(recoverable_exc, "msg", None) or str(recoverable_exc)
                last_error_msg = detail.strip() or recoverable_exc.__class__.__name__
            except Exception as unexpected_exc:
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                return ActionOutcome(
                    success=False,
                    message=f"Unexpected error during '{step.display_name}': {unexpected_exc}",
                    attempts=attempt,
                    duration_ms=elapsed_ms,
                )

            if attempt < total_allowed_attempts:
                backoff = config.RETRY_BACKOFF_SECONDS * attempt
                if not self._wait_backoff(backoff, ctx):
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    return ActionOutcome(
                        success=False,
                        message="Action aborted during retry backoff.",
                        attempts=attempt,
                        duration_ms=elapsed_ms,
                    )

        elapsed_ms = (time.perf_counter() - started) * 1000.0
        suffix = (
            f" (failed after {total_allowed_attempts} attempt(s))"
            if total_allowed_attempts > 1
            else ""
        )
        return ActionOutcome(
            success=False,
            message=f"{last_error_msg}{suffix}",
            attempts=total_allowed_attempts,
            duration_ms=elapsed_ms,
        )