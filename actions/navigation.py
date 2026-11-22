"""Browser navigation, history traversal, and viewport scrolling actions."""

from __future__ import annotations

from typing import Any

from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver

import config
from actions.base_action import ActionOutcome, BaseAction
from actions.waiting import WaitHandler
from models.workflow_step import WorkflowStep

_ALLOWED_URL_SCHEMES: tuple[str, ...] = ("http://", "https://", "file://")


class OpenUrlAction(BaseAction):
    """Navigates the active browser window to a target URL and waits for page readiness."""

    action_type: str = config.ACTION_OPEN_URL

    def perform(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        resolved: dict[str, str],
        context: dict[str, Any],
    ) -> ActionOutcome:
        target_url = resolved["input_value"].strip()
        if not target_url:
            fallback = str(context.get("default_url", "")).strip()
            target_url = self.resolve_placeholders(fallback, context).strip()

        if not target_url:
            raise ValueError("Open URL action requires a non-empty URL.")

        if not target_url.lower().startswith(_ALLOWED_URL_SCHEMES):
            raise ValueError(
                f"Invalid URL {target_url!r}. URL must start with http://, https://, or file://."
            )

        driver.get(target_url)
        WaitHandler.wait_for_page_ready(driver, timeout=step.timeout)

        try:
            page_title = driver.title.strip()
        except WebDriverException:
            page_title = ""

        title_suffix = f" ({page_title!r})" if page_title else ""
        return ActionOutcome(
            success=True,
            message=f"Opened {target_url}{title_suffix}.",
        )


class NavigateBackAction(BaseAction):
    """Navigates one step backward in browser session history."""

    action_type: str = config.ACTION_NAVIGATE_BACK

    def perform(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        resolved: dict[str, str],
        context: dict[str, Any],
    ) -> ActionOutcome:
        driver.back()
        WaitHandler.wait_for_page_ready(driver, timeout=step.timeout)
        try:
            current = driver.current_url
        except WebDriverException:
            current = "previous page"
        return ActionOutcome(
            success=True,
            message=f"Navigated back to {current}.",
        )


class NavigateForwardAction(BaseAction):
    """Navigates one step forward in browser session history."""

    action_type: str = config.ACTION_NAVIGATE_FORWARD

    def perform(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        resolved: dict[str, str],
        context: dict[str, Any],
    ) -> ActionOutcome:
        driver.forward()
        WaitHandler.wait_for_page_ready(driver, timeout=step.timeout)
        try:
            current = driver.current_url
        except WebDriverException:
            current = "next page"
        return ActionOutcome(
            success=True,
            message=f"Navigated forward to {current}.",
        )


class ScrollAction(BaseAction):
    """Scrolls the viewport to top, bottom, a vertical pixel offset, or a target element."""

    action_type: str = config.ACTION_SCROLL

    def perform(
        self,
        driver: WebDriver,
        step: WorkflowStep,
        resolved: dict[str, str],
        context: dict[str, Any],
    ) -> ActionOutcome:
        mode = str(step.options.get("scroll_mode", config.DEFAULT_SCROLL_MODE)).strip().lower()

        if mode == "bottom":
            driver.execute_script("window.scrollTo({top: document.body.scrollHeight, behavior: 'instant'});")
            return ActionOutcome(success=True, message="Scrolled to bottom of page.")

        if mode == "top":
            driver.execute_script("window.scrollTo({top: 0, behavior: 'instant'});")
            return ActionOutcome(success=True, message="Scrolled to top of page.")

        if mode == "by_pixels":
            raw_pixels = resolved["input_value"].strip() or "500"
            try:
                offset = int(raw_pixels)
            except ValueError as exc:
                raise ValueError(
                    f"Scroll 'by_pixels' requires an integer offset, got {raw_pixels!r}."
                ) from exc
            driver.execute_script("window.scrollBy(0, arguments[0]);", offset)
            return ActionOutcome(success=True, message=f"Scrolled vertically by {offset}px.")

        if mode == "to_element":
            selector_val = resolved["selector_value"].strip()
            if not selector_val:
                raise ValueError("Scroll 'to_element' requires a non-empty selector value.")
            element = WaitHandler.wait_for_present(
                driver=driver,
                strategy=step.selector_strategy,
                value=selector_val,
                timeout=step.timeout,
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center', behavior: 'instant'});",
                element,
            )
            return ActionOutcome(
                success=True,
                message=f"Scrolled to element [{step.selector_strategy}: {selector_val}].",
            )

        supported = ", ".join(config.SCROLL_MODES)
        raise ValueError(f"Unsupported scroll mode '{mode}'. Choose from: {supported}.")