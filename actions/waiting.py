"""Condition-based Selenium waiting utilities with bounded maximum timeouts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import config
from core.selector_manager import SelectorManager

if TYPE_CHECKING:
    from models.workflow_step import WorkflowStep

_POLL_FREQUENCY: float = 0.25


def clamp_timeout(timeout: float | None, allow_short: bool = False) -> float:
    """Return a bounded timeout in seconds within Nexora's configured limits."""
    raw = config.DEFAULT_TIMEOUT if timeout is None else float(timeout)
    if allow_short:
        return max(0.1, min(raw, config.MAX_TIMEOUT))
    return max(config.MIN_TIMEOUT, min(raw, config.MAX_TIMEOUT))


class WaitHandler:
    """Provides explicit condition-based waits using WebDriverWait and expected_conditions."""

    @staticmethod
    def wait_for_present(
        driver: WebDriver,
        strategy: str,
        value: str,
        timeout: float | None = None,
    ) -> WebElement:
        """Wait until at least one matching element exists in the DOM."""
        bounded = clamp_timeout(timeout)
        locator = SelectorManager.to_by_locator(strategy, value)
        try:
            return WebDriverWait(driver, bounded, poll_frequency=_POLL_FREQUENCY).until(
                EC.presence_of_element_located(locator)
            )
        except TimeoutException as exc:
            raise TimeoutException(
                f"Timed out after {bounded:.1f}s waiting for element [{strategy}: {value}] to be present."
            ) from exc

    @staticmethod
    def wait_for_visible(
        driver: WebDriver,
        strategy: str,
        value: str,
        timeout: float | None = None,
    ) -> WebElement:
        """Wait until a matching element is present in the DOM and visible."""
        bounded = clamp_timeout(timeout)
        locator = SelectorManager.to_by_locator(strategy, value)
        try:
            return WebDriverWait(driver, bounded, poll_frequency=_POLL_FREQUENCY).until(
                EC.visibility_of_element_located(locator)
            )
        except TimeoutException as exc:
            raise TimeoutException(
                f"Timed out after {bounded:.1f}s waiting for element [{strategy}: {value}] to become visible."
            ) from exc

    @staticmethod
    def wait_for_clickable(
        driver: WebDriver,
        strategy: str,
        value: str,
        timeout: float | None = None,
    ) -> WebElement:
        """Wait until a matching element is visible and enabled for clicking."""
        bounded = clamp_timeout(timeout)
        locator = SelectorManager.to_by_locator(strategy, value)
        try:
            return WebDriverWait(driver, bounded, poll_frequency=_POLL_FREQUENCY).until(
                EC.element_to_be_clickable(locator)
            )
        except TimeoutException as exc:
            raise TimeoutException(
                f"Timed out after {bounded:.1f}s waiting for element [{strategy}: {value}] to become clickable."
            ) from exc

    @staticmethod
    def wait_for_invisible(
        driver: WebDriver,
        strategy: str,
        value: str,
        timeout: float | None = None,
    ) -> bool:
        """Wait until a matching element becomes hidden or detached from the DOM."""
        bounded = clamp_timeout(timeout)
        locator = SelectorManager.to_by_locator(strategy, value)
        try:
            result = WebDriverWait(driver, bounded, poll_frequency=_POLL_FREQUENCY).until(
                EC.invisibility_of_element_located(locator)
            )
            return bool(result)
        except TimeoutException as exc:
            raise TimeoutException(
                f"Timed out after {bounded:.1f}s waiting for element [{strategy}: {value}] to disappear."
            ) from exc

    @staticmethod
    def wait_for_text_present(
        driver: WebDriver,
        expected_text: str,
        strategy: str | None = None,
        value: str | None = None,
        timeout: float | None = None,
    ) -> bool:
        """Wait until `expected_text` appears in the target element or anywhere in `<body>`."""
        cleaned_text = (expected_text or "").strip()
        if not cleaned_text:
            raise ValueError("Wait condition 'text_present' requires non-empty target text.")

        bounded = clamp_timeout(timeout)
        if strategy and value and value.strip():
            locator = SelectorManager.to_by_locator(strategy, value)
            target_desc = f"[{strategy}: {value.strip()}]"
        else:
            locator = (By.TAG_NAME, "body")
            target_desc = "page body"

        try:
            matched = WebDriverWait(driver, bounded, poll_frequency=_POLL_FREQUENCY).until(
                EC.text_to_be_present_in_element(locator, cleaned_text)
            )
            return bool(matched)
        except TimeoutException as exc:
            raise TimeoutException(
                f"Timed out after {bounded:.1f}s waiting for text {cleaned_text!r} in {target_desc}."
            ) from exc

    @staticmethod
    def wait_for_url_contains(
        driver: WebDriver,
        url_fragment: str,
        timeout: float | None = None,
    ) -> bool:
        """Wait until the active browser URL contains `url_fragment`."""
        cleaned = (url_fragment or "").strip()
        if not cleaned:
            raise ValueError("Wait condition 'url_contains' requires a non-empty URL substring.")

        bounded = clamp_timeout(timeout)
        try:
            matched = WebDriverWait(driver, bounded, poll_frequency=_POLL_FREQUENCY).until(
                EC.url_contains(cleaned)
            )
            return bool(matched)
        except TimeoutException as exc:
            current_url = ""
            try:
                current_url = driver.current_url
            except WebDriverException:
                pass
            raise TimeoutException(
                f"Timed out after {bounded:.1f}s waiting for URL to contain {cleaned!r} "
                f"(current URL: {current_url!r})."
            ) from exc

    @staticmethod
    def wait_for_page_ready(
        driver: WebDriver,
        timeout: float | None = None,
    ) -> bool:
        """Wait until `document.readyState` reports `'complete'`."""
        bounded = clamp_timeout(timeout)
        try:
            ready = WebDriverWait(driver, bounded, poll_frequency=_POLL_FREQUENCY).until(
                lambda drv: drv.execute_script("return document.readyState") == "complete"
            )
            return bool(ready)
        except TimeoutException as exc:
            raise TimeoutException(
                f"Timed out after {bounded:.1f}s waiting for page navigation to complete."
            ) from exc

    @classmethod
    def wait_for_condition(
        cls,
        driver: WebDriver,
        condition: str,
        strategy: str = "css",
        selector_value: str = "",
        target_value: str = "",
        timeout: float | None = None,
    ) -> Any:
        """Dispatch a condition-based wait by condition name."""
        mode = (condition or config.DEFAULT_WAIT_CONDITION).strip().lower()

        if mode == "present":
            return cls.wait_for_present(driver, strategy, selector_value, timeout=timeout)
        if mode == "visible":
            return cls.wait_for_visible(driver, strategy, selector_value, timeout=timeout)
        if mode == "clickable":
            return cls.wait_for_clickable(driver, strategy, selector_value, timeout=timeout)
        if mode == "invisible":
            return cls.wait_for_invisible(driver, strategy, selector_value, timeout=timeout)
        if mode == "text_present":
            return cls.wait_for_text_present(
                driver,
                expected_text=target_value,
                strategy=strategy if selector_value.strip() else None,
                value=selector_value if selector_value.strip() else None,
                timeout=timeout,
            )
        if mode == "url_contains":
            return cls.wait_for_url_contains(driver, url_fragment=target_value, timeout=timeout)
        if mode == "page_ready":
            return cls.wait_for_page_ready(driver, timeout=timeout)

        supported = ", ".join((*config.WAIT_CONDITIONS, "page_ready"))
        raise ValueError(f"Unsupported wait condition '{condition}'. Choose from: {supported}.")

    @classmethod
    def wait_for_step(
        cls,
        driver: WebDriver,
        step: WorkflowStep,
        resolved_selector: str | None = None,
        resolved_input: str | None = None,
    ) -> str:
        """Execute a `wait` WorkflowStep and return a human-readable confirmation message."""
        condition = str(step.options.get("wait_condition", config.DEFAULT_WAIT_CONDITION))
        selector = resolved_selector if resolved_selector is not None else step.selector_value
        target_val = resolved_input if resolved_input is not None else step.input_value
        bounded = clamp_timeout(step.timeout)

        cls.wait_for_condition(
            driver=driver,
            condition=condition,
            strategy=step.selector_strategy,
            selector_value=selector,
            target_value=target_val,
            timeout=bounded,
        )

        if condition in ("text_present", "url_contains"):
            return f"Wait condition '{condition}' satisfied for {target_val.strip()!r}."
        if condition == "page_ready":
            return "Page navigation completed (document.readyState == 'complete')."
        return (
            f"Wait condition '{condition}' satisfied for "
            f"[{step.selector_strategy}: {selector.strip()}]."
        )