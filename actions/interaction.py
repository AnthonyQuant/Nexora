"""Element interaction actions for clicking, text entry, and dropdown option selection."""

from __future__ import annotations

from typing import Any

from selenium.common.exceptions import ElementClickInterceptedException, WebDriverException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import Select

import config
from actions.base_action import ActionOutcome, BaseAction
from actions.waiting import WaitHandler
from core.selector_manager import SelectorManager
from models.workflow_step import WorkflowStep


def _inspect_match_warning(driver: WebDriver, strategy: str, selector_value: str) -> str:
    """Return a non-blocking warning if a selector matches multiple DOM elements."""
    try:
        matches = SelectorManager.find_elements(driver, strategy, selector_value)
        if len(matches) > 1:
            return (
                f"Selector [{strategy}: {selector_value}] matched {len(matches)} elements; "
                "interacting with the first match."
            )
    except (ValueError, WebDriverException):
        pass
    return ""


class ClickElementAction(BaseAction):
    """Waits for a target element to become clickable and triggers a click."""

    action_type: str = config.ACTION_CLICK_ELEMENT

    def perform(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        resolved: dict[str, str],
        context: dict[str, Any],
    ) -> ActionOutcome:
        selector_val = resolved["selector_value"].strip()
        if not selector_val:
            raise ValueError("Click Element action requires a non-empty selector value.")

        warning = _inspect_match_warning(driver, step.selector_strategy, selector_val)
        element = WaitHandler.wait_for_clickable(
            driver=driver,
            strategy=step.selector_strategy,
            value=selector_val,
            timeout=step.timeout,
        )

        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
                element,
            )
        except WebDriverException:
            pass

        force_js = bool(step.options.get("js_click", False))
        allow_js_fallback = bool(step.options.get("js_fallback", True))

        if force_js:
            driver.execute_script("arguments[0].click();", element)
            return ActionOutcome(
                success=True,
                message=f"Clicked [{step.selector_strategy}: {selector_val}] via JavaScript.",
                warning=warning,
            )

        try:
            element.click()
            return ActionOutcome(
                success=True,
                message=f"Clicked [{step.selector_strategy}: {selector_val}].",
                warning=warning,
            )
        except ElementClickInterceptedException:
            if not allow_js_fallback:
                raise
            driver.execute_script("arguments[0].click();", element)
            fallback_note = "Native click was intercepted; completed click via JavaScript fallback."
            combined_warning = f"{warning} {fallback_note}".strip() if warning else fallback_note
            return ActionOutcome(
                success=True,
                message=f"Clicked [{step.selector_strategy}: {selector_val}] (JS fallback).",
                warning=combined_warning,
            )


class EnterTextAction(BaseAction):
    """Waits for an input or textarea element, clears it if configured, and types text."""

    action_type: str = config.ACTION_ENTER_TEXT

    def perform(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        resolved: dict[str, str],
        context: dict[str, Any],
    ) -> ActionOutcome:
        selector_val = resolved["selector_value"].strip()
        if not selector_val:
            raise ValueError("Enter Text action requires a non-empty selector value.")

        text_value = resolved["input_value"]
        warning = _inspect_match_warning(driver, step.selector_strategy, selector_val)

        element = WaitHandler.wait_for_visible(
            driver=driver,
            strategy=step.selector_strategy,
            value=selector_val,
            timeout=step.timeout,
        )

        clear_first = bool(step.options.get("clear_first", True))
        if clear_first:
            element.clear()

        if text_value:
            element.send_keys(text_value)

        press_enter = bool(step.options.get("press_enter", False))
        if press_enter:
            element.send_keys(Keys.RETURN)

        mask_log = bool(step.options.get("mask_log", False))
        logged_preview = "********" if mask_log else repr(text_value)
        enter_suffix = " + Enter" if press_enter else ""

        return ActionOutcome(
            success=True,
            message=f"Entered {logged_preview}{enter_suffix} into [{step.selector_strategy}: {selector_val}].",
            warning=warning,
        )


class SelectOptionAction(BaseAction):
    """Selects an option inside an HTML `<select>` dropdown by visible text, value, or index."""

    action_type: str = config.ACTION_SELECT_OPTION

    def perform(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        resolved: dict[str, str],
        context: dict[str, Any],
    ) -> ActionOutcome:
        selector_val = resolved["selector_value"].strip()
        if not selector_val:
            raise ValueError("Select Option action requires a non-empty selector value.")

        option_target = resolved["input_value"].strip()
        if not option_target:
            raise ValueError("Select Option action requires a target option value.")

        select_mode = str(step.options.get("select_mode", config.DEFAULT_SELECT_MODE)).strip().lower()
        if select_mode not in config.SELECT_MODES:
            supported = ", ".join(config.SELECT_MODES)
            raise ValueError(f"Unsupported select mode '{select_mode}'. Choose from: {supported}.")

        warning = _inspect_match_warning(driver, step.selector_strategy, selector_val)
        element = WaitHandler.wait_for_visible(
            driver=driver,
            strategy=step.selector_strategy,
            value=selector_val,
            timeout=step.timeout,
        )

        dropdown = Select(element)
        if select_mode == "visible_text":
            dropdown.select_by_visible_text(option_target)
        elif select_mode == "value":
            dropdown.select_by_value(option_target)
        elif select_mode == "index":
            try:
                index_val = int(option_target)
            except ValueError as exc:
                raise ValueError(
                    f"Select mode 'index' requires a non-negative integer, got {option_target!r}."
                ) from exc
            if index_val < 0:
                raise ValueError("Select option index must be 0 or greater.")
            dropdown.select_by_index(index_val)

        return ActionOutcome(
            success=True,
            message=(
                f"Selected option {option_target!r} ({select_mode}) "
                f"in [{step.selector_strategy}: {selector_val}]."
            ),
            warning=warning,
        )