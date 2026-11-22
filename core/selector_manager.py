"""Multi-strategy element selector resolution, static syntax checks, and live DOM validation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from selenium.common.exceptions import (
    InvalidSelectorException,
    NoSuchElementException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

import config

if TYPE_CHECKING:
    from models.workflow import Workflow

_STRATEGY_TO_BY: dict[str, str] = {
    "id": By.ID,
    "name": By.NAME,
    "css": By.CSS_SELECTOR,
    "xpath": By.XPATH,
}

_XPATH_VALID_STARTS: tuple[str, ...] = (
    "/",
    "./",
    "(",
    "*",
    "@",
    "id(",
    "ancestor",
    "child",
    "descendant",
    "following",
    "parent",
    "preceding",
    "self",
)


def _has_balanced_delimiters(text: str) -> tuple[bool, str]:
    """Verify balanced parentheses, square brackets, and quotes in a selector string."""
    in_single = False
    in_double = False
    paren_depth = 0
    bracket_depth = 0

    for idx, ch in enumerate(text):
        prev_ch = text[idx - 1] if idx > 0 else ""
        if ch == "'" and not in_double and prev_ch != "\\":
            in_single = not in_single
        elif ch == '"' and not in_single and prev_ch != "\\":
            in_double = not in_double
        elif not in_single and not in_double:
            if ch == "(":
                paren_depth += 1
            elif ch == ")":
                paren_depth -= 1
                if paren_depth < 0:
                    return False, "Unmatched closing parenthesis ')' in selector."
            elif ch == "[":
                bracket_depth += 1
            elif ch == "]":
                bracket_depth -= 1
                if bracket_depth < 0:
                    return False, "Unmatched closing bracket ']' in selector."

    if in_single or in_double:
        return False, "Unclosed quotation mark in selector."
    if paren_depth != 0:
        return False, "Unbalanced parentheses '()' in selector."
    if bracket_depth != 0:
        return False, "Unbalanced square brackets '[]' in selector."
    return True, ""


class SelectorManager:
    """Resolves `id`, `name`, `css`, and `xpath` selectors and validates element matches."""

    @staticmethod
    def normalize_strategy(strategy: str) -> str:
        """Return a normalized lowercase selector strategy or raise ValueError."""
        cleaned = (strategy or "").strip().lower()
        if cleaned not in _STRATEGY_TO_BY:
            supported = ", ".join(config.SELECTOR_STRATEGIES)
            raise ValueError(
                f"Unsupported selector strategy '{strategy}'. Choose from: {supported}."
            )
        return cleaned

    @classmethod
    def to_by_locator(cls, strategy: str, value: str) -> tuple[str, str]:
        """Convert `(strategy, value)` into a Selenium `(By.<TYPE>, selector)` tuple."""
        normalized = cls.normalize_strategy(strategy)
        cleaned_value = (value or "").strip()
        if not cleaned_value:
            raise ValueError(f"Selector value for strategy '{normalized}' cannot be empty.")
        return _STRATEGY_TO_BY[normalized], cleaned_value

    @classmethod
    def validate_selector_syntax(cls, strategy: str, value: str) -> tuple[bool, str]:
        """Validate selector syntax statically before launching a browser session."""
        try:
            normalized = cls.normalize_strategy(strategy)
        except ValueError as exc:
            return False, str(exc)

        cleaned = (value or "").strip()
        if not cleaned:
            return False, f"Selector value for '{normalized}' cannot be empty."

        # Skip deep syntax checks when value contains unresolved CSV template placeholders
        if "{{" in cleaned and "}}" in cleaned:
            return True, "Template placeholder selector syntax accepted."

        if normalized == "id":
            if cleaned.startswith("#"):
                return (
                    False,
                    f"Element ID '{cleaned}' should not start with '#'. Remove '#' or switch strategy to 'css'.",
                )
            if any(ch.isspace() for ch in cleaned):
                return False, f"Element ID '{cleaned}' cannot contain whitespace."
            return True, "Valid element ID."

        if normalized == "name":
            if any(ch in cleaned for ch in ("\n", "\r")):
                return False, "Element name selector cannot contain newline characters."
            return True, "Valid element name."

        balanced, balance_msg = _has_balanced_delimiters(cleaned)
        if not balanced:
            return False, balance_msg

        if normalized == "css":
            if cleaned.startswith(("/", "./", "../")):
                return (
                    False,
                    f"Selector '{cleaned}' looks like an XPath expression. Switch strategy to 'xpath'.",
                )
            if cleaned[-1] in (">", "+", "~", ","):
                return False, f"CSS selector '{cleaned}' cannot end with a trailing combinator."
            return True, "Valid CSS selector syntax."

        if normalized == "xpath":
            lowered = cleaned.lower()
            if not lowered.startswith(_XPATH_VALID_STARTS):
                return (
                    False,
                    f"XPath '{cleaned}' should start with '/', '//', './', or '('.",
                )
            return True, "Valid XPath syntax."

        return True, "Valid selector."

    @classmethod
    def validate_live_selector(
        cls,
        driver: WebDriver,
        strategy: str,
        value: str,
        allow_multiple: bool = False,
    ) -> dict[str, Any]:
        """Inspect a selector against the active DOM and report zero or multiple matches."""
        is_valid, syntax_msg = cls.validate_selector_syntax(strategy, value)
        if not is_valid:
            return {
                "valid_syntax": False,
                "match_count": 0,
                "status": "invalid_selector",
                "warning": syntax_msg,
            }

        locator = cls.to_by_locator(strategy, value)
        try:
            matches = driver.find_elements(*locator)
        except InvalidSelectorException as exc:
            return {
                "valid_syntax": False,
                "match_count": 0,
                "status": "invalid_selector",
                "warning": f"Browser rejected selector [{strategy}: {value}]: {exc.msg}",
            }
        except WebDriverException as exc:
            return {
                "valid_syntax": True,
                "match_count": 0,
                "status": "error",
                "warning": f"DOM query failed for [{strategy}: {value}]: {exc.msg}",
            }

        count = len(matches)
        if count == 0:
            return {
                "valid_syntax": True,
                "match_count": 0,
                "status": "zero_matches",
                "warning": f"Selector [{strategy}: {value}] matched 0 elements on the current page.",
            }
        if count > 1 and not allow_multiple:
            return {
                "valid_syntax": True,
                "match_count": count,
                "status": "multiple_matches",
                "warning": (
                    f"Selector [{strategy}: {value}] unexpectedly matched {count} elements "
                    "(expected a single unique target)."
                ),
            }

        return {
            "valid_syntax": True,
            "match_count": count,
            "status": "ok",
            "warning": "",
        }

    @classmethod
    def find_elements(
        cls,
        driver: WebDriver,
        strategy: str,
        value: str,
    ) -> list[WebElement]:
        """Return all WebElements matching `(strategy, value)` on the current page."""
        locator = cls.to_by_locator(strategy, value)
        return driver.find_elements(*locator)

    @classmethod
    def find_element(
        cls,
        driver: WebDriver,
        strategy: str,
        value: str,
    ) -> tuple[WebElement, str]:
        """Return `(first_matching_element, warning_message)` or raise NoSuchElementException."""
        matches = cls.find_elements(driver, strategy, value)
        if not matches:
            raise NoSuchElementException(
                f"Element not found using [{strategy}: {value}]."
            )

        warning = ""
        if len(matches) > 1:
            warning = (
                f"Selector [{strategy}: {value}] matched {len(matches)} elements; "
                "interacting with the first match."
            )
        return matches[0], warning

    @classmethod
    def element_exists(
        cls,
        driver: WebDriver,
        strategy: str,
        value: str,
    ) -> bool:
        """Return True if at least one element matches `(strategy, value)` right now."""
        try:
            return len(cls.find_elements(driver, strategy, value)) > 0
        except (ValueError, WebDriverException):
            return False

    @classmethod
    def validate_workflow_selectors(cls, workflow: Workflow) -> list[dict[str, Any]]:
        """Run static selector syntax checks across every step in a Workflow."""
        issues: list[dict[str, Any]] = []
        for idx, step in enumerate(workflow.steps, start=1):
            selector_val = step.selector_value.strip()
            if selector_val:
                ok, msg = cls.validate_selector_syntax(step.selector_strategy, selector_val)
                if not ok:
                    issues.append(
                        {
                            "step_index": idx,
                            "step_name": step.display_name,
                            "strategy": step.selector_strategy,
                            "selector": selector_val,
                            "message": msg,
                        }
                    )

            cond_target = step.condition_target.strip()
            if cond_target and step.condition in (
                config.CONDITION_IF_ELEMENT_EXISTS,
                config.CONDITION_SKIP_IF_MISSING,
                config.CONDITION_STOP_IF_MISSING,
            ):
                ok, msg = cls.validate_selector_syntax(step.selector_strategy, cond_target)
                if not ok:
                    issues.append(
                        {
                            "step_index": idx,
                            "step_name": step.display_name,
                            "strategy": step.selector_strategy,
                            "selector": cond_target,
                            "message": f"Condition target error: {msg}",
                        }
                    )

        return issues